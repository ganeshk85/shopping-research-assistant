from dataclasses import replace
from pathlib import Path

import pytest

from shopping_assistant.config import Settings


@pytest.fixture
def settings_factory(tmp_path: Path):
    """Build Settings without reading .env, overriding any fields."""

    base = Settings(
        anthropic_api_key="test-anthropic",
        llm_model="claude-sonnet-5-5",
        tavily_api_key="test-tavily",
        notifier="console",
        webhook_url="",
        resend_api_key="",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        alert_email_from="",
        alert_email_to="",
        data_dir=tmp_path,
        check_interval_hours=6,
        default_target_discount=0.10,
        default_currency="CAD",
    )

    def make(**overrides) -> Settings:
        return replace(base, **overrides)

    return make
