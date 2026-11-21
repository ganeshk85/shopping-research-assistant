"""API contract (US-33): request and response models.

These are the shapes the web app (and later the mobile app) see. The TypeScript client
in `source/packages/api-client` is generated from the OpenAPI spec built from them, so change
them deliberately and regenerate (`shopping-assistant api openapi`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints, model_validator

from ..models import CheckRun, ItemStatus, LastAction, NotifierChannel, ResearchComparison, RetailListing


class ErrorBody(BaseModel):
    """Every error response (and the SSE `error` event) has this shape."""

    code: str = Field(description="Stable machine-readable code, e.g. 'not_found', 'validation_error'.")
    message: str = Field(description="Plain-language explanation that can be shown to the user.")
    details: Optional[Any] = Field(default=None, description="Extra data, e.g. the invalid fields.")


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok", "unavailable"]


# --- research threads ------------------------------------------------------------


class ThreadCreated(BaseModel):
    thread_id: str = Field(description="Use this ID to send the first message; the thread is listed after that.")


class ThreadSummary(BaseModel):
    thread_id: str
    title: str
    finalized_product: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(description="Plain text (what the CLI shows).")
    comparison: Optional[ResearchComparison] = Field(
        default=None, description="Set on a message that presented a comparison; show it as cards instead of `text`."
    )
    listings: Optional[list[RetailListing]] = Field(
        default=None, description="Set on a message that presented retailer listings."
    )


class FinalizedProduct(BaseModel):
    """The product the user chose. Only `name` is guaranteed."""

    model_config = ConfigDict(extra="ignore")

    name: str
    brand: Optional[str] = None
    estimated_price: Optional[float] = None
    currency: str = "CAD"


class PendingConfirmation(BaseModel):
    """Listings waiting for the user to choose what to track (FR-4)."""

    model_config = ConfigDict(extra="ignore")

    product_name: str
    listings: list[RetailListing] = Field(description="Numbered from 1 in this order when confirming.")
    suggested_target: float = Field(description="Default target: the discount below the cheapest listing.")
    discount: float = Field(description="The fraction used for the suggested target, e.g. 0.1.")


class TurnResult(BaseModel):
    """What one message (or confirmation) produced."""

    thread_id: str
    reply: str = Field(description="All assistant text produced this turn.")
    last_action: Optional[LastAction] = None
    comparison: Optional[ResearchComparison] = Field(
        default=None, description="The latest comparison; option numbers refer to its candidates."
    )
    finalized_product: Optional[FinalizedProduct] = Field(
        default=None, description="Set when a product was chosen in this turn."
    )
    pending_confirmation: Optional[PendingConfirmation] = None
    saved_item_ids: list[int] = Field(default_factory=list, description="Watchlist items created this turn.")


class ThreadDetail(BaseModel):
    thread: ThreadSummary
    messages: list[ChatMessage]
    comparison: Optional[ResearchComparison] = None
    finalized_product: Optional[FinalizedProduct] = None
    pending_confirmation: Optional[PendingConfirmation] = None


class SendMessage(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ConfirmTracking(BaseModel):
    """Answer to a pending confirmation. Listing numbers are 1-based."""

    action: Literal["track", "cancel"]
    selected: list[int] = Field(default_factory=list)
    target_price: Optional[float] = Field(default=None, gt=0, description="Omit to use the suggested target.")


# --- streamed turn events (Server-Sent Events) -------------------------------------


class ProgressEvent(BaseModel):
    step: str = Field(description="Graph step name, e.g. 'research_and_compare'.")
    message: str = Field(description="What the assistant is doing now, for display.")


class StreamProgress(BaseModel):
    event: Literal["progress"]
    data: ProgressEvent


class StreamResult(BaseModel):
    event: Literal["result"]
    data: TurnResult


class StreamError(BaseModel):
    event: Literal["error"]
    data: ErrorBody


class StreamEvent(RootModel[Annotated[Union[StreamProgress, StreamResult, StreamError], Field(discriminator="event")]]):
    """One SSE message: `event: <event>` then `data: <JSON of data>`. A stream sends any number of
    `progress` events, then exactly one `result` or `error`, then closes."""


# --- watchlist ----------------------------------------------------------------------


class WatchlistItem(BaseModel):
    id: int
    product_name: str
    retailer: str
    url: str
    currency: str
    status: ItemStatus
    initial_price: float
    target_price: float
    lowest_price_seen: float = Field(description="Lowest in-stock price seen.")
    latest_price: Optional[float] = Field(default=None, description="Price at the most recent check.")
    latest_in_stock: Optional[bool] = None
    last_checked_at: Optional[datetime] = Field(default=None, description="None = not yet checked.")
    last_check_error: Optional[str] = None
    consecutive_failures: int
    needs_attention: bool = Field(description="True after repeated failed checks.")
    created_at: datetime


class UpdateWatchlistItem(BaseModel):
    status: Optional[ItemStatus] = Field(default=None, description="'paused' stops checks; 'active' resumes.")
    target_price: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _something_to_change(self) -> "UpdateWatchlistItem":
        if self.status is None and self.target_price is None:
            raise ValueError("Give a status or a target_price to change.")
        return self


class PriceHistoryEntryOut(BaseModel):
    id: int
    price: float
    in_stock: bool
    checked_at: datetime
    is_lowest: bool = Field(description="The first check at the lowest in-stock price.")


class PriceHistory(BaseModel):
    item_id: int
    currency: str
    target_price: float
    entries: list[PriceHistoryEntryOut] = Field(description="Oldest first.")


# --- price checks (US-32) -------------------------------------------------------------


class ScheduleStatus(BaseModel):
    """The background worker (`shopping-assistant worker`), as last reported."""

    worker_running: bool = Field(description="False if the worker is stopped or hasn't reported for 3 minutes.")
    interval_hours: Optional[int] = None
    next_run_at: Optional[datetime] = Field(default=None, description="When the next scheduled check is due.")
    last_heartbeat_at: Optional[datetime] = None


class CheckStatus(BaseModel):
    running: Optional[CheckRun] = Field(default=None, description="The check in progress, if any.")
    last_finished: Optional[CheckRun] = Field(default=None, description="The most recent check that ended.")
    schedule: ScheduleStatus


# --- notification settings (US-35) ------------------------------------------------------


EmailAddress = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
]
WebhookUrl = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000, pattern=r"^https?://\S+$")]


class NotificationSettingsOut(BaseModel):
    """The alert channel in use. Secrets are never returned: the webhook URL is masked."""

    channel: NotifierChannel
    source: Literal["saved", "env"] = Field(description="'env' = nothing saved yet; the .env values are in use.")
    webhook_url_hint: Optional[str] = Field(
        default=None, description="Masked webhook URL, e.g. 'https://discord.com/…f3a9'. None if none is set."
    )
    alert_email: Optional[str] = None
    email_available: bool = Field(description="Whether the server can send email (sender and Resend/SMTP in .env).")
    updated_at: Optional[datetime] = None


class UpdateNotificationSettings(BaseModel):
    """Omit `webhook_url` or `alert_email` to keep the saved value; send null to clear it."""

    channel: NotifierChannel
    webhook_url: Optional[WebhookUrl] = None
    alert_email: Optional[EmailAddress] = None


class TestAlertResult(BaseModel):
    channel: NotifierChannel
    message: str
