"""Pydantic schemas and LangGraph state definitions."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Research (Graph 1)
# ---------------------------------------------------------------------------


class ProductCandidate(BaseModel):
    name: str
    brand: str
    estimated_price: float
    currency: str = "CAD"
    rating_summary: str
    key_specs: list[str] = Field(default_factory=list)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    best_for: str


class ResearchComparison(BaseModel):
    candidates: list[ProductCandidate]
    recommendation_summary: str
    clarifying_question: Optional[str] = None
    sources: list[str] = Field(
        default_factory=list, description="URLs of the search results the comparison is based on."
    )


class RetailListing(BaseModel):
    product_name: str
    retailer: str
    url: str
    current_price: float
    currency: str = "CAD"
    in_stock: bool = True
    price_verified: bool = False  # True = price/stock read from the product page by the scraper
    note: Optional[str] = None  # e.g. why verification failed


class TrackingDecision(BaseModel):
    """User's answer at the confirmation step (resume value for the interrupt, FR-4)."""

    action: Literal["track", "cancel"]
    selected: list[int] = Field(default_factory=list)  # 1-based listing numbers
    target_price: Optional[float] = None  # None = use the suggested default


# ---------------------------------------------------------------------------
# Monitoring (Graph 2)
# ---------------------------------------------------------------------------

ExtractionMethod = Literal["json-ld", "css-fallback", "failed"]


class ScrapedPriceResult(BaseModel):
    url: str
    current_price: Optional[float] = None
    currency: str = "CAD"
    in_stock: bool = False
    extraction_method: ExtractionMethod
    error: Optional[str] = None
    page_title: Optional[str] = None  # product name from the page, to confirm it's the right item


ItemStatus = Literal["active", "paused"]


class TrackedItem(BaseModel):
    id: int
    product_name: str
    retailer: str
    url: str
    currency: str = "CAD"
    initial_price: float
    target_price: float
    lowest_price_seen: float
    last_notified_price: Optional[float] = None
    status: ItemStatus = "active"
    created_at: datetime
    # Monitor health (Sprint 5): last attempt and failure streak.
    last_check_at: Optional[datetime] = None
    last_check_error: Optional[str] = None
    consecutive_failures: int = 0


class PriceHistoryEntry(BaseModel):
    id: int
    item_id: int
    price: float
    in_stock: bool
    checked_at: datetime


# ---------------------------------------------------------------------------
# LangGraph states
# ---------------------------------------------------------------------------

Intent = Literal[
    "explore_or_refine", "ask_followup", "finalize_product", "confirm_choice", "purchase_request"
]


class FollowUpAnswer(BaseModel):
    """Answer to a question about options already shown (numbering stays unchanged)."""

    answer: str = Field(description="Direct, grounded answer in 2-6 sentences, referring to options by number and name.")
    sources: list[str] = Field(default_factory=list, description="URLs of the search results used.")


class IntentDecision(BaseModel):
    """LLM routing decision for the latest user message (FRD FR-1)."""

    intent: Intent = Field(
        description=(
            "explore_or_refine: the user is starting a search or adding/changing criteria. "
            "ask_followup: a question about options already shown that does not change the criteria. "
            "finalize_product: the user explicitly picks ONE product to track. "
            "confirm_choice: the user seems to be choosing but it is ambiguous which product. "
            "purchase_request: the user asks the assistant to buy, order, check out, add to cart, "
            "or pay for something."
        )
    )
    candidate_number: Optional[int] = Field(
        default=None,
        description="1-based option number from the most recent comparison, if the user chose by number or position.",
    )
    product_name: Optional[str] = Field(
        default=None, description="Exact product name the user chose, if they named it."
    )
    search_query: str = Field(
        description=(
            "For explore_or_refine: a standalone product-search query combining ALL of the user's "
            "criteria so far (product type, budget in CAD, key needs, use case). For ask_followup: a "
            "focused query naming the products and the aspect asked about (e.g. 'Sony WH-1000XM6 vs "
            "Bose QuietComfort Ultra comfort')."
        )
    )
    clarification: Optional[str] = Field(
        default=None, description="Short question to ask when intent is confirm_choice."
    )


class ResearchState(TypedDict, total=False):
    """Graph 1 state. Comparisons/products are stored as plain dicts (checkpoint-safe)."""

    messages: Annotated[list[AnyMessage], add_messages]
    intent: Intent
    # What this turn did (set by the last node that ran).
    last_action: Literal[
        "researched", "answered", "finalized", "asked", "error", "declined",
        "no_listings", "tracking_saved", "tracking_cancelled",
    ]
    search_query: str
    candidate_number: Optional[int]
    product_name: Optional[str]
    clarification: Optional[str]
    last_comparison: Optional[dict]  # ResearchComparison.model_dump()
    finalized_product: Optional[dict]  # ProductCandidate.model_dump() or {"name": ...}
    listings: list[dict]  # RetailListing.model_dump() for the finalized product
    tracking_request: Optional[dict]  # {"listings": [...], "target_price": float} awaiting save
    saved_item_ids: list[int]


AlertReason = Literal["target_reached", "new_low"]


class PriceCheck(BaseModel):
    """One successful price check of a tracked item (Graph 2)."""

    item: TrackedItem
    price: float
    in_stock: bool
    previous_price: Optional[float]  # last recorded price before this check
    previous_lowest: float  # lowest_price_seen BEFORE this check (FR-6.6)
    reason: Optional[AlertReason] = None  # set when this check should alert


class FailedCheck(BaseModel):
    item_id: int
    product_name: str
    retailer: str
    error: str


class MonitorState(TypedDict, total=False):
    """Graph 2 state (in-memory; the monitor graph has no checkpointer)."""

    items: list[TrackedItem]
    checks: list[PriceCheck]
    failures: list[FailedCheck]
    alerts: list[PriceCheck]
    sent_alert_ids: list[int]
    failed_alert_ids: list[int]
