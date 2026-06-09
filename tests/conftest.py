"""Pytest configuration and fixtures."""

import pytest

from aicbc.config.settings import Settings, get_settings


@pytest.fixture
def test_settings() -> Settings:
    """Return test settings."""
    return Settings(environment="test", debug=True)
