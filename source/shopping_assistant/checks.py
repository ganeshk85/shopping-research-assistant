"""Price-check runs: one at a time per user, each one recorded (US-32, US-34).

The worker, the API and the CLI all start checks through here:

    run_check(store, trigger, make_monitor)        lock, record, run, release (blocking)
    begin_check(store, trigger) -> (lock, run)     lock and record now ...
    complete_check(store, lock, run, check)        ... run later, e.g. in a background thread

The lock is a PostgreSQL session advisory lock on its own connection, so it works across
processes and is released automatically if the process holding it dies. A run left
'running' by a dead process is closed as failed by the next check that gets the lock.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

import psycopg

from .config import ConfigError
from .database import DatabaseError, UserStore, describe_url
from .models import CheckRun, CheckTrigger

if TYPE_CHECKING:
    from .monitor import MonitorSummary, PriceMonitor

log = logging.getLogger(__name__)

# First key of pg_try_advisory_lock(int, int); the second is the user id.
CHECK_LOCK_CLASS = 0x5A5E_C4EC


class CheckAlreadyRunning(RuntimeError):
    """Another price check for this user is in progress (worker, API or CLI)."""

    def __init__(self, running: Optional[CheckRun] = None) -> None:
        super().__init__("A price check is already running. Wait for it to finish, then try again.")
        self.running = running


class CheckLock:
    """A held check lock. Release it exactly once (or use it as a context manager)."""

    def __init__(self, conn: psycopg.Connection, user_id: int) -> None:
        self._conn: Optional[psycopg.Connection] = conn
        self.user_id = user_id

    @classmethod
    def try_acquire(cls, store: UserStore) -> Optional["CheckLock"]:
        """The lock for this user, or None if another check holds it. Never waits."""
        url = store.database.url
        try:
            conn = psycopg.connect(url, autocommit=True)
        except psycopg.OperationalError as exc:
            raise DatabaseError(f"Can't connect to the database at {describe_url(url)}: {exc}") from exc
        try:
            got = conn.execute("SELECT pg_try_advisory_lock(%s, %s)", (CHECK_LOCK_CLASS, store.user_id)).fetchone()[0]
        except BaseException:
            conn.close()
            raise
        if not got:
            conn.close()
            return None
        return cls(conn, store.user_id)

    @property
    def held(self) -> bool:
        return self._conn is not None

    def release(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            conn.execute("SELECT pg_advisory_unlock(%s, %s)", (CHECK_LOCK_CLASS, self.user_id))
        except psycopg.Error:
            log.warning("Couldn't release the check lock cleanly; closing its connection releases it")
        finally:
            conn.close()

    def __enter__(self) -> "CheckLock":
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def begin_check(store: UserStore, trigger: CheckTrigger) -> tuple[CheckLock, CheckRun]:
    """Take the user's check lock and record a 'running' run.

    Raises CheckAlreadyRunning (and logs it) if another check holds the lock.
    """
    lock = CheckLock.try_acquire(store)
    if lock is None:
        running = next(iter(store.list_check_runs(limit=1, status="running")), None)
        log.info("Skipped a %s price check: another check is already running", trigger)
        raise CheckAlreadyRunning(running)
    try:
        interrupted = store.close_interrupted_check_runs()  # safe: nobody else holds the lock
        if interrupted:
            log.warning("Closed %d price check(s) interrupted by a stopped process", interrupted)
        run = store.start_check_run(trigger)
    except BaseException:
        lock.release()
        raise
    return lock, run


def complete_check(
    store: UserStore, lock: CheckLock, run: CheckRun, check: Callable[[], "MonitorSummary"]
) -> tuple[CheckRun, "MonitorSummary"]:
    """Run `check` under the held lock, record the outcome, and always release the lock.

    A failure is recorded on the run and re-raised.
    """
    try:
        summary = check()
    except BaseException as exc:
        store.fail_check_run(run.id, failure_message(exc))
        raise
    else:
        store.finish_check_run(
            run.id,
            active_items=summary.active_items,
            checked=summary.checked,
            failed=len(summary.failures),
            alerts_sent=len(summary.alerts_sent),
            alerts_failed=len(summary.alerts_failed),
        )
    finally:
        lock.release()
    finished = store.get_check_run(run.id)
    assert finished is not None
    return finished, summary


def run_check(
    store: UserStore, trigger: CheckTrigger, make_monitor: Callable[[], "PriceMonitor"]
) -> tuple[CheckRun, "MonitorSummary"]:
    """Lock, record and run one check of the user's active items (blocking).

    The monitor is built after the lock is taken, so a misconfigured notifier is
    recorded as a failed run rather than lost.
    """
    lock, run = begin_check(store, trigger)
    return complete_check(store, lock, run, lambda: make_monitor().run_once_sync())


def failure_message(exc: BaseException) -> str:
    if isinstance(exc, ConfigError):
        return f"Setup needed: {exc}"
    if isinstance(exc, KeyboardInterrupt):
        return "Stopped before it finished."
    return f"{type(exc).__name__}: {exc}"[:500]
