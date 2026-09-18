"""Configuration loading must fail loudly when DATABASE_URL is absent.

A connector that starts without a database URL will do several minutes of
downloading before discovering it has nowhere to write. Validation happens
first, or it is not worth having.
"""

from __future__ import annotations

import pytest

from clinician_standing.config import ConfigError, get_settings, reset_settings_cache


def validate() -> None:
    """Validate the current environment through the package's own entry point.

    Imported directly. The previous version of this file probed for one of
    several possible shapes and skipped when it found none, which meant a
    renamed `validate` silently stopped being tested.
    """
    reset_settings_cache()
    get_settings(refresh=True).validate()


def test_validate_raises_when_database_url_missing():
    """No DATABASE_URL in the environment -> validation fails, and says so."""
    with pytest.raises(ConfigError) as excinfo:
        validate()

    message = str(excinfo.value)
    assert "DATABASE_URL" in message.upper(), (
        f"the error must name the missing variable; got {excinfo.typename}: {message!r}"
    )


def test_validate_passes_with_database_url_set(valid_env):
    """A complete environment validates without raising."""
    validate()  # must not raise


def test_validate_rejects_empty_database_url(monkeypatch):
    """An empty string is a misconfiguration, not a valid URL.

    This is the realistic failure in CI: a repository secret that was never set
    expands to the empty string rather than being absent.
    """
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(ConfigError):
        validate()
