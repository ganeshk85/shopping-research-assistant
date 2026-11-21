"""Watchlist over HTTP (US-31): list, view, pause/resume, retarget, delete, price history.

Another user's item is indistinguishable from a missing one: both are 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..database import UserStore
from ..watchlist import WatchlistRow, last_checked_at, load_row, load_watchlist, lowest_in_stock_entry, needs_attention
from .deps import current_store
from .errors import not_found
from .schemas import ErrorBody, PriceHistory, PriceHistoryEntryOut, UpdateWatchlistItem, WatchlistItem

router = APIRouter(prefix="/watchlist", tags=["watchlist"], responses={404: {"model": ErrorBody}})


def _item(row: WatchlistRow) -> WatchlistItem:
    i = row.item
    return WatchlistItem(
        id=i.id,
        product_name=i.product_name,
        retailer=i.retailer,
        url=i.url,
        currency=i.currency,
        status=i.status,
        initial_price=i.initial_price,
        target_price=i.target_price,
        lowest_price_seen=i.lowest_price_seen,
        latest_price=row.last_price,
        latest_in_stock=row.last_in_stock,
        last_checked_at=last_checked_at(row),
        last_check_error=i.last_check_error,
        consecutive_failures=i.consecutive_failures,
        needs_attention=needs_attention(i),
        created_at=i.created_at,
    )


def _require(store: UserStore, item_id: int) -> WatchlistRow:
    row = load_row(store, item_id)
    if row is None:
        raise not_found("Watchlist item")
    return row


@router.get("", response_model=list[WatchlistItem], summary="List my watchlist")
def list_items(store: UserStore = Depends(current_store)) -> list[WatchlistItem]:
    return [_item(r) for r in load_watchlist(store)]


@router.get("/{item_id}", response_model=WatchlistItem, summary="Get one item")
def get_item(item_id: int, store: UserStore = Depends(current_store)) -> WatchlistItem:
    return _item(_require(store, item_id))


@router.patch(
    "/{item_id}",
    response_model=WatchlistItem,
    summary="Pause, resume or change the target",
    responses={422: {"model": ErrorBody}},
)
def update_item(item_id: int, body: UpdateWatchlistItem, store: UserStore = Depends(current_store)) -> WatchlistItem:
    _require(store, item_id)
    if body.status is not None:
        store.update_status(item_id, body.status)
    if body.target_price is not None:
        store.update_target_price(item_id, round(body.target_price, 2))
    return _item(_require(store, item_id))


@router.delete("/{item_id}", status_code=204, summary="Delete an item and its price history")
def delete_item(item_id: int, store: UserStore = Depends(current_store)) -> Response:
    """Irreversible: the web app asks the user to confirm first."""
    if not store.delete_tracked_item(item_id):
        raise not_found("Watchlist item")
    return Response(status_code=204)


@router.get("/{item_id}/history", response_model=PriceHistory, summary="Price history, oldest first")
def get_history(item_id: int, store: UserStore = Depends(current_store)) -> PriceHistory:
    item = _require(store, item_id).item
    history = store.get_price_history(item_id)
    lowest_id = lowest_in_stock_entry(history)
    return PriceHistory(
        item_id=item.id,
        currency=item.currency,
        target_price=item.target_price,
        entries=[
            PriceHistoryEntryOut(id=h.id, price=h.price, in_stock=h.in_stock, checked_at=h.checked_at,
                                 is_lowest=h.id == lowest_id)
            for h in history
        ],
    )
