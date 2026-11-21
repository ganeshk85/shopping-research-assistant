"""Notification settings over HTTP (US-35).

A user picks the alert channel and its destination (webhook URL or email address). Server
secrets (Resend key, SMTP login, the sender address, LLM and search keys) stay in .env and
are never returned; the saved webhook URL is returned masked, since it carries a token.
With nothing saved, the .env values are used, as in v1.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Response

from ..config import ConfigError, Settings
from ..database import UserStore
from ..models import NotificationSettings
from ..tools.notifier import NotificationError, email_configured, with_saved_settings
from .deps import Services, current_store, get_services
from .errors import ApiError
from .schemas import ErrorBody, NotificationSettingsOut, TestAlertResult, UpdateNotificationSettings

router = APIRouter(prefix="/settings/notifications", tags=["settings"])

TEST_SUBJECT = "Test alert from Shopping Research Assistant"
TEST_BODY = "If you can read this, price-drop alerts will reach you here. No action is needed."


def mask_url(url: str) -> str:
    """'https://discord.com/…f3a9': enough to recognise the URL, not enough to use it."""
    parsed = urlparse(url)
    tail = url.rstrip("/")[-4:]
    return f"{parsed.scheme}://{parsed.netloc}/…{tail}"


def redact_url(message: str, url: str) -> str:
    """Remove a webhook URL's secret parts (its path and query hold the token) from error text."""
    if not url:
        return message
    parsed = urlparse(url)
    message = message.replace(url, mask_url(url))
    for secret in (parsed.path, parsed.query):
        if len(secret) > 1:
            message = message.replace(secret, "…")
    return message


def _out(settings: Settings, saved: Optional[NotificationSettings]) -> NotificationSettingsOut:
    effective = with_saved_settings(settings, saved)
    return NotificationSettingsOut(
        channel=effective.notifier if effective.notifier in ("console", "webhook", "email") else "console",
        source="saved" if saved else "env",
        webhook_url_hint=mask_url(effective.webhook_url) if effective.webhook_url else None,
        alert_email=effective.alert_email_to or None,
        email_available=email_configured(settings),
        updated_at=saved.updated_at if saved else None,
    )


@router.get("", response_model=NotificationSettingsOut, summary="My alert channel")
def get_settings(store: UserStore = Depends(current_store), services: Services = Depends(get_services)):
    return _out(services.settings, store.get_notification_settings())


@router.put(
    "",
    response_model=NotificationSettingsOut,
    summary="Save my alert channel",
    responses={422: {"model": ErrorBody}},
)
def save_settings(
    body: UpdateNotificationSettings,
    store: UserStore = Depends(current_store),
    services: Services = Depends(get_services),
) -> NotificationSettingsOut:
    saved = store.get_notification_settings()
    given = body.model_fields_set
    candidate = NotificationSettings(
        channel=body.channel,
        # Omitted = keep what's saved (so the masked URL never has to be sent back); null = clear.
        webhook_url=body.webhook_url if "webhook_url" in given else (saved.webhook_url if saved else None),
        alert_email=body.alert_email if "alert_email" in given else (saved.alert_email if saved else None),
    )
    _validate(services, candidate)
    return _out(services.settings, store.save_notification_settings(candidate))


def _validate(services: Services, candidate: NotificationSettings) -> None:
    if candidate.channel == "webhook" and not candidate.webhook_url:
        raise ApiError(422, "invalid_settings", "Enter a webhook URL to use webhook alerts.")
    if candidate.channel == "email":
        if not candidate.alert_email:
            raise ApiError(422, "invalid_settings", "Enter the email address alerts should go to.")
        if not email_configured(services.settings):
            raise ApiError(
                422, "invalid_settings",
                "Email isn't set up on the server. Add ALERT_EMAIL_FROM and RESEND_API_KEY (or SMTP_HOST) to .env.",
            )
    try:
        services.notifier_factory(with_saved_settings(services.settings, candidate))
    except ConfigError as exc:  # e.g. a Telegram URL without chat_id
        raise ApiError(422, "invalid_settings", str(exc).replace(" Set it in .env.", "")) from exc


@router.delete("", status_code=204, summary="Forget my alert channel (use the .env settings)")
def reset_settings(store: UserStore = Depends(current_store)) -> Response:
    store.delete_notification_settings()
    return Response(status_code=204)


@router.post(
    "/test",
    response_model=TestAlertResult,
    summary="Send a test alert through my channel",
    responses={502: {"model": ErrorBody, "description": "The alert couldn't be delivered"},
               503: {"model": ErrorBody, "description": "The channel isn't set up"}},
)
def send_test_alert(
    store: UserStore = Depends(current_store), services: Services = Depends(get_services)
) -> TestAlertResult:
    effective = with_saved_settings(services.settings, store.get_notification_settings())
    notifier = services.notifier_factory(effective)  # ConfigError -> 503 not_configured
    try:
        notifier.send(TEST_SUBJECT, TEST_BODY)
    except NotificationError as exc:
        message = redact_url(str(exc), effective.webhook_url)
        raise ApiError(502, "notification_failed", f"The test alert couldn't be delivered: {message}") from exc
    where = {"console": "the API's console window", "webhook": "your webhook", "email": effective.alert_email_to}
    return TestAlertResult(channel=effective.notifier, message=f"Test alert sent to {where.get(effective.notifier)}.")
