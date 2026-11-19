"""Tavily search wrapper (Graph 1): product/review research and Canadian retail lookup."""

from __future__ import annotations

import re
from typing import Any, Optional, Protocol, Sequence
from urllib.parse import urlparse

from pydantic import BaseModel

from ..config import Settings

REVIEW_DOMAINS: tuple[str, ...] = (
    "nytimes.com",  # Wirecutter
    "rtings.com",
    "reddit.com",
    "techradar.com",
    "theverge.com",
    "tomsguide.com",
    "cnet.com",
    "pcmag.com",
    "consumerreports.org",
)

class Retailer(BaseModel):
    """A supported Canadian retailer: search domain, display name, product-page URL pattern."""

    domain: str
    name: str
    product_path: str  # regex matched against the URL path
    aliases: tuple[str, ...] = ()  # other hosts for the same store; not searched

    def matches(self, host: str) -> bool:
        return any(_matches_domain(host, d) for d in (self.domain, *self.aliases))

    def is_product_path(self, path: str) -> bool:
        return re.search(self.product_path, path, re.I) is not None


# Supported v1 retailers. Each was live-checked on 2026-11-16 (see MEMORY.md) and
# serves prices the scraper can read. URL patterns come from real Tavily results.
RETAILERS: tuple[Retailer, ...] = (
    Retailer(domain="amazon.ca", name="Amazon.ca", product_path=r"/(dp|gp/product)/[A-Z0-9]{10}"),
    Retailer(domain="walmart.ca", name="Walmart Canada", product_path=r"^/(en|fr)/ip/[^/]+/[A-Z0-9]+"),
    Retailer(domain="staples.ca", name="Staples Canada", product_path=r"^/products/\d+-"),
    Retailer(domain="costco.ca", name="Costco Canada", product_path=r"^/p/-/[^/]+/\d+|\.product\.\d+\.html$"),
    # dell.ca redirects to dell.com; only the Canadian store (en-ca / fr-ca) counts.
    Retailer(
        domain="dell.com",
        name="Dell Canada",
        product_path=r"^/(en|fr)-ca/shop/.*/(apd|spd|pd)/",
        aliases=("dell.ca",),
    ),
    Retailer(
        domain="newegg.ca",
        name="Newegg Canada",
        product_path=r"/p/(N82E\d+|[A-Z0-9]{2,4}-[A-Z0-9]{3,4}-[A-Z0-9]{4,6})",
    ),
    Retailer(
        domain="canadacomputers.com",
        name="Canada Computers",
        product_path=r"^/(en|qc)/[^/]+/\d+/[^/]+\.html$",
    ),
    Retailer(domain="canadiantire.ca", name="Canadian Tire", product_path=r"^/(en|fr)/pdp/[^/]+-\d+p\.html$"),
)

# Kept for backwards compatibility: domain → display name.
CANADIAN_RETAILERS: dict[str, str] = {r.domain: r.name for r in RETAILERS}

# Retailers excluded from v1 because they block the headless scraper. Never returned as listings.
#   Best Buy Canada: Akamai 403 (2026-11-15 spike).
#   RONA: DataDome captcha 403 (2026-11-16 spike).
EXCLUDED_RETAILERS: tuple[str, ...] = ("bestbuy.ca", "bestbuy.com", "rona.ca")

# URL fragments that are never product pages. Cart/checkout are blocked for safety (BRL-1).
_BLOCKED_PATH_PARTS = (
    "/cart", "/checkout", "/basket", "/signin", "/login", "/account", "/gp/buy",
    "/search", "/s?", "/s/", "/category", "/b?", "/b/", "/stores/",
    # Non-product pages seen on brand stores in the 2026-11-16 live check.
    "/c/", "/support", "/articles", "/specifications", "/manuals", "/faq", "/blog", "/news",
    # Retailer tracking/review pages seen in live results (Walmart).
    "/wapcrs/", "/reviews/",
)
_PRICE_HINT_RE = re.compile(r"(?:CA?\$|C\$|\$)\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)")


class SearchResult(BaseModel):
    title: str
    url: str
    content: str = ""
    score: float = 0.0
    raw_content: Optional[str] = None


class RetailSearchResult(SearchResult):
    retailer: str
    price_hint: Optional[float] = None


class _TavilyLike(Protocol):
    def search(self, query: str, **kwargs: Any) -> dict: ...


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def is_blocked_url(url: str) -> bool:
    """True for cart/checkout/login/search/category URLs, which are never valid listings."""
    lowered = url.lower()
    path_and_query = lowered.split(_domain(url), 1)[-1]
    return any(part in path_and_query for part in _BLOCKED_PATH_PARTS)


def looks_like_product_url(url: str) -> bool:
    """Heuristic: is this a direct product page (not search/category/cart)?"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or is_blocked_url(url):
        return False
    host = _domain(url)
    if any(_matches_domain(host, d) for d in EXCLUDED_RETAILERS):
        return False
    retailer = find_retailer(url)
    if retailer is not None:
        return retailer.is_product_path(parsed.path)
    # Brand stores: require a non-trivial path.
    return len(parsed.path.strip("/")) > 3


def find_retailer(url: str) -> Optional[Retailer]:
    host = _domain(url)
    return next((r for r in RETAILERS if r.matches(host)), None)


def retailer_name(url: str) -> str:
    retailer = find_retailer(url)
    return retailer.name if retailer else _domain(url)


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def model_tokens(product_name: str) -> list[str]:
    """Model-number tokens from a product name, e.g. 'Sony WH-1000XM5' → ['wh1000xm5'].

    Only words of 3+ characters that mix letters and digits count, so plain words,
    years, and short tokens like '16' or 'M3' don't make matching too strict.
    """
    tokens = []
    for word in product_name.split():
        norm = _normalize(word)
        if len(norm) >= 3 and any(c.isdigit() for c in norm) and any(c.isalpha() for c in norm):
            tokens.append(norm)
    return tokens


def matches_model(product_name: str, *texts: str) -> bool:
    """True if every model token appears in the URL/title (stops WF-1000XM5 matching WH-1000XM5)."""
    tokens = model_tokens(product_name)
    if not tokens:
        return True
    haystack = _normalize(" ".join(texts))
    return all(t in haystack for t in tokens)


def extract_price_hint(text: str) -> Optional[float]:
    """First dollar amount in a search snippet. Unverified; the scraper confirms it later."""
    m = _PRICE_HINT_RE.search(text or "")
    return float(m.group(1).replace(",", "")) if m else None


class ProductSearch:
    """Thin, testable wrapper around TavilyClient."""

    def __init__(self, settings: Settings, client: Optional[_TavilyLike] = None) -> None:
        if client is None:
            settings.require("tavily_api_key")
            from tavily import TavilyClient

            client = TavilyClient(api_key=settings.tavily_api_key)
        self._client = client

    def _search(self, query: str, **kwargs: Any) -> list[dict]:
        response = self._client.search(query, **kwargs)
        return list(response.get("results", []))

    def research_products(
        self, query: str, max_results: int = 8, min_trusted: int = 4
    ) -> list[SearchResult]:
        """Find reviews and roundups for a need.

        Searches trusted review sites first (restricted). Only if that returns fewer
        than `min_trusted` results does it top up with an open web search.
        """
        search_query = f"best {query} review comparison"
        results = self._search(
            search_query,
            search_depth="advanced",
            max_results=max_results,
            include_domains=list(REVIEW_DOMAINS),
        )
        if len([r for r in results if r.get("url")]) < min_trusted:
            seen = {r.get("url") for r in results}
            extra = self._search(search_query, search_depth="advanced", max_results=max_results)
            results += [r for r in extra if r.get("url") not in seen]

        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=float(r.get("score") or 0.0),
                raw_content=r.get("raw_content"),
            )
            for r in results
            if r.get("url")
        ][:max_results]

    def find_retail_listings(
        self,
        product_name: str,
        brand_domains: Sequence[str] = (),
        max_results: int = 20,
        fill_missing: bool = True,
        per_retailer_results: int = 5,
    ) -> list[RetailSearchResult]:
        """Find direct product pages for an exact model at Canadian retailers.

        One combined search across all retailers runs first. With `fill_missing`, each
        retailer that got no listing then gets a cheap targeted search ("basic" depth),
        because the combined top-N results tend to be dominated by a few sites.
        """
        domains = list(CANADIAN_RETAILERS) + [
            d.lower() for d in brand_domains
            if not any(_matches_domain(d.lower(), x) for x in EXCLUDED_RETAILERS)
        ]
        query = f'"{product_name}" price Canada'
        listings: list[RetailSearchResult] = []
        seen: set[str] = set()

        results = self._search(
            query,
            search_depth="advanced",
            max_results=max_results,
            include_domains=domains,
            exclude_domains=list(EXCLUDED_RETAILERS),
            country="canada",
        )
        self._collect(results, product_name, domains, listings, seen)

        if fill_missing:
            for domain in domains:
                if any(_matches_domain(_domain(l.url), domain) for l in listings):
                    continue
                extra = self._search(
                    query,
                    search_depth="basic",
                    max_results=per_retailer_results,
                    include_domains=[domain],
                    country="canada",
                )
                self._collect(extra, product_name, [domain], listings, seen)
        return listings

    @staticmethod
    def _collect(
        results: list[dict],
        product_name: str,
        domains: Sequence[str],
        listings: list[RetailSearchResult],
        seen: set[str],
    ) -> None:
        """Validate raw results and append new product listings in place."""
        for r in results:
            url = (r.get("url") or "").split("#", 1)[0]
            host = _domain(url)
            if not url or url in seen or not any(_matches_domain(host, d) for d in domains):
                continue
            if not looks_like_product_url(url):
                continue
            if not matches_model(product_name, url, r.get("title", "")):
                continue
            seen.add(url)
            listings.append(
                RetailSearchResult(
                    title=r.get("title", ""),
                    url=url,
                    content=r.get("content", ""),
                    score=float(r.get("score") or 0.0),
                    retailer=retailer_name(url),
                    price_hint=extract_price_hint(f"{r.get('title', '')} {r.get('content', '')}"),
                )
            )
