"""Background price-check worker (US-34): `shopping-assistant worker`.

A separate process that checks prices at start-up and every CHECK_INTERVAL_HOURS, so
alerts arrive without a CLI window open. It:
- runs each check through `checks.run_check` (one check at a time across worker, API
  and CLI; a check that finds the lock taken is skipped and logged);
- builds a fresh PriceMonitor per run, so notification settings saved in the app apply
  to the next check without a restart;
- writes a heartbeat and the next run time to `worker_status` for the API to report;
- on stop, lets a check in progress finish. A failed run never stops the schedule.

Scraping and drop evaluation make no LLM calls (repo rule 1); only alert wording may.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

from .checks import CheckAlreadyRunning, run_check
from .config import Settings
from .database import UserStore, open_store
from .models import CheckRun
from .scheduler import MonitorScheduler

log = logging.getLogger(__name__)

WORKER_NAME = "price-monitor"
HEARTBEAT_SECONDS = 60
# The API treats the worker as stopped if it hasn't heard from it for this long.
STALE_AFTER_SECONDS = 3 * HEARTBEAT_SECONDS

MonitorFactory = Callable[[UserStore], object]  # returns something with run_once_sync()


def _default_monitor_factory(settings: Settings) -> MonitorFactory:
    from .monitor import PriceMonitor

    return lambda store: PriceMonitor(settings, store=store)


class PriceCheckWorker:
    def __init__(
        self,
        settings: Settings,
        *,
        store: Optional[UserStore] = None,
        monitor_factory: Optional[MonitorFactory] = None,
        interval_seconds: Optional[float] = None,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
        on_result: Optional[Callable[[Optional[CheckRun]], None]] = None,
    ) -> None:
        self.settings = settings
        # One user's watchlist until multi-user (BL-02) adds a loop over users.
        self.store = store or open_store(settings)
        self._make_monitor = monitor_factory or _default_monitor_factory(settings)
        self.interval_seconds = interval_seconds or settings.check_interval_hours * 3600
        self._heartbeat_seconds = heartbeat_seconds
        self._on_result = on_result
        self._scheduler = MonitorScheduler(
            self.run_scheduled_check, self.interval_seconds, on_result=self._after_run, on_error=self._after_error
        )
        self._stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    @property
    def database(self):
        return self.store.database

    # -- one run ---------------------------------------------------------------

    def run_scheduled_check(self) -> Optional[CheckRun]:
        """One scheduled check. Returns the recorded run, or None if another check was running."""
        try:
            run, _ = run_check(self.store, "schedule", lambda: self._make_monitor(self.store))
        except CheckAlreadyRunning:
            return None  # begin_check already logged the skip
        log.info(
            "Price check #%d finished: %d of %d checked, %d failed, %d alert(s) sent, %d to retry",
            run.id, run.checked or 0, run.active_items or 0, run.failed or 0, run.alerts_sent or 0,
            run.alerts_failed or 0,
        )
        return run

    def _after_run(self, run: object) -> None:
        self._beat()
        if self._on_result:
            self._on_result(run)  # type: ignore[arg-type]

    def _after_error(self, exc: BaseException) -> None:
        # The failure is already on the run (checks.complete_check); keep the schedule going.
        log.error("Price check failed: %s. Trying again at the next interval.", exc)
        self._beat()

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        hours = self.interval_seconds / 3600
        self.database.worker_started(WORKER_NAME, os.getpid(), max(1, round(hours)))
        self._scheduler.start()
        self._beat()
        self._stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="worker-heartbeat", daemon=True)
        self._heartbeat_thread.start()
        log.info("Worker started: checking now, then every %g hour(s)", hours)

    def stop(self) -> None:
        """Stop scheduling; waits for a check in progress to finish."""
        self._stop.set()
        self._scheduler.stop(wait=True)
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5)
        try:
            self.database.worker_stopped(WORKER_NAME)
        except Exception:  # the database may be the reason we're stopping
            log.warning("Couldn't record the worker stop", exc_info=True)
        log.info("Worker stopped after %d check(s)", self._scheduler.runs)

    @property
    def runs(self) -> int:
        return self._scheduler.runs

    def next_run_time(self):
        return self._scheduler.next_run_time()

    def _beat(self) -> None:
        try:
            self.database.worker_heartbeat(WORKER_NAME, self._scheduler.next_run_time())
        except Exception:
            log.warning("Worker heartbeat failed; retrying in %ss", self._heartbeat_seconds, exc_info=True)

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_seconds):
            self._beat()
