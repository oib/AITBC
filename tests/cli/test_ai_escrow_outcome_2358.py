"""#2358: 'Escrow secured' must not print for a payment that failed on-chain.

``ai submit``/``ai pay`` used to print "Escrow secured" for any
``POST /v1/payments`` 201 — including payments the coordinator marked
``failed`` when the ESCROW_LOCK never sealed. The fix routes both call
sites through ``_report_escrow_outcome``, which only claims success for
``escrowed``/``confirmed`` and surfaces ``payment_error`` otherwise;
``ai refund`` refuses a failed payment up front instead of hitting the
refund endpoint's bare 400.
"""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.ai as ai_pkg
from aitbc_cli.commands.ai import refunds as refunds_mod


@pytest.fixture
def messages(monkeypatch):
    """Capture success/warning/abort output from the ai package helpers."""
    captured: dict[str, list[str]] = {"success": [], "warning": [], "abort": []}
    monkeypatch.setattr(ai_pkg, "success", lambda m, **kw: captured["success"].append(m))
    monkeypatch.setattr(ai_pkg, "warning", lambda m, **kw: captured["warning"].append(m))
    real_abort = ai_pkg.abort

    def _abort(ctx, message, **kw):
        captured["abort"].append(message)
        raise SystemExit(1)

    monkeypatch.setattr(ai_pkg, "abort", _abort)
    return captured, real_abort


def _result(**over):
    base = {"payment_id": "pay-1", "status": "escrowed", "payment_error": None}
    base.update(over)
    return base


class TestReportEscrowOutcome:
    def test_escrowed_prints_secured(self, messages):
        captured, _ = messages
        ai_pkg._report_escrow_outcome(None, "job-1", _result())
        assert captured["success"] == ["Escrow secured: pay-1"]
        assert captured["warning"] == []

    def test_confirmed_prints_secured(self, messages):
        captured, _ = messages
        ai_pkg._report_escrow_outcome(None, "job-1", _result(status="confirmed"))
        assert captured["success"] == ["Escrow secured: pay-1"]

    def test_failed_warns_with_reason_not_secured(self, messages):
        captured, _ = messages
        ai_pkg._report_escrow_outcome(
            None,
            "job-1",
            _result(status="failed", payment_error="the escrow lock did not seal on-chain"),
        )
        assert captured["success"] == []
        assert len(captured["warning"]) == 1
        msg = captured["warning"][0]
        assert "NOT secured" in msg
        assert "the escrow lock did not seal on-chain" in msg
        assert "aitbc ai pay --job-id job-1" in msg

    def test_pending_without_reason_warns_unconfirmed(self, messages):
        captured, _ = messages
        ai_pkg._report_escrow_outcome(None, "job-1", _result(status="pending", payment_error=None))
        assert captured["success"] == []
        assert "not yet confirmed" in captured["warning"][0]
        assert "status=pending" in captured["warning"][0]


class _FakeClient:
    """Minimal stand-in for AITBCHTTPClient used by ``ai refund``."""

    def __init__(self, job: dict[str, Any]):
        self._job = job
        self.posts: list[tuple[str, dict]] = []

    def get(self, path: str, **kw):
        assert path.startswith("/v1/jobs/")
        return self._job

    def post(self, path: str, json=None, **kw):
        self.posts.append((path, json or {}))
        return {"status": "refunded"}


def _invoke_refund(monkeypatch, job: dict[str, Any]):
    client = _FakeClient(job)
    monkeypatch.setattr(ai_pkg, "get_config", lambda: object())
    monkeypatch.setattr(ai_pkg, "_require_auth_headers", lambda ctx: {"Authorization": "Bearer x"})
    monkeypatch.setattr(ai_pkg, "_coordinator_base_url", lambda ctx, url=None: "http://coord.test")
    monkeypatch.setattr(ai_pkg, "AITBCHTTPClient", lambda **kw: client)
    monkeypatch.setattr(ai_pkg, "_new_idempotency_key", lambda seed: "idem-1")
    runner = CliRunner()
    result = runner.invoke(refunds_mod.refund, ["--job-id", "job-1", "--reason", "test"], obj={})
    return result, client


def test_refund_aborts_on_failed_payment_without_posting(monkeypatch):
    """A failed payment locked nothing — refund must not hit the endpoint."""
    job = {
        "job_id": "job-1",
        "payment_id": "pay-1",
        "payment_status": "failed",
        "payment_error": "the escrow lock did not seal on-chain",
    }
    result, client = _invoke_refund(monkeypatch, job)
    assert result.exit_code != 0
    assert "nothing was escrowed" in result.output
    assert "aitbc ai cancel" in result.output
    assert client.posts == []


def test_refund_still_posts_for_escrowed_payment(monkeypatch):
    job = {
        "job_id": "job-1",
        "payment_id": "pay-1",
        "payment_status": "escrowed",
        "payment_error": None,
    }
    result, client = _invoke_refund(monkeypatch, job)
    assert result.exit_code == 0, result.output
    assert client.posts and client.posts[0][0] == "/v1/payments/pay-1/refund"
