"""Graph 1 tracking setup end to end: finalize → listings → interrupt → save (US-05 to US-08, US-21)."""

import pytest

from shopping_assistant.models import IntentDecision, ScrapedPriceResult, TrackingDecision
from shopping_assistant.research import ResearchSession
from shopping_assistant.tools.search import RetailSearchResult

from test_research_graph import COMPARISON, FakeLLM, FakeSearch, explore

# Sessions save to (and checkpoint in) the test database; start each test empty.
pytestmark = pytest.mark.usefixtures("store")

AMZ = "https://www.amazon.ca/dp/B0CHX4ZD9K"
STAPLES = "https://www.staples.ca/products/3105225-en-bose-quietcomfort-ultra"
COSTCO = "https://www.costco.ca/p/-/bose-quietcomfort-ultra/4000203391"


class FakeRetailSearch(FakeSearch):
    def __init__(self, listings=None, error=None, **kw):
        super().__init__(**kw)
        self.listings = listings if listings is not None else [
            RetailSearchResult(title="Bose QuietComfort Ultra", url=AMZ, retailer="Amazon.ca", price_hint=45.0),
            RetailSearchResult(title="Bose QuietComfort Ultra", url=STAPLES, retailer="Staples Canada", price_hint=429.99),
            RetailSearchResult(title="Bose QuietComfort Ultra", url=COSTCO, retailer="Costco Canada"),
        ]
        self.listing_error = error
        self.listing_calls = []

    def find_retail_listings(self, product_name, brand_domains=(), **kw):
        self.listing_calls.append((product_name, list(brand_domains)))
        if self.listing_error:
            raise self.listing_error
        return self.listings


class FakeVerifier:
    def __init__(self, prices=None, error=None):
        self.prices = prices if prices is not None else {AMZ: 399.0, STAPLES: 429.99, COSTCO: None}
        self.error = error
        self.calls = []

    def __call__(self, urls):
        self.calls.append(list(urls))
        if self.error:
            raise self.error
        out = []
        for u in urls:
            p = self.prices.get(u)
            out.append(ScrapedPriceResult(url=u, current_price=p, in_stock=p is not None,
                                          extraction_method="json-ld" if p else "failed",
                                          error=None if p else "crawl failed (status 403)"))
        return out


FINALIZE_2 = IntentDecision(intent="finalize_product", candidate_number=2, search_query="headphones")


def make_session(settings, *decisions, search=None, verifier=None):
    intent = FakeLLM(explore("headphones"), *decisions)
    session = ResearchSession(
        settings, intent_llm=intent, research_llm=FakeLLM(COMPARISON, COMPARISON),
        search=search or FakeRetailSearch(), verify_prices=verifier or FakeVerifier(),
    )
    thread = session.new_thread_id()
    session.send(thread, "noise cancelling headphones")
    return session, thread


# --- US-05: listings ----------------------------------------------------------------


def test_finalize_finds_verified_listings_and_pauses(settings_factory):
    search, verifier = FakeRetailSearch(), FakeVerifier()
    session, thread = make_session(settings_factory(), FINALIZE_2, search=search, verifier=verifier)
    progress = []
    turn = session.send(thread, "option 2", on_progress=progress.append)

    assert search.listing_calls == [("Bose QuietComfort Ultra", ["bose.ca"])]
    assert verifier.calls == [[AMZ, STAPLES, COSTCO]]
    assert progress[:3] == ["understand_intent", "finalize_product", "locate_retail_listings"]

    pending = turn.pending_confirmation
    assert pending["product_name"] == "Bose QuietComfort Ultra"
    # Costco dropped: no scraped price and no snippet hint. Amazon uses scraped 399, not hint 45.
    assert [(l["retailer"], l["current_price"], l["price_verified"]) for l in pending["listings"]] == [
        ("Amazon.ca", 399.0, True),
        ("Staples Canada", 429.99, True),
    ]
    assert pending["suggested_target"] == 359.1  # 10% below cheapest (BRL-3)
    assert "Great choice: Bose QuietComfort Ultra" in turn.reply
    assert "1. Amazon.ca: CA$399.00 (checked on the page, in stock)" in turn.reply
    assert session.list_threads()[0]["finalized_product"] == "Bose QuietComfort Ultra"
    # Nothing saved before confirmation (BRL-6).
    assert session.store.list_tracked_items() == []


def test_verification_failure_falls_back_to_unverified_prices(settings_factory):
    session, thread = make_session(settings_factory(), FINALIZE_2, verifier=FakeVerifier(error=RuntimeError("browser crashed")))
    turn = session.send(thread, "option 2")
    listings = turn.pending_confirmation["listings"]
    # Staples keeps its snippet price (429.99, plausible vs the CA$429 estimate). Amazon's snippet
    # "price" of 45.00 is implausible for a ~CA$429 product, so it's dropped, not offered.
    assert [(l["retailer"], l["current_price"], l["price_verified"]) for l in listings] == [
        ("Staples Canada", 429.99, False)
    ]
    assert "unverified" in turn.reply
    assert "skipped 2 other results" in turn.reply  # Amazon (implausible) + Costco (no price)


@pytest.mark.parametrize("search", [FakeRetailSearch(listings=[]), FakeRetailSearch(error=ConnectionError("tavily down"))])
def test_no_listings_returns_to_research(settings_factory, search):
    session, thread = make_session(settings_factory(), FINALIZE_2, search=search)
    turn = session.send(thread, "option 2")
    assert turn.last_action == "no_listings" and turn.pending_confirmation is None
    assert "couldn't find Canadian retailer listings" in turn.reply
    assert turn.finalized_product["name"] == "Bose QuietComfort Ultra"


# --- US-06 / US-08: confirm and save --------------------------------------------------


def test_confirm_with_default_target_saves_each_listing(settings_factory):
    session, thread = make_session(settings_factory(), FINALIZE_2)
    session.send(thread, "option 2")
    turn = session.confirm(thread, TrackingDecision(action="track", selected=[1, 2]))

    assert turn.last_action == "tracking_saved" and turn.pending_confirmation is None
    items = session.store.list_tracked_items()
    assert [(i.retailer, i.initial_price, i.target_price, i.status) for i in items] == [
        ("Amazon.ca", 399.0, 359.1, "active"),
        ("Staples Canada", 429.99, 359.1, "active"),
    ]
    assert sorted(turn.saved_item_ids) == [i.id for i in items]
    assert [h.price for h in session.store.get_price_history(items[0].id)] == [399.0]
    assert "Tracking is set up for Bose QuietComfort Ultra" in turn.reply
    assert "Amazon.ca: now CA$399.00, alert at or below CA$359.10" in turn.reply


def test_custom_target_and_single_listing(settings_factory):
    session, thread = make_session(settings_factory(), FINALIZE_2)
    session.send(thread, "option 2")
    session.confirm(thread, TrackingDecision(action="track", selected=[2], target_price=380.0))
    items = session.store.list_tracked_items()
    assert [(i.retailer, i.target_price) for i in items] == [("Staples Canada", 380.0)]


def test_default_target_uses_only_selected_listings(settings_factory):
    session, thread = make_session(settings_factory(), FINALIZE_2)
    session.send(thread, "option 2")
    session.confirm(thread, TrackingDecision(action="track", selected=[2]))  # Staples 429.99 only
    assert session.store.list_tracked_items()[0].target_price == 386.99


def test_already_tracked_url_is_not_duplicated(settings_factory):
    settings = settings_factory()
    session, thread = make_session(settings, FINALIZE_2, FINALIZE_2)
    session.send(thread, "option 2")
    session.confirm(thread, TrackingDecision(action="track", selected=[1]))
    session.send(thread, "option 2 again")
    turn = session.confirm(thread, TrackingDecision(action="track", selected=[1, 2]))
    items = session.store.list_tracked_items()
    assert [i.retailer for i in items] == ["Amazon.ca", "Staples Canada"]
    assert "Amazon.ca: already on your watchlist" in turn.reply


# --- US-07: cancel ------------------------------------------------------------------


def test_cancel_saves_nothing(settings_factory):
    session, thread = make_session(settings_factory(), FINALIZE_2)
    session.send(thread, "option 2")
    turn = session.confirm(thread, TrackingDecision(action="cancel"))
    assert turn.last_action == "tracking_cancelled"
    assert "won't track anything" in turn.reply
    assert session.store.list_tracked_items() == []
    with pytest.raises(RuntimeError):
        session.confirm(thread, TrackingDecision(action="cancel"))  # nothing pending anymore


def test_invalid_decision_saves_nothing(settings_factory):
    session, thread = make_session(settings_factory(), FINALIZE_2)
    session.send(thread, "option 2")
    turn = session.confirm(thread, TrackingDecision(action="track", selected=[9]))
    assert turn.last_action == "tracking_cancelled" and "Nothing was saved" in turn.reply
    assert session.store.list_tracked_items() == []


def test_new_message_while_pending_cancels_first(settings_factory):
    session, thread = make_session(settings_factory(), FINALIZE_2, explore("cheaper headphones"))
    session.send(thread, "option 2")
    turn = session.send(thread, "actually, show me cheaper ones")
    assert turn.last_action == "researched"
    history = [text for _, text in session.history(thread)]
    assert any("won't track anything" in t for t in history)
    assert session.store.list_tracked_items() == []


def test_pending_confirmation_survives_restart(settings_factory):
    settings = settings_factory()
    session, thread = make_session(settings, FINALIZE_2)
    session.send(thread, "option 2")
    session.close()

    s2 = ResearchSession(settings, intent_llm=FakeLLM(), research_llm=FakeLLM(),
                         search=FakeRetailSearch(), verify_prices=FakeVerifier())
    pending = s2.pending_confirmation(thread)
    assert pending and len(pending["listings"]) == 2
    s2.confirm(thread, TrackingDecision(action="track", selected=[1]))
    assert len(s2.store.list_tracked_items()) == 1
    s2.close()


# --- US-21: never buys ----------------------------------------------------------------


def test_purchase_request_is_declined_without_side_effects(settings_factory):
    search = FakeRetailSearch()
    session, thread = make_session(
        settings_factory(), IntentDecision(intent="purchase_request", search_query="buy bose"), search=search
    )
    turn = session.send(thread, "just buy the Bose for me")
    assert turn.last_action == "declined"
    assert "can't buy, order, or add anything to a cart" in turn.reply
    assert "alert you when the price drops" in turn.reply
    assert search.listing_calls == [] and session.store.list_tracked_items() == []


def test_safety_rule_is_in_every_llm_system_prompt():
    from shopping_assistant.graphs.research_graph import FOLLOWUP_SYSTEM, INTENT_SYSTEM, RESEARCH_SYSTEM

    for prompt in (INTENT_SYSTEM, RESEARCH_SYSTEM, FOLLOWUP_SYSTEM):
        assert "never purchase" in prompt and "add items to carts" in prompt
