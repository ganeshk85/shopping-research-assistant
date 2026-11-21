"""Research session service: the UI-facing entry point for Graph 1.

The CLI (and later a web API) calls this instead of touching LangGraph directly.
Conversation state is checkpointed in Postgres (PostgresSaver on the shared pool),
keyed by thread ID; the `research_threads` table lists each user's threads so they
can resume one (US-03, US-25). A session belongs to one user (its `UserStore`):
another user's thread ID raises `ThreadAccessError`.

Tracking setup pauses the graph with `interrupt()` (FR-4). A paused thread exposes
`pending_confirmation`; answer it with `confirm()`. Sending a normal message while
a confirmation is pending cancels it first (LangGraph would otherwise silently
drop it).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from .config import Settings
from .database import UserStore, open_store
from .graphs.research_graph import TrackingDeps, build_research_graph
from .models import ScrapedPriceResult, TrackingDecision

# Server-side refusal fallback (recommended default for current Claude models):
# if a safety check declines a request, the API retries it on a fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

ProgressCallback = Callable[[str], None]  # receives the name of each node as it finishes
StepCallback = Callable[[str], None]  # receives the name of each node as it STARTS (for live progress)


def build_llms(settings: Settings) -> tuple[Any, Any]:
    """Return (intent_llm, research_llm). Routing is cheap (low effort); research needs depth."""
    settings.require("anthropic_api_key")
    from langchain_anthropic import ChatAnthropic

    common = dict(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        max_retries=2,
        betas=[FALLBACK_BETA],
        model_kwargs={"fallbacks": "default"},
    )
    intent_llm = ChatAnthropic(max_tokens=4000, output_config={"effort": "low"}, **common)
    research_llm = ChatAnthropic(max_tokens=16000, output_config={"effort": "medium"}, **common)
    return intent_llm, research_llm


def default_price_verifier(settings: Settings) -> Callable[[list[str]], Sequence[ScrapedPriceResult]]:
    """Sync wrapper around the async Crawl4AI scraper (graph nodes run synchronously)."""
    from .tools.scraper import scrape_prices

    def verify(urls: list[str]) -> Sequence[ScrapedPriceResult]:
        return asyncio.run(
            # 3 at a time: the URLs are mostly on different retailers, so this stays polite (NFR-6).
            scrape_prices(urls, concurrency=3, default_currency=settings.default_currency)
        )

    return verify


@dataclass
class ResearchTurn:
    """What one user turn (or confirmation) produced, for display."""

    thread_id: str
    reply: str  # all assistant messages produced this turn, joined
    last_action: Optional[str] = None
    finalized_product: Optional[dict] = None
    comparison: Optional[dict] = None
    pending_confirmation: Optional[dict] = None  # interrupt payload: listings + suggested target
    saved_item_ids: list[int] = field(default_factory=list)


@dataclass
class ThreadSnapshot:
    """A thread's current state, for showing it again (e.g. when a web page reloads)."""

    thread_id: str
    # Oldest first: {"role", "text"} plus "comparison" / "listings" when the message showed one.
    messages: list[dict]
    comparison: Optional[dict] = None  # the latest comparison (numbered options)
    finalized_product: Optional[dict] = None
    pending_confirmation: Optional[dict] = None


class ResearchSession:
    def __init__(
        self,
        settings: Settings,
        *,
        store: Optional[UserStore] = None,
        intent_llm: Any = None,
        research_llm: Any = None,
        search: Any = None,
        checkpointer: Any = None,
        verify_prices: Optional[Callable[[list[str]], Sequence[ScrapedPriceResult]]] = None,
        enable_tracking: bool = True,
    ) -> None:
        self.settings = settings
        # Check the API keys before touching the database, so the clearest error comes first.
        if intent_llm is None or research_llm is None:
            intent_llm, research_llm = build_llms(settings)
        if search is None:
            from .tools.search import ProductSearch

            search = ProductSearch(settings)
        self.store = store or open_store(settings)
        if checkpointer is None:
            from langgraph.checkpoint.postgres import PostgresSaver

            checkpointer = PostgresSaver(self.store.database.pool)
        tracking = None
        if enable_tracking:
            tracking = TrackingDeps(
                store=self.store,
                verify_prices=verify_prices or default_price_verifier(settings),
                default_discount=settings.default_target_discount,
                default_currency=settings.default_currency,
            )
        self.graph = build_research_graph(intent_llm, research_llm, search, checkpointer, tracking)

    # -- threads -------------------------------------------------------------

    @staticmethod
    def new_thread_id() -> str:
        return uuid.uuid4().hex[:12]

    def list_threads(self, limit: int = 20) -> list[dict]:
        return self.store.list_research_threads(limit)

    def history(self, thread_id: str) -> list[tuple[str, str]]:
        """(role, text) pairs for a thread, oldest first."""
        self.store.check_thread_access(thread_id)
        return self._messages(self.graph.get_state(self._config(thread_id)))

    def pending_confirmation(self, thread_id: str) -> Optional[dict]:
        """The confirmation payload if this thread is paused waiting for one."""
        self.store.check_thread_access(thread_id)
        return self._pending(self.graph.get_state(self._config(thread_id)))

    def snapshot(self, thread_id: str) -> ThreadSnapshot:
        """Messages, latest comparison, chosen product and any pending confirmation, in one read."""
        self.store.check_thread_access(thread_id)
        state = self.graph.get_state(self._config(thread_id))
        values = state.values or {}
        return ThreadSnapshot(
            thread_id=thread_id,
            messages=self._chat_entries(state),
            comparison=values.get("last_comparison"),
            finalized_product=values.get("finalized_product"),
            pending_confirmation=self._pending(state),
        )

    @staticmethod
    def _messages(state: Any) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for m in (state.values or {}).get("messages", []):
            if isinstance(m, HumanMessage):
                out.append(("user", str(m.content)))
            elif isinstance(m, AIMessage):
                out.append(("assistant", str(m.content)))
        return out

    @staticmethod
    def _chat_entries(state: Any) -> list[dict]:
        out: list[dict] = []
        for m in (state.values or {}).get("messages", []):
            if isinstance(m, HumanMessage):
                out.append({"role": "user", "text": str(m.content)})
            elif isinstance(m, AIMessage):
                extra = m.additional_kwargs or {}
                out.append({
                    "role": "assistant",
                    "text": str(m.content),
                    "comparison": extra.get("comparison"),
                    "listings": extra.get("listings"),
                })
        return out

    @staticmethod
    def _pending(state: Any) -> Optional[dict]:
        for intr in getattr(state, "interrupts", ()) or ():
            value = getattr(intr, "value", None)
            if isinstance(value, dict) and value.get("type") == "confirm_tracking":
                return value
        return None

    # -- turns ---------------------------------------------------------------

    def send(
        self,
        thread_id: str,
        text: str,
        on_progress: Optional[ProgressCallback] = None,
        on_step: Optional[StepCallback] = None,
    ) -> ResearchTurn:
        text = text.strip()
        if not text:
            raise ValueError("Message is empty.")
        if self.pending_confirmation(thread_id):
            # Explicitly cancel so the conversation records it (see module docstring).
            self.confirm(thread_id, TrackingDecision(action="cancel"))
        self.store.upsert_research_thread(thread_id, title=text)
        return self._run(thread_id, {"messages": [HumanMessage(text)]}, on_progress, on_step)

    def confirm(
        self,
        thread_id: str,
        decision: TrackingDecision,
        on_progress: Optional[ProgressCallback] = None,
        on_step: Optional[StepCallback] = None,
    ) -> ResearchTurn:
        """Answer a pending tracking confirmation (FR-4)."""
        if not self.pending_confirmation(thread_id):
            raise RuntimeError("There is no tracking confirmation waiting in this conversation.")
        return self._run(thread_id, Command(resume=decision.model_dump()), on_progress, on_step)

    def _run(
        self,
        thread_id: str,
        graph_input: Any,
        on_progress: Optional[ProgressCallback],
        on_step: Optional[StepCallback] = None,
    ) -> ResearchTurn:
        config = self._config(thread_id)
        before = len(self.graph.get_state(config).values.get("messages", []))
        # "tasks" events mark when each node starts (they carry "input"); "updates" when it finishes.
        for mode, chunk in self.graph.stream(graph_input, config, stream_mode=["updates", "tasks"]):
            if mode == "tasks":
                if on_step and "input" in chunk:
                    on_step(chunk["name"])
            elif on_progress:
                for node in chunk:
                    if not node.startswith("__"):
                        on_progress(node)

        state = self.graph.get_state(config).values
        new_messages = state.get("messages", [])[before:]
        reply = "\n\n".join(str(m.content) for m in new_messages if isinstance(m, AIMessage))
        last_action = state.get("last_action")
        pending = self.pending_confirmation(thread_id)
        # A product counts as chosen this turn if finalization ran (with or without tracking).
        chose_product = pending is not None or last_action in ("finalized", "no_listings", "tracking_saved")
        finalized = state.get("finalized_product") if chose_product else None
        if finalized:
            self.store.upsert_research_thread(thread_id, title="", finalized_product=finalized["name"])
        return ResearchTurn(
            thread_id=thread_id,
            reply=reply,
            last_action=last_action,
            finalized_product=finalized,
            comparison=state.get("last_comparison"),
            pending_confirmation=pending,
            saved_item_ids=list(state.get("saved_item_ids") or []) if last_action == "tracking_saved" else [],
        )

    def close(self) -> None:
        """Nothing to release: the connection pool is shared for the whole process."""

    def __enter__(self) -> "ResearchSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}
