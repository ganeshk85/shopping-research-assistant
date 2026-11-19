"""Tracking-setup helpers (FRD FR-3, FR-4): pure functions shared by the graph and any UI.

- build_listings: merge Tavily listing results with scraper verification
- default_target_price: suggested alert price (BRL-3: 10% below current)
- parse_selection / parse_target: turn user text into a TrackingDecision
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional, Sequence

from .models import RetailListing, ScrapedPriceResult, TrackingDecision
from .tools.search import RetailSearchResult, is_blocked_url, matches_model

MAX_LISTINGS = 8
MAX_PER_RETAILER = 3


MIN_PRICE_RATIO = 0.4  # below 40% of the research estimate: almost always an accessory / wrong item
MAX_PRICE_RATIO = 2.5  # above 250%: a bundle, a different model, or a bad parse


def price_is_plausible(price: float, expected: Optional[float]) -> bool:
    if not expected or expected <= 0:
        return True
    return MIN_PRICE_RATIO * expected <= price <= MAX_PRICE_RATIO * expected


def build_listings(
    product_name: str,
    results: Sequence[RetailSearchResult],
    scraped: Sequence[ScrapedPriceResult],
    *,
    default_currency: str = "CAD",
    expected_price: Optional[float] = None,
) -> tuple[list[RetailListing], int]:
    """Combine search results with scraped prices.

    Scraped price/stock wins; otherwise the search snippet's price hint is used and the
    listing is marked unverified. Dropped (counted in the second return value):
    - cart/checkout URLs (never offered, BRL-1)
    - pages whose own product title shows a different product
    - prices implausibly far from the research estimate (`expected_price`)
    - listings with no price at all (a baseline price is required to track)
    Order: verified & in-stock first, then by price.
    """
    by_url = {s.url: s for s in scraped}
    listings: list[RetailListing] = []
    dropped = 0
    for r in results:
        if is_blocked_url(r.url):  # defence in depth: never offer cart/checkout pages (BRL-1)
            dropped += 1
            continue
        if not matches_model(product_name, r.title, r.url):
            dropped += 1  # search result is for a different product
            continue
        s = by_url.get(r.url)
        scraped_ok = s is not None and s.current_price is not None and s.extraction_method != "failed"
        if scraped_ok and s.page_title and not matches_model(product_name, s.page_title, r.url):
            dropped += 1  # the page itself is for a different product
            continue
        price = s.current_price if scraped_ok else r.price_hint
        if price is None or not price_is_plausible(price, expected_price):
            dropped += 1
            continue
        if scraped_ok:
            listings.append(RetailListing(
                product_name=product_name, retailer=r.retailer, url=r.url,
                current_price=s.current_price, currency=s.currency, in_stock=s.in_stock,
                price_verified=True,
            ))
        else:
            listings.append(RetailListing(
                product_name=product_name, retailer=r.retailer, url=r.url,
                current_price=price, currency=default_currency, in_stock=True,
                price_verified=False,
                note=(s.error if s is not None and s.error else "price from search results, not verified"),
            ))
    listings.sort(key=lambda l: (not l.price_verified, not l.in_stock, l.current_price))
    return listings, dropped


def select_for_verification(
    results: Sequence[RetailSearchResult],
    max_total: int = MAX_LISTINGS,
    max_per_retailer: int = MAX_PER_RETAILER,
) -> list[RetailSearchResult]:
    """Keep a manageable, retailer-diverse subset to scrape (each scrape takes seconds)."""
    counts: Counter[str] = Counter()
    picked: list[RetailSearchResult] = []
    # First pass: one per retailer so every store is represented.
    for r in results:
        if counts[r.retailer] == 0:
            picked.append(r)
            counts[r.retailer] += 1
    for r in results:
        if len(picked) >= max_total:
            break
        if r not in picked and counts[r.retailer] < max_per_retailer:
            picked.append(r)
            counts[r.retailer] += 1
    return picked[:max_total]


def default_target_price(prices: Sequence[float], discount: float = 0.10) -> float:
    """BRL-3: suggest `discount` below the lowest selected current price, rounded to cents."""
    if not prices:
        raise ValueError("No prices to base a target on.")
    return round(min(prices) * (1 - discount), 2)


_CANCEL_WORDS = {"c", "cancel", "n", "no", "none", "q", "quit", "exit"}


def parse_selection(text: str, count: int) -> TrackingDecision | str:
    """'1,3' / '1 3' / '2-4' / 'all' → TrackingDecision; 'c' → cancel; else an error message."""
    t = text.strip().lower()
    if t in _CANCEL_WORDS:
        return TrackingDecision(action="cancel")
    if t in ("all", "a", "*"):
        return TrackingDecision(action="track", selected=list(range(1, count + 1)))
    selected: list[int] = []
    for part in re.split(r"[,\s]+", t):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            return f"'{part}' isn't a listing number."
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        if lo > hi:
            lo, hi = hi, lo
        for n in range(lo, hi + 1):
            if not 1 <= n <= count:
                return f"{n} isn't between 1 and {count}."
            if n not in selected:
                selected.append(n)
    if not selected:
        return "Please choose at least one listing number, 'all', or 'c' to cancel."
    return TrackingDecision(action="track", selected=selected)


def parse_target(text: str) -> Optional[float] | str:
    """'' → None (use default); '$399.99' → 399.99; invalid → error message."""
    t = text.strip().lower().replace(",", "")
    for prefix in ("ca$", "c$", "$"):
        t = t.removeprefix(prefix)
    t = t.removesuffix("$").removesuffix("cad").strip()
    if not t:
        return None
    try:
        value = float(t)
    except ValueError:
        return f"'{text.strip()}' isn't a price."
    if value <= 0:
        return "The target price must be above zero."
    return round(value, 2)


def validate_decision(decision: TrackingDecision, listings: Sequence[dict]) -> Optional[str]:
    """Return an error message if the decision can't be applied, else None."""
    if decision.action == "cancel":
        return None
    if not decision.selected:
        return "No listings were selected."
    bad = [n for n in decision.selected if not 1 <= n <= len(listings)]
    if bad:
        return f"Listing number(s) {bad} don't exist."
    if decision.target_price is not None and decision.target_price <= 0:
        return "The target price must be above zero."
    return None


def brand_store_domains(brand: Optional[str]) -> list[str]:
    """Best-guess Canadian brand-store domain, e.g. 'Sony' → ['sony.ca']."""
    if not brand:
        return []
    slug = re.sub(r"[^a-z0-9]", "", brand.lower())
    return [f"{slug}.ca"] if len(slug) >= 2 else []
