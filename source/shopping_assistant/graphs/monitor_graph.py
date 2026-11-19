"""Graph 2: price monitor (FRD FR-6 to FR-8). Async, no checkpointer; all state is in SQLite.

    fetch_active_trackers ─▶ scrape_current_prices ─▶ evaluate_drops ─┬─▶ END (no alerts: no LLM call)
                                                                      └─▶ generate_and_send_alert ─▶ END

Only `generate_and_send_alert` may call an LLM (NFR-2), and only to word the alert;
every number comes from `alerts.alert_facts`. If the LLM fails, refuses, or drops the
new price from its text, the deterministic template is sent instead (FR-8.2).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from .. import database as db
from ..alerts import alert_facts, alert_reason, alert_subject, template_alert
from ..models import FailedCheck, MonitorState, PriceCheck, ScrapedPriceResult, TrackedItem
from ..tools.notifier import NotificationError, Notifier
from ..tools.search import matches_model

log = logging.getLogger(__name__)

Scraper = Callable[[list[str]], Awaitable[Sequence[ScrapedPriceResult]]]

ALERT_SYSTEM = """You write short price-drop alerts for a shopper in Canada.
Using ONLY the JSON facts provided, write 2-4 plain-text sentences (no markdown):
what dropped, where, the new price versus the previous price or the starting price,
and why it matters (target reached and/or lowest price seen). Copy prices and
percentages exactly as written in the facts; never calculate or invent numbers.
Keep a neutral, factual tone with no hype or pressure to buy. You never purchase
anything or handle payments. End with the link on its own line."""


@dataclass
class MonitorDeps:
    db_path: Path
    scrape: Scraper
    notifier: Notifier
    alert_llm: Any = None  # chat model with .ainvoke(); None = always use the template


def failure_reason(item: TrackedItem, result: ScrapedPriceResult) -> Optional[str]:
    """Why a scrape can't be used for this item, or None if it's usable."""
    if result.extraction_method == "failed" or result.current_price is None:
        return result.error or "no price found on page"
    if result.page_title and not matches_model(item.product_name, result.page_title, item.url):
        # The retailer may have reused the URL for another product: never alert on it.
        return f"page now shows a different product ({result.page_title[:60]})"
    if result.currency.upper() != item.currency.upper():
        return f"price is in {result.currency}, expected {item.currency}"
    return None


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


async def write_alert(check: PriceCheck, llm: Any) -> tuple[str, bool]:
    """Alert body and whether the LLM wrote it (False = template)."""
    if llm is None:
        return template_alert(check), False
    facts = alert_facts(check)
    try:
        reply = await llm.ainvoke([SystemMessage(ALERT_SYSTEM), HumanMessage(json.dumps(facts, indent=2))])
    except Exception as exc:
        log.warning("Alert text generation failed, using template: %s", exc)
        return template_alert(check), False
    if getattr(reply, "response_metadata", {}).get("stop_reason") == "refusal":
        return template_alert(check), False
    text = _message_text(reply)
    if not text or facts["new_price"] not in text:
        # Guard against a garbled or invented price: the alert must state the real one.
        return template_alert(check), False
    if facts["url"] not in text:
        text = f"{text}\n{facts['url']}"
    return text, True


def build_monitor_graph(deps: MonitorDeps):
    async def fetch_active_trackers(state: MonitorState) -> dict:
        return {"items": db.list_tracked_items(deps.db_path, status="active")}

    def route_after_fetch(state: MonitorState) -> str:
        return "scrape_current_prices" if state.get("items") else END

    async def scrape_current_prices(state: MonitorState) -> dict:
        """FR-6: deterministic scraping, no LLM. Failures never change prices (FR-6.7)."""
        items = state["items"]
        try:
            results = list(await deps.scrape([i.url for i in items]))
        except Exception as exc:
            log.warning("Scraping run failed: %s", exc)
            results = [
                ScrapedPriceResult(url=i.url, extraction_method="failed", error=f"scraper error: {exc}")
                for i in items
            ]
        checks: list[PriceCheck] = []
        failures: list[FailedCheck] = []
        for item, result in zip(items, results):  # scrape_prices keeps input order
            error = failure_reason(item, result)
            if error:
                failures.append(FailedCheck(
                    item_id=item.id, product_name=item.product_name, retailer=item.retailer, error=error
                ))
                db.mark_check_failed(deps.db_path, item.id, error)
                continue
            previous_price = db.latest_price(deps.db_path, item.id)
            previous_lowest = db.record_price_check(
                deps.db_path, item.id, result.current_price, result.in_stock
            )
            db.mark_check_ok(deps.db_path, item.id)
            checks.append(PriceCheck(
                item=item, price=result.current_price, in_stock=result.in_stock,
                previous_price=previous_price, previous_lowest=previous_lowest,
            ))
        return {"checks": checks, "failures": failures}

    def evaluate_drops(state: MonitorState) -> dict:
        """FR-7: apply the alert rule to every successful check."""
        alerts = []
        for c in state.get("checks", []):
            reason = alert_reason(
                c.price, c.in_stock, c.item.target_price, c.previous_lowest, c.item.last_notified_price
            )
            if reason:
                alerts.append(c.model_copy(update={"reason": reason}))
        return {"alerts": alerts}

    def route_after_evaluate(state: MonitorState) -> str:
        return "generate_and_send_alert" if state.get("alerts") else END

    async def generate_and_send_alert(state: MonitorState) -> dict:
        """FR-8: word the alert, send it, then record last_notified_price on success only."""
        sent: list[int] = []
        failed: list[int] = []
        for check in state["alerts"]:
            body, _by_llm = await write_alert(check, deps.alert_llm)
            try:
                await asyncio.to_thread(deps.notifier.send, alert_subject(check), body)
            except NotificationError as exc:
                log.warning("Alert for item %s not delivered: %s", check.item.id, exc)
                failed.append(check.item.id)  # last_notified unchanged → retried next run
                continue
            db.update_last_notified(deps.db_path, check.item.id, check.price)
            sent.append(check.item.id)
        return {"sent_alert_ids": sent, "failed_alert_ids": failed}

    graph = StateGraph(MonitorState)
    graph.add_node("fetch_active_trackers", fetch_active_trackers)
    graph.add_node("scrape_current_prices", scrape_current_prices)
    graph.add_node("evaluate_drops", evaluate_drops)
    graph.add_node("generate_and_send_alert", generate_and_send_alert)
    graph.add_edge(START, "fetch_active_trackers")
    graph.add_conditional_edges("fetch_active_trackers", route_after_fetch, ["scrape_current_prices", END])
    graph.add_edge("scrape_current_prices", "evaluate_drops")
    graph.add_conditional_edges("evaluate_drops", route_after_evaluate, ["generate_and_send_alert", END])
    graph.add_edge("generate_and_send_alert", END)
    return graph.compile()
