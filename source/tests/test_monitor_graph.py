"""Graph 2 end to end with a fake scraper, notifier and LLM (US-10, US-13 to US-17)."""

import pytest
from langchain_core.messages import AIMessage

from shopping_assistant import database as db
from shopping_assistant.graphs.monitor_graph import write_alert
from shopping_assistant.models import ScrapedPriceResult
from shopping_assistant.monitor import PriceMonitor
from shopping_assistant.tools.notifier import NotificationError

AMZ = "https://www.amazon.ca/dp/B0F3PQHWTZ"
STAPLES = "https://www.staples.ca/products/3124721-en-sony-wh1000xm6"
COSTCO = "https://www.costco.ca/p/-/sony-wh-1000xm6/4000377234"
NAME = "Sony WH-1000XM6"


class FakeScraper:
    """Returns the next queued {url: (price, in_stock[, page_title])} per run."""

    def __init__(self, *runs):
        self.runs = list(runs)
        self.calls = []

    async def __call__(self, urls):
        self.calls.append(list(urls))
        prices = self.runs.pop(0)
        out = []
        for u in urls:
            spec = prices.get(u)
            if spec is None or isinstance(spec, str):
                out.append(ScrapedPriceResult(url=u, extraction_method="failed", error=spec or "blocked"))
            else:
                price, in_stock, *title = spec
                out.append(ScrapedPriceResult(url=u, current_price=price, in_stock=in_stock, extraction_method="json-ld",
                                              page_title=title[0] if title else f"{NAME} Wireless Headphones"))
        return out


class FakeNotifier:
    def __init__(self, fail_times=0):
        self.sent = []
        self.fail_times = fail_times

    def send(self, subject, body):
        if self.fail_times:
            self.fail_times -= 1
            raise NotificationError("webhook down")
        self.sent.append((subject, body))


class FakeAlertLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.reply


def good_llm():
    return FakeAlertLLM(AIMessage(
        "Sony WH-1000XM6 dropped to CA$399.00 at Amazon.ca, down from CA$478.00 when you started tracking. "
        "That's below your CA$430.20 target.\n" + AMZ
    ))


@pytest.fixture
def setup(settings_factory):
    settings = settings_factory()
    path = db.init_db(settings.watchlist_db_path)
    ids = {
        "amz": db.add_tracked_item(path, product_name=NAME, retailer="Amazon.ca", url=AMZ, initial_price=478.0, target_price=430.2),
        "staples": db.add_tracked_item(path, product_name=NAME, retailer="Staples Canada", url=STAPLES, initial_price=479.99, target_price=430.2),
    }
    return settings, path, ids


def monitor(settings, scraper, notifier=None, llm=None):
    return PriceMonitor(settings, scrape=scraper, notifier=notifier or FakeNotifier(), alert_llm=llm)


# --- US-10 / US-13: checks and history ---------------------------------------------


async def test_no_drop_records_history_and_never_calls_llm(setup):
    settings, path, ids = setup
    llm = good_llm()
    notifier = FakeNotifier()
    summary = await monitor(settings, FakeScraper({AMZ: (478.0, True), STAPLES: (485.0, True)}), notifier, llm).run_once()

    assert summary.active_items == 2 and summary.checked == 2 and not summary.failures
    assert summary.alerts_sent == [] and notifier.sent == [] and llm.calls == []  # NFR-2
    assert [h.price for h in db.get_price_history(path, ids["staples"])] == [479.99, 485.0]


async def test_empty_watchlist(settings_factory):
    scraper = FakeScraper()
    summary = await monitor(settings_factory(), scraper).run_once()
    assert summary.active_items == 0 and scraper.calls == []
    assert "No active items" in summary.render()


async def test_paused_items_are_not_checked(setup):
    settings, path, ids = setup
    db.update_status(path, ids["staples"], "paused")
    scraper = FakeScraper({AMZ: (478.0, True)})
    await monitor(settings, scraper).run_once()
    assert scraper.calls == [[AMZ]]


# --- US-14: alerts --------------------------------------------------------------------


async def test_target_reached_sends_llm_alert_and_records_last_notified(setup):
    settings, path, ids = setup
    llm, notifier = good_llm(), FakeNotifier()
    summary = await monitor(settings, FakeScraper({AMZ: (399.0, True), STAPLES: (479.99, True)}), notifier, llm).run_once()

    assert [a.item.id for a in summary.alerts_sent] == [ids["amz"]]
    assert summary.alerts_sent[0].reason == "target_reached"
    subject, body = notifier.sent[0]
    assert subject == "Target price reached: Sony WH-1000XM6 now CA$399.00 at Amazon.ca"
    assert body.startswith("Sony WH-1000XM6 dropped to CA$399.00") and AMZ in body
    assert db.get_tracked_item(path, ids["amz"]).last_notified_price == 399.0
    assert db.get_tracked_item(path, ids["amz"]).lowest_price_seen == 399.0
    # The LLM got precomputed facts, not raw numbers to do maths on.
    assert '"percent_below_start": 16.5' in llm.calls[0][1].content
    assert "<- alert sent" in summary.render()


async def test_new_low_above_target_alerts(setup):
    settings, path, ids = setup
    notifier = FakeNotifier()
    summary = await monitor(settings, FakeScraper({AMZ: (460.0, True), STAPLES: (479.99, True)}), notifier).run_once()
    assert [a.reason for a in summary.alerts_sent] == ["new_low"]
    assert notifier.sent[0][0].startswith("New low price:")


async def test_out_of_stock_low_price_does_not_alert_or_set_low(setup):
    settings, path, ids = setup
    notifier = FakeNotifier()
    await monitor(settings, FakeScraper({AMZ: (350.0, False), STAPLES: (479.99, True)}), notifier).run_once()
    assert notifier.sent == []
    item = db.get_tracked_item(path, ids["amz"])
    assert item.lowest_price_seen == 478.0  # OOS price recorded in history but not as the low
    assert db.get_price_history(path, ids["amz"])[-1].in_stock is False


# --- US-15: no duplicates ---------------------------------------------------------------


async def test_same_price_twice_alerts_once_then_lower_again_alerts(setup):
    settings, path, ids = setup
    notifier = FakeNotifier()
    scraper = FakeScraper(
        {AMZ: (399.0, True), STAPLES: (479.99, True)},
        {AMZ: (399.0, True), STAPLES: (479.99, True)},
        {AMZ: (389.0, True), STAPLES: (479.99, True)},
    )
    m = monitor(settings, scraper, notifier)
    first, second, third = await m.run_once(), await m.run_once(), await m.run_once()
    assert len(first.alerts_sent) == 1 and len(second.alerts_sent) == 0 and len(third.alerts_sent) == 1
    assert [s for s, _ in notifier.sent] == [
        "Target price reached: Sony WH-1000XM6 now CA$399.00 at Amazon.ca",
        "Target price reached: Sony WH-1000XM6 now CA$389.00 at Amazon.ca",
    ]


async def test_failed_delivery_is_retried_next_run(setup):
    settings, path, ids = setup
    notifier = FakeNotifier(fail_times=1)
    scraper = FakeScraper({AMZ: (399.0, True), STAPLES: (479.99, True)}, {AMZ: (399.0, True), STAPLES: (479.99, True)})
    m = monitor(settings, scraper, notifier)

    first = await m.run_once()
    assert first.alerts_sent == [] and [a.item.id for a in first.alerts_failed] == [ids["amz"]]
    assert db.get_tracked_item(path, ids["amz"]).last_notified_price is None
    assert "will be retried" in first.render()

    second = await m.run_once()
    assert [a.item.id for a in second.alerts_sent] == [ids["amz"]]
    assert len(notifier.sent) == 1


# --- US-12 carried over: failed checks ------------------------------------------------


async def test_failed_scrape_changes_nothing(setup):
    settings, path, ids = setup
    summary = await monitor(settings, FakeScraper({AMZ: "crawl failed (status 307): PerimeterX", STAPLES: (479.99, True)})).run_once()
    assert summary.checked == 1
    assert [(f.item_id, f.error) for f in summary.failures] == [(ids["amz"], "crawl failed (status 307): PerimeterX")]
    assert [h.price for h in db.get_price_history(path, ids["amz"])] == [478.0]
    assert "check failed (crawl failed" in summary.render()


async def test_check_health_is_recorded_per_item(setup):
    settings, path, ids = setup
    scraper = FakeScraper(
        {AMZ: "crawl failed (status 307)", STAPLES: (479.99, True)},
        {AMZ: "timeout", STAPLES: (479.99, True)},
        {AMZ: (478.0, True), STAPLES: (479.99, True)},
    )
    m = monitor(settings, scraper)
    await m.run_once()
    await m.run_once()
    amz = db.get_tracked_item(path, ids["amz"])
    assert amz.consecutive_failures == 2 and amz.last_check_error == "timeout"
    assert db.get_tracked_item(path, ids["staples"]).consecutive_failures == 0
    await m.run_once()
    assert db.get_tracked_item(path, ids["amz"]).consecutive_failures == 0


async def test_page_showing_different_product_is_a_failure_not_an_alert(setup):
    settings, path, ids = setup
    notifier = FakeNotifier()
    scraper = FakeScraper({AMZ: (99.0, True, "Sony WH-CH520 Wireless Headphones"), STAPLES: (479.99, True)})
    summary = await monitor(settings, scraper, notifier).run_once()
    assert notifier.sent == []
    assert "different product" in summary.failures[0].error
    assert [h.price for h in db.get_price_history(path, ids["amz"])] == [478.0]


async def test_whole_scrape_run_crashing_is_reported_per_item(setup):
    settings, path, ids = setup

    async def broken(urls):
        raise RuntimeError("browser failed to launch")

    summary = await monitor(settings, broken).run_once()
    assert summary.checked == 0 and len(summary.failures) == 2
    assert "browser failed to launch" in summary.failures[0].error


# --- US-17: template fallback ------------------------------------------------------------


@pytest.mark.parametrize(
    "llm",
    [
        None,  # no API key configured
        FakeAlertLLM(error=TimeoutError("api timeout")),
        FakeAlertLLM(AIMessage("", response_metadata={"stop_reason": "refusal"})),
        FakeAlertLLM(AIMessage("Sony WH-1000XM6 is now only CA$349.00!")),  # invented price
        FakeAlertLLM(AIMessage("")),
    ],
)
async def test_alert_falls_back_to_template(setup, llm):
    settings, path, ids = setup
    notifier = FakeNotifier()
    await monitor(settings, FakeScraper({AMZ: (399.0, True), STAPLES: (479.99, True)}), notifier, llm).run_once()
    body = notifier.sent[0][1]
    assert body.startswith("Sony WH-1000XM6 is now CA$399.00 at Amazon.ca.")
    assert f"Link: {AMZ}" in body


async def test_llm_alert_gets_link_appended_if_missing(setup):
    settings, path, ids = setup
    from shopping_assistant.models import PriceCheck

    item = db.get_tracked_item(path, ids["amz"])
    check = PriceCheck(item=item, price=399.0, in_stock=True, previous_price=478.0, previous_lowest=478.0, reason="target_reached")
    llm = FakeAlertLLM(AIMessage([{"type": "thinking", "thinking": ""}, {"type": "text", "text": "Now CA$399.00 at Amazon.ca."}]))
    body, by_llm = await write_alert(check, llm)
    assert by_llm is True and body == f"Now CA$399.00 at Amazon.ca.\n{AMZ}"


def test_monitor_requires_valid_notifier_config(settings_factory):
    from shopping_assistant.config import ConfigError

    with pytest.raises(ConfigError, match="WEBHOOK_URL"):
        PriceMonitor(settings_factory(notifier="webhook"), scrape=FakeScraper(), alert_llm=None)
