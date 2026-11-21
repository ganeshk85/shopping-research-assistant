"""Bring a v1 SQLite watchlist into Postgres (US-27): `shopping-assistant db import-v1 [PATH]`.

Imports every tracked item of `watchlist.db` with its full price history into one user's
watchlist, keeping targets, status, lowest price, last notified price, check health and
timestamps. An item whose URL is already on the watchlist is skipped, so running it twice
creates no duplicates. Old research conversations (`checkpoints.db`) are not imported.

The SQLite file is opened read-only and never changed.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg

from .config import ConfigError
from .database import UserStore

log = logging.getLogger(__name__)

NOT_IMPORTED_NOTE = (
    "Old research conversations (checkpoints.db) are not imported; start new ones in the app."
)


@dataclass
class ImportReport:
    source: Path
    items_imported: int = 0
    history_rows: int = 0
    already_present: list[str] = field(default_factory=list)  # URLs skipped as duplicates
    invalid: list[str] = field(default_factory=list)  # "url: reason"

    def render(self) -> str:
        lines = [
            f"Imported {self.items_imported} item(s) and {self.history_rows} price-history row(s) from {self.source}."
        ]
        if self.already_present:
            lines.append(f"Skipped {len(self.already_present)} item(s) already on your watchlist.")
        for problem in self.invalid:
            lines.append(f"Couldn't import {problem}")
        lines.append(NOT_IMPORTED_NOTE)
        return "\n".join(lines)


def _timestamp(value: Any) -> Optional[datetime]:
    """v1 stored ISO-8601 text in UTC; a value without an offset is taken as UTC."""
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _item(row: sqlite3.Row, columns: set[str]) -> dict:
    def opt(name: str, default: Any = None) -> Any:
        return row[name] if name in columns else default

    return {
        "product_name": row["product_name"],
        "retailer": row["retailer"],
        "url": row["url"],
        "currency": (row["currency"] or "CAD").upper(),
        "initial_price": float(row["initial_price"]),
        "target_price": float(row["target_price"]),
        "lowest_price_seen": float(row["lowest_price_seen"]),
        "last_notified_price": None if row["last_notified_price"] is None else float(row["last_notified_price"]),
        "status": row["status"] or "active",
        "created_at": _timestamp(row["created_at"]) or datetime.now(timezone.utc),
        # Check-health columns were added in Sprint 5; older files don't have them.
        "last_check_at": _timestamp(opt("last_check_at")),
        "last_check_error": opt("last_check_error"),
        "consecutive_failures": int(opt("consecutive_failures", 0) or 0),
    }


def import_v1(store: UserStore, path: Path) -> ImportReport:
    """Import `path` (a v1 watchlist.db) into `store`'s watchlist. Safe to run again."""
    if not path.is_file():
        raise ConfigError(f"No v1 watchlist found at {path}. Pass the path to watchlist.db.")
    report = ImportReport(source=path)
    try:
        src = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ConfigError(f"Can't open {path} as a v1 watchlist: {exc}") from exc
    src.row_factory = sqlite3.Row
    try:
        try:
            columns = {r["name"] for r in src.execute("PRAGMA table_info(tracked_items)")}
            if not columns:
                raise ConfigError(f"{path} isn't a v1 watchlist (it has no tracked_items table).")
            rows = src.execute("SELECT * FROM tracked_items ORDER BY id").fetchall()
        except sqlite3.DatabaseError as exc:
            raise ConfigError(f"Can't read {path} as a v1 watchlist: {exc}") from exc

        for row in rows:
            url = row["url"]
            if store.find_tracked_item_by_url(url) is not None:
                report.already_present.append(url)
                continue
            history = [
                {"price": float(h["price"]), "in_stock": bool(h["in_stock"]), "checked_at": _timestamp(h["checked_at"])}
                for h in src.execute(
                    "SELECT price, in_stock, checked_at FROM price_history WHERE item_id = ? ORDER BY checked_at, id",
                    (row["id"],),
                )
            ]
            try:
                store.import_tracked_item(_item(row, columns), history)
            except (psycopg.errors.IntegrityError, ValueError, TypeError) as exc:
                # e.g. a target of 0, an unknown status, or an unreadable date: skip just this item.
                log.warning("Skipped v1 item %s: %s", url, exc)
                report.invalid.append(f"{url}: {str(exc).splitlines()[0]}")
                continue
            report.items_imported += 1
            report.history_rows += len(history)
    finally:
        src.close()
    return report
