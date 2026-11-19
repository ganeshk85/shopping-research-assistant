"""Watchlist view and management (US-18, US-19, US-20)."""

from datetime import datetime, timedelta, timezone

import pytest

from shopping_assistant import database as db
from shopping_assistant.watchlist import (
    WatchlistCommand,
    apply_command,
    load_watchlist,
    parse_watchlist_command,
    relative_time,
    render_history,
    render_watchlist,
)

NAME = "Sony WH-1000XM6"


@pytest.fixture
def path(tmp_path):
    p = db.init_db(tmp_path / "watchlist.db")
    db.add_tracked_item(p, product_name=NAME, retailer="Amazon.ca", url="https://www.amazon.ca/dp/B0F3PQHWTZ",
                        initial_price=478.0, target_price=430.2)
    db.add_tracked_item(p, product_name=NAME, retailer="Walmart Canada", url="https://www.walmart.ca/en/ip/x/7FIUKUA6U033",
                        initial_price=478.0, target_price=430.2)
    return p


# --- US-18: view ---------------------------------------------------------------------


def test_render_watchlist_columns_and_fresh_items(path):
    text = render_watchlist(load_watchlist(path))
    header, rule, amz, wal = text.splitlines()[:4]
    for col in ("Product", "Retailer", "Status", "Now", "Lowest", "Target", "Last check"):
        assert col in header
    assert "Sony WH-1000XM6" in amz and "Amazon.ca" in amz and "active" in amz
    assert amz.count("CA$478.00") == 2 and "CA$430.20" in amz
    assert amz.endswith("not yet checked")


def test_render_shows_latest_price_out_of_stock_and_last_check(path):
    db.record_price_check(path, 1, 399.0, False)
    db.mark_check_ok(path, 1)
    text = render_watchlist(load_watchlist(path))
    amz = text.splitlines()[2]
    assert "CA$399.00*" in amz and amz.endswith("just now")
    assert "* out of stock at the last check" in text


def test_last_check_falls_back_to_history_for_pre_upgrade_items(path):
    db.record_price_check(path, 1, 470.0, True)  # recorded without mark_check_ok (old monitor)
    amz = render_watchlist(load_watchlist(path)).splitlines()[2]
    assert amz.endswith("just now")


def test_history_marks_only_first_equal_lowest(path):
    db.record_price_check(path, 1, 399.0, True)
    db.record_price_check(path, 1, 399.0, True)
    text = apply_command(path, WatchlistCommand("history", 1))
    assert text.count("<- lowest") == 1


def test_repeated_failures_are_flagged(path):
    db.mark_check_failed(path, 2, "crawl failed (status 307): PerimeterX block")
    assert "warning" not in render_watchlist(load_watchlist(path))  # one failure: no noise
    db.mark_check_failed(path, 2, "crawl failed (status 307): PerimeterX block")
    text = render_watchlist(load_watchlist(path))
    assert "warning: last 2 checks failed (crawl failed (status 307): PerimeterX block)" in text
    db.mark_check_ok(path, 2)  # a success clears the streak
    assert "warning" not in render_watchlist(load_watchlist(path))


def test_non_cad_item_is_flagged(tmp_path):
    p = db.init_db(tmp_path / "w.db")
    db.add_tracked_item(p, product_name="X1", retailer="shop.example", url="https://shop.example/p/x1",
                        initial_price=100.0, target_price=90.0, currency="USD")
    assert "prices for this item are in USD, not CAD" in render_watchlist(load_watchlist(p))


def test_empty_watchlist(tmp_path):
    assert "watchlist is empty" in render_watchlist(load_watchlist(db.init_db(tmp_path / "w.db")))


@pytest.mark.parametrize(
    "delta, expected",
    [(timedelta(seconds=5), "just now"), (timedelta(minutes=5), "5m ago"), (timedelta(hours=3), "3h ago"), (timedelta(days=2), "2d ago")],
)
def test_relative_time(delta, expected):
    now = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
    assert relative_time(now - delta, now) == expected
    assert relative_time(None) == "never"


# --- US-19: commands ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("p 1", WatchlistCommand("pause", 1)),
        ("pause #2", WatchlistCommand("pause", 2)),
        ("r 1", WatchlistCommand("resume", 1)),
        ("t 1 399.99", WatchlistCommand("target", 1, 399.99)),
        ("t 1 CA$1,049.5", WatchlistCommand("target", 1, 1049.5)),
        ("h 2", WatchlistCommand("history", 2)),
        ("d 2", WatchlistCommand("delete", 2)),
        ("b", WatchlistCommand("back")),
        ("", WatchlistCommand("back")),
        ("?", WatchlistCommand("help")),
        ("l", WatchlistCommand("refresh")),
    ],
)
def test_parse_watchlist_command(text, expected):
    assert parse_watchlist_command(text) == expected


@pytest.mark.parametrize(
    "text, msg",
    [("zap 1", "Unknown command"), ("p", "Which item?"), ("p x", "Which item?"), ("t 1", "new target price"),
     ("t 1 abc", "isn't a price"), ("t 1 0", "above zero")],
)
def test_parse_watchlist_command_errors(text, msg):
    result = parse_watchlist_command(text)
    assert isinstance(result, str) and msg in result


def test_pause_resume_retarget_delete(path):
    assert apply_command(path, WatchlistCommand("pause", 1)).startswith("Paused #1")
    assert db.get_tracked_item(path, 1).status == "paused"
    assert "already paused" in apply_command(path, WatchlistCommand("pause", 1))
    assert apply_command(path, WatchlistCommand("resume", 1)).startswith("Resumed #1")
    assert "already active" in apply_command(path, WatchlistCommand("resume", 1))

    msg = apply_command(path, WatchlistCommand("target", 1, 399.0))
    assert msg == "Target for #1 Sony WH-1000XM6 at Amazon.ca changed from CA$430.20 to CA$399.00."
    assert db.get_tracked_item(path, 1).target_price == 399.0

    db.record_price_check(path, 2, 470.0, True)
    assert "Deleted #2" in apply_command(path, WatchlistCommand("delete", 2))
    assert db.get_tracked_item(path, 2) is None and db.get_price_history(path, 2) == []


def test_unknown_item(path):
    assert apply_command(path, WatchlistCommand("pause", 99)) == "There's no item #99 on your watchlist."


# --- US-20: history ---------------------------------------------------------------------


def test_history_oldest_first_with_in_stock_lowest_marked(path):
    db.record_price_check(path, 1, 350.0, False)  # cheaper but out of stock: not the lowest
    db.record_price_check(path, 1, 399.0, True)
    db.record_price_check(path, 1, 420.0, True)
    text = apply_command(path, WatchlistCommand("history", 1))
    rows = [l for l in text.splitlines() if "CA$" in l and "Target" not in l]
    assert [r.split()[2] for r in rows] == ["CA$478.00", "CA$350.00", "CA$399.00", "CA$420.00"]
    assert rows[2].endswith("<- lowest") and "<- lowest" not in rows[1]
    assert "out of stock" in rows[1]
    assert text.splitlines()[0] == "Price history for #1 Sony WH-1000XM6 at Amazon.ca:"


def test_history_empty():
    from shopping_assistant.models import TrackedItem

    item = TrackedItem(id=1, product_name="X", retailer="R", url="u", initial_price=1, target_price=1,
                       lowest_price_seen=1, created_at=datetime.now(timezone.utc))
    assert "No prices recorded yet." in render_history(item, [])
