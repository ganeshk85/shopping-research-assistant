"""End-to-end smoke test (offline): research → finalize → confirm tracking → watchlist →
price check alert → no duplicate → pause → skipped. All external services are faked."""

from shopping_assistant.models import IntentDecision, TrackingDecision
from shopping_assistant.monitor import PriceMonitor
from shopping_assistant.research import ResearchSession
from shopping_assistant.watchlist import WatchlistCommand, apply_command, load_watchlist, render_watchlist

from test_monitor_graph import FakeNotifier, FakeScraper
from test_research_graph import COMPARISON, FakeLLM, explore
from test_tracking_flow import AMZ, STAPLES, FakeRetailSearch, FakeVerifier


async def test_full_journey(settings_factory, store):
    settings = settings_factory()

    # 1. Research and choose a product (Graph 1).
    session = ResearchSession(
        settings,
        intent_llm=FakeLLM(
            explore("noise cancelling headphones"),
            IntentDecision(intent="finalize_product", candidate_number=2, search_query="headphones"),
        ),
        research_llm=FakeLLM(COMPARISON),
        search=FakeRetailSearch(),
        verify_prices=FakeVerifier(),
    )
    thread = session.new_thread_id()
    assert session.send(thread, "noise cancelling headphones").last_action == "researched"
    turn = session.send(thread, "let's go with option 2")
    assert turn.pending_confirmation is not None

    # 2. Confirm tracking with a custom target.
    turn = session.confirm(thread, TrackingDecision(action="track", selected=[1, 2], target_price=400.0))
    assert turn.last_action == "tracking_saved" and len(turn.saved_item_ids) == 2
    session.close()

    # 3. The watchlist shows both items, not yet checked.
    text = render_watchlist(load_watchlist(store))
    assert text.count("not yet checked") == 2 and "Bose QuietComfort Ultra" in text

    # 4. A price check finds Amazon below target → one alert (Graph 2).
    notifier = FakeNotifier()
    same = {AMZ: (389.0, True, "Bose QuietComfort Ultra Headphones"), STAPLES: (429.99, True, "Bose QuietComfort Ultra")}
    monitor = PriceMonitor(settings, scrape=FakeScraper(same, same, same), notifier=notifier, alert_llm=None)
    summary = await monitor.run_once()
    assert [a.item.retailer for a in summary.alerts_sent] == ["Amazon.ca"]
    assert notifier.sent[0][0] == "Target price reached: Bose QuietComfort Ultra now CA$389.00 at Amazon.ca"

    # 5. Same prices again → no duplicate alert; watchlist shows the new price and a recent check.
    assert (await monitor.run_once()).alerts_sent == []
    text = render_watchlist(load_watchlist(store))
    assert "CA$389.00" in text and "just now" in text

    # 6. Pause Amazon → the next check skips it.
    amazon_id = next(i.id for i in store.list_tracked_items() if i.retailer == "Amazon.ca")
    apply_command(store, WatchlistCommand("pause", amazon_id))
    summary = await monitor.run_once()
    assert summary.active_items == 1 and [c.item.retailer for c in summary.checks] == ["Staples Canada"]
    assert len(notifier.sent) == 1
