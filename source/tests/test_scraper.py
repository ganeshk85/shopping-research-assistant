from pathlib import Path
from types import SimpleNamespace

import pytest

from shopping_assistant.tools import scraper
from shopping_assistant.tools.scraper import extract_price, parse_price_text, scrape_prices

FIXTURES = Path(__file__).parent / "fixtures"
AMAZON = "https://www.amazon.ca/dp/B09XS7JWHH"
BRAND_FR = "https://www.brand.ca/fr/produit/casque-xm5"
BRAND = "https://electronics.sony.ca/en/product/wh1000xm5"


def html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("$449.99", 449.99),
        ("CA$1,299.00", 1299.0),
        ("1 049,99 $", 1049.99),
        ("1.299,50 €", 1299.5),
        ("$398", 398.0),
        (449, 449.0),
        (0, None),
        ("", None),
        ("Free", None),
        (None, None),
        (True, None),
    ],
)
def test_parse_price_text(raw, expected):
    assert parse_price_text(raw) == expected


def test_jsonld_single_offer():
    r = extract_price(html("jsonld_single_offer.html"), BRAND)
    assert (r.current_price, r.currency, r.in_stock, r.extraction_method) == (449.99, "CAD", True, "json-ld")


def test_jsonld_offer_list_prefers_cheapest_in_stock():
    r = extract_price(html("jsonld_offer_list.html"), BRAND)
    assert r.current_price == 399.99
    assert r.in_stock is True


def test_jsonld_graph_aggregate_offer_uses_low_price():
    r = extract_price(html("jsonld_graph.html"), BRAND)
    assert r.current_price == 1299.0
    assert r.extraction_method == "json-ld"


def test_jsonld_out_of_stock():
    r = extract_price(html("jsonld_out_of_stock.html"), BRAND)
    assert r.current_price == 299.0
    assert r.in_stock is False


def test_jsonld_without_price_falls_back_to_meta():
    r = extract_price(html("jsonld_missing_price.html"), BRAND)
    assert r.current_price == 249.95
    assert r.extraction_method == "css-fallback"
    assert r.in_stock is True


def test_malformed_jsonld_is_repaired():
    r = extract_price(html("malformed_jsonld.html"), BRAND)
    assert r.current_price == 89.99
    assert r.extraction_method == "json-ld"


def test_amazon_css_fallback():
    r = extract_price(html("amazon_css.html"), AMAZON)
    assert (r.current_price, r.in_stock, r.extraction_method) == (398.0, True, "css-fallback")


def test_generic_css_fallback_french_format_out_of_stock():
    r = extract_price(html("generic_css_fr_out_of_stock.html"), BRAND_FR)
    assert r.current_price == 1049.99
    assert r.in_stock is False


NEWEGG = "https://www.newegg.ca/samsung-2tb-990-pro-nvme-2-0/p/N82E16820147861"


def test_newegg_uses_buy_box_not_marketplace_rows():
    r = extract_price(html("newegg_instock.html"), NEWEGG)
    assert (r.current_price, r.in_stock, r.extraction_method) == (874.97, True, "css-fallback")


def test_out_of_stock_page_without_price_explains_why():
    r = extract_price(html("newegg_out_of_stock.html"), NEWEGG)
    assert r.extraction_method == "failed"
    assert r.in_stock is False
    assert r.error == "out of stock (no price shown)"


def test_no_price_is_failed():
    r = extract_price(html("no_price.html"), AMAZON)
    assert r.extraction_method == "failed"
    assert r.current_price is None
    assert r.error


# --- Crawl4AI wrapper, with a fake crawler (no network) ------------------------


class FakeCrawler:
    def __init__(self, pages: dict):
        self.pages = pages
        self.calls: list[str] = []

    async def arun(self, url, config=None):
        self.calls.append(url)
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page


@pytest.fixture(autouse=True)
def no_crawl4ai_config(monkeypatch):
    # Avoid constructing real Crawl4AI configs in unit tests.
    monkeypatch.setattr(scraper, "_run_config", lambda timeout: None)


async def test_scrape_prices_isolates_failures_and_keeps_order():
    ok = SimpleNamespace(success=True, html=html("jsonld_single_offer.html"), status_code=200)
    blocked = SimpleNamespace(success=True, html="<html>captcha</html>", status_code=503)
    crawler = FakeCrawler(
        {
            "https://a.example/p/1": ok,
            "https://b.example/p/2": TimeoutError("page timeout"),
            "https://c.example/p/3": blocked,
            "https://d.example/p/4": SimpleNamespace(success=False, html=None, status_code=None, error_message="net::ERR"),
        }
    )
    results = await scrape_prices(list(crawler.pages), crawler=crawler)

    assert [r.url for r in results] == list(crawler.pages)
    assert results[0].current_price == 449.99
    assert [r.extraction_method for r in results[1:]] == ["failed"] * 3
    assert "timeout" in results[1].error
    assert "503" in results[2].error
    assert "net::ERR" in results[3].error


async def test_scrape_prices_empty():
    assert await scrape_prices([]) == []
