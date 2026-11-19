"""SQLite watchlist storage: tracked items and price history."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .models import ItemStatus, PriceHistoryEntry, TrackedItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracked_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name        TEXT    NOT NULL,
    retailer            TEXT    NOT NULL,
    url                 TEXT    NOT NULL,
    currency            TEXT    NOT NULL DEFAULT 'CAD',
    initial_price       REAL    NOT NULL,
    target_price        REAL    NOT NULL,
    lowest_price_seen   REAL    NOT NULL,
    last_notified_price REAL,
    status              TEXT    NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'paused')),
    created_at          TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES tracked_items(id) ON DELETE CASCADE,
    price       REAL    NOT NULL,
    in_stock    INTEGER NOT NULL,
    checked_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_price_history_item ON price_history(item_id, checked_at);

-- Registry of research conversations (US-03). Message history itself lives in
-- the LangGraph checkpoint DB; this table only lists threads for the CLI.
CREATE TABLE IF NOT EXISTS research_threads (
    thread_id         TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    finalized_product TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> Path:
    """Create the database file and tables if needed. Returns the DB path."""
    if db_path is None:
        from .config import load_settings

        db_path = load_settings().watchlist_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
    return db_path


def _row_to_item(row: sqlite3.Row) -> TrackedItem:
    return TrackedItem(**dict(row))


def add_tracked_item(
    db_path: Path,
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
    now = _now()
    with connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO tracked_items
               (product_name, retailer, url, currency, initial_price, target_price,
                lowest_price_seen, last_notified_price, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'active', ?)""",
            (product_name, retailer, url, currency, initial_price, target_price, initial_price, now),
        )
        item_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO price_history (item_id, price, in_stock, checked_at) VALUES (?, ?, ?, ?)",
            (item_id, initial_price, int(in_stock), now),
        )
    return item_id


def find_tracked_item_by_url(db_path: Path, url: str) -> Optional[TrackedItem]:
    """The tracked item for this URL (any status), if one exists."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM tracked_items WHERE url = ? ORDER BY id DESC LIMIT 1", (url,)
        ).fetchone()
    return _row_to_item(row) if row else None


def get_tracked_item(db_path: Path, item_id: int) -> Optional[TrackedItem]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tracked_items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def list_tracked_items(db_path: Path, status: Optional[ItemStatus] = None) -> list[TrackedItem]:
    with connect(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tracked_items WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tracked_items ORDER BY id").fetchall()
    return [_row_to_item(r) for r in rows]


def update_status(db_path: Path, item_id: int, status: ItemStatus) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute("UPDATE tracked_items SET status = ? WHERE id = ?", (status, item_id))
    return cur.rowcount > 0


def update_target_price(db_path: Path, item_id: int, target_price: float) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE tracked_items SET target_price = ? WHERE id = ?", (target_price, item_id)
        )
    return cur.rowcount > 0


def delete_tracked_item(db_path: Path, item_id: int) -> bool:
    with connect(db_path) as conn:
        cur = conn.execute("DELETE FROM tracked_items WHERE id = ?", (item_id,))
    return cur.rowcount > 0


def record_price_check(
    db_path: Path, item_id: int, price: float, in_stock: bool
) -> float:
    """Log a price check and update lowest_price_seen.

    Returns the *previous* lowest_price_seen (captured before the update),
    which drop evaluation needs to detect a new low (FRD FR-6.6).
    """
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT lowest_price_seen FROM tracked_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"tracked item {item_id} not found")
        previous_lowest = float(row["lowest_price_seen"])
        conn.execute(
            "INSERT INTO price_history (item_id, price, in_stock, checked_at) VALUES (?, ?, ?, ?)",
            (item_id, price, int(in_stock), _now()),
        )
        if price < previous_lowest:
            conn.execute(
                "UPDATE tracked_items SET lowest_price_seen = ? WHERE id = ?", (price, item_id)
            )
    return previous_lowest


def update_last_notified(db_path: Path, item_id: int, price: float) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE tracked_items SET last_notified_price = ? WHERE id = ?", (price, item_id)
        )


def upsert_research_thread(
    db_path: Path, thread_id: str, title: str, finalized_product: Optional[str] = None
) -> None:
    """Create a thread entry, or bump updated_at (and set finalized_product if given)."""
    now = _now()
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO research_threads (thread_id, title, finalized_product, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(thread_id) DO UPDATE SET
                   updated_at = excluded.updated_at,
                   finalized_product = COALESCE(excluded.finalized_product, research_threads.finalized_product)""",
            (thread_id, title[:80], finalized_product, now, now),
        )


def list_research_threads(db_path: Path, limit: int = 20) -> list[dict]:
    """Most recently updated threads first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM research_threads ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_price_history(db_path: Path, item_id: int) -> list[PriceHistoryEntry]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM price_history WHERE item_id = ? ORDER BY checked_at, id", (item_id,)
        ).fetchall()
    return [PriceHistoryEntry(**{**dict(r), "in_stock": bool(r["in_stock"])}) for r in rows]
