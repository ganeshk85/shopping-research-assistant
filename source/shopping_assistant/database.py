"""Postgres storage: users, tracked items, price history and research threads (v2).

- `Database` owns one connection pool per database URL (shared with the LangGraph
  `PostgresSaver`) and applies the numbered SQL migrations in `migrations/`.
- `UserStore` is the repository for ONE user. Every query is filtered by its
  `user_id`, so callers can't read or change another user's rows (US-26). Price
  history is reached through its item, so it's scoped the same way.

Until sign-in exists (BL-01), callers use the default `admin` user via `open_store(settings)`.
"""

from __future__ import annotations

import atexit
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from typing import Any, Iterator, Optional

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from .config import ConfigError, Settings
from .models import (
    CheckRun,
    CheckTrigger,
    ItemStatus,
    NotificationSettings,
    PriceHistoryEntry,
    TrackedItem,
    WorkerStatus,
)

DEFAULT_USERNAME = "admin"  # the single user until sign-in exists (BL-01)
_MIGRATION_LOCK = 0x5A_5E_A2_C4  # pg_advisory_xact_lock key: one migrator at a time
# PostgresSaver needs autocommit + dict rows + no server-side prepared statements;
# the repository uses explicit transactions on the same connections.
_CONNECTION_KWARGS: dict[str, Any] = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}


class DatabaseError(ConfigError):
    """The database can't be reached or its schema isn't set up. The message says what to do."""


class ThreadAccessError(LookupError):
    """The research thread belongs to another user (treated as 'not found' by callers)."""


def describe_url(url: str) -> str:
    """'user@host:port/dbname' with the password left out, for error messages."""
    try:
        p = conninfo_to_dict(url)
    except psycopg.ProgrammingError:
        return "(unreadable DATABASE_URL)"
    return f"{p.get('user', '?')}@{p.get('host', 'localhost')}:{p.get('port', 5432)}/{p.get('dbname', '?')}"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def load_migrations() -> list[Migration]:
    """All `NNNN_name.sql` files shipped in the package, in version order."""
    out = []
    for entry in resources.files("shopping_assistant.migrations").iterdir():
        m = re.fullmatch(r"(\d{4})_(\w+)\.sql", entry.name)
        if m:
            out.append(Migration(int(m.group(1)), entry.name, entry.read_text(encoding="utf-8")))
    return sorted(out, key=lambda m: m.version)


class Database:
    def __init__(self, url: str, *, max_size: int = 8, timeout: float = 10.0) -> None:
        if not url:
            raise ConfigError("Missing required configuration: DATABASE_URL. Set it in .env.")
        self.url = url
        self.pool = ConnectionPool(
            url, min_size=1, max_size=max_size, kwargs=_CONNECTION_KWARGS, open=False,
            name="shopping_assistant",
        )
        try:
            self.pool.open(wait=True, timeout=timeout)
        except PoolTimeout as exc:
            self.pool.close()
            raise DatabaseError(
                f"Can't connect to the database at {describe_url(url)}. Check that PostgreSQL is "
                "running and that DATABASE_URL in .env has the right login and database name."
            ) from exc

    @property
    def closed(self) -> bool:
        return self.pool.closed

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        """An autocommit connection from the pool; use `conn.transaction()` for multi-statement work."""
        with self.pool.connection() as conn:
            yield conn

    # -- schema --------------------------------------------------------------

    def applied_migrations(self) -> set[int]:
        with self.connection() as conn:
            exists = conn.execute("SELECT to_regclass('schema_migrations') AS t").fetchone()["t"]
            if not exists:
                return set()
            return {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}

    def pending_migrations(self) -> list[Migration]:
        done = self.applied_migrations()
        return [m for m in load_migrations() if m.version not in done]

    def migrate(self) -> list[str]:
        """Apply pending migrations (each in its own transaction) and the checkpoint tables.

        Safe to run repeatedly and from several processes at once. Returns the names applied.
        """
        applied: list[str] = []
        try:
            # A plain connection: migration files hold several statements, which need the
            # simple query protocol (no prepared statements).
            with psycopg.connect(self.url) as conn:
                with conn.transaction():
                    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
                    conn.execute(
                        """CREATE TABLE IF NOT EXISTS schema_migrations (
                               version    INTEGER     PRIMARY KEY,
                               name       TEXT        NOT NULL,
                               applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
                    )
                    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
                    for m in load_migrations():
                        if m.version in done:
                            continue
                        conn.execute(m.sql.encode())  # bytes: no parameter parsing of '%'
                        conn.execute(
                            "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)", (m.version, m.name)
                        )
                        applied.append(m.name)
        except psycopg.OperationalError as exc:
            raise DatabaseError(f"Can't connect to the database at {describe_url(self.url)}: {exc}") from exc

        from langgraph.checkpoint.postgres import PostgresSaver

        PostgresSaver(self.pool).setup()  # LangGraph's own tables; idempotent
        return applied

    # -- users ---------------------------------------------------------------

    def default_user_id(self) -> int:
        try:
            with self.connection() as conn:
                row = conn.execute("SELECT id FROM users WHERE username = %s", (DEFAULT_USERNAME,)).fetchone()
        except psycopg.errors.UndefinedTable:
            row = None
        if row is None:
            raise DatabaseError("The database isn't set up yet. Run: shopping-assistant db migrate")
        return int(row["id"])

    def create_user(self, username: str, display_name: Optional[str] = None) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "INSERT INTO users (username, display_name) VALUES (%s, %s) RETURNING id",
                (username, display_name or username),
            ).fetchone()
        return int(row["id"])

    def for_user(self, user_id: int) -> "UserStore":
        return UserStore(self, user_id)

    def default_store(self) -> "UserStore":
        return self.for_user(self.default_user_id())

    # -- background worker (US-34) -------------------------------------------

    def worker_started(self, name: str, pid: int, interval_hours: int) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO worker_status (name, pid, started_at, heartbeat_at, interval_hours)
                   VALUES (%s, %s, now(), now(), %s)
                   ON CONFLICT (name) DO UPDATE SET pid = EXCLUDED.pid, started_at = now(), heartbeat_at = now(),
                       interval_hours = EXCLUDED.interval_hours, next_run_at = NULL, stopped_at = NULL""",
                (name, pid, interval_hours),
            )

    def worker_heartbeat(self, name: str, next_run_at: Optional[Any]) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE worker_status SET heartbeat_at = now(), next_run_at = %s WHERE name = %s",
                (next_run_at, name),
            )

    def worker_stopped(self, name: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE worker_status SET stopped_at = now(), next_run_at = NULL WHERE name = %s", (name,)
            )

    def get_worker_status(self, name: str) -> Optional[WorkerStatus]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM worker_status WHERE name = %s", (name,)).fetchone()
        return WorkerStatus(**row) if row else None


# One Database (pool) per URL for the whole process: services share it.
_databases: dict[str, Database] = {}
_registry_lock = threading.Lock()


def get_database(url: str) -> Database:
    with _registry_lock:
        database = _databases.get(url)
        if database is None or database.closed:
            database = Database(url)
            _databases[url] = database
        return database


def close_databases() -> None:
    with _registry_lock:
        for database in _databases.values():
            database.close()
        _databases.clear()


atexit.register(close_databases)


def open_store(settings: Settings) -> "UserStore":
    """The repository for the current user: `admin` until sign-in exists (BL-01)."""
    return get_database(settings.database_url).default_store()


class UserStore:
    """Repository scoped to one user. Same operations as the v1 module functions."""

    def __init__(self, database: Database, user_id: int) -> None:
        self.database = database
        self.user_id = user_id

    def _conn(self):
        return self.database.connection()

    # -- tracked items -------------------------------------------------------

    def add_tracked_item(
        self,
        *,
        product_name: str,
        retailer: str,
        url: str,
        initial_price: float,
        target_price: float,
        currency: str = "CAD",
        in_stock: bool = True,
    ) -> int:
        """Insert a tracked item plus its baseline price_history row. Returns the new id."""
        with self._conn() as conn, conn.transaction():
            item_id = conn.execute(
                """INSERT INTO tracked_items
                   (user_id, product_name, retailer, url, currency, initial_price, target_price, lowest_price_seen)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (self.user_id, product_name, retailer, url, currency, initial_price, target_price, initial_price),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO price_history (item_id, price, in_stock) VALUES (%s, %s, %s)",
                (item_id, initial_price, in_stock),
            )
        return int(item_id)

    def import_tracked_item(self, item: dict, history: list[dict]) -> int:
        """Insert an item exactly as given (timestamps, lowest, last notified, health) plus its history.

        Used by the v1 import (US-27). One transaction: an item never arrives without its history.
        """
        with self._conn() as conn, conn.transaction():
            item_id = conn.execute(
                """INSERT INTO tracked_items
                   (user_id, product_name, retailer, url, currency, initial_price, target_price, lowest_price_seen,
                    last_notified_price, status, created_at, last_check_at, last_check_error, consecutive_failures)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (
                    self.user_id, item["product_name"], item["retailer"], item["url"], item["currency"],
                    item["initial_price"], item["target_price"], item["lowest_price_seen"],
                    item["last_notified_price"], item["status"], item["created_at"], item["last_check_at"],
                    item["last_check_error"], item["consecutive_failures"],
                ),
            ).fetchone()["id"]
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO price_history (item_id, price, in_stock, checked_at) VALUES (%s, %s, %s, %s)",
                    [(item_id, h["price"], h["in_stock"], h["checked_at"]) for h in history],
                )
        return int(item_id)

    def find_tracked_item_by_url(self, url: str) -> Optional[TrackedItem]:
        """This user's tracked item for this URL (any status), if one exists."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tracked_items WHERE user_id = %s AND url = %s", (self.user_id, url)
            ).fetchone()
        return TrackedItem(**row) if row else None

    def get_tracked_item(self, item_id: int) -> Optional[TrackedItem]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tracked_items WHERE id = %s AND user_id = %s", (item_id, self.user_id)
            ).fetchone()
        return TrackedItem(**row) if row else None

    def list_tracked_items(self, status: Optional[ItemStatus] = None) -> list[TrackedItem]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tracked_items WHERE user_id = %s AND status = %s ORDER BY id",
                    (self.user_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tracked_items WHERE user_id = %s ORDER BY id", (self.user_id,)
                ).fetchall()
        return [TrackedItem(**r) for r in rows]

    def _update_item(self, sql_set: str, params: tuple, item_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE tracked_items SET {sql_set} WHERE id = %s AND user_id = %s",
                (*params, item_id, self.user_id),
            )
        return cur.rowcount > 0

    def update_status(self, item_id: int, status: ItemStatus) -> bool:
        return self._update_item("status = %s", (status,), item_id)

    def update_target_price(self, item_id: int, target_price: float) -> bool:
        return self._update_item("target_price = %s", (target_price,), item_id)

    def update_last_notified(self, item_id: int, price: float) -> None:
        self._update_item("last_notified_price = %s", (price,), item_id)

    def mark_check_ok(self, item_id: int) -> None:
        """Record a successful monitor check (clears any failure streak)."""
        self._update_item("last_check_at = now(), last_check_error = NULL, consecutive_failures = 0", (), item_id)

    def mark_check_failed(self, item_id: int, error: str) -> None:
        """Record a failed monitor check so repeated failures are visible in the watchlist."""
        self._update_item(
            "last_check_at = now(), last_check_error = %s, consecutive_failures = consecutive_failures + 1",
            (error[:300],), item_id,
        )

    def delete_tracked_item(self, item_id: int) -> bool:
        """Delete an item; its price history goes with it (ON DELETE CASCADE)."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM tracked_items WHERE id = %s AND user_id = %s", (item_id, self.user_id)
            )
        return cur.rowcount > 0

    # -- price history -------------------------------------------------------

    def record_price_check(self, item_id: int, price: float, in_stock: bool) -> float:
        """Log a price check and update lowest_price_seen.

        Returns the *previous* lowest_price_seen (captured before the update),
        which drop evaluation needs to detect a new low (FRD FR-6.6). Only in-stock
        prices can become the new low: a price you couldn't buy at shouldn't block the
        "new low" alert when stock returns.
        """
        with self._conn() as conn, conn.transaction():
            row = conn.execute(
                "SELECT lowest_price_seen FROM tracked_items WHERE id = %s AND user_id = %s FOR UPDATE",
                (item_id, self.user_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"tracked item {item_id} not found")
            previous_lowest = float(row["lowest_price_seen"])
            conn.execute(
                "INSERT INTO price_history (item_id, price, in_stock) VALUES (%s, %s, %s)",
                (item_id, price, in_stock),
            )
            if in_stock and price < previous_lowest:
                conn.execute("UPDATE tracked_items SET lowest_price_seen = %s WHERE id = %s", (price, item_id))
        return previous_lowest

    def latest_price(self, item_id: int) -> Optional[float]:
        """Most recently recorded price for an item (None if it has no history)."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT h.price FROM price_history h JOIN tracked_items t ON t.id = h.item_id
                   WHERE h.item_id = %s AND t.user_id = %s
                   ORDER BY h.checked_at DESC, h.id DESC LIMIT 1""",
                (item_id, self.user_id),
            ).fetchone()
        return float(row["price"]) if row else None

    def get_price_history(self, item_id: int) -> list[PriceHistoryEntry]:
        """Oldest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT h.* FROM price_history h JOIN tracked_items t ON t.id = h.item_id
                   WHERE h.item_id = %s AND t.user_id = %s ORDER BY h.checked_at, h.id""",
                (item_id, self.user_id),
            ).fetchall()
        return [PriceHistoryEntry(**r) for r in rows]

    # -- research threads ----------------------------------------------------

    def check_thread_access(self, thread_id: str) -> None:
        """Raise ThreadAccessError if the thread exists and belongs to someone else.

        A thread ID nobody has used yet is fine: it becomes this user's on the first message.
        """
        with self._conn() as conn:
            row = conn.execute("SELECT user_id FROM research_threads WHERE thread_id = %s", (thread_id,)).fetchone()
        if row is not None and row["user_id"] != self.user_id:
            raise ThreadAccessError(f"conversation {thread_id} not found")

    def upsert_research_thread(self, thread_id: str, title: str, finalized_product: Optional[str] = None) -> None:
        """Create a thread entry, or bump updated_at (and set finalized_product if given)."""
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO research_threads (thread_id, user_id, title, finalized_product)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (thread_id) DO UPDATE SET
                       updated_at = now(),
                       finalized_product = COALESCE(EXCLUDED.finalized_product, research_threads.finalized_product)
                   WHERE research_threads.user_id = EXCLUDED.user_id""",
                (thread_id, self.user_id, title[:80], finalized_product),
            )
        if cur.rowcount == 0:  # the conflict row is another user's: nothing was written
            raise ThreadAccessError(f"conversation {thread_id} not found")

    def get_research_thread(self, thread_id: str) -> Optional[dict]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM research_threads WHERE thread_id = %s AND user_id = %s", (thread_id, self.user_id)
            ).fetchone()

    def list_research_threads(self, limit: int = 20) -> list[dict]:
        """Most recently updated threads first."""
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM research_threads WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s",
                (self.user_id, limit),
            ).fetchall()

    # -- price-check runs (US-32, US-34) -------------------------------------
    # Callers hold the user's check lock (checks.CheckLock) while a run is 'running'.

    def start_check_run(self, trigger: CheckTrigger) -> CheckRun:
        with self._conn() as conn:
            row = conn.execute(
                "INSERT INTO monitor_runs (user_id, trigger) VALUES (%s, %s) RETURNING *", (self.user_id, trigger)
            ).fetchone()
        return CheckRun(**row)

    def finish_check_run(
        self, run_id: int, *, active_items: int, checked: int, failed: int, alerts_sent: int, alerts_failed: int
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE monitor_runs SET status = 'finished', finished_at = now(), active_items = %s,
                       checked = %s, failed = %s, alerts_sent = %s, alerts_failed = %s
                   WHERE id = %s AND user_id = %s""",
                (active_items, checked, failed, alerts_sent, alerts_failed, run_id, self.user_id),
            )

    def fail_check_run(self, run_id: int, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE monitor_runs SET status = 'failed', finished_at = now(), error = %s
                   WHERE id = %s AND user_id = %s""",
                (error[:500], run_id, self.user_id),
            )

    def close_interrupted_check_runs(self) -> int:
        """Mark runs left 'running' by a process that died as failed. Call only while holding the lock."""
        with self._conn() as conn:
            cur = conn.execute(
                """UPDATE monitor_runs SET status = 'failed', finished_at = now(),
                       error = 'Interrupted: the process running this check stopped.'
                   WHERE user_id = %s AND status = 'running'""",
                (self.user_id,),
            )
        return cur.rowcount

    def get_check_run(self, run_id: int) -> Optional[CheckRun]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM monitor_runs WHERE id = %s AND user_id = %s", (run_id, self.user_id)
            ).fetchone()
        return CheckRun(**row) if row else None

    def list_check_runs(self, limit: int = 20, status: Optional[str] = None) -> list[CheckRun]:
        """Newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM monitor_runs WHERE user_id = %s AND (%s::text IS NULL OR status = %s)
                   ORDER BY started_at DESC, id DESC LIMIT %s""",
                (self.user_id, status, status, limit),
            ).fetchall()
        return [CheckRun(**r) for r in rows]

    def last_ended_check_run(self) -> Optional[CheckRun]:
        """The most recent run that finished or failed."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM monitor_runs WHERE user_id = %s AND status <> 'running'
                   ORDER BY finished_at DESC, id DESC LIMIT 1""",
                (self.user_id,),
            ).fetchone()
        return CheckRun(**row) if row else None

    # -- notification settings (US-35) ---------------------------------------

    def get_notification_settings(self) -> Optional[NotificationSettings]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT channel, webhook_url, alert_email, updated_at FROM notification_settings WHERE user_id = %s",
                (self.user_id,),
            ).fetchone()
        return NotificationSettings(**row) if row else None

    def save_notification_settings(self, settings: NotificationSettings) -> NotificationSettings:
        with self._conn() as conn:
            row = conn.execute(
                """INSERT INTO notification_settings (user_id, channel, webhook_url, alert_email)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE SET channel = EXCLUDED.channel,
                       webhook_url = EXCLUDED.webhook_url, alert_email = EXCLUDED.alert_email, updated_at = now()
                   RETURNING channel, webhook_url, alert_email, updated_at""",
                (self.user_id, settings.channel, settings.webhook_url, settings.alert_email),
            ).fetchone()
        return NotificationSettings(**row)

    def delete_notification_settings(self) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM notification_settings WHERE user_id = %s", (self.user_id,))
        return cur.rowcount > 0
