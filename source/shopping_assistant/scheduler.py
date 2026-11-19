"""Background price checks (US-09): APScheduler runs PriceMonitor on an interval.

Checks only run while this process is alive (documented v1 limitation, BRD §10).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

JOB_ID = "price-check"


class MonitorScheduler:
    """Run `check` now, then every `interval_seconds`, in a background thread.

    `check` is any zero-argument callable (normally `PriceMonitor.run_once_sync`).
    `on_result` / `on_error` receive each outcome; errors never stop the schedule.
    """

    def __init__(
        self,
        check: Callable[[], object],
        interval_seconds: float,
        *,
        on_result: Optional[Callable[[object], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
        run_immediately: bool = True,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._check = check
        self.interval_seconds = interval_seconds
        self._on_result = on_result
        self._on_error = on_error
        self._run_immediately = run_immediately
        self._scheduler: Optional[BackgroundScheduler] = None
        self._lock = threading.Lock()
        self.runs = 0
        self.errors = 0

    def _job(self) -> None:
        try:
            result = self._check()
        except BaseException as exc:  # keep the schedule alive no matter what
            with self._lock:
                self.errors += 1
            log.exception("Scheduled price check failed")
            if self._on_error:
                self._on_error(exc)
            return
        with self._lock:
            self.runs += 1
        if self._on_result:
            self._on_result(result)

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def start(self) -> None:
        if self.running:
            return
        self._scheduler = BackgroundScheduler(timezone=timezone.utc)
        extra = {}
        if self._run_immediately:
            # Note: passing next_run_time=None would add the job *paused* in APScheduler 3.x,
            # so the argument is only given when running immediately.
            extra["next_run_time"] = datetime.now(timezone.utc)
        self._scheduler.add_job(
            self._job,
            IntervalTrigger(seconds=self.interval_seconds, timezone=timezone.utc),
            id=JOB_ID,
            max_instances=1,  # never overlap two checks
            coalesce=True,  # after a long sleep/suspend, run once instead of catching up
            misfire_grace_time=None,
            **extra,
        )
        self._scheduler.start()

    def next_run_time(self) -> Optional[datetime]:
        if not self.running:
            return None
        job = self._scheduler.get_job(JOB_ID)
        return job.next_run_time if job else None

    def stop(self, wait: bool = True) -> None:
        """Stop scheduling; with wait=True, let a check in progress finish first."""
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
        self._scheduler = None
