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


class RetailListing(BaseModel):
    product_name: str
    retailer: str
    url: str
    current_price: float
    currency: str = "CAD"
    in_stock: bool = True
    price_verified: bool = False


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


class PriceHistoryEntry(BaseModel):
    id: int
    item_id: int
    price: float
    in_stock: bool
    checked_at: datetime


# ---------------------------------------------------------------------------
# LangGraph states
# ---------------------------------------------------------------------------

Intent = Literal["explore_or_refine", "finalize_product"]


class ResearchState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: Intent
    last_comparison: ResearchComparison
    finalized_product: str
    listings: list[RetailListing]
    saved_item_ids: list[int]


class PriceCheck(TypedDict):
    item: TrackedItem
    result: ScrapedPriceResult
    previous_lowest: float


class MonitorState(TypedDict, total=False):
    items: list[TrackedItem]
    checks: list[PriceCheck]
    alerts: list[PriceCheck]
    sent_alert_ids: list[int]
