"""Shared services and request dependencies.

`current_store` is the ONLY place that decides who the user is. In v2 there is no
sign-in (BL-01), so it always returns the default admin's store. Adding auth later means
changing this one function; no endpoint takes a user ID from the client (US-33).
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from fastapi import Depends, Request

from ..checks import CheckLock, complete_check
from ..config import Settings
from ..database import Database, UserStore, get_database
from ..models import CheckRun
from ..monitor import PriceMonitor
from ..research import ResearchSession
from ..tools.notifier import Notifier, build_notifier
from .errors import ApiError

log = logging.getLogger(__name__)

SessionFactory = Callable[[UserStore], ResearchSession]
MonitorFactory = Callable[[UserStore], PriceMonitor]


class Services:
    """Process-wide objects the endpoints share (held on `app.state.services`)."""

    def __init__(
        self,
        settings: Settings,
        session_factory: Optional[SessionFactory] = None,
        monitor_factory: Optional[MonitorFactory] = None,
        notifier_factory: Optional[Callable[[Settings], Notifier]] = None,
    ) -> None:
        self.settings = settings
        self._session_factory = session_factory or (lambda store: ResearchSession(settings, store=store))
        self.monitor_factory: MonitorFactory = monitor_factory or (lambda store: PriceMonitor(settings, store=store))
        self.notifier_factory: Callable[[Settings], Notifier] = notifier_factory or build_notifier
        self._sessions: dict[int, ResearchSession] = {}
        self._busy: set[str] = set()
        self._lock = threading.Lock()
        # Checks started from the API run here; the per-user lock already prevents overlap.
        self._checks = ThreadPoolExecutor(max_workers=1, thread_name_prefix="price-check")

    def start_check(self, store: UserStore, lock: CheckLock, run: CheckRun, monitor: PriceMonitor) -> None:
        """Run an already-locked, already-recorded check in the background."""

        def work() -> None:
            try:
                complete_check(store, lock, run, monitor.run_once_sync)
            except Exception:  # recorded on the run by complete_check
                log.exception("Price check #%d failed", run.id)

        self._checks.submit(work)

    def shutdown(self) -> None:
        """Let a check in progress finish (its lock and run row are closed properly)."""
        self._checks.shutdown(wait=True)

    def database(self) -> Database:
        return get_database(self.settings.database_url)

    def research_session(self, store: UserStore) -> ResearchSession:
        """One session per user, created on first use (raises ConfigError if keys are missing)."""
        with self._lock:
            session = self._sessions.get(store.user_id)
            if session is None:
                session = self._session_factory(store)
                self._sessions[store.user_id] = session
            return session

    def claim_thread(self, thread_id: str) -> None:
        """Allow one turn per conversation at a time (a second one would race on its state)."""
        with self._lock:
            if thread_id in self._busy:
                raise ApiError(409, "thread_busy", "The assistant is still working on this conversation.")
            self._busy.add(thread_id)

    def release_thread(self, thread_id: str) -> None:
        with self._lock:
            self._busy.discard(thread_id)


def get_services(request: Request) -> Services:
    return request.app.state.services


def current_store(services: Services = Depends(get_services)) -> UserStore:
    """The signed-in user's repository: the default admin until sign-in exists (BL-01)."""
    return services.database().default_store()


def research_session(
    store: UserStore = Depends(current_store), services: Services = Depends(get_services)
) -> ResearchSession:
    return services.research_session(store)
