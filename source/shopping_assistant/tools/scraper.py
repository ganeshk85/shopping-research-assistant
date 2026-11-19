"""Deterministic price/stock scraper (Graph 2). No LLM calls in this module.

Extraction order (FRD FR-6.3):
  1. schema.org Product/Offer data in <script type="application/ld+json">
  2. Fallback: price meta tags / itemprop microdata / known retailer CSS selectors
The HTML parsing functions are pure, so they can be unit-tested with saved fixtures;
`scrape_price` / `scrape_prices` wrap Crawl4AI's headless browser for live pages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Optional, Protocol, Sequence

from bs4 import BeautifulSoup

from ..models import ScrapedPriceResult

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Price text parsing
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\d[\d\s.,  ]*")


def parse_price_text(value: Any) -> Optional[float]:
    """Parse '$1,299.99', '1 299,99 $', 449.99, '449' → float. Returns None if no price."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    match = _NUMBER_RE.search(str(value))
    if not match:
        return None
    num = re.sub(r"[\s  ]", "", match.group()).rstrip(".,")
    if "," in num and "." in num:
        # Whichever separator comes last is the decimal separator.
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        whole, _, frac = num.rpartition(",")
        num = f"{whole.replace(',', '')}.{frac}" if len(frac) in (1, 2) else num.replace(",", "")
    elif num.count(".") > 1:
        whole, _, frac = num.rpartition(".")
        num = f"{whole.replace('.', '')}.{frac}"
    try:
        price = float(num)
    except ValueError:
        return None
    return price if price > 0 else None


# ---------------------------------------------------------------------------
# JSON-LD extraction
# ---------------------------------------------------------------------------

_OUT_OF_STOCK = ("outofstock", "soldout", "discontinued", "preorder_unavailable")
_IN_STOCK = ("instock", "limitedavailability", "onlineonly", "instoreonly", "preorder", "backorder")


@dataclass(frozen=True)
class ParsedOffer:
    price: float
    currency: Optional[str]
    in_stock: bool


def _availability_in_stock(value: Any) -> Optional[bool]:
    if not value:
        return None
    token = str(value).rsplit("/", 1)[-1].replace(" ", "").lower()
    if any(t in token for t in _OUT_OF_STOCK):
        return False
    if any(t in token for t in _IN_STOCK):
        return True
    return None


def _types(node: dict) -> set[str]:
    t = node.get("@type", [])
    values = t if isinstance(t, list) else [t]
    return {str(v).rsplit("/", 1)[-1].lower() for v in values}


def _walk(node: Any) -> Iterator[dict]:
    """Yield every dict in a JSON-LD document (handles lists and @graph)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            if isinstance(v, (dict, list)):
                yield from _walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _load_json_ld_blocks(soup: BeautifulSoup) -> list[Any]:
    blocks: list[Any] = []
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            # Some sites emit trailing commas or control chars; try a light cleanup.
            cleaned = re.sub(r",\s*([}\]])", r"\1", raw.replace("\n", " ").replace("\t", " "))
            try:
                blocks.append(json.loads(cleaned))
            except json.JSONDecodeError:
                log.debug("Skipping unparseable JSON-LD block")
    return blocks


def _offer_from_node(offer: dict) -> Optional[ParsedOffer]:
    types = _types(offer)
    price = None
    if "aggregateoffer" in types:
        price = parse_price_text(offer.get("lowPrice")) or parse_price_text(offer.get("price"))
    else:
        price = parse_price_text(offer.get("price"))
    if price is None:
        spec = offer.get("priceSpecification")
        specs = spec if isinstance(spec, list) else [spec] if isinstance(spec, dict) else []
        for s in specs:
            price = parse_price_text(s.get("price"))
            if price is not None:
                offer = {**s, **offer}
                break
    if price is None:
        return None
    in_stock = _availability_in_stock(offer.get("availability"))
    return ParsedOffer(
        price=price,
        currency=(offer.get("priceCurrency") or None),
        in_stock=True if in_stock is None else in_stock,
    )


def _offers_of(product: dict) -> Iterable[dict]:
    offers = product.get("offers")
    if isinstance(offers, dict):
        # AggregateOffer may nest individual offers; prefer the aggregate itself first.
        yield offers
        nested = offers.get("offers")
        if isinstance(nested, list):
            yield from (o for o in nested if isinstance(o, dict))
    elif isinstance(offers, list):
        yield from (o for o in offers if isinstance(o, dict))


def parse_json_ld(html: str) -> Optional[ParsedOffer]:
    """Return the best offer from schema.org JSON-LD, or None if absent."""
    soup = BeautifulSoup(html, "lxml")
    blocks = _load_json_ld_blocks(soup)
    nodes = [n for block in blocks for n in _walk(block)]

    candidates: list[ParsedOffer] = []
    for node in nodes:
        if "product" in _types(node) or "productgroup" in _types(node):
            for offer in _offers_of(node):
                parsed = _offer_from_node(offer)
                if parsed:
                    candidates.append(parsed)
    if not candidates:
        # Some pages publish a bare Offer without a wrapping Product.
        for node in nodes:
            if _types(node) & {"offer", "aggregateoffer"}:
                parsed = _offer_from_node(node)
                if parsed:
                    candidates.append(parsed)
    if not candidates:
        return None
    # Prefer in-stock offers, then the lowest price.
    return min(candidates, key=lambda o: (not o.in_stock, o.price))


# ---------------------------------------------------------------------------
# Fallback extraction (meta / microdata / retailer CSS)
# ---------------------------------------------------------------------------

_META_PRICE_SELECTORS = [
    ('meta[property="product:price:amount"]', 'meta[property="product:price:currency"]'),
    ('meta[property="og:price:amount"]', 'meta[property="og:price:currency"]'),
    ('[itemprop="price"]', '[itemprop="priceCurrency"]'),
]

# Retailer-specific selectors; isolated here so layout changes are a one-line fix.
_RETAILER_CSS: dict[str, list[str]] = {
    "amazon.": [
        "#corePrice_feature_div .a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        "#apex_desktop .a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
    ],
    # Newegg has no Product JSON-LD. Main buy-box price; avoids marketplace seller rows.
    "newegg.": [
        ".product-buy-box .product-price--x ul.price",
        ".product-buy-box .product-pane ul.price",
    ],
}
_GENERIC_CSS = [".price", ".product-price", "[data-price]"]

_OUT_OF_STOCK_TEXT = re.compile(
    r"\b(out of stock|currently unavailable|sold out|no longer available|"
    r"temporarily out of stock|rupture de stock)\b",
    re.I,
)


def _attr_or_text(el: Any) -> Optional[str]:
    for attr in ("content", "data-price", "value"):
        if el.has_attr(attr) and str(el[attr]).strip():
            return str(el[attr])
    text = el.get_text(" ", strip=True)
    return text or None


def parse_fallback(html: str, url: str = "") -> Optional[ParsedOffer]:
    """Extract price from meta tags, microdata, or known retailer CSS selectors."""
    soup = BeautifulSoup(html, "lxml")
    price: Optional[float] = None
    currency: Optional[str] = None

    for price_sel, currency_sel in _META_PRICE_SELECTORS:
        el = soup.select_one(price_sel)
        if el is not None:
            price = parse_price_text(_attr_or_text(el))
            if price is not None:
                cur_el = soup.select_one(currency_sel)
                currency = _attr_or_text(cur_el) if cur_el is not None else None
                break

    if price is None:
        host = url.lower()
        selectors = [s for key, sels in _RETAILER_CSS.items() if key in host for s in sels]
        for sel in selectors + _GENERIC_CSS:
            el = soup.select_one(sel)
            if el is not None:
                price = parse_price_text(_attr_or_text(el))
                if price is not None:
                    break

    if price is None:
        return None
    body_text = soup.get_text(" ", strip=True)[:20000]
    in_stock = not _OUT_OF_STOCK_TEXT.search(body_text)
    return ParsedOffer(price=price, currency=currency, in_stock=in_stock)


# ---------------------------------------------------------------------------
# Public extraction API
# ---------------------------------------------------------------------------


def extract_page_title(html: str) -> Optional[str]:
    """Product name shown on the page: JSON-LD Product name, else og:title, else <title>."""
    soup = BeautifulSoup(html, "lxml")
    for node in (n for block in _load_json_ld_blocks(soup) for n in _walk(block)):
        if _types(node) & {"product", "productgroup"} and isinstance(node.get("name"), str):
            return node["name"].strip() or None
    og = soup.select_one('meta[property="og:title"]')
    if og is not None and og.get("content", "").strip():
        return og["content"].strip()
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return None


def extract_price(html: str, url: str, default_currency: str = "CAD") -> ScrapedPriceResult:
    """Run JSON-LD extraction, then the fallback. Never raises on bad HTML."""
    try:
        title = extract_page_title(html)
    except Exception:
        title = None
    result = _extract_price(html, url, default_currency)
    return result.model_copy(update={"page_title": title})


def _extract_price(html: str, url: str, default_currency: str) -> ScrapedPriceResult:
    try:
        offer = parse_json_ld(html)
        method = "json-ld"
        if offer is None:
            offer = parse_fallback(html, url)
            method = "css-fallback"
    except Exception as exc:  # defensive: malformed markup must not stop monitoring
        log.warning("Price extraction error for %s: %s", url, exc)
        return ScrapedPriceResult(url=url, extraction_method="failed", error=f"parse error: {exc}")

    if offer is None:
        # Some retailers (e.g. Newegg marketplace) hide the price entirely when out of stock.
        try:
            text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)[:20000]
        except Exception:
            text = ""
        reason = (
            "out of stock (no price shown)" if _OUT_OF_STOCK_TEXT.search(text) else "no price found on page"
        )
        return ScrapedPriceResult(url=url, extraction_method="failed", in_stock=False, error=reason)
    return ScrapedPriceResult(
        url=url,
        current_price=round(offer.price, 2),
        currency=(offer.currency or default_currency).upper(),
        in_stock=offer.in_stock,
        extraction_method=method,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Crawl4AI wrapper
# ---------------------------------------------------------------------------


class _Crawler(Protocol):
    async def arun(self, url: str, config: Any = None) -> Any: ...


def _run_config(page_timeout_ms: int) -> Any:
    from crawl4ai import CacheMode, CrawlerRunConfig

    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="domcontentloaded",
        page_timeout=page_timeout_ms,
        delay_before_return_html=2.0,
        magic=True,
        override_navigator=True,
        verbose=False,
    )


def browser_config(user_agent: str = DEFAULT_USER_AGENT) -> Any:
    from crawl4ai import BrowserConfig

    return BrowserConfig(
        headless=True,
        user_agent=user_agent,
        enable_stealth=True,
        verbose=False,
        headers={"Accept-Language": "en-CA,en;q=0.9"},
    )


async def scrape_price(
    url: str,
    crawler: _Crawler,
    *,
    default_currency: str = "CAD",
    page_timeout_ms: int = 45_000,
) -> ScrapedPriceResult:
    """Render one URL with an open Crawl4AI crawler and extract its price."""
    try:
        result = await crawler.arun(url=url, config=_run_config(page_timeout_ms))
    except Exception as exc:
        log.warning("Crawl failed for %s: %s", url, exc)
        return ScrapedPriceResult(url=url, extraction_method="failed", error=f"crawl error: {exc}")

    if not getattr(result, "success", False) or not getattr(result, "html", None):
        status = getattr(result, "status_code", None)
        msg = getattr(result, "error_message", None) or "empty page"
        return ScrapedPriceResult(
            url=url, extraction_method="failed", error=f"crawl failed (status {status}): {msg}"
        )
    status = getattr(result, "status_code", None)
    if isinstance(status, int) and status >= 400:
        return ScrapedPriceResult(url=url, extraction_method="failed", error=f"HTTP {status}")
    return extract_price(result.html, url, default_currency)


async def scrape_prices(
    urls: Sequence[str],
    *,
    concurrency: int = 2,
    default_currency: str = "CAD",
    crawler: Optional[_Crawler] = None,
) -> list[ScrapedPriceResult]:
    """Scrape several URLs with low concurrency (NFR-6). Results keep input order.

    One failing URL never affects the others (US-12).
    """
    if not urls:
        return []
    sem = asyncio.Semaphore(max(1, concurrency))

    async def run(c: _Crawler, u: str) -> ScrapedPriceResult:
        async with sem:
            return await scrape_price(u, c, default_currency=default_currency)

    if crawler is not None:
        return list(await asyncio.gather(*(run(crawler, u) for u in urls)))

    from crawl4ai import AsyncWebCrawler

    async with AsyncWebCrawler(config=browser_config()) as live:
        return list(await asyncio.gather(*(run(live, u) for u in urls)))
