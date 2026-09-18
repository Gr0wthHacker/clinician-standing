"""Configuration loading must fail loudly when DATABASE_URL is absent.

A connector that starts without a database URL will do several minutes of
downloading before discovering it has nowhere to write. Validation happens
first, or it is not worth having.
"""

from __future__ import annotations

import pytest

from conftest import find_attr, require, try_import

CONFIG_MODULE = "clinician_standing.config"


def _validator():
    """Return a zero-argument callable that validates the current environment.

    The config module is written by a separate workstream, so probe for the
    shapes it might reasonably take rather than pinning one.
    """
    module = try_import(CONFIG_MODULE)
    if module is None:
        return None

    # 1. A module-level validate() is the documented shape.
    fn = find_attr(module, "validate", "validate_config")
    if callable(fn):
        return fn

    # 2. A settings accessor that returns an object with .validate().
    #    It is usually cached, so clear the cache before each read or the test
    #    would validate whatever environment the first caller happened to see.
    accessor = find_attr(module, "get_settings", "get_config", "load_settings")
    if callable(accessor):
        reset = find_attr(module, "reset_settings_cache", "reset_cache")

        def _via_accessor():
            if callable(reset):
                reset()
            try:
                settings = accessor(refresh=True)
            except TypeError:
                settings = accessor()
            validate = getattr(settings, "validate", None)
            return validate() if callable(validate) else settings

        return _via_accessor

    # 3. A settings class constructed from the environment.
    config_cls = find_attr(module, "Settings", "Config")
    if config_cls is None:
        return None
    factory = find_attr(config_cls, "from_env", "load")
    if not callable(factory):
        return None

    def _via_class():
        settings = factory()
        validate = getattr(settings, "validate", None)
        return validate() if callable(validate) else settings

    return _via_class


@require(CONFIG_MODULE)
def test_validate_raises_when_database_url_missing():
    """No DATABASE_URL in the environment -> validation fails, and says so."""
    validate = _validator()
    if validate is None:
        pytest.skip(f"awaiting a validate entry point in {CONFIG_MODULE}")

    with pytest.raises(Exception) as excinfo:
        validate()

    message = str(excinfo.value)
    assert "DATABASE_URL" in message.upper(), (
        f"the error must name the missing variable; got {excinfo.typename}: {message!r}"
    )


@require(CONFIG_MODULE)
def test_validate_passes_with_database_url_set(valid_env):
    """A complete environment validates without raising."""
    validate = _validator()
    if validate is None:
        pytest.skip(f"awaiting a validate entry point in {CONFIG_MODULE}")

    validate()  # must not raise


@require(CONFIG_MODULE)
def test_validate_rejects_empty_database_url(monkeypatch):
    """An empty string is a misconfiguration, not a valid URL.

    This is the realistic failure in CI: a repository secret that was never set
    expands to the empty string rather than being absent.
    """
    validate = _validator()
    if validate is None:
        pytest.skip(f"awaiting a validate entry point in {CONFIG_MODULE}")

    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(Exception):  # noqa: B017
        validate()
