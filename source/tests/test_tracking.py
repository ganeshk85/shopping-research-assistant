"""Pure tracking-setup helpers (FR-3, FR-4)."""

import pytest

from shopping_assistant.models import ScrapedPriceResult, TrackingDecision
from shopping_assistant.tools.search import RetailSearchResult
from shopping_assistant.tracking import (
    brand_store_domains,
    build_listings,
    default_target_price,
    parse_selection,
    parse_target,
    price_is_plausible,
    select_for_verification,
    validate_decision,
)

AMZ = "https://www.amazon.ca/dp/B09XS7JWHH"
STAPLES = "https://www.staples.ca/products/3033227-en-sony-wh1000xm5"
WALMART = "https://www.walmart.ca/en/ip/Sony-WH-1000XM5/6000206790323"
COSTCO = "https://www.costco.ca/p/-/sony-wh-1000xm5/4000027281"


def rsr(url, retailer, hint=None, title="Sony WH-1000XM5"):
    return RetailSearchResult(title=title, url=url, retailer=retailer, price_hint=hint)


def scraped(url, price=None, in_stock=True, method="json-ld", error=None):
    return ScrapedPriceResult(url=url, current_price=price, in_stock=in_stock, extraction_method=method, error=error)


# --- build_listings ----------------------------------------------------------------


def test_build_listings_prefers_scraped_price_and_sorts():
    results = [rsr(AMZ, "Amazon.ca", 45.0), rsr(STAPLES, "Staples Canada"), rsr(WALMART, "Walmart Canada", 459.0), rsr(COSTCO, "Costco Canada")]
    checks = [
        scraped(AMZ, 498.0, method="css-fallback"),  # hint of 45 must be ignored
        scraped(STAPLES, 499.99),
        scraped(WALMART, method="failed", error="crawl failed (status 307): PerimeterX"),
        scraped(COSTCO, 498.0, in_stock=False),
    ]
    listings, dropped = build_listings("Sony WH-1000XM5", results, checks)
    summary = [(l.retailer, l.current_price, l.price_verified, l.in_stock) for l in listings]
    assert summary == [
        ("Amazon.ca", 498.0, True, True),
        ("Staples Canada", 499.99, True, True),
        ("Costco Canada", 498.0, True, False),  # verified but out of stock sorts after in-stock
        ("Walmart Canada", 459.0, False, True),  # unverified last, uses snippet hint
    ]
    assert "PerimeterX" in listings[-1].note
    assert dropped == 0


def test_build_listings_drops_listings_without_any_price():
    listings, dropped = build_listings("X", [rsr(STAPLES, "Staples Canada")], [scraped(STAPLES, method="failed")])
    assert listings == [] and dropped == 1


def test_build_listings_never_includes_cart_or_checkout_urls():
    bad = rsr("https://www.amazon.ca/gp/cart/view.html", "Amazon.ca", 10.0)
    listings, dropped = build_listings("X", [bad], [scraped(bad.url, 10.0)])
    assert listings == [] and dropped == 1


def test_regression_live_run_wrong_products_are_dropped():
    """2026-11-18: 'Soundcore Liberty 5 Pro' (est. CA$220) listed iCan earbuds at CA$9.88 and Dell monitors."""
    ican = "https://www.canadacomputers.com/en/on-ear-headphones/259482/ican-md033-bk-wireless-earbuds.html"
    dell = "https://www.dell.com/en-ca/shop/monitors/apd/alienware-27-gaming-monitor-aw2725dm/aw2725dm/-"
    good = "https://www.amazon.ca/dp/B0DT4F2NM9"
    results = [
        # Search titles that slipped through by a different route must still be caught here...
        rsr(ican, "Canada Computers", title="soundcore liberty 5 pro alternatives"),
        # ...and wrong products are dropped by their own search title/URL.
        rsr(dell, "Dell Canada", 379.99, title="Alienware 27 Gaming Monitor - AW2725DM"),
        rsr(good, "Amazon.ca", title="soundcore Liberty 5 Pro Earbuds : Amazon.ca"),
    ]
    checks = [
        ScrapedPriceResult(url=ican, current_price=9.88, in_stock=True, extraction_method="json-ld",
                           page_title="iCan MD033-BK Wireless Earbuds with Noise Cancelling Mic"),
        ScrapedPriceResult(url=dell, extraction_method="failed", error="timeout"),
        ScrapedPriceResult(url=good, current_price=199.99, in_stock=True, extraction_method="css-fallback",
                           page_title="soundcore Liberty 5 Pro Noise Cancelling Earbuds"),
    ]
    listings, dropped = build_listings("Soundcore Liberty 5 Pro", results, checks, expected_price=220.0)
    assert [(l.retailer, l.current_price) for l in listings] == [("Amazon.ca", 199.99)]
    assert dropped == 2  # iCan: the page's own title is a different product; Dell: search title mismatch


@pytest.mark.parametrize(
    "price, expected, ok",
    [(220.0, 220.0, True), (88.0, 220.0, True), (87.99, 220.0, False), (550.0, 220.0, True), (550.01, 220.0, False),
     (9.88, None, True), (9.88, 0, True)],
)
def test_price_is_plausible(price, expected, ok):
    assert price_is_plausible(price, expected) is ok


def test_implausible_snippet_hint_is_dropped():
    listings, dropped = build_listings("Sony WH-1000XM5", [rsr(AMZ, "Amazon.ca", 45.0)], [], expected_price=449.99)
    assert listings == [] and dropped == 1


def test_select_for_verification_covers_each_retailer_first():
    results = [rsr(f"https://www.amazon.ca/dp/B0000000{i:02d}", "Amazon.ca") for i in range(6)] + [
        rsr(STAPLES, "Staples Canada"),
        rsr(COSTCO, "Costco Canada"),
    ]
    picked = select_for_verification(results, max_total=5, max_per_retailer=3)
    retailers = [r.retailer for r in picked]
    assert retailers[:3] == ["Amazon.ca", "Staples Canada", "Costco Canada"]
    assert len(picked) == 5 and retailers.count("Amazon.ca") == 3


# --- target price ---------------------------------------------------------------------


def test_default_target_is_ten_percent_below_lowest():
    assert default_target_price([499.99, 498.0]) == 448.2
    assert default_target_price([100.0], discount=0.2) == 80.0
    with pytest.raises(ValueError):
        default_target_price([])


@pytest.mark.parametrize(
    "text, expected",
    [("", None), ("399", 399.0), ("$399.99", 399.99), ("CA$1,049.50", 1049.5), ("399 CAD", 399.0),
     ("abc", "'abc' isn't a price."), ("0", "The target price must be above zero."), ("-5", "The target price must be above zero.")],
)
def test_parse_target(text, expected):
    assert parse_target(text) == expected


# --- selection ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, selected",
    [("1", [1]), ("1,3", [1, 3]), ("3 1", [3, 1]), ("2-4", [2, 3, 4]), ("all", [1, 2, 3, 4]), ("1,1,2", [1, 2])],
)
def test_parse_selection_valid(text, selected):
    d = parse_selection(text, 4)
    assert isinstance(d, TrackingDecision) and d.action == "track" and d.selected == selected


@pytest.mark.parametrize("text", ["c", "cancel", "no"])
def test_parse_selection_cancel(text):
    assert parse_selection(text, 4).action == "cancel"


@pytest.mark.parametrize("text, msg", [("5", "between 1 and 4"), ("x", "isn't a listing number"), ("", "at least one")])
def test_parse_selection_errors(text, msg):
    result = parse_selection(text, 4)
    assert isinstance(result, str) and msg in result


def test_validate_decision():
    listings = [{}, {}]
    assert validate_decision(TrackingDecision(action="cancel"), listings) is None
    assert validate_decision(TrackingDecision(action="track", selected=[1, 2]), listings) is None
    assert "don't exist" in validate_decision(TrackingDecision(action="track", selected=[3]), listings)
    assert "No listings" in validate_decision(TrackingDecision(action="track"), listings)
    assert "above zero" in validate_decision(TrackingDecision(action="track", selected=[1], target_price=-1), listings)


def test_brand_store_domains():
    assert brand_store_domains("Sony") == ["sony.ca"]
    assert brand_store_domains("Anker Soundcore") == ["ankersoundcore.ca"]
    assert brand_store_domains(None) == []
