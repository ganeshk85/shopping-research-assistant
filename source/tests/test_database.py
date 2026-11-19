from pathlib import Path

import pytest

from shopping_assistant import database as db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return db.init_db(tmp_path / "watchlist.db")


def _add(db_path: Path, **overrides) -> int:
    fields = dict(
        product_name="Sony WH-1000XM5",
        retailer="Amazon.ca",
        url="https://www.amazon.ca/dp/B09XS7JWHH",
        initial_price=449.99,
        target_price=404.99,
    )
    fields.update(overrides)
    return db.add_tracked_item(db_path, **fields)


def test_init_creates_tables(db_path: Path) -> None:
    with db.connect(db_path) as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tracked_items", "price_history"} <= names


def test_add_and_get_item(db_path: Path) -> None:
    item_id = _add(db_path)
    item = db.get_tracked_item(db_path, item_id)
    assert item is not None
    assert item.status == "active"
    assert item.currency == "CAD"
    assert item.lowest_price_seen == 449.99
    assert item.last_notified_price is None
    history = db.get_price_history(db_path, item_id)
    assert [h.price for h in history] == [449.99]


def test_list_filters_by_status(db_path: Path) -> None:
    a = _add(db_path)
    b = _add(db_path, retailer="electronics.sony.ca", url="https://electronics.sony.ca/en/product/wh1000xm5")
    assert db.update_status(db_path, b, "paused")
    assert [i.id for i in db.list_tracked_items(db_path, "active")] == [a]
    assert [i.id for i in db.list_tracked_items(db_path, "paused")] == [b]
    assert len(db.list_tracked_items(db_path)) == 2


def test_record_price_check_returns_previous_lowest(db_path: Path) -> None:
    item_id = _add(db_path)
    prev = db.record_price_check(db_path, item_id, 399.99, True)
    assert prev == 449.99
    assert db.get_tracked_item(db_path, item_id).lowest_price_seen == 399.99

    prev = db.record_price_check(db_path, item_id, 420.00, True)
    assert prev == 399.99
    assert db.get_tracked_item(db_path, item_id).lowest_price_seen == 399.99
    assert len(db.get_price_history(db_path, item_id)) == 3


def test_record_price_check_unknown_item(db_path: Path) -> None:
    with pytest.raises(KeyError):
        db.record_price_check(db_path, 999, 10.0, True)


def test_update_target_and_last_notified(db_path: Path) -> None:
    item_id = _add(db_path)
    assert db.update_target_price(db_path, item_id, 380.0)
    db.update_last_notified(db_path, item_id, 399.99)
    item = db.get_tracked_item(db_path, item_id)
    assert item.target_price == 380.0
    assert item.last_notified_price == 399.99


def test_delete_cascades_history(db_path: Path) -> None:
    item_id = _add(db_path)
    db.record_price_check(db_path, item_id, 430.0, True)
    assert db.delete_tracked_item(db_path, item_id)
    assert db.get_tracked_item(db_path, item_id) is None
    assert db.get_price_history(db_path, item_id) == []


def test_out_of_stock_price_is_recorded_but_not_the_low(db_path: Path) -> None:
    item_id = _add(db_path)
    assert db.record_price_check(db_path, item_id, 350.0, False) == 449.99
    assert db.get_tracked_item(db_path, item_id).lowest_price_seen == 449.99
    assert db.latest_price(db_path, item_id) == 350.0


def test_check_health_tracking(db_path: Path) -> None:
    item_id = _add(db_path)
    item = db.get_tracked_item(db_path, item_id)
    assert item.last_check_at is None and item.consecutive_failures == 0
    db.mark_check_failed(db_path, item_id, "blocked")
    db.mark_check_failed(db_path, item_id, "timeout")
    item = db.get_tracked_item(db_path, item_id)
    assert item.consecutive_failures == 2 and item.last_check_error == "timeout" and item.last_check_at
    db.mark_check_ok(db_path, item_id)
    item = db.get_tracked_item(db_path, item_id)
    assert item.consecutive_failures == 0 and item.last_check_error is None


def test_migration_upgrades_a_v0_database(tmp_path: Path) -> None:
    """A watchlist.db created before Sprint 5 (no health columns) upgrades in place, keeping data."""
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE tracked_items (id INTEGER PRIMARY KEY AUTOINCREMENT, product_name TEXT NOT NULL,
            retailer TEXT NOT NULL, url TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'CAD',
            initial_price REAL NOT NULL, target_price REAL NOT NULL, lowest_price_seen REAL NOT NULL,
            last_notified_price REAL, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL);
        INSERT INTO tracked_items (product_name, retailer, url, initial_price, target_price, lowest_price_seen, created_at)
            VALUES ('Old item', 'Amazon.ca', 'https://www.amazon.ca/dp/B000000001', 100, 90, 100, '2026-11-15T00:00:00+00:00');
    """)
    conn.commit()
    conn.close()

    db.init_db(path)
    db.init_db(path)  # idempotent
    item = db.list_tracked_items(path)[0]
    assert item.product_name == "Old item" and item.consecutive_failures == 0 and item.last_check_at is None
    db.mark_check_failed(path, item.id, "x")
    assert db.get_tracked_item(path, item.id).consecutive_failures == 1


def test_invalid_status_rejected(db_path: Path) -> None:
    item_id = _add(db_path)
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        db.update_status(db_path, item_id, "deleted")  # type: ignore[arg-type]
