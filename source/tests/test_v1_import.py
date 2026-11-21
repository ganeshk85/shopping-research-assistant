"""Importing a v1 SQLite watchlist into Postgres (US-27)."""

import sqlite3
from datetime import datetime, timezone

import pytest

from shopping_assistant.config import ConfigError
from shopping_assistant.v1_import import NOT_IMPORTED_NOTE, import_v1

V1_ITEMS = """CREATE TABLE tracked_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, product_name TEXT NOT NULL, retailer TEXT NOT NULL, url TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CAD', initial_price REAL NOT NULL, target_price REAL NOT NULL,
    lowest_price_seen REAL NOT NULL, last_notified_price REAL, status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL{extra})"""
HEALTH = ", last_check_at TEXT, last_check_error TEXT, consecutive_failures INTEGER NOT NULL DEFAULT 0"
V1_HISTORY = """CREATE TABLE price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, price REAL NOT NULL,
    in_stock INTEGER NOT NULL, checked_at TEXT NOT NULL)"""

AMZ = "https://www.amazon.ca/dp/B0F3PQHWTZ"
STAPLES = "https://www.staples.ca/products/3124721-en-sony-wh1000xm6"


def make_v1(path, *, with_health=True, items=None):
    conn = sqlite3.connect(path)
    conn.execute(V1_ITEMS.format(extra=HEALTH if with_health else ""))
    conn.execute(V1_HISTORY)
    for item, history in items or []:
        cols = ", ".join(item)
        conn.execute(f"INSERT INTO tracked_items ({cols}) VALUES ({', '.join('?' * len(item))})", list(item.values()))
        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.executemany(
            "INSERT INTO price_history (item_id, price, in_stock, checked_at) VALUES (?, ?, ?, ?)",
            [(item_id, *h) for h in history],
        )
    conn.commit()
    conn.close()
    return path


def amazon(**extra):
    return {
        "product_name": "Sony WH-1000XM6", "retailer": "Amazon.ca", "url": AMZ, "currency": "CAD",
        "initial_price": 498.0, "target_price": 430.2, "lowest_price_seen": 449.0, "last_notified_price": 449.0,
        "status": "paused", "created_at": "2026-11-16T14:00:00+00:00", **extra,
    }


HISTORY = [
    (498.0, 1, "2026-11-16T14:00:00+00:00"),
    (449.0, 1, "2026-11-17T20:00:00.123456+00:00"),
    (459.0, 0, "2026-11-18T02:00:00"),  # no offset: taken as UTC
]


def test_imports_items_and_history_preserving_fields(store, tmp_path):
    staples = amazon(url=STAPLES, retailer="Staples Canada", status="active", last_notified_price=None,
                     last_check_at="2026-11-18T02:00:00+00:00", last_check_error="blocked", consecutive_failures=2)
    path = make_v1(tmp_path / "watchlist.db", items=[(amazon(), HISTORY), (staples, [(479.99, 1, "2026-11-16T14:00:01+00:00")])])

    report = import_v1(store, path)
    assert (report.items_imported, report.history_rows, report.already_present) == (2, 4, [])

    item = store.find_tracked_item_by_url(AMZ)
    assert (item.product_name, item.retailer, item.status, item.target_price) == ("Sony WH-1000XM6", "Amazon.ca", "paused", 430.2)
    assert (item.initial_price, item.lowest_price_seen, item.last_notified_price) == (498.0, 449.0, 449.0)
    assert item.created_at == datetime(2026, 11, 16, 14, tzinfo=timezone.utc)
    history = store.get_price_history(item.id)
    assert [(h.price, h.in_stock) for h in history] == [(498.0, True), (449.0, True), (459.0, False)]
    assert history[2].checked_at == datetime(2026, 11, 18, 2, tzinfo=timezone.utc)

    s = store.find_tracked_item_by_url(STAPLES)
    assert (s.last_check_error, s.consecutive_failures, s.last_notified_price) == ("blocked", 2, None)
    assert s.last_check_at == datetime(2026, 11, 18, 2, tzinfo=timezone.utc)


def test_running_twice_creates_no_duplicates(store, tmp_path):
    path = make_v1(tmp_path / "watchlist.db", items=[(amazon(), HISTORY)])
    import_v1(store, path)
    again = import_v1(store, path)
    assert (again.items_imported, again.history_rows, again.already_present) == (0, 0, [AMZ])
    assert len(store.list_tracked_items()) == 1
    assert len(store.get_price_history(store.list_tracked_items()[0].id)) == 3
    assert "Skipped 1 item(s) already on your watchlist." in again.render()


def test_imports_a_pre_sprint5_file_without_health_columns(store, tmp_path):
    path = make_v1(tmp_path / "old.db", with_health=False, items=[(amazon(), HISTORY[:1])])
    assert import_v1(store, path).items_imported == 1
    item = store.find_tracked_item_by_url(AMZ)
    assert item.last_check_at is None and item.consecutive_failures == 0


def test_an_invalid_item_is_skipped_and_reported(store, tmp_path):
    path = make_v1(tmp_path / "watchlist.db", items=[(amazon(target_price=0), []), (amazon(url=STAPLES), [])])
    report = import_v1(store, path)
    assert report.items_imported == 1 and report.invalid[0].startswith(AMZ)
    assert store.find_tracked_item_by_url(AMZ) is None  # nothing half-imported


def test_goes_to_this_users_watchlist_only(store, pg_database, tmp_path):
    other = pg_database.for_user(pg_database.create_user("other"))
    import_v1(store, make_v1(tmp_path / "watchlist.db", items=[(amazon(), HISTORY)]))
    assert other.list_tracked_items() == []


def test_report_says_conversations_are_not_imported(store, tmp_path):
    text = import_v1(store, make_v1(tmp_path / "watchlist.db")).render()
    assert text.startswith("Imported 0 item(s) and 0 price-history row(s)")
    assert NOT_IMPORTED_NOTE in text and "not imported" in NOT_IMPORTED_NOTE


@pytest.mark.parametrize("content", [None, b"not a database", "empty-sqlite"])
def test_missing_or_wrong_file_is_a_clear_error(store, tmp_path, content):
    path = tmp_path / "watchlist.db"
    if content == "empty-sqlite":
        sqlite3.connect(path).close()
    elif content is not None:
        path.write_bytes(content * 100)
    with pytest.raises(ConfigError):
        import_v1(store, path)


def test_cli_import_v1(store, tmp_path, monkeypatch, capsys):
    from shopping_assistant import main

    monkeypatch.setenv("DATABASE_URL", store.database.url)
    path = make_v1(tmp_path / "watchlist.db", items=[(amazon(), HISTORY)])
    assert main.db_command(["import-v1", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Imported 1 item(s) and 3 price-history row(s)" in out and "not imported" in out
    assert main.db_command(["import-v1", str(tmp_path / "missing.db")]) == 1
    assert "No v1 watchlist found" in capsys.readouterr().out
