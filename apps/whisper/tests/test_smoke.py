"""Smoke tests for the whisper service app.

The module is loaded under a unique name — `main.py` sits at the app root and
sibling apps ship their own `main.py`, so a bare `import main` would collide in
sys.modules across suites.

The /health handler is invoked directly rather than through TestClient: the
lifespan handler loads a faster-whisper model, which must not run in tests.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "aitbc_whisper_main", Path(__file__).resolve().parents[1] / "main.py"
)
whisper_main = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(whisper_main)


def test_safe_suffix_accepts_normal_extension() -> None:
    assert whisper_main._safe_suffix("clip.wav") == ".wav"
    assert whisper_main._safe_suffix("clip.FLAC") == ".flac"


def test_safe_suffix_rejects_missing_or_oversized() -> None:
    assert whisper_main._safe_suffix(None) == ".wav"
    assert whisper_main._safe_suffix("clip." + "a" * 64) == ".wav"


def test_health_reports_not_ready_without_model() -> None:
    body = asyncio.run(whisper_main.health())
    assert body["service"] == "whisper"
    # No model is loaded in tests, so the service must report not-ready.
    assert body["ready"] is False
