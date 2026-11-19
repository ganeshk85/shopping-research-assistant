"""Watchlist view and management (US-18, US-19, US-20). UI-agnostic: returns text and results."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from . import database as db
from .alerts import format_price
from .models import PriceHistoryEntry, TrackedItem

FAILURE_WARNING_THRESHOLD = 2  # show a warning after this many failed checks in a row


@dataclass
class WatchlistRow:
    item: TrackedItem
    last_price: Optional[float]
    last_in_stock: Optional[bool]
    last_recorded_check: Optional[datetime] = None  # newest history row after the baseline


def load_watchlist(db_path: Path) -> list[WatchlistRow]:
    rows = []
    for item in db.list_tracked_items(db_path):
        history = db.get_price_history(db_path, item.id)
        last = history[-1] if history else None
        rows.append(WatchlistRow(
            item,
            last.price if last else None,
            last.in_stock if last else None,
            # history[0] is the baseline saved when tracking started, not a monitor check.
            last.checked_at if len(history) > 1 else None,
        ))
    return rows


def _last_check(row: WatchlistRow, now: Optional[datetime]) -> str:
    # Items checked before the health columns existed (pre-Sprint 5 DBs) fall back to history.
    when = row.item.last_check_at or row.last_recorded_check
    return "not yet checked" if when is None else relative_time(when, now)


def relative_time(when: Optional[datetime], now: Optional[datetime] = None) -> str:
    if when is None:
        return "never"
    now = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = max(0, int((now - when).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def render_watchlist(rows: list[WatchlistRow], now: Optional[datetime] = None) -> str:
    """US-18: product, retailer, status, latest/lowest/target price, last check, warnings."""
    if not rows:
        return "Your watchlist is empty. Pick a product in the research chat (option 1) to start tracking."
    header = f"{'#':>3}  {'Product':<26} {'Retailer':<17} {'Status':<7} {'Now':>12} {'Lowest':>12} {'Target':>12}  Last check"
    lines = [header, "-" * len(header)]
    for r in rows:
        i = r.item
        cur = i.currency
        now_price = "-" if r.last_price is None else format_price(r.last_price, cur)
        if r.last_in_stock is False:
            now_price += "*"
        checked = _last_check(r, now)
        lines.append(
            f"{i.id:>3}  {_cut(i.product_name, 26):<26} {_cut(i.retailer, 17):<17} {i.status:<7} "
            f"{now_price:>12} {format_price(i.lowest_price_seen, cur):>12} {format_price(i.target_price, cur):>12}  {checked}"
        )
        if cur.upper() != "CAD":
            lines.append(f"     note: prices for this item are in {cur.upper()}, not CAD")
        if i.consecutive_failures >= FAILURE_WARNING_THRESHOLD:
            lines.append(
                f"     warning: last {i.consecutive_failures} checks failed ({_cut(i.last_check_error or 'unknown error', 70)})"
            )
    if any(r.last_in_stock is False for r in rows):
        lines.append("  * out of stock at the last check")
    return "\n".join(lines)


def render_history(item: TrackedItem, history: list[PriceHistoryEntry]) -> str:
    """US-20: oldest to newest, with the lowest in-stock price highlighted."""
    lines = [f"Price history for #{item.id} {item.product_name} at {item.retailer}:", item.url, ""]
    if not history:
        return "\n".join(lines + ["No prices recorded yet."])
    in_stock_prices = [h.price for h in history if h.in_stock]
    lowest = min(in_stock_prices) if in_stock_prices else None
    marked = False
    for h in history:
        when = h.checked_at.astimezone().strftime("%Y-%m-%d %H:%M")
        stock = "in stock" if h.in_stock else "out of stock"
        is_lowest = not marked and lowest is not None and h.in_stock and h.price == lowest
        marked = marked or is_lowest  # mark only the first time the lowest price appeared
        mark = "  <- lowest" if is_lowest else ""
        lines.append(f"  {when}  {format_price(h.price, item.currency):>12}  {stock}{mark}")
    lines.append("")
    lines.append(f"Target: {format_price(item.target_price, item.currency)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands (US-19)
# ---------------------------------------------------------------------------

Action = Literal["pause", "resume", "delete", "target", "history", "back", "help", "refresh"]

WATCHLIST_HELP = """Commands:
  p <#>          pause an item          r <#>          resume an item
  t <#> <price>  change target price    h <#>          show price history
  d <#>          delete an item         l              list again
  b              back to the menu"""

_ALIASES = {
    "p": "pause", "pause": "pause", "r": "resume", "resume": "resume",
    "d": "delete", "delete": "delete", "del": "delete", "rm": "delete",
    "t": "target", "target": "target", "h": "history", "history": "history",
    "b": "back", "back": "back", "q": "back", "exit": "back", "": "back", "0": "back",
    "?": "help", "help": "help", "l": "refresh", "list": "refresh",
}


@dataclass
class WatchlistCommand:
    action: Action
    item_id: Optional[int] = None
    price: Optional[float] = None


def parse_watchlist_command(text: str) -> WatchlistCommand | str:
    """'p 3' / 't 3 399.99' / 'h 2' / 'b' → WatchlistCommand, or an error message."""
    parts = text.strip().split()
    verb = parts[0].lower() if parts else ""
    action = _ALIASES.get(verb)
    if action is None:
        return f"Unknown command '{verb}'. Type ? for help."
    if action in ("back", "help", "refresh"):
        return WatchlistCommand(action)  # type: ignore[arg-type]
    if len(parts) < 2 or not parts[1].lstrip("#").isdigit():
        return f"Which item? e.g. '{verb} 3'"
    item_id = int(parts[1].lstrip("#"))
    if action == "target":
        if len(parts) < 3:
            return "Give the new target price, e.g. 't 3 399.99'"
        raw = re.sub(r"(?i)^(ca)?\$", "", parts[2].replace(",", ""))
        try:
            price = float(raw)
        except ValueError:
            return f"'{parts[2]}' isn't a price."
        if price <= 0:
            return "The target price must be above zero."
        return WatchlistCommand("target", item_id, round(price, 2))
    return WatchlistCommand(action, item_id)  # type: ignore[arg-type]


def apply_command(db_path: Path, cmd: WatchlistCommand) -> str:
    """Run a command that needs an item. Delete is irreversible: callers confirm first."""
    item = db.get_tracked_item(db_path, cmd.item_id) if cmd.item_id is not None else None
    if item is None:
        return f"There's no item #{cmd.item_id} on your watchlist."
    label = f"#{item.id} {item.product_name} at {item.retailer}"
    if cmd.action == "pause":
        if item.status == "paused":
            return f"{label} is already paused."
        db.update_status(db_path, item.id, "paused")
        return f"Paused {label}. It won't be checked until you resume it."
    if cmd.action == "resume":
        if item.status == "active":
            return f"{label} is already active."
        db.update_status(db_path, item.id, "active")
        return f"Resumed {label}."
    if cmd.action == "target":
        db.update_target_price(db_path, item.id, cmd.price)
        return (
            f"Target for {label} changed from {format_price(item.target_price, item.currency)} "
            f"to {format_price(cmd.price, item.currency)}."
        )
    if cmd.action == "history":
        return render_history(item, db.get_price_history(db_path, item.id))
    if cmd.action == "delete":
        db.delete_tracked_item(db_path, item.id)
        return f"Deleted {label} and its price history."
    return "Nothing to do."
