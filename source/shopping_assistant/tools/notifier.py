"""Alert delivery: Console, Webhook (Discord/Slack/Telegram/generic), Email (Resend/SMTP).

Every `send` raises NotificationError on failure so callers can leave
`last_notified_price` unchanged and retry on the next run (FRD FR-10.2).
"""

from __future__ import annotations

import smtplib
import sys
from email.message import EmailMessage
from typing import Callable, Optional, Protocol, TextIO
from urllib.parse import parse_qs, urlparse

import httpx

from ..config import ConfigError, Settings

RESEND_URL = "https://api.resend.com/emails"
DISCORD_LIMIT = 2000
SLACK_LIMIT = 3000
TELEGRAM_LIMIT = 4096


class NotificationError(RuntimeError):
    """Raised when an alert could not be delivered."""


class Notifier(Protocol):
    def send(self, subject: str, body: str) -> None: ...


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class ConsoleNotifier:
    def __init__(self, stream: Optional[TextIO] = None) -> None:
        self._stream = stream

    def send(self, subject: str, body: str) -> None:
        stream = self._stream or sys.stdout
        line = "=" * 60
        print(f"\n{line}\n🔔 {subject}\n{line}\n{body}\n{line}\n", file=stream, flush=True)


class WebhookNotifier:
    """Posts to Discord, Slack, Telegram, or a generic JSON webhook based on the URL.

    Telegram URL format: https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>
    """

    def __init__(self, url: str, client: Optional[httpx.Client] = None, timeout: float = 15.0) -> None:
        if not url:
            raise ConfigError("Missing required configuration: WEBHOOK_URL. Set it in .env.")
        self.url = url
        self.kind = self.detect_kind(url)
        if self.kind == "telegram" and not parse_qs(urlparse(url).query).get("chat_id"):
            raise ConfigError("Telegram WEBHOOK_URL must include ?chat_id=<CHAT_ID>.")
        self._client = client
        self._timeout = timeout

    @staticmethod
    def detect_kind(url: str) -> str:
        host = urlparse(url).netloc.lower()
        if host.endswith("discord.com") or host.endswith("discordapp.com"):
            return "discord"
        if host == "hooks.slack.com":
            return "slack"
        if host == "api.telegram.org":
            return "telegram"
        return "generic"

    def build_request(self, subject: str, body: str) -> tuple[str, dict]:
        text = f"{subject}\n\n{body}"
        if self.kind == "discord":
            return self.url, {"content": _truncate(text, DISCORD_LIMIT)}
        if self.kind == "slack":
            return self.url, {"text": _truncate(f"*{subject}*\n{body}", SLACK_LIMIT)}
        if self.kind == "telegram":
            parsed = urlparse(self.url)
            chat_id = parse_qs(parsed.query)["chat_id"][0]
            post_url = parsed._replace(query="").geturl()
            return post_url, {
                "chat_id": chat_id,
                "text": _truncate(text, TELEGRAM_LIMIT),
                "disable_web_page_preview": False,
            }
        return self.url, {"subject": subject, "body": body, "text": text}

    def send(self, subject: str, body: str) -> None:
        post_url, payload = self.build_request(subject, body)
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            resp = client.post(post_url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(f"{self.kind} webhook failed: {exc}") from exc
        finally:
            if self._client is None:
                client.close()


class ResendEmailNotifier:
    def __init__(
        self,
        api_key: str,
        sender: str,
        recipient: str,
        client: Optional[httpx.Client] = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_key, self.sender, self.recipient = api_key, sender, recipient
        self._client = client
        self._timeout = timeout

    def send(self, subject: str, body: str) -> None:
        client = self._client or httpx.Client(timeout=self._timeout)
        try:
            resp = client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"from": self.sender, "to": [self.recipient], "subject": subject, "text": body},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationError(f"Resend email failed: {exc}") from exc
        finally:
            if self._client is None:
                client.close()


class SmtpEmailNotifier:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        sender: str,
        recipient: str,
        smtp_factory: Optional[Callable[..., smtplib.SMTP]] = None,
        timeout: float = 20.0,
    ) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.recipient = sender, recipient
        self._factory = smtp_factory
        self._timeout = timeout

    def build_message(self, subject: str, body: str) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg.set_content(body)
        return msg

    def send(self, subject: str, body: str) -> None:
        msg = self.build_message(subject, body)
        use_ssl = self.port == 465
        factory = self._factory or (smtplib.SMTP_SSL if use_ssl else smtplib.SMTP)
        try:
            with factory(self.host, self.port, timeout=self._timeout) as smtp:
                if not use_ssl:
                    smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationError(f"SMTP email failed: {exc}") from exc


def build_notifier(settings: Settings) -> Notifier:
    """Create the notifier selected by NOTIFIER, validating its required settings (US-22)."""
    kind = settings.notifier
    if kind == "console":
        return ConsoleNotifier()
    if kind == "webhook":
        settings.require("webhook_url")
        return WebhookNotifier(settings.webhook_url)
    if kind == "email":
        settings.require("alert_email_from", "alert_email_to")
        if settings.resend_api_key:
            return ResendEmailNotifier(
                settings.resend_api_key, settings.alert_email_from, settings.alert_email_to
            )
        settings.require("smtp_host")
        return SmtpEmailNotifier(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.alert_email_from,
            settings.alert_email_to,
        )
    raise ConfigError(f"Unknown NOTIFIER '{kind}'. Use console, webhook, or email.")
