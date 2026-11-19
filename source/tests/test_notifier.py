import io
import json
import smtplib

import httpx
import pytest

from shopping_assistant.config import ConfigError
from shopping_assistant.tools.notifier import (
    RESEND_URL,
    ConsoleNotifier,
    NotificationError,
    ResendEmailNotifier,
    SmtpEmailNotifier,
    WebhookNotifier,
    build_notifier,
)


def recording_client(status: int = 200):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json={})

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


def test_console_notifier_prints():
    buf = io.StringIO()
    ConsoleNotifier(stream=buf).send("Price drop", "Now $399")
    out = buf.getvalue()
    assert "Price drop" in out and "Now $399" in out


@pytest.mark.parametrize(
    "url, kind, key",
    [
        ("https://discord.com/api/webhooks/1/abc", "discord", "content"),
        ("https://hooks.slack.com/services/T/B/X", "slack", "text"),
        ("https://example.com/hook", "generic", "body"),
    ],
)
def test_webhook_payload_formats(url, kind, key):
    client, reqs = recording_client()
    n = WebhookNotifier(url, client=client)
    assert n.kind == kind
    n.send("Deal!", "Sony now $399")
    payload = json.loads(reqs[0].content)
    assert "Sony now $399" in payload[key]
    assert str(reqs[0].url) == url


def test_webhook_telegram_moves_chat_id_into_body():
    client, reqs = recording_client()
    n = WebhookNotifier("https://api.telegram.org/botTOKEN/sendMessage?chat_id=42", client=client)
    n.send("Deal!", "body")
    assert str(reqs[0].url) == "https://api.telegram.org/botTOKEN/sendMessage"
    assert json.loads(reqs[0].content)["chat_id"] == "42"


def test_webhook_telegram_requires_chat_id():
    with pytest.raises(ConfigError, match="chat_id"):
        WebhookNotifier("https://api.telegram.org/botTOKEN/sendMessage")


def test_discord_message_truncated():
    client, reqs = recording_client()
    WebhookNotifier("https://discord.com/api/webhooks/1/abc", client=client).send("s", "x" * 5000)
    assert len(json.loads(reqs[0].content)["content"]) == 2000


def test_webhook_http_error_raises_notification_error():
    client, _ = recording_client(status=500)
    with pytest.raises(NotificationError):
        WebhookNotifier("https://example.com/hook", client=client).send("s", "b")


def test_resend_email_request():
    client, reqs = recording_client()
    ResendEmailNotifier("re_key", "alerts@example.com", "me@example.com", client=client).send("Deal", "Body")
    req = reqs[0]
    assert str(req.url) == RESEND_URL
    assert req.headers["Authorization"] == "Bearer re_key"
    assert json.loads(req.content)["to"] == ["me@example.com"]


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, fail=False):
        self.host, self.port, self.sent, self.started_tls, self.logged_in = host, port, [], False, None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


def test_smtp_email_sends_with_starttls():
    FakeSMTP.instances.clear()
    n = SmtpEmailNotifier("smtp.example.com", 587, "u", "p", "a@example.com", "b@example.com", smtp_factory=FakeSMTP)
    n.send("Deal", "Body")
    smtp = FakeSMTP.instances[0]
    assert smtp.started_tls and smtp.logged_in == ("u", "p")
    assert smtp.sent[0]["To"] == "b@example.com"


def test_smtp_failure_raises_notification_error():
    def broken(*a, **k):
        raise smtplib.SMTPConnectError(421, "down")

    n = SmtpEmailNotifier("h", 587, "", "", "a@x.com", "b@x.com", smtp_factory=broken)
    with pytest.raises(NotificationError):
        n.send("s", "b")


# --- factory / configuration errors (US-22) -----------------------------------


def test_build_console(settings_factory):
    assert isinstance(build_notifier(settings_factory()), ConsoleNotifier)


def test_build_webhook_requires_url(settings_factory):
    with pytest.raises(ConfigError, match="WEBHOOK_URL"):
        build_notifier(settings_factory(notifier="webhook"))


def test_build_email_prefers_resend(settings_factory):
    s = settings_factory(notifier="email", resend_api_key="k", alert_email_from="a@x.com", alert_email_to="b@x.com")
    assert isinstance(build_notifier(s), ResendEmailNotifier)


def test_build_email_smtp_requires_host(settings_factory):
    s = settings_factory(notifier="email", alert_email_from="a@x.com", alert_email_to="b@x.com")
    with pytest.raises(ConfigError, match="SMTP_HOST"):
        build_notifier(s)


def test_build_email_requires_addresses(settings_factory):
    with pytest.raises(ConfigError, match="ALERT_EMAIL_FROM, ALERT_EMAIL_TO"):
        build_notifier(settings_factory(notifier="email"))


def test_unknown_notifier(settings_factory):
    with pytest.raises(ConfigError, match="Unknown NOTIFIER"):
        build_notifier(settings_factory(notifier="pigeon"))
