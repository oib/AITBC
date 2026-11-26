"""Shared fixtures for the memory service suite."""

import pytest

from memory_app.config import settings


@pytest.fixture(autouse=True)
def _open_mode_opt_in(monkeypatch):
    """#3029: open mode now requires the explicit MEMORY_OPEN_MODE opt-in.

    Most of this suite exercises the unauthenticated single-tenant path;
    opt it in here so each test declares the posture via settings rather
    than depending on the old fail-open default. Tests that configure key
    material are unaffected — auth wins over open mode either way, and a
    pin that needs the gate closed monkeypatches the flag back to False.
    """
    monkeypatch.setattr(settings, "memory_open_mode", True)
