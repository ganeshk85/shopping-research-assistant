"""Application settings loaded from environment variables / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    llm_model: str
    tavily_api_key: str
    notifier: str
    webhook_url: str
    resend_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    alert_email_from: str
    alert_email_to: str
    data_dir: Path
    check_interval_hours: int
    default_target_discount: float
    default_currency: str

    @property
    def watchlist_db_path(self) -> Path:
        return self.data_dir / "watchlist.db"

    @property
    def checkpoints_db_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    def require(self, *names: str) -> None:
        """Raise a clear error if any of the named settings are empty."""
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            keys = ", ".join(n.upper() for n in missing)
            raise ConfigError(f"Missing required configuration: {keys}. Set it in .env.")


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)

    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir

    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "claude-sonnet-5-5"),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        notifier=os.getenv("NOTIFIER", "console").lower(),
        webhook_url=os.getenv("WEBHOOK_URL", ""),
        resend_api_key=os.getenv("RESEND_API_KEY", ""),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        alert_email_from=os.getenv("ALERT_EMAIL_FROM", ""),
        alert_email_to=os.getenv("ALERT_EMAIL_TO", ""),
        data_dir=data_dir,
        check_interval_hours=_int("CHECK_INTERVAL_HOURS", 6),
        default_target_discount=_float("DEFAULT_TARGET_DISCOUNT", 0.10),
        default_currency=os.getenv("DEFAULT_CURRENCY", "CAD").upper(),
    )
