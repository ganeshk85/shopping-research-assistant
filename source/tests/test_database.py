"""Postgres repository (US-24, US-26, US-28). Runs against the local test database."""

import psycopg
import pytest

from shopping_assistant.config import ConfigError
from shopping_assistant.database import (
    Database,
    DatabaseError,
    ThreadAccessError,
    UserStore,
    describe_url,
    load_migrations,
)


def _add(store: UserStore, **overrides) -> int:
    fields = dict(
        product_name="Sony WH-1000XM5",
        retailer="Amazon.ca",
        url="https://www.amazon.ca/dp/B09XS7JWHH",
        initial_price=449.99,
        target_price=404.99,
    )
    fields.update(overrides)
    return store.add_tracked_item(**fields)


# --- schema and migrations (US-24, US-28) ------------------------------------------


def test_migrations_create_tables_and_are_idempotent(pg_database: Database, store) -> None:
    assert pg_database.migrate() == []  # already applied by the fixture: nothing to do
    assert pg_database.pending_migrations() == []
    assert pg_database.applied_migrations() == {m.version for m in load_migrations()}
    with pg_database.connection() as conn:
        names = {r["tablename"] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert {"users", "tracked_items", "price_history", "research_threads", "schema_migrations", "checkpoints"} <= names


def test_migration_files_are_numbered_in_order() -> None:
    versions = [m.version for m in load_migrations()]
    assert versions and versions == sorted(set(versions)) and versions[0] == 1


def test_default_user_is_admin(pg_database: Database, store) -> None:
    assert store.user_id == pg_database.default_user_id()
    with pg_database.connection() as conn:
        users = conn.execute("SELECT username, display_name FROM users").fetchall()
    assert users == [{"username": "admin", "display_name": "Admin"}]  # 'owner' renamed by 0002


def test_unreachable_database_gives_a_clear_error() -> None:
    # Port 1 on localhost: refused immediately, no network involved.
    with pytest.raises(DatabaseError, match="Can't connect to the database at app@localhost:1/nowhere") as exc:
        Database("postgresql://app:secret@localhost:1/nowhere", timeout=1)
    assert "secret" not in str(exc.value)  # never echo the password
    assert "DATABASE_URL" in str(exc.value)


def test_missing_database_url() -> None:
    with pytest.raises(ConfigError, match="DATABASE_URL"):
        Database("")


def test_describe_url_hides_password() -> None:
    assert describe_url("postgresql://u:p4ss@db.local:5433/app") == "u@db.local:5433/app"


# --- tracked items and history (v1 behaviour on Postgres) --------------------------


def test_add_and_get_item(store) -> None:
    item_id = _add(store)
    item = store.get_tracked_item(item_id)
    assert item is not None
    assert item.status == "active"
    assert item.currency == "CAD"
    assert item.lowest_price_seen == 449.99
    assert item.last_notified_price is None
    assert item.created_at.tzinfo is not None
    history = store.get_price_history(item_id)
    assert [(h.price, h.in_stock) for h in history] == [(449.99, True)]


def test_list_filters_by_status(store) -> None:
    a = _add(store)
    b = _add(store, retailer="electronics.sony.ca", url="https://electronics.sony.ca/en/product/wh1000xm5")
    assert store.update_status(b, "paused")
    assert [i.id for i in store.list_tracked_items("active")] == [a]
    assert [i.id for i in store.list_tracked_items("paused")] == [b]
    assert len(store.list_tracked_items()) == 2


def test_record_price_check_returns_previous_lowest(store) -> None:
    item_id = _add(store)
    prev = store.record_price_check(item_id, 399.99, True)
    assert prev == 449.99
    assert store.get_tracked_item(item_id).lowest_price_seen == 399.99

    prev = store.record_price_check(item_id, 420.00, True)
    assert prev == 399.99
    assert store.get_tracked_item(item_id).lowest_price_seen == 399.99
    assert len(store.get_price_history(item_id)) == 3
    assert store.latest_price(item_id) == 420.00


def test_record_price_check_unknown_item(store) -> None:
    with pytest.raises(KeyError):
        store.record_price_check(999, 10.0, True)


def test_update_target_and_last_notified(store) -> None:
    item_id = _add(store)
    assert store.update_target_price(item_id, 380.0)
    store.update_last_notified(item_id, 399.99)
    item = store.get_tracked_item(item_id)
    assert item.target_price == 380.0
    assert item.last_notified_price == 399.99


def test_delete_cascades_history(store) -> None:
    item_id = _add(store)
    store.record_price_check(item_id, 430.0, True)
    assert store.delete_tracked_item(item_id)
    assert store.get_tracked_item(item_id) is None
    assert store.get_price_history(item_id) == []
    with store.database.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM price_history").fetchone()["n"] == 0


def test_out_of_stock_price_is_recorded_but_not_the_low(store) -> None:
    item_id = _add(store)
    assert store.record_price_check(item_id, 350.0, False) == 449.99
    assert store.get_tracked_item(item_id).lowest_price_seen == 449.99
    assert store.latest_price(item_id) == 350.0


def test_check_health_tracking(store) -> None:
    item_id = _add(store)
    item = store.get_tracked_item(item_id)
    assert item.last_check_at is None and item.consecutive_failures == 0
    store.mark_check_failed(item_id, "blocked")
    store.mark_check_failed(item_id, "timeout")
    item = store.get_tracked_item(item_id)
    assert item.consecutive_failures == 2 and item.last_check_error == "timeout" and item.last_check_at
    store.mark_check_ok(item_id)
    item = store.get_tracked_item(item_id)
    assert item.consecutive_failures == 0 and item.last_check_error is None


def test_invalid_status_rejected(store) -> None:
    item_id = _add(store)
    with pytest.raises(psycopg.errors.CheckViolation):
        store.update_status(item_id, "deleted")  # type: ignore[arg-type]


def test_same_url_twice_for_one_user_is_rejected(store) -> None:
    _add(store)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _add(store, target_price=300.0)
    assert store.find_tracked_item_by_url("https://www.amazon.ca/dp/B09XS7JWHH") is not None


# --- research threads -------------------------------------------------------------


def test_threads_are_listed_newest_first_and_keep_the_finalized_product(store) -> None:
    store.upsert_research_thread("t1", "headphones")
    store.upsert_research_thread("t2", "monitors")
    store.upsert_research_thread("t1", title="", finalized_product="Sony WH-1000XM6")
    store.upsert_research_thread("t1", title="ignored on update")
    threads = store.list_research_threads()
    assert [t["thread_id"] for t in threads] == ["t1", "t2"]
    assert threads[0]["title"] == "headphones" and threads[0]["finalized_product"] == "Sony WH-1000XM6"
    assert store.get_research_thread("t2")["title"] == "monitors"


# --- isolation between users (US-26) -------------------------------------------------


@pytest.fixture
def alice(pg_database: Database, store) -> UserStore:
    return pg_database.for_user(pg_database.create_user("alice"))


def test_users_never_see_or_change_each_others_items(store, alice) -> None:
    mine = _add(store)
    theirs = _add(alice, retailer="Staples Canada", url="https://www.staples.ca/products/1-en-sony")

    assert [i.id for i in store.list_tracked_items()] == [mine]
    assert [i.id for i in alice.list_tracked_items()] == [theirs]
    assert alice.get_tracked_item(mine) is None
    assert alice.find_tracked_item_by_url("https://www.amazon.ca/dp/B09XS7JWHH") is None
    assert alice.get_price_history(mine) == [] and alice.latest_price(mine) is None

    # Every write through the other user's store is a no-op (or "not found").
    assert not alice.update_status(mine, "paused")
    assert not alice.update_target_price(mine, 1.0)
    assert not alice.delete_tracked_item(mine)
    alice.update_last_notified(mine, 1.0)
    alice.mark_check_failed(mine, "x")
    alice.mark_check_ok(mine)
    with pytest.raises(KeyError):
        alice.record_price_check(mine, 1.0, True)

    item = store.get_tracked_item(mine)
    assert (item.status, item.target_price, item.last_notified_price, item.last_check_at) == ("active", 404.99, None, None)
    assert len(store.get_price_history(mine)) == 1


def test_each_user_can_track_the_same_url(store, alice) -> None:
    _add(store)
    _add(alice)
    assert len(store.list_tracked_items()) == 1 and len(alice.list_tracked_items()) == 1


def test_users_never_see_or_take_over_each_others_threads(store, alice) -> None:
    store.upsert_research_thread("shared-id", "my headphones")
    assert alice.list_research_threads() == []
    assert alice.get_research_thread("shared-id") is None
    with pytest.raises(ThreadAccessError):
        alice.check_thread_access("shared-id")
    with pytest.raises(ThreadAccessError):
        alice.upsert_research_thread("shared-id", "hijack", finalized_product="X")
    store.check_thread_access("shared-id")
    alice.check_thread_access("never-used")  # an unused ID is free to start
    thread = store.get_research_thread("shared-id")
    assert thread["title"] == "my headphones" and thread["finalized_product"] is None
