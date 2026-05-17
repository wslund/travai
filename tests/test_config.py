"""Sanity-tester för config."""

from travai.config import settings


def test_settings_loads() -> None:
    """Config ska kunna laddas utan att krascha."""
    assert settings.atg_base_url.startswith("https://")
    assert settings.atg_rate_limit_seconds > 0
