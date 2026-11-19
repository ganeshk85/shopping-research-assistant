import pytest

from shopping_assistant.config import ConfigError
from shopping_assistant.tools.search import (
    ProductSearch,
    canonical_listing_url,
    extract_price_hint,
    is_blocked_url,
    looks_like_product_url,
    matches_model,
    model_tokens,
    name_words,
    retailer_name,
)


class FakeTavily:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {"results": self.results}


@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://www.amazon.ca/Sony-WH-1000XM5/dp/B09XS7JWHH", True),
        ("https://www.amazon.ca/gp/product/B09XS7JWHH?th=1", True),
        ("https://www.amazon.ca/s?k=sony+headphones", False),
        ("https://www.amazon.ca/gp/cart/view.html", False),
        ("https://www.amazon.ca/gp/buy/spc/handlers/display.html", False),
        # Best Buy is excluded from v1 (blocks the scraper), even for product pages.
        ("https://www.bestbuy.ca/en-ca/product/sony-wh-1000xm5/16112937", False),
        ("https://www.bestbuy.ca/en-ca/search?search=sony", False),
        # RONA is excluded from v1 (DataDome blocks the scraper).
        ("https://www.rona.ca/en/product/dewalt-20-volt-max-1-2-in-cordless-compact-drill-driver-kit-dcd777c2-00276320", False),
        ("https://electronics.sony.ca/en/product/wh1000xm5", True),
        ("https://shop.brand.ca/checkout/123", False),
        # New v1 retailers: real product URLs from the 2026-11-16 Tavily discovery...
        ("https://www.walmart.ca/en/ip/Sony-WH-1000XM5-Wireless-Industry-Leading-Noise-Cancelling-Headphones/6000206790323", True),
        ("https://www.staples.ca/products/3033227-en-sony-wh1000xm5-wireless-noise-cancelling-headphones-black", True),
        ("https://www.costco.ca/p/-/sony-wh-1000xm5-wireless-noise-cancelling-headphones/4000027281", True),
        ("https://www.costco.ca/.product.4000027281.html?bvstate=pg%3A5", True),
        ("https://www.dell.com/en-ca/shop/cty/apd/210-BRND", True),
        ("https://www.dell.com/en-ca/shop/laptop-computers/spd/xps139350", True),
        ("https://www.newegg.ca/sony-wh-1000xm5-headphone-black/p/0TH-000U-00HM4", True),
        ("https://www.newegg.ca/samsung-2tb-990-pro-nvme-2-0/p/N82E16820147861", True),
        ("https://www.canadacomputers.com/en/over-ear-headphones/222384/sony-wh-1000xm5-wireless-noise-cancelling-headphones-platinum-silver-wh1000xm5-s.html", True),
        ("https://www.canadiantire.ca/en/pdp/dewalt-dcd777c1-20v-max-lithium-ion-brushless-cordless-drill-driver-with-battery-charger-1-2-in-0546714p.html", True),
        # ...and their non-product pages from the same results.
        ("https://www.walmart.ca/en/reviews/product/2P9FP9H47OOW", False),
        ("https://www.walmart.ca/wapcrs/track?bt=1&rd=https%3A%2F%2Fwww.walmart.ca%2Fen%2Fip%2Fx%2F3RK4", False),
        ("https://www.staples.ca/search?query=sony+wh+1000xm5", False),
        ("https://www.costco.ca/headphones.html?refine=%7C%7CBrand_attr-Sony", False),
        ("https://www.dell.com/en-us/shop/dell-27-plus-4k-monitor-s2725qs/apd/210-brnd", False),  # US store
        ("https://www.dell.com/en-ca/shop/deals/dc/monitor-deals", False),
        ("https://www.dell.ca/Student", False),
        ("https://www.newegg.ca/p/pl?d=samsung+ssd+2tb+nvme", False),
        ("https://www.canadacomputers.com/en/947/over-ear-headphones?id_manufacturer=1908", False),
        ("https://cloud.email.canadiantire.ca/Dewalt_Rules", False),
        # Brand-store non-product pages seen in the live check.
        ("https://www.sony.ca/en/audio/headphones/c/all-headphones", False),
        ("https://www.sony.ca/en/electronics/support/wh-1000xm5/specifications", False),
        ("https://www.sony.ca/en/electronics/support/articles/00346233", False),
        ("ftp://example.com/product", False),
    ],
)
def test_looks_like_product_url(url, ok):
    assert looks_like_product_url(url) is ok


def test_cart_and_checkout_always_blocked():
    for url in ("https://x.ca/cart", "https://x.ca/checkout/step1", "https://x.ca/account/login"):
        assert is_blocked_url(url)


def test_retailer_name_and_price_hint():
    assert retailer_name("https://www.amazon.ca/dp/B09XS7JWHH") == "Amazon.ca"
    assert retailer_name("https://www.dell.com/en-ca/shop/cty/apd/210-BRND") == "Dell Canada"
    assert retailer_name("https://www.canadiantire.ca/en/pdp/x-1p.html") == "Canadian Tire"
    assert retailer_name("https://electronics.sony.ca/p") == "electronics.sony.ca"
    assert extract_price_hint("Now only $1,299.99 on Amazon.ca") == 1299.99
    assert extract_price_hint("CA$398 with free shipping") == 398.0
    assert extract_price_hint("no price here") is None


class SequencedTavily(FakeTavily):
    """Returns a different result list for each successive call."""

    def __init__(self, *batches):
        super().__init__([])
        self.batches = list(batches)

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {"results": self.batches.pop(0)}


def _hit(url):
    return {"title": url, "url": url, "content": "...", "score": 0.5}


def test_research_products_uses_only_trusted_sites_when_enough():
    trusted = [_hit(f"https://www.rtings.com/r{i}") for i in range(4)]
    fake = SequencedTavily(trusted)
    results = ProductSearch(settings=None, client=fake).research_products("noise cancelling headphones")
    assert len(results) == 4 and len(fake.calls) == 1
    query, kwargs = fake.calls[0]
    assert "noise cancelling headphones" in query
    assert "rtings.com" in kwargs["include_domains"]


def test_research_products_tops_up_with_open_search():
    trusted = [_hit("https://www.rtings.com/a"), {"title": "no url", "url": ""}]
    open_web = [_hit("https://www.rtings.com/a"), _hit("https://blog.example/b")]
    fake = SequencedTavily(trusted, open_web)
    results = ProductSearch(settings=None, client=fake).research_products("headphones")
    assert [r.url for r in results] == ["https://www.rtings.com/a", "https://blog.example/b"]
    assert "include_domains" not in fake.calls[1][1]


@pytest.mark.parametrize(
    "name, tokens",
    [
        ("Sony WH-1000XM5", ["wh1000xm5"]),
        ("Bose QuietComfort Ultra", []),
        ("Apple iPhone 16 Pro", []),
        ("MacBook Air M3 2024", []),
        ("Samsung QN90D 65-inch", ["qn90d", "65inch"]),
    ],
)
def test_model_tokens(name, tokens):
    assert model_tokens(name) == tokens


@pytest.mark.parametrize(
    "texts, ok",
    [
        # Regression: 2026-11-18 live run matched these to "Soundcore Liberty 5 Pro".
        (("https://www.canadacomputers.com/en/on-ear-headphones/259482/ican-md033-bk-wireless-earbuds-with-noise-cancelling-mic-md033-bk.html",
          "iCan MD033 Wireless Earbuds with Noise Cancelling Mic"), False),
        (("https://www.dell.com/en-ca/shop/monitors/apd/alienware-27-gaming-monitor-aw2725dm/aw2725dm/-",
          "Alienware 27 Gaming Monitor - AW2725DM"), False),
        (("https://www.amazon.ca/dp/B0XXXXXXX1", "soundcore Liberty 4 Pro Noise Cancelling Earbuds"), False),
        (("https://www.amazon.ca/dp/B0XXXXXXX2", "soundcore Liberty 5 Pro Wireless Earbuds, Adaptive ANC"), True),
        (("https://www.soundcore.com/ca/products/liberty-5-pro", ""), True),  # brand store: brand in the host counts
        (("https://www.soundcore.com/ca/products/liberty-4-pro", ""), False),
    ],
)
def test_matches_model_by_name_words(texts, ok):
    assert matches_model("Soundcore Liberty 5 Pro", *texts) is ok


def test_name_words_and_joined_words():
    assert name_words("Bose QuietComfort Ultra Earbuds (2nd Gen)") == ["bose", "quietcomfort", "ultra", "2nd"]
    # Long words also match across spacing differences, in either direction.
    assert matches_model("Bose QuietComfort Ultra Earbuds (2nd Gen)", "Bose Quiet Comfort Ultra Earbuds 2nd Gen") is True
    assert matches_model("Bose QuietComfort Ultra Earbuds (2nd Gen)", "BoseQuietComfortUltraEarbuds-2nd-Gen") is True
    assert matches_model("Bose QuietComfort Ultra Earbuds (2nd Gen)", "Bose QuietComfort Ultra Earbuds") is False  # 1st gen
    assert matches_model("Wireless Earbuds", "anything") is True  # nothing identifying: can't filter


def test_matches_model_rejects_sibling_model():
    assert matches_model("Sony WH-1000XM5", "https://www.sony.ca/p/wh1000xm5-b")
    assert not matches_model("Sony WH-1000XM5", "https://www.sony.ca/p/wf1000xm5-b", "WF-1000XM5 earbuds")
    # Names without a model number must match by their identifying words.
    assert not matches_model("Bose QuietComfort Ultra", "https://www.bose.ca/anything")
    assert matches_model("Bose QuietComfort Ultra", "https://www.bose.ca/en/p/quietcomfort-ultra-headphones")


def test_find_retail_listings_filters_and_dedupes():
    fake = FakeTavily([
        {"title": "Best Buy (excluded)", "url": "https://www.bestbuy.ca/en-ca/product/sony-wh-1000xm5/16112937", "content": "$449.99"},
        {"title": "Sony WH-1000XM5 Wireless Headphones : Amazon.ca", "url": "https://www.amazon.ca/dp/B09XS7JWHH", "content": "Price: $398.00"},
        {"title": "dup", "url": "https://www.amazon.ca/dp/B09XS7JWHH#reviews", "content": "$1"},
        {"title": "search page", "url": "https://www.amazon.ca/s?k=sony", "content": "$1"},
        {"title": "US store", "url": "https://www.amazon.com/dp/B09XS7JWHH", "content": "$348"},
        {"title": "brand", "url": "https://electronics.sony.ca/en/product/wh1000xm5", "content": "CA$449.99"},
        {"title": "WF-1000XM5 earbuds", "url": "https://electronics.sony.ca/en/product/wf1000xm5", "content": "$429.99"},
    ])
    listings = ProductSearch(settings=None, client=fake).find_retail_listings(
        "Sony WH-1000XM5", brand_domains=["sony.ca", "bestbuy.ca"]
    )
    assert [(l.retailer, l.price_hint) for l in listings] == [
        ("Amazon.ca", 398.0),
        ("electronics.sony.ca", 449.99),
    ]
    _, kwargs = fake.calls[0]
    assert kwargs["include_domains"] == [
        "amazon.ca", "walmart.ca", "staples.ca", "costco.ca", "dell.com",
        "newegg.ca", "canadacomputers.com", "canadiantire.ca", "sony.ca",
    ]
    assert "bestbuy.ca" in kwargs["exclude_domains"]


class DomainAwareTavily(FakeTavily):
    """Honours include_domains and max_results like the real API."""

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        allowed = kwargs.get("include_domains") or []
        hits = [r for r in self.results if any(d in r["url"] for d in allowed)]
        return {"results": hits[: kwargs.get("max_results", 20)]}


def test_fill_missing_searches_only_retailers_without_hits():
    pool = [
        {"title": "Sony WH-1000XM5", "url": f"https://www.amazon.ca/dp/B09XS7JWH{i}", "content": ""}
        for i in range(5)
    ] + [
        {"title": "Sony WH-1000XM5", "url": "https://www.canadacomputers.com/en/over-ear-headphones/222384/sony-wh-1000xm5-s.html", "content": "$499.99"},
    ]
    fake = DomainAwareTavily(pool)
    # Combined search returns only the top 5, all Amazon, crowding out Canada Computers.
    listings = ProductSearch(settings=None, client=fake).find_retail_listings("Sony WH-1000XM5", max_results=5)

    assert {l.retailer for l in listings} == {"Amazon.ca", "Canada Computers"}
    combined, *targeted = fake.calls
    assert combined[1]["search_depth"] == "advanced"
    targeted_domains = [kw["include_domains"] for _, kw in targeted]
    assert ["amazon.ca"] not in targeted_domains  # already had hits
    assert ["canadacomputers.com"] in targeted_domains
    assert all(kw["search_depth"] == "basic" for _, kw in targeted)


def test_fill_missing_can_be_disabled():
    fake = DomainAwareTavily([])
    ProductSearch(settings=None, client=fake).find_retail_listings("Sony WH-1000XM5", fill_missing=False)
    assert len(fake.calls) == 1


def test_duplicate_listing_with_tracking_params_is_merged():
    """Regression, 2026-11-18 CLI run: the same Walmart item was listed twice."""
    base = "https://www.walmart.ca/en/ip/Sony-WH-1000XM6-Brand-New/7FIUKUA6U033"
    fake = FakeTavily([
        {"title": "Sony WH-1000XM6", "url": base, "content": ""},
        {"title": "Sony WH-1000XM6", "url": base + "?classType=VARIANT&athbdg=L3021", "content": ""},
        {"title": "Sony WH-1000XM6", "url": "https://electronics.sony.ca/p/wh1000xm6?colour=black", "content": ""},
    ])
    listings = ProductSearch(settings=None, client=fake).find_retail_listings(
        "Sony WH-1000XM6", brand_domains=["sony.ca"], fill_missing=False
    )
    assert [l.url for l in listings] == [base, "https://electronics.sony.ca/p/wh1000xm6?colour=black"]


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.amazon.ca/dp/B09XS7JWHH?th=1#reviews", "https://www.amazon.ca/dp/B09XS7JWHH"),
        ("https://www.costco.ca/.product.4000027281.html?bvstate=pg", "https://www.costco.ca/.product.4000027281.html"),
        ("https://shop.brand.ca/p/x?variant=2#top", "https://shop.brand.ca/p/x?variant=2"),
    ],
)
def test_canonical_listing_url(url, expected):
    assert canonical_listing_url(url) == expected


def test_missing_tavily_key_names_the_key(settings_factory):
    with pytest.raises(ConfigError, match="TAVILY_API_KEY"):
        ProductSearch(settings_factory(tavily_api_key=""))
