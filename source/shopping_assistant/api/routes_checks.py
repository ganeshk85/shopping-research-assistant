"""Price checks over HTTP (US-32): start one, follow it, see the schedule.

A check runs in the background: POST returns 202 with the run at once, then the client
polls GET /checks/{id} (or /checks/status) until it is 'finished' or 'failed'.
Only one check runs at a time per user, whoever started it (worker, API or CLI).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from ..checks import CheckAlreadyRunning, begin_check
from ..database import UserStore
from ..models import CheckRun
from ..worker import STALE_AFTER_SECONDS, WORKER_NAME
from .deps import Services, current_store, get_services
from .errors import ApiError, not_found
from .schemas import CheckStatus, ErrorBody, ScheduleStatus

router = APIRouter(prefix="/checks", tags=["checks"])


@router.post(
    "",
    status_code=202,
    response_model=CheckRun,
    summary="Start a price check of every active item",
    responses={409: {"model": ErrorBody, "description": "A check is already running"},
               503: {"model": ErrorBody, "description": "Alerts or the database aren't set up"}},
)
def start_check(store: UserStore = Depends(current_store), services: Services = Depends(get_services)) -> CheckRun:
    """Returns at once with the new run (status 'running'). Alerts use the saved notification settings."""
    monitor = services.monitor_factory(store)  # ConfigError -> 503 before anything is recorded
    try:
        lock, run = begin_check(store, "api")
    except CheckAlreadyRunning as exc:
        details = {"running_check_id": exc.running.id} if exc.running else None
        raise ApiError(409, "check_running", str(exc), details) from exc
    services.start_check(store, lock, run, monitor)
    return run


@router.get("", response_model=list[CheckRun], summary="Recent price checks, newest first")
def list_checks(
    limit: int = Query(default=20, ge=1, le=100), store: UserStore = Depends(current_store)
) -> list[CheckRun]:
    return store.list_check_runs(limit=limit)


@router.get("/status", response_model=CheckStatus, summary="Running check, last check and next scheduled check")
def check_status(store: UserStore = Depends(current_store)) -> CheckStatus:
    running = next(iter(store.list_check_runs(limit=1, status="running")), None)
    return CheckStatus(running=running, last_finished=store.last_ended_check_run(), schedule=_schedule(store))


def _schedule(store: UserStore) -> ScheduleStatus:
    worker = store.database.get_worker_status(WORKER_NAME)
    if worker is None:
        return ScheduleStatus(worker_running=False)
    fresh = datetime.now(timezone.utc) - worker.heartbeat_at < timedelta(seconds=STALE_AFTER_SECONDS)
    running = worker.stopped_at is None and fresh
    return ScheduleStatus(
        worker_running=running,
        interval_hours=worker.interval_hours,
        next_run_at=worker.next_run_at if running else None,
        last_heartbeat_at=worker.heartbeat_at,
    )


@router.get(
    "/{check_id}", response_model=CheckRun, summary="One price check", responses={404: {"model": ErrorBody}}
)
def get_check(check_id: int, store: UserStore = Depends(current_store)) -> CheckRun:
    run = store.get_check_run(check_id)
    if run is None:
        raise not_found("Price check")
    return run
