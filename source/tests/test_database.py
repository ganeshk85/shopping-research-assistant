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


def test_invalid_status_rejected(db_path: Path) -> None:
    item_id = _add(db_path)
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        db.update_status(db_path, item_id, "deleted")  # type: ignore[arg-type]
