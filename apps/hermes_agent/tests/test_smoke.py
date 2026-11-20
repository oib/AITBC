"""Smoke tests for the hermes_agent service app.

`main.py` lives at the app root and sibling apps ship their own `main.py`, so
the module is loaded under a unique name instead of `import main`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

_spec = importlib.util.spec_from_file_location("aitbc_hermes_main", Path(__file__).resolve().parents[1] / "main.py")
hermes_main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(hermes_main)


def test_health_endpoint_responds() -> None:
    client = TestClient(hermes_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "hermes_agent"
    assert "ready" in body


def test_find_hermes_missing_binary_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_BIN", "definitely-not-a-real-binary-xyz")
    monkeypatch.setattr(hermes_main.shutil, "which", lambda _: None)
    # Also hide the common install locations.
    monkeypatch.setattr(hermes_main.os.path, "isfile", lambda _: False)
    assert hermes_main._find_hermes() is None


def test_reasoning_levels_are_closed_set() -> None:
    assert "medium" in hermes_main._REASONING_LEVELS
    assert "bogus" not in hermes_main._REASONING_LEVELS


def test_uvicorn_launch_log_level_is_info() -> None:
    """#2320: log_level="critical" made paid-job failures invisible in the
    journal (the same gap #2319 fixed in whisper). The launch must stay at
    "info"; access_log stays off to avoid request noise."""
    src = Path(hermes_main.__file__).read_text()
    run_lines = [ln for ln in src.splitlines() if "uvicorn.run(" in ln]
    assert run_lines, "no uvicorn.run launch found"
    assert all('log_level="info"' in ln for ln in run_lines)
    assert all("access_log=False" in ln for ln in run_lines)
