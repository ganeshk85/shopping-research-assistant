"""Price monitor service: the UI-facing entry point for Graph 2 (US-10, US-13 to US-17).

`PriceMonitor.run_once()` checks every active tracked item once and returns a
`MonitorSummary`. The scheduler (Sprint 5) will call the same method.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from . import database as db
from .alerts import format_price
from .config import Settings
from .graphs.monitor_graph import MonitorDeps, Scraper, build_monitor_graph
from .models import FailedCheck, PriceCheck
from .tools.notifier import Notifier, build_notifier

log = logging.getLogger(__name__)

_DEFAULT = object()


def build_alert_llm(settings: Settings) -> Any:
    """Cheap model config for wording alerts; None (template only) if no API key is set."""
    if not settings.anthropic_api_key:
        return None
    from langchain_anthropic import ChatAnthropic

    from .research import FALLBACK_BETA

    return ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        max_tokens=2000,
        max_retries=2,
        output_config={"effort": "low"},
        betas=[FALLBACK_BETA],
        model_kwargs={"fallbacks": "default"},
    )


def default_scraper(settings: Settings) -> Scraper:
    from .tools.scraper import scrape_prices

    async def scrape(urls: list[str]):
        # 2 at a time (NFR-6): background checks can afford to be slow and polite.
        return await scrape_prices(urls, concurrency=2, default_currency=settings.default_currency)

    return scrape


@dataclass
class MonitorSummary:
    active_items: int = 0
    checks: list[PriceCheck] = field(default_factory=list)
    failures: list[FailedCheck] = field(default_factory=list)
    alerts_sent: list[PriceCheck] = field(default_factory=list)
    alerts_failed: list[PriceCheck] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return len(self.checks)

    def render(self) -> str:
        if self.active_items == 0:
            return "No active items on your watchlist. Track a product from the research chat first."
        lines = [
            f"Checked {self.checked} of {self.active_items} active item(s): "
            f"{len(self.alerts_sent)} alert(s) sent, {len(self.failures)} check(s) failed."
        ]
        for c in self.checks:
            cur = c.item.currency
            stock = "" if c.in_stock else " (out of stock)"
            flag = "  <- alert sent" if any(a.item.id == c.item.id for a in self.alerts_sent) else ""
            lines.append(
                f"- #{c.item.id} {c.item.product_name} at {c.item.retailer}: "
                f"{format_price(c.price, cur)}{stock}, target {format_price(c.item.target_price, cur)}{flag}"
            )
        for f in self.failures:
            lines.append(f"- #{f.item_id} {f.product_name} at {f.retailer}: check failed ({f.error})")
        for a in self.alerts_failed:
            lines.append(f"- #{a.item.id}: alert could not be delivered; it will be retried next check")
        return "\n".join(lines)


class PriceMonitor:
    def __init__(
        self,
        settings: Settings,
        *,
        scrape: Optional[Scraper] = None,
        notifier: Optional[Notifier] = None,
        alert_llm: Any = _DEFAULT,
    ) -> None:
        self.settings = settings
        self.db_path = db.init_db(settings.watchlist_db_path)
        self.notifier = notifier or build_notifier(settings)  # ConfigError if misconfigured (US-22)
        deps = MonitorDeps(
            db_path=self.db_path,
            scrape=scrape or default_scraper(settings),
            notifier=self.notifier,
            alert_llm=build_alert_llm(settings) if alert_llm is _DEFAULT else alert_llm,
        )
        self.graph = build_monitor_graph(deps)

    async def run_once(self) -> MonitorSummary:
        state = await self.graph.ainvoke({})
        items = state.get("items", [])
        alerts = {a.item.id: a for a in state.get("alerts", [])}
        return MonitorSummary(
            active_items=len(items),
            checks=state.get("checks", []),
            failures=state.get("failures", []),
            alerts_sent=[alerts[i] for i in state.get("sent_alert_ids", [])],
            alerts_failed=[alerts[i] for i in state.get("failed_alert_ids", [])],
        )

    def run_once_sync(self) -> MonitorSummary:
        return asyncio.run(self.run_once())
