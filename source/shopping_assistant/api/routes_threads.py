"""Research conversations over HTTP (US-29, US-30).

Sending a message streams Server-Sent Events, because a turn can take 20-60 seconds:
`progress` events as each step starts, then one `result` (or `error`). The research
session is synchronous, so the turn runs in a worker thread and pushes events onto an
asyncio queue that the response drains.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..database import UserStore
from ..models import TrackingDecision
from ..research import ResearchSession, ResearchTurn, ThreadSnapshot
from ..tracking import validate_decision
from .deps import Services, current_store, get_services, research_session
from .errors import ApiError, error_for, not_found
from .schemas import (
    ChatMessage,
    ConfirmTracking,
    ErrorBody,
    FinalizedProduct,
    PendingConfirmation,
    ProgressEvent,
    SendMessage,
    ThreadCreated,
    ThreadDetail,
    ThreadSummary,
    TurnResult,
)

router = APIRouter(prefix="/threads", tags=["research"])

# Shown while each graph step runs (keyed by the step that is starting).
STEP_MESSAGES = {
    "understand_intent": "Reading your message",
    "research_and_compare": "Searching independent reviews and comparing products",
    "answer_followup": "Looking up the answer",
    "finalize_product": "Locking in your choice",
    "ask_to_confirm": "Checking which product you meant",
    "decline_purchase": "Replying",
    "locate_retail_listings": "Finding Canadian retailer listings and checking each price (this can take a minute)",
    "confirm_tracking_terms": "Preparing your tracking options",
    "save_to_watchlist": "Saving to your watchlist",
}


# --- conversions ----------------------------------------------------------------------


def _pending(payload: Optional[dict]) -> Optional[PendingConfirmation]:
    return PendingConfirmation.model_validate(payload) if payload else None


def _product(payload: Optional[dict]) -> Optional[FinalizedProduct]:
    return FinalizedProduct.model_validate(payload) if payload else None


def turn_result(turn: ResearchTurn) -> TurnResult:
    return TurnResult(
        thread_id=turn.thread_id,
        reply=turn.reply,
        last_action=turn.last_action,
        comparison=turn.comparison,
        finalized_product=_product(turn.finalized_product),
        pending_confirmation=_pending(turn.pending_confirmation),
        saved_item_ids=turn.saved_item_ids,
    )


def _summary(row: dict) -> ThreadSummary:
    return ThreadSummary.model_validate(row)


def _require_thread(store: UserStore, thread_id: str) -> dict:
    row = store.get_research_thread(thread_id)
    if row is None:  # unused, or another user's: both are "not found"
        raise not_found("Conversation")
    return row


def _sse(event: str, data: Any) -> bytes:
    payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


# --- endpoints ----------------------------------------------------------------------------


@router.post("", status_code=201, response_model=ThreadCreated, summary="Start a new conversation")
def create_thread() -> ThreadCreated:
    """Returns a fresh thread ID. Nothing is stored until the first message is sent."""
    return ThreadCreated(thread_id=ResearchSession.new_thread_id())


@router.get("", response_model=list[ThreadSummary], summary="List my conversations")
def list_threads(
    limit: int = Query(20, ge=1, le=100), store: UserStore = Depends(current_store)
) -> list[ThreadSummary]:
    """Most recently updated first."""
    return [_summary(r) for r in store.list_research_threads(limit)]


@router.get("/{thread_id}", response_model=ThreadDetail, summary="Get a conversation")
def get_thread(
    thread_id: str,
    store: UserStore = Depends(current_store),
    session: ResearchSession = Depends(research_session),
) -> ThreadDetail:
    """Messages, the latest comparison, the chosen product and any pending confirmation."""
    row = _require_thread(store, thread_id)
    snap: ThreadSnapshot = session.snapshot(thread_id)
    return ThreadDetail(
        thread=_summary(row),
        messages=[ChatMessage.model_validate(m) for m in snap.messages],
        comparison=snap.comparison,
        finalized_product=_product(snap.finalized_product),
        pending_confirmation=_pending(snap.pending_confirmation),
    )


@router.post(
    "/{thread_id}/messages",
    summary="Send a message (streams progress)",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Server-Sent Events. Each message is `event: progress|result|error` plus `data: <JSON>`; "
                "see the `StreamEvent` schema. Any number of `progress` events, then one `result` or `error`."
            ),
            "content": {"text/event-stream": {"schema": {"$ref": "#/components/schemas/StreamEvent"}}},
        },
        404: {"model": ErrorBody, "description": "The conversation belongs to someone else."},
        409: {"model": ErrorBody, "description": "A turn is already running in this conversation."},
    },
)
async def send_message(
    thread_id: str,
    body: SendMessage,
    store: UserStore = Depends(current_store),
    session: ResearchSession = Depends(research_session),
    services: Services = Depends(get_services),
) -> StreamingResponse:
    """A new or existing thread ID. A pending confirmation is cancelled first (FR-4.4)."""
    await asyncio.to_thread(store.check_thread_access, thread_id)
    services.claim_thread(thread_id)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

    def emit(event: str, data: Any) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, _sse(event, data))

    def on_step(node: str) -> None:
        message = STEP_MESSAGES.get(node)
        if message:
            emit("progress", ProgressEvent(step=node, message=message))

    def work() -> None:
        try:
            turn = session.send(thread_id, body.text, on_step=on_step)
            emit("result", turn_result(turn))
        except Exception as exc:  # reported in the stream; the conversation is unchanged
            emit("error", error_for(exc)[1])
        finally:
            services.release_thread(thread_id)
            loop.call_soon_threadsafe(queue.put_nowait, None)

    # Start now (not when the client starts reading), so the thread is always released.
    loop.run_in_executor(None, work)

    async def events() -> AsyncIterator[bytes]:
        while (chunk := await queue.get()) is not None:
            yield chunk

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/{thread_id}/confirmation",
    response_model=PendingConfirmation,
    summary="Get the pending tracking confirmation",
    responses={404: {"model": ErrorBody, "description": "No such conversation, or nothing pending."}},
)
def get_confirmation(
    thread_id: str,
    store: UserStore = Depends(current_store),
    session: ResearchSession = Depends(research_session),
) -> PendingConfirmation:
    _require_thread(store, thread_id)
    pending = _pending(session.pending_confirmation(thread_id))
    if pending is None:
        raise ApiError(404, "no_pending_confirmation", "Nothing is waiting for confirmation in this conversation.")
    return pending


@router.post(
    "/{thread_id}/confirmation",
    response_model=TurnResult,
    summary="Confirm or cancel tracking",
    responses={
        404: {"model": ErrorBody},
        409: {"model": ErrorBody, "description": "Nothing pending, or a turn is already running."},
        422: {"model": ErrorBody, "description": "Invalid choice; the confirmation stays pending."},
    },
)
def confirm_tracking(
    thread_id: str,
    body: ConfirmTracking,
    store: UserStore = Depends(current_store),
    session: ResearchSession = Depends(research_session),
    services: Services = Depends(get_services),
) -> TurnResult:
    """`track` saves one watchlist item per selected listing; `cancel` saves nothing."""
    _require_thread(store, thread_id)
    services.claim_thread(thread_id)
    try:
        pending = session.pending_confirmation(thread_id)
        if pending is None:
            raise ApiError(409, "no_pending_confirmation", "Nothing is waiting for confirmation in this conversation.")
        decision = TrackingDecision(action=body.action, selected=body.selected, target_price=body.target_price)
        # Validate here: the graph would treat a bad answer as a cancel (US-30 keeps it pending).
        problem = validate_decision(decision, pending.get("listings") or [])
        if body.action == "track" and len(set(body.selected)) != len(body.selected):
            problem = problem or "Each listing can only be selected once."
        if problem:
            raise ApiError(422, "invalid_decision", problem, {"listing_count": len(pending.get("listings") or [])})
        return turn_result(session.confirm(thread_id, decision))
    finally:
        services.release_thread(thread_id)
