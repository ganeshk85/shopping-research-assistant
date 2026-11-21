import os
from dataclasses import replace
from pathlib import Path

import pytest
from dotenv import dotenv_values

from shopping_assistant.config import PROJECT_ROOT, Settings

# Database tests use the local test database (localhost only, never the app DB).
# Everything else stays offline with fakes (repo rule 3).
TEST_DATABASE_URL = (
    os.getenv("TEST_DATABASE_URL") or dotenv_values(PROJECT_ROOT / ".env").get("TEST_DATABASE_URL") or ""
).strip()

# Tables emptied before each database test. Users other than the default admin are removed too.
_APP_TABLES = (
    "tracked_items, price_history, research_threads, monitor_runs, notification_settings, worker_status, "
    "checkpoints, checkpoint_blobs, checkpoint_writes"
)


@pytest.fixture
def settings_factory(tmp_path: Path):
    """Build Settings without reading .env, overriding any fields."""

    base = Settings(
        anthropic_api_key="test-anthropic",
        llm_model="claude-sonnet-5-5",
        tavily_api_key="test-tavily",
        notifier="console",
        webhook_url="",
        resend_api_key="",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        alert_email_from="",
        alert_email_to="",
        data_dir=tmp_path,
        check_interval_hours=6,
        default_target_discount=0.10,
        default_currency="CAD",
        database_url=TEST_DATABASE_URL,
    )

    def make(**overrides) -> Settings:
        return replace(base, **overrides)

    return make


@pytest.fixture(scope="session")
def pg_database():
    """The migrated test database, shared by all tests (skipped if unavailable)."""
    from psycopg.conninfo import conninfo_to_dict

    from shopping_assistant.database import DatabaseError, get_database

    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set in .env; database tests skipped")
    dbname = conninfo_to_dict(TEST_DATABASE_URL).get("dbname", "")
    if not dbname.endswith("_test"):
        # The tests empty tables: never point them at a real database.
        pytest.skip(f"TEST_DATABASE_URL must name a database ending in '_test' (got '{dbname}')")
    try:
        database = get_database(TEST_DATABASE_URL)
        database.migrate()
    except DatabaseError as exc:
        pytest.skip(f"Test database unavailable, database tests skipped: {exc}")
    return database


@pytest.fixture
def store(pg_database):
    """An empty database and the default admin's repository."""
    from shopping_assistant.database import DEFAULT_USERNAME

    with pg_database.connection() as conn:
        conn.execute(f"TRUNCATE {_APP_TABLES} RESTART IDENTITY CASCADE")
        conn.execute("DELETE FROM users WHERE username <> %s", (DEFAULT_USERNAME,))
    return pg_database.default_store()
