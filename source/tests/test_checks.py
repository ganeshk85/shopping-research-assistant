"""Price-check runs, the shared lock and the background worker (US-32, US-34)."""

import logging
import time

import pytest

from shopping_assistant.checks import CheckAlreadyRunning, begin_check, complete_check, run_check
from shopping_assistant.config import ConfigError
from shopping_assistant.models import NotificationSettings
from shopping_assistant.monitor import MonitorSummary
from shopping_assistant.worker import WORKER_NAME, PriceCheckWorker


def summary(active=2, checked=2, failed=0, sent=1, retry=0):
    return MonitorSummary(
        active_items=active, checks=[object()] * checked, failures=[object()] * failed,
        alerts_sent=[object()] * sent, alerts_failed=[object()] * retry,
    )


class FakeMonitor:
    def __init__(self, result=None, error=None, delay=0.0):
        self.result, self.error, self.delay, self.calls = result or summary(), error, delay, 0

    def run_once_sync(self):
        self.calls += 1
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out waiting")


# --- runs and the lock ------------------------------------------------------------------


def test_run_check_records_a_finished_run(store):
    run, result = run_check(store, "cli", lambda: FakeMonitor(summary(active=3, checked=2, failed=1, sent=1, retry=1)))
    assert result.active_items == 3
    assert run.status == "finished" and run.trigger == "cli" and run.finished_at is not None
    assert (run.active_items, run.checked, run.failed, run.alerts_sent, run.alerts_failed) == (3, 2, 1, 1, 1)
    assert store.list_check_runs() == [run]
    assert store.last_ended_check_run() == run


def test_second_check_is_refused_and_logged_while_one_runs(store, caplog):
    lock, running = begin_check(store, "schedule")
    try:
        with caplog.at_level(logging.INFO, logger="shopping_assistant.checks"):
            with pytest.raises(CheckAlreadyRunning) as exc:
                begin_check(store, "api")
        assert exc.value.running == running
        assert "already running" in str(exc.value)
        assert "Skipped a api price check" in caplog.text
        assert [r.status for r in store.list_check_runs()] == ["running"]  # the refused one isn't recorded
    finally:
        lock.release()
    run_check(store, "api", FakeMonitor)  # free again once released


def test_failed_check_is_recorded_and_releases_the_lock(store):
    with pytest.raises(ConfigError):
        run_check(store, "schedule", lambda: FakeMonitor(error=ConfigError("Missing required configuration: WEBHOOK_URL.")))
    [failed] = store.list_check_runs()
    assert failed.status == "failed" and failed.error.startswith("Setup needed: Missing required configuration")
    run, _ = run_check(store, "schedule", FakeMonitor)
    assert run.status == "finished"


def test_monitor_built_after_the_lock_so_setup_errors_are_recorded(store):
    def broken():
        raise ConfigError("Missing required configuration: WEBHOOK_URL.")

    with pytest.raises(ConfigError):
        run_check(store, "schedule", broken)
    assert store.list_check_runs()[0].status == "failed"


def test_run_left_running_by_a_dead_process_is_closed_by_the_next_check(store):
    stale = store.start_check_run("schedule")  # as if its process died holding the lock
    run_check(store, "cli", FakeMonitor)
    closed = store.get_check_run(stale.id)
    assert closed.status == "failed" and closed.error.startswith("Interrupted")


def test_lock_released_twice_is_harmless(store):
    lock, run = begin_check(store, "cli")
    complete_check(store, lock, run, FakeMonitor().run_once_sync)
    assert not lock.held
    lock.release()


def test_check_lock_and_runs_are_per_user(store, pg_database):
    other = pg_database.for_user(pg_database.create_user("other"))
    lock, admin_run = begin_check(store, "schedule")
    try:
        other_run, _ = run_check(other, "api", FakeMonitor)  # not blocked by admin's check
    finally:
        lock.release()
    assert other.get_check_run(admin_run.id) is None and store.get_check_run(other_run.id) is None
    assert [r.id for r in store.list_check_runs()] == [admin_run.id]


# --- notification settings repository (US-35) -----------------------------------------------


def test_notification_settings_saved_per_user(store, pg_database):
    other = pg_database.for_user(pg_database.create_user("other"))
    assert store.get_notification_settings() is None
    saved = store.save_notification_settings(NotificationSettings(channel="email", alert_email="me@example.com"))
    assert saved.channel == "email" and saved.updated_at is not None
    store.save_notification_settings(NotificationSettings(channel="console", alert_email="me@example.com"))
    assert store.get_notification_settings().channel == "console"
    assert other.get_notification_settings() is None and not other.delete_notification_settings()
    assert store.delete_notification_settings() and store.get_notification_settings() is None


# --- the worker (US-34) -------------------------------------------------------------------------


def test_worker_checks_at_start_and_reports_its_schedule(settings_factory, store):
    monitor = FakeMonitor()
    results = []
    worker = PriceCheckWorker(
        settings_factory(), store=store, monitor_factory=lambda s: monitor, on_result=results.append
    )
    worker.start()
    try:
        wait_for(lambda: results)
        [run] = store.list_check_runs()
        assert run.trigger == "schedule" and run.status == "finished"
        status = wait_for(lambda: (s := store.database.get_worker_status(WORKER_NAME)) and s.next_run_at and s)
        assert status.interval_hours == 6 and status.stopped_at is None
        assert (status.next_run_at - run.started_at).total_seconds() > 5 * 3600
    finally:
        worker.stop()
    stopped = store.database.get_worker_status(WORKER_NAME)
    assert stopped.stopped_at is not None and stopped.next_run_at is None


def test_worker_skips_a_run_while_another_check_holds_the_lock(settings_factory, store):
    worker = PriceCheckWorker(settings_factory(), store=store, monitor_factory=lambda s: FakeMonitor())
    lock, _ = begin_check(store, "cli")
    try:
        assert worker.run_scheduled_check() is None
    finally:
        lock.release()
    assert worker.run_scheduled_check().status == "finished"


def test_worker_keeps_its_schedule_after_a_failed_run(settings_factory, store):
    monitors = iter([FakeMonitor(error=RuntimeError("browser crashed")), FakeMonitor(), FakeMonitor()])
    worker = PriceCheckWorker(
        settings_factory(), store=store, monitor_factory=lambda s: next(monitors), interval_seconds=0.3
    )
    worker.start()
    try:
        wait_for(lambda: any(r.status == "finished" for r in store.list_check_runs()))
    finally:
        worker.stop()
    runs = list(reversed(store.list_check_runs()))
    assert runs[0].status == "failed" and "browser crashed" in runs[0].error
    assert runs[1].status == "finished"


def test_worker_stop_waits_for_a_check_in_progress(settings_factory, store):
    worker = PriceCheckWorker(settings_factory(), store=store, monitor_factory=lambda s: FakeMonitor(delay=0.5))
    worker.start()
    wait_for(lambda: store.list_check_runs())  # started
    worker.stop()
    assert store.list_check_runs()[0].status == "finished"


def test_worker_picks_up_changed_notification_settings_without_restart(settings_factory, store):
    """A fresh monitor is built per run, reading the saved settings each time."""
    seen = []

    def factory(user_store):
        saved = user_store.get_notification_settings()
        seen.append(saved.channel if saved else "env")
        return FakeMonitor()

    worker = PriceCheckWorker(settings_factory(), store=store, monitor_factory=factory)
    worker.run_scheduled_check()
    store.save_notification_settings(NotificationSettings(channel="webhook", webhook_url="https://example.com/hook"))
    worker.run_scheduled_check()
    assert seen == ["env", "webhook"]
