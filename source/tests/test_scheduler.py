"""Background monitor scheduling (US-09). Uses sub-second intervals; no network."""

import threading
import time

import pytest

from shopping_assistant.scheduler import MonitorScheduler


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_runs_immediately_then_repeats_and_stops():
    results = []
    s = MonitorScheduler(lambda: "summary", 0.2, on_result=results.append)
    s.start()
    try:
        assert wait_for(lambda: len(results) >= 3)
        assert s.next_run_time() is not None and s.running
    finally:
        s.stop()
    count = len(results)
    time.sleep(0.5)
    assert len(results) == count  # nothing runs after stop
    assert not s.running and s.next_run_time() is None
    assert results[0] == "summary" and s.runs == count


def test_without_run_immediately_first_check_waits_for_interval():
    calls = []
    s = MonitorScheduler(lambda: calls.append(1), 0.6, run_immediately=False)
    s.start()
    try:
        time.sleep(0.3)
        assert calls == []  # job scheduled (not paused), just not due yet
        assert s.next_run_time() is not None
        assert wait_for(lambda: len(calls) >= 1)
    finally:
        s.stop()


def test_errors_are_reported_and_do_not_stop_the_schedule():
    attempts = []
    errors = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("browser crashed")
        return "ok"

    s = MonitorScheduler(flaky, 0.2, on_error=errors.append)
    s.start()
    try:
        assert wait_for(lambda: len(attempts) >= 3)
    finally:
        s.stop()
    assert [str(e) for e in errors] == ["browser crashed"]
    assert s.errors == 1 and s.runs >= 2


def test_checks_never_overlap():
    active = []
    overlap = threading.Event()
    lock = threading.Lock()

    def slow():
        with lock:
            if active:
                overlap.set()
            active.append(1)
        time.sleep(0.5)  # longer than the interval
        with lock:
            active.pop()

    s = MonitorScheduler(slow, 0.1)
    s.start()
    time.sleep(1.2)
    s.stop()
    assert not overlap.is_set()


def test_stop_waits_for_check_in_progress():
    finished = threading.Event()

    def slow():
        time.sleep(0.4)
        finished.set()

    s = MonitorScheduler(slow, 10)
    s.start()
    time.sleep(0.1)  # check is now running
    s.stop(wait=True)
    assert finished.is_set()


def test_invalid_interval():
    with pytest.raises(ValueError):
        MonitorScheduler(lambda: None, 0)
