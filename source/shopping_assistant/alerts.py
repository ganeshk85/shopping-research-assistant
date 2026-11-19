"""Price-drop decision and alert text (FRD FR-7, FR-8). Pure functions, no I/O.

The alert rule lives in one place (`alert_reason`) so it can be tested exhaustively:

    in_stock
    AND (price <= target OR price < previous_lowest)
    AND price < COALESCE(last_notified, +inf)
"""

from __future__ import annotations

import math
from typing import Optional

from .models import AlertReason, PriceCheck


def alert_reason(
    price: float,
    in_stock: bool,
    target: float,
    previous_lowest: float,
    last_notified: Optional[float],
) -> Optional[AlertReason]:
    """Why this check should alert, or None if it shouldn't."""
    if not in_stock:
        return None
    if price >= (last_notified if last_notified is not None else math.inf):
        return None  # US-15: never re-alert at the same or a higher price
    if price <= target:
        return "target_reached"
    if price < previous_lowest:
        return "new_low"
    return None


def should_alert(
    price: float,
    in_stock: bool,
    target: float,
    previous_lowest: float,
    last_notified: Optional[float],
) -> bool:
    return alert_reason(price, in_stock, target, previous_lowest, last_notified) is not None


def format_price(value: float, currency: str = "CAD") -> str:
    prefix = "CA$" if currency.upper() == "CAD" else f"{currency.upper()} "
    return f"{prefix}{value:,.2f}"


_price = format_price


def percent_below(initial: float, price: float) -> float:
    """How far `price` is below the price when tracking started, in percent (negative = above)."""
    if initial <= 0:
        return 0.0
    return round((initial - price) / initial * 100, 1)


def alert_facts(check: PriceCheck) -> dict:
    """Every number an alert may mention, precomputed so the LLM never does arithmetic."""
    item = check.item
    cur = item.currency
    return {
        "product": item.product_name,
        "retailer": item.retailer,
        "url": item.url,
        "reason": check.reason,
        "new_price": _price(check.price, cur),
        "previous_price": _price(check.previous_price, cur) if check.previous_price is not None else None,
        "price_when_tracking_started": _price(item.initial_price, cur),
        "percent_below_start": percent_below(item.initial_price, check.price),
        "target_price": _price(item.target_price, cur),
        "lowest_before_this_check": _price(check.previous_lowest, cur),
        "is_new_all_time_low": check.price < check.previous_lowest,
    }


def alert_subject(check: PriceCheck) -> str:
    item = check.item
    label = "Target price reached" if check.reason == "target_reached" else "New low price"
    return f"{label}: {item.product_name} now {_price(check.price, item.currency)} at {item.retailer}"


def template_alert(check: PriceCheck) -> str:
    """Deterministic alert body (FR-8.2): used when LLM text generation fails."""
    f = alert_facts(check)
    lines = [f"{f['product']} is now {f['new_price']} at {f['retailer']}."]
    if f["previous_price"] and f["previous_price"] != f["new_price"]:
        lines.append(f"Previous check: {f['previous_price']}.")
    pct = f["percent_below_start"]
    if pct > 0:
        lines.append(f"That's {pct:g}% below {f['price_when_tracking_started']}, the price when you started tracking.")
    if f["reason"] == "target_reached":
        lines.append(f"It's at or below your target of {f['target_price']}.")
    if f["is_new_all_time_low"]:
        lines.append(f"It's the lowest price seen so far (previous low {f['lowest_before_this_check']}).")
    lines.append(f"Link: {f['url']}")
    return "\n".join(lines)
