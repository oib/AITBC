"""Smoke tests for the ffmpeg service app.

`main.py` lives at the app root, not under src/, and several sibling apps ship
their own `main.py` — so the module is loaded under a unique name instead of
`import main`, which would collide in sys.modules across suites.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

_spec = importlib.util.spec_from_file_location("aitbc_ffmpeg_main", Path(__file__).resolve().parents[1] / "main.py")
ffmpeg_main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ffmpeg_main)


def test_safe_suffix_accepts_normal_extension() -> None:
    assert ffmpeg_main._safe_suffix("clip.mp4") == ".mp4"
    assert ffmpeg_main._safe_suffix("clip.MP4") == ".mp4"


def test_safe_suffix_rejects_missing_or_oversized() -> None:
    assert ffmpeg_main._safe_suffix(None) == ".mp4"
    assert ffmpeg_main._safe_suffix("") == ".mp4"
    assert ffmpeg_main._safe_suffix("clip." + "a" * 64) == ".mp4"


def test_safe_suffix_rejects_non_alnum_extension() -> None:
    assert ffmpeg_main._safe_suffix("clip.foo-bar") == ".mp4"
    assert ffmpeg_main._safe_suffix("clip.tar.gz") == ".gz"


def test_health_endpoint_responds() -> None:
    client = TestClient(ffmpeg_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "ffmpeg"
    assert "ready" in body


def test_uvicorn_launch_log_level_is_info() -> None:
    """#2320: log_level="critical" made paid-job failures invisible in the
    journal (the same gap #2319 fixed in whisper). The launch must stay at
    "info"; access_log stays off to avoid request noise."""
    src = Path(ffmpeg_main.__file__).read_text()
    run_lines = [ln for ln in src.splitlines() if "uvicorn.run(" in ln]
    assert run_lines, "no uvicorn.run launch found"
    assert all('log_level="info"' in ln for ln in run_lines)
    assert all("access_log=False" in ln for ln in run_lines)
