"""ESCROW-LEAK-RESIDUAL-1 (#1775): pre-escrow validation ordering and
post-lock failure coverage for the market CLI ``sw_job_*`` runners.

Every path that can fail between ``_escrow_create`` and escrow release must
either happen before the lock or attempt ``_refund_orphaned_escrow`` — these
escrows have no job row, so no sweeper ever reclaims them.
"""

import json
import urllib.request
from types import SimpleNamespace
from typing import Any, cast

import click
import pytest

import aitbc_cli.commands.market.jobs as jobs_mod


def _ctx() -> click.Context:
    return cast(click.Context, SimpleNamespace(obj={}))


def _config() -> Any:
    return SimpleNamespace(
        hub_proposer_id="0xPROP",
        blockchain_rpc_api_key=None,
        hub_discovery_url="https://hub.aitbc.bubuit.net",
        blockchain_rpc_url="http://127.0.0.1:8202",
        coordinator_api_url=None,
    )


def _offer(service_type: str = "hermes", **over: Any) -> dict[str, Any]:
    offer = {
        "service_type": service_type,
        "model": "m",
        "price": "1",
        "price_unit": "per_minute",
        "provider_address": "0xP",
        "offer_id": "o1",
        "public_endpoint": "http://127.0.0.1:8270",
    }
    offer.update(over)
    return offer


class _FakeResp:
    def __init__(self, payload: Any) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *a: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.fixture
def escrow_spy(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Any], list[tuple[str, str, str]]]:
    """Stub escrow create (recorded) + capture refund_escrow calls."""
    creates: list[Any] = []
    refunds: list[tuple[str, str, str]] = []
    monkeypatch.setattr(jobs_mod, "get_config", _config)
    monkeypatch.setattr(jobs_mod, "get_chain_id", lambda: "bc-2")

    def _create(*a: Any, **kw: Any) -> str:
        creates.append((a, kw))
        return "contract-1"

    monkeypatch.setattr(jobs_mod, "_escrow_create", _create)

    def _refund(ctx: Any, job_id: str, reason: str) -> dict[str, Any]:
        refunds.append((job_id, reason, "ok"))
        return {"refunded": True}

    monkeypatch.setattr(jobs_mod, "refund_escrow", _refund)
    return creates, refunds


# --- pre-lock ordering: failures must happen BEFORE _escrow_create ---------


def test_ollama_unsafe_scheme_never_locks_escrow(
    escrow_spy: tuple[list[Any], list[Any]],
) -> None:
    creates, refunds = escrow_spy
    offer = _offer("ollama", price_unit="per_1k_tokens", endpoint="file:///etc/passwd")
    offer.pop("public_endpoint")
    with pytest.raises(click.Abort):
        jobs_mod._run_ollama(_ctx(), offer, "prompt", "0xB", "dead", 512, False, "json")
    assert creates == []
    assert refunds == []


def test_whisper_missing_file_never_locks_escrow(
    escrow_spy: tuple[list[Any], list[Any]],
) -> None:
    creates, refunds = escrow_spy
    offer = _offer("whisper", price_unit="per_audio_min")
    with pytest.raises(FileNotFoundError):
        jobs_mod._run_whisper(_ctx(), offer, "/nonexistent/audio.wav", "0xB", "dead", None, "transcribe", "text", "json")
    assert creates == []
    assert refunds == []


def test_ffmpeg_missing_file_never_locks_escrow(
    escrow_spy: tuple[list[Any], list[Any]],
) -> None:
    creates, refunds = escrow_spy
    offer = _offer("ffmpeg", price_unit="per_processing_hour")
    with pytest.raises(FileNotFoundError):
        jobs_mod._run_ffmpeg(_ctx(), offer, "/nonexistent/video.mp4", "0xB", "dead", "mp4", "h264", "1080p", "4M", "json")
    assert creates == []
    assert refunds == []


# --- post-lock coverage: every failure refunds ----------------------------


def test_ollama_keyboard_interrupt_refunds(escrow_spy: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    creates, refunds = escrow_spy

    def _boom(req: Any, timeout: int = 0) -> Any:
        raise KeyboardInterrupt()

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    offer = _offer("ollama", price_unit="per_1k_tokens")
    with pytest.raises(KeyboardInterrupt):
        jobs_mod._run_ollama(_ctx(), offer, "prompt", "0xB", "dead", 512, False, "json")
    assert len(creates) == 1
    assert len(refunds) == 1
    assert refunds[0][1] == "job_failed"


def test_hermes_keyboard_interrupt_refunds(escrow_spy: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    creates, refunds = escrow_spy

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def post(self, *a: Any, **kw: Any) -> Any:
            raise KeyboardInterrupt()

    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", _Client)
    with pytest.raises(KeyboardInterrupt):
        jobs_mod._run_hermes(_ctx(), _offer(), "hi", 60, "0xB", "dead", "json")
    assert len(creates) == 1
    assert len(refunds) == 1


def test_hermes_non_dict_response_refunds(escrow_spy: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    creates, refunds = escrow_spy

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def post(self, *a: Any, **kw: Any) -> Any:
            return ["not", "a", "dict"]

    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", _Client)
    with pytest.raises(click.Abort):
        jobs_mod._run_hermes(_ctx(), _offer(), "hi", 60, "0xB", "dead", "json")
    assert len(creates) == 1
    assert len(refunds) == 1


def test_hermes_malformed_duration_refunds(escrow_spy: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    creates, refunds = escrow_spy

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def post(self, *a: Any, **kw: Any) -> dict[str, Any]:
            return {"status": "completed", "duration_minutes": "abc", "text": "hi"}

    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", _Client)
    with pytest.raises(click.Abort):
        jobs_mod._run_hermes(_ctx(), _offer(), "hi", 60, "0xB", "dead", "json")
    assert len(creates) == 1
    assert len(refunds) == 1


def test_hermes_nan_duration_refunds(escrow_spy: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    creates, refunds = escrow_spy

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def post(self, *a: Any, **kw: Any) -> dict[str, Any]:
            return {"status": "completed", "duration_minutes": "NaN", "text": "hi"}

    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", _Client)
    with pytest.raises(click.Abort):
        jobs_mod._run_hermes(_ctx(), _offer(), "hi", 60, "0xB", "dead", "json")
    assert len(creates) == 1
    assert len(refunds) == 1


def test_ollama_non_dict_response_refunds(escrow_spy: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    creates, refunds = escrow_spy

    def _resp(req: Any, timeout: int = 0) -> Any:
        return _FakeResp([1, 2, 3])

    monkeypatch.setattr(urllib.request, "urlopen", _resp)
    offer = _offer("ollama", price_unit="per_1k_tokens")
    with pytest.raises(click.Abort):
        jobs_mod._run_ollama(_ctx(), offer, "prompt", "0xB", "dead", 512, False, "json")
    assert len(creates) == 1
    assert len(refunds) == 1


def test_ollama_malformed_eval_count_refunds(escrow_spy: tuple[list[Any], list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    creates, refunds = escrow_spy

    def _resp(req: Any, timeout: int = 0) -> Any:
        return _FakeResp({"response": "hi", "eval_count": "lots"})

    monkeypatch.setattr(urllib.request, "urlopen", _resp)
    offer = _offer("ollama", price_unit="per_1k_tokens")
    with pytest.raises(click.Abort):
        jobs_mod._run_ollama(_ctx(), offer, "prompt", "0xB", "dead", 512, False, "json")
    assert len(creates) == 1
    assert len(refunds) == 1


def test_whisper_malformed_duration_refunds(
    escrow_spy: tuple[list[Any], list[Any]], tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    creates, refunds = escrow_spy
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")

    def _resp(req: Any, timeout: int = 0) -> Any:
        return _FakeResp({"text": "hi", "duration_minutes": "bogus"})

    monkeypatch.setattr(urllib.request, "urlopen", _resp)
    offer = _offer("whisper", price_unit="per_audio_min")
    with pytest.raises(click.Abort):
        jobs_mod._run_whisper(_ctx(), offer, str(audio), "0xB", "dead", None, "transcribe", "text", "json")
    assert len(creates) == 1
    assert len(refunds) == 1


def test_ffmpeg_malformed_hours_refunds(
    escrow_spy: tuple[list[Any], list[Any]], tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    creates, refunds = escrow_spy
    video = tmp_path / "v.mp4"
    video.write_bytes(b"ftyp")

    def _resp(req: Any, timeout: int = 0) -> Any:
        return _FakeResp({"processing_time_hours": {"bad": "shape"}})

    monkeypatch.setattr(urllib.request, "urlopen", _resp)
    offer = _offer("ffmpeg", price_unit="per_processing_hour")
    with pytest.raises(click.Abort):
        jobs_mod._run_ffmpeg(_ctx(), offer, str(video), "0xB", "dead", "mp4", "h264", "1080p", "4M", "json")
    assert len(creates) == 1
    assert len(refunds) == 1
