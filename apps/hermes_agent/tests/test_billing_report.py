"""#2365: hermes /run attests duration_minutes to the market service.

The billing POST is settlement input, not paid-work gating: it fires after
the run completes, carries the job's access triple via
``report_request_billing``, and a refused report must not break the paid
response (settlement falls back to full-lock).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# Same unique-module-name convention as the sibling suites.
_spec = importlib.util.spec_from_file_location("aitbc_hermes_main_billing", Path(__file__).resolve().parents[1] / "main.py")
hermes = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["aitbc_hermes_main_billing"] = hermes
_spec.loader.exec_module(hermes)

HermesRunRequest = hermes.HermesRunRequest


def _patch_hermes(monkeypatch: pytest.MonkeyPatch, fake: Path) -> None:
    monkeypatch.setattr(hermes, "_HERMES_PATH", str(fake))
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_MODEL", "test-model")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_PROVIDER", "test-provider")
    monkeypatch.setattr(hermes, "_HERMES_DEFAULT_TOOLSETS", "core")
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_MODELS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_PROVIDERS", [])
    monkeypatch.setattr(hermes, "_HERMES_ALLOWED_TOOLSETS", [])


def _fake_hermes(tmp_path: Path) -> Path:
    fake = tmp_path / "fake-hermes"
    fake.write_text('#!/bin/sh\necho "hermes done"\n')
    fake.chmod(0o755)
    return fake


def _raw_request() -> SimpleNamespace:
    return SimpleNamespace(
        headers={
            "X-Access-Key": "k",
            "X-Access-Secret": "s",
            "X-Job-Id": "job-H1",
        }
    )


@pytest.mark.asyncio
async def test_run_reports_duration_minutes_billing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hermes(monkeypatch, _fake_hermes(tmp_path))
    report = AsyncMock(return_value=True)
    monkeypatch.setattr(hermes, "report_request_billing", report)

    raw = _raw_request()
    resp = await hermes._run_hermes_inner(HermesRunRequest(prompt="x", max_time=30), raw, "0xProvider1")
    assert resp.status_code == 200
    report.assert_awaited_once()
    call = report.await_args
    assert call.args[0] is raw
    assert set(call.args[1]) == {"duration_minutes"}
    assert call.args[1]["duration_minutes"] >= 0
    # #2365 respin: the report is signed as the provider — the address comes
    # from the verified job record, never the buyer-held request headers.
    assert call.kwargs["provider_address"] == "0xProvider1"


@pytest.mark.asyncio
async def test_run_billing_refusal_still_delivers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hermes(monkeypatch, _fake_hermes(tmp_path))
    monkeypatch.setattr(hermes, "report_request_billing", AsyncMock(return_value=False))
    resp = await hermes._run_hermes_inner(HermesRunRequest(prompt="x", max_time=30), _raw_request())
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_run_without_raw_request_skips_billing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct/internal calls (raw_request=None) never attempt the POST."""
    _patch_hermes(monkeypatch, _fake_hermes(tmp_path))
    report = AsyncMock(return_value=True)
    monkeypatch.setattr(hermes, "report_request_billing", report)
    resp = await hermes._run_hermes_inner(HermesRunRequest(prompt="x", max_time=30))
    assert resp.status_code == 200
    report.assert_not_awaited()
