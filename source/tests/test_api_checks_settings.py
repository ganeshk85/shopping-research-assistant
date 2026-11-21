"""HTTP API, Sprint 8: price checks (US-32) and notification settings (US-35).
TestClient + fakes; data goes to the local test database."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from shopping_assistant.api.app import create_app
from shopping_assistant.api.routes_settings import mask_url, redact_url
from shopping_assistant.checks import begin_check
from shopping_assistant.config import ConfigError
from shopping_assistant.models import NotificationSettings
from shopping_assistant.monitor import PriceMonitor
from shopping_assistant.tools.notifier import NotificationError, build_notifier
from shopping_assistant.worker import WORKER_NAME

from test_monitor_graph import AMZ, NAME, STAPLES, FakeNotifier, FakeScraper

V1 = "/api/v1"
DISCORD = "https://discord.com/api/webhooks/123456/SECRET-TOKEN-abcd"


@pytest.fixture
def make_client(settings_factory, store):
    """A client whose price checks use a fake scraper and notifier."""

    def make(*scrapes, settings=None, monitor_factory=None, notifier=None, monitor_notifier=None):
        settings = settings or settings_factory()
        scraper = FakeScraper(*scrapes)

        def monitors(user_store):
            return PriceMonitor(settings, store=user_store, scrape=scraper,
                                notifier=monitor_notifier or FakeNotifier(), alert_llm=None)

        def notifiers(effective):
            build_notifier(effective)  # same validation as the real thing (ConfigError)
            return notifier or FakeNotifier()

        client = TestClient(create_app(settings, monitor_factory=monitor_factory or monitors,
                                       notifier_factory=notifiers))
        client.scraper = scraper
        return client

    return make


def wait_until_done(client, check_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"{V1}/checks/{check_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("check did not finish")


# --- US-32: price checks -----------------------------------------------------------------------


def test_start_check_returns_at_once_then_reports_the_summary(make_client, store):
    store.add_tracked_item(product_name=NAME, retailer="Amazon.ca", url=AMZ, initial_price=478.0, target_price=430.2)
    store.add_tracked_item(product_name=NAME, retailer="Staples Canada", url=STAPLES, initial_price=479.99, target_price=430.2)
    sent = FakeNotifier()
    client = make_client({AMZ: (399.0, True), STAPLES: "blocked"}, monitor_notifier=sent)

    r = client.post(f"{V1}/checks")
    assert r.status_code == 202
    started = r.json()
    assert started["status"] == "running" and started["trigger"] == "api" and started["checked"] is None

    run = wait_until_done(client, started["id"])
    assert run["status"] == "finished"
    assert (run["active_items"], run["checked"], run["failed"], run["alerts_sent"], run["alerts_failed"]) == (2, 1, 1, 1, 0)
    assert len(sent.sent) == 1

    assert [c["id"] for c in client.get(f"{V1}/checks").json()] == [started["id"]]
    status = client.get(f"{V1}/checks/status").json()
    assert status["running"] is None and status["last_finished"]["id"] == started["id"]


def test_start_check_refused_while_another_check_runs(make_client, store):
    client = make_client()
    lock, running = begin_check(store, "schedule")  # e.g. the worker
    try:
        r = client.post(f"{V1}/checks")
        assert r.status_code == 409
        assert r.json()["code"] == "check_running" and r.json()["details"] == {"running_check_id": running.id}
        status = client.get(f"{V1}/checks/status").json()
        assert status["running"]["id"] == running.id and status["running"]["trigger"] == "schedule"
    finally:
        lock.release()
    assert len(store.list_check_runs()) == 1


def test_start_check_with_broken_alert_setup_is_503_and_not_recorded(make_client, store):
    def broken(_):
        raise ConfigError("Missing required configuration: WEBHOOK_URL. Set it in .env.")

    r = make_client(monitor_factory=broken).post(f"{V1}/checks")
    assert r.status_code == 503 and r.json()["code"] == "not_configured"
    assert store.list_check_runs() == []


def test_unknown_or_other_users_check_is_404(make_client, store, pg_database):
    other = pg_database.for_user(pg_database.create_user("other"))
    other_run = other.start_check_run("api")
    client = make_client()
    for check_id in (other_run.id, 99999):
        r = client.get(f"{V1}/checks/{check_id}")
        assert r.status_code == 404 and r.json()["code"] == "not_found"
    assert client.get(f"{V1}/checks").json() == []
    assert client.get(f"{V1}/checks/status").json()["running"] is None


def test_status_reports_the_worker_schedule(make_client, store):
    client = make_client()
    assert client.get(f"{V1}/checks/status").json()["schedule"] == {
        "worker_running": False, "interval_hours": None, "next_run_at": None, "last_heartbeat_at": None,
    }
    db = store.database
    next_run = datetime.now(timezone.utc) + timedelta(hours=6)
    db.worker_started(WORKER_NAME, 4242, 6)
    db.worker_heartbeat(WORKER_NAME, next_run)
    schedule = client.get(f"{V1}/checks/status").json()["schedule"]
    assert schedule["worker_running"] is True and schedule["interval_hours"] == 6
    assert datetime.fromisoformat(schedule["next_run_at"]) == next_run

    with db.connection() as conn:  # a worker that died without saying so
        conn.execute("UPDATE worker_status SET heartbeat_at = now() - interval '10 minutes'")
    schedule = client.get(f"{V1}/checks/status").json()["schedule"]
    assert schedule["worker_running"] is False and schedule["next_run_at"] is None

    db.worker_heartbeat(WORKER_NAME, next_run)
    db.worker_stopped(WORKER_NAME)
    assert client.get(f"{V1}/checks/status").json()["schedule"]["worker_running"] is False


# --- US-35: notification settings ---------------------------------------------------------------


def test_settings_default_to_env_without_exposing_secrets(make_client, settings_factory):
    settings = settings_factory(
        notifier="email", alert_email_from="alerts@example.com", alert_email_to="me@example.com",
        resend_api_key="re_SERVER_SECRET", smtp_password="SMTP_SECRET",
    )
    r = make_client(settings=settings).get(f"{V1}/settings/notifications")
    assert r.json() == {
        "channel": "email", "source": "env", "webhook_url_hint": None, "alert_email": "me@example.com",
        "email_available": True, "updated_at": None,
    }
    assert "SECRET" not in r.text and "test-anthropic" not in r.text and "test-tavily" not in r.text


def test_save_webhook_returns_it_masked_and_keeps_it_when_omitted(make_client, store):
    client = make_client()
    r = client.put(f"{V1}/settings/notifications", json={"channel": "webhook", "webhook_url": DISCORD})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["channel"] == "webhook" and body["source"] == "saved"
    assert body["webhook_url_hint"] == "https://discord.com/…abcd" and "SECRET-TOKEN" not in r.text
    assert store.get_notification_settings().webhook_url == DISCORD

    # Switching channel and back without resending the URL keeps it.
    client.put(f"{V1}/settings/notifications", json={"channel": "console"})
    r = client.put(f"{V1}/settings/notifications", json={"channel": "webhook"})
    assert r.status_code == 200 and r.json()["webhook_url_hint"] == "https://discord.com/…abcd"
    assert "SECRET-TOKEN" not in client.get(f"{V1}/settings/notifications").text


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"channel": "webhook"}, "Enter a webhook URL"),
        ({"channel": "webhook", "webhook_url": "https://api.telegram.org/bot1:abc/sendMessage"}, "chat_id"),
        ({"channel": "email", "alert_email": "me@example.com"}, "Email isn't set up on the server"),
        ({"channel": "email"}, "Enter the email address"),
    ],
)
def test_invalid_settings_are_rejected_and_not_saved(make_client, store, payload, message):
    r = make_client().put(f"{V1}/settings/notifications", json=payload)
    assert r.status_code == 422 and r.json()["code"] == "invalid_settings"
    assert message in r.json()["message"]
    assert store.get_notification_settings() is None


@pytest.mark.parametrize(
    "payload",
    [
        {"channel": "sms"},
        {"channel": "webhook", "webhook_url": "ftp://example.com/hook"},
        {"channel": "email", "alert_email": "not-an-email"},
    ],
)
def test_malformed_settings_are_validation_errors(make_client, payload):
    r = make_client().put(f"{V1}/settings/notifications", json=payload)
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


def test_email_saved_when_the_server_can_send_email(make_client, settings_factory):
    settings = settings_factory(alert_email_from="alerts@example.com", resend_api_key="re_x")
    client = make_client(settings=settings)
    r = client.put(f"{V1}/settings/notifications", json={"channel": "email", "alert_email": " me@example.com "})
    assert r.status_code == 200 and r.json()["alert_email"] == "me@example.com"


def test_reset_settings_falls_back_to_env(make_client, store):
    client = make_client()
    client.put(f"{V1}/settings/notifications", json={"channel": "webhook", "webhook_url": DISCORD})
    assert client.delete(f"{V1}/settings/notifications").status_code == 204
    body = client.get(f"{V1}/settings/notifications").json()
    assert body["source"] == "env" and body["channel"] == "console"


def test_test_alert_goes_through_the_saved_channel(make_client):
    notifier = FakeNotifier()
    client = make_client(notifier=notifier)
    client.put(f"{V1}/settings/notifications", json={"channel": "webhook", "webhook_url": DISCORD})
    r = client.post(f"{V1}/settings/notifications/test")
    assert r.status_code == 200 and r.json() == {"channel": "webhook", "message": "Test alert sent to your webhook."}
    assert notifier.sent and notifier.sent[0][0].startswith("Test alert")


def test_failed_test_alert_returns_the_error_without_the_token(make_client):
    class Failing:
        def send(self, subject, body):
            raise NotificationError(f"discord webhook failed: Client error '404 Not Found' for url '{DISCORD}'")

    client = make_client(notifier=Failing())
    client.put(f"{V1}/settings/notifications", json={"channel": "webhook", "webhook_url": DISCORD})
    r = client.post(f"{V1}/settings/notifications/test")
    assert r.status_code == 502 and r.json()["code"] == "notification_failed"
    assert "404 Not Found" in r.json()["message"] and "SECRET-TOKEN" not in r.text


def test_test_alert_with_broken_env_setup_is_503(make_client, settings_factory):
    r = make_client(settings=settings_factory(notifier="webhook")).post(f"{V1}/settings/notifications/test")
    assert r.status_code == 503 and "WEBHOOK_URL" in r.json()["message"]


def test_redact_url_hides_telegram_token():
    url = "https://api.telegram.org/bot123:SECRET/sendMessage?chat_id=42"
    message = "telegram webhook failed: 401 for url 'https://api.telegram.org/bot123:SECRET/sendMessage'"
    assert "SECRET" not in redact_url(message, url)
    assert mask_url(url).startswith("https://api.telegram.org/…")
