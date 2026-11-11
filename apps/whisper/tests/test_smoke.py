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

_spec = importlib.util.spec_from_file_location("aitbc_whisper_main", Path(__file__).resolve().parents[1] / "main.py")
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


# --- WHISPER-BLOCK-1 (#1422): event-loop offload + concurrency bound ---


class _FakeSegment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


class _FakeInfo:
    language = "en"
    language_probability = 0.99
    duration = 12.5


class _FakeModel:
    """Stand-in for faster_whisper.WhisperModel — records the call, no decode."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def transcribe(self, path, beam_size, language, task):
        self.calls.append({"path": path, "beam_size": beam_size, "language": language, "task": task})
        segments = iter([_FakeSegment(0.0, 1.5, " hello "), _FakeSegment(1.5, 3.0, "world")])
        return segments, _FakeInfo()


class _FakeUpload:
    """Minimal UploadFile stand-in: only .filename and .read() are used."""

    filename = "clip.wav"

    async def read(self, size: int = -1) -> bytes:
        # One chunk then EOF.
        if getattr(self, "_done", False):
            return b""
        self._done = True
        return b"RIFFfakeaudio"


def _patch_probe(monkeypatch, seconds: float | None = 60.0) -> None:
    monkeypatch.setattr(whisper_main, "_probe_duration", lambda path: seconds)


def _transcribe(**overrides):
    kwargs = {"file": _FakeUpload(), "language": None, "task": "transcribe", "beam_size": 5}
    kwargs.update(overrides)
    return asyncio.run(whisper_main.transcribe(**kwargs))


def test_transcribe_runs_model_off_event_loop(monkeypatch) -> None:
    """The model call must go through asyncio.to_thread, not inline."""
    fake = _FakeModel()
    monkeypatch.setattr(whisper_main, "_model", fake)
    _patch_probe(monkeypatch)

    # The model runs inside _transcribe_sync; record which thread executes it.
    real_sync = whisper_main._transcribe_sync
    worker_threads: list[int] = []

    def spy_sync(path, language, task, beam_size):
        import threading

        worker_threads.append(threading.get_ident())
        return real_sync(path, language, task, beam_size)

    monkeypatch.setattr(whisper_main, "_transcribe_sync", spy_sync)

    import threading

    main_thread = threading.get_ident()
    resp = _transcribe()
    body = resp.body.decode()
    assert '"text": "hello world"' in body or "hello world" in body
    assert fake.calls and fake.calls[0]["beam_size"] == 5
    # The model ran on a worker thread, not the event-loop thread.
    assert worker_threads and worker_threads[0] != main_thread


def test_transcribe_rejects_bad_language(monkeypatch) -> None:
    monkeypatch.setattr(whisper_main, "_model", _FakeModel())
    _patch_probe(monkeypatch)
    try:
        _transcribe(language="not a language!!")
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 400
    else:  # pragma: no cover
        raise AssertionError("expected HTTPException")


def test_transcribe_busy_returns_503(monkeypatch) -> None:
    """A second job while one is in flight is refused before spooling."""
    monkeypatch.setattr(whisper_main, "_model", _FakeModel())
    _patch_probe(monkeypatch)
    monkeypatch.setattr(whisper_main, "_inflight", whisper_main._MAX_CONCURRENT)
    try:
        _transcribe()
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
    else:  # pragma: no cover
        raise AssertionError("expected HTTPException 503")
    # The refused request must not have consumed a slot.
    assert whisper_main._inflight == whisper_main._MAX_CONCURRENT


def test_transcribe_sem_releases_after_job(monkeypatch) -> None:
    """The semaphore is released in the finally path — a later job proceeds."""
    fake = _FakeModel()
    monkeypatch.setattr(whisper_main, "_model", fake)
    _patch_probe(monkeypatch)
    _transcribe()
    _transcribe()
    assert len(fake.calls) == 2


# --- MEDIA-UPLOAD-1 (#1671): wall-clock bound on the decode ---


def test_transcribe_timeout_returns_504(monkeypatch) -> None:
    """A decode that outlives _TRANSCRIBE_TIMEOUT_SECONDS answers 504 instead
    of holding the request open until restart. The 504 abandons only the
    await — the shielded decode keeps the slot until the worker exits
    (#1688), so _inflight drains once the orphaned thread returns."""
    import time

    monkeypatch.setattr(whisper_main, "_model", _FakeModel())
    _patch_probe(monkeypatch)
    monkeypatch.setattr(whisper_main, "_TRANSCRIBE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(whisper_main, "_inflight", 0)

    def slow_sync(path, language, task, beam_size):
        time.sleep(0.4)
        return {"segment_list": [], "full_text": [], "language": "en", "language_probability": 0.9, "duration": 1.0}

    monkeypatch.setattr(whisper_main, "_transcribe_sync", slow_sync)

    async def scenario():
        request = asyncio.ensure_future(
            whisper_main.transcribe(file=_FakeUpload(), language=None, task="transcribe", beam_size=5)
        )
        try:
            await request
        except whisper_main.HTTPException as exc:
            assert exc.status_code == 504
        else:  # pragma: no cover
            raise AssertionError("expected HTTPException 504")
        # The orphaned worker is still draining — the slot stays held, so a
        # second request is refused rather than starting a concurrent decode.
        assert whisper_main._inflight == whisper_main._MAX_CONCURRENT
        try:
            await whisper_main.transcribe(file=_FakeUpload(), language=None, task="transcribe", beam_size=5)
        except whisper_main.HTTPException as exc:
            assert exc.status_code == 503
        else:  # pragma: no cover
            raise AssertionError("expected HTTPException 503 while orphan decodes")
        # The worker exits on its own; the supervised job then releases.
        for _ in range(200):
            if whisper_main._inflight == 0:
                break
            await asyncio.sleep(0.02)
        assert whisper_main._inflight == 0

    asyncio.run(scenario())


# --- WHISPER-CANCEL-SLOT-1 (#1688): slot lifetime follows the worker thread ---


def test_cancelled_request_keeps_slot_until_worker_done(monkeypatch) -> None:
    """Cancelling the awaiting request must not free _inflight while the
    faster-whisper worker thread is still decoding."""
    import threading

    monkeypatch.setattr(whisper_main, "_model", _FakeModel())
    _patch_probe(monkeypatch)
    monkeypatch.setattr(whisper_main, "_inflight", 0)

    started = threading.Event()
    finish = threading.Event()

    def blocking_sync(path, language, task, beam_size):
        started.set()
        finish.wait(timeout=10)
        return {"segment_list": [], "full_text": [], "language": "en", "language_probability": 0.9, "duration": 1.0}

    monkeypatch.setattr(whisper_main, "_transcribe_sync", blocking_sync)

    async def scenario():
        request = asyncio.ensure_future(
            whisper_main.transcribe(file=_FakeUpload(), language=None, task="transcribe", beam_size=5)
        )
        # Wait until the worker thread is actually inside the decode.
        await asyncio.to_thread(started.wait, 5)
        request.cancel()
        cancelled = False
        try:
            await request
        except asyncio.CancelledError:
            cancelled = True
        assert cancelled, "expected the request to be cancelled"
        # The orphaned worker is still running — the slot must still be held,
        # so a second request is refused rather than starting a concurrent decode.
        assert whisper_main._inflight == whisper_main._MAX_CONCURRENT
        try:
            await whisper_main.transcribe(file=_FakeUpload(), language=None, task="transcribe", beam_size=5)
        except whisper_main.HTTPException as exc:
            assert exc.status_code == 503
        else:  # pragma: no cover
            raise AssertionError("expected HTTPException 503 while orphan decodes")
        # Let the worker finish; the supervised job then releases the slot.
        finish.set()
        for _ in range(200):
            if whisper_main._inflight == 0:
                break
            await asyncio.sleep(0.02)
        assert whisper_main._inflight == 0

    asyncio.run(scenario())
