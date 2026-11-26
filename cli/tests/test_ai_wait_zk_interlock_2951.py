"""#2951: --wait must poll through the ZK-release interlock, not die on a 409.

The reported failure: a completed job whose payment is still ``escrowed``
(the ZK gate / acceptance window has not opened yet) made the auto-accept
fire early, eat a 409 "no payment awaiting acceptance (payment_status=escrowed)",
and never retry — so ``--wait`` stalled instead of releasing.
"""

from __future__ import annotations

import pytest

import aitbc_cli.commands.ai as _ai
from aitbc_cli.commands.ai.submit import _await_payment_release


def _status(payment_status, *, zk_status="verified", state="COMPLETED"):
    return {"payment_status": payment_status, "zk_status": zk_status, "state": state}


class _JobClient:
    """Minimal stand-in for AITBCHTTPClient: scripted GET /v1/jobs/{id}."""

    def __init__(self, statuses):
        self._statuses = list(statuses)
        self.get_paths = []
        self.last_payment_status = None

    def get(self, path):
        self.get_paths.append(path)
        status = self._statuses.pop(0) if self._statuses else _status("released")
        self.last_payment_status = status.get("payment_status")
        return status


@pytest.fixture
def accept_calls(monkeypatch):
    calls = []

    def fake_post(http_client, path, *, json=None, idempotency_key, **kwargs):
        calls.append((path, idempotency_key))
        return {}

    monkeypatch.setattr(_ai, "_post_idempotent", fake_post)
    return calls


def _run_release(http_client, status):
    return _await_payment_release(
        None,
        http_client,
        "job-2951",
        "pay-1",
        status,
        "COMPLETED",
        lambda: False,
        0,
    )


def test_wait_polls_through_escrowed_until_acceptance_window_opens(monkeypatch):
    """escrowed is 'not yet' — no accept fires until pending_acceptance."""
    client = _JobClient([_status("escrowed"), _status("pending_acceptance"), _status("released")])
    posts = []

    def fake_post(http_client, path, *, json=None, idempotency_key, **kwargs):
        # The accept must only fire once a poll has actually observed the
        # acceptance window open — firing while the last seen status is still
        # ``escrowed`` is exactly the #2951 race.
        assert client.last_payment_status == "pending_acceptance"
        posts.append(path)
        return {}

    monkeypatch.setattr(_ai, "_post_idempotent", fake_post)

    final, _ = _run_release(client, _status("escrowed"))

    assert final["payment_status"] == "released"
    assert posts == ["/v1/jobs/job-2951/accept"]


def test_escrowed_at_accept_response_is_retried_with_fresh_key(monkeypatch):
    """A 409 'no payment awaiting acceptance (payment_status=escrowed)' is a
    'not yet', not a refusal — the wait loop retries instead of stalling."""
    calls = []

    def fake_post(http_client, path, *, json=None, idempotency_key, **kwargs):
        calls.append(idempotency_key)
        if len(calls) == 1:
            err = _ai.NetworkError("POST request failed: 409 Client Error")
            err.status = 409  # type: ignore[attr-defined]
            err.detail = "job has no payment awaiting acceptance (payment_status=escrowed)"  # type: ignore[attr-defined]
            raise err
        return {}

    monkeypatch.setattr(_ai, "_post_idempotent", fake_post)
    monkeypatch.setattr(_ai, "http_response_status", lambda e: getattr(e, "status", None))
    monkeypatch.setattr(_ai, "http_error_detail", lambda e: getattr(e, "detail", None))

    client = _JobClient(
        [
            _status("pending_acceptance"),  # after the 409 retry
            _status("released"),
        ]
    )

    final, _ = _run_release(client, _status("pending_acceptance"))

    assert final["payment_status"] == "released"
    assert len(calls) == 2
    # The recorded 409 rejection must not be replayed — each retry uses a new key.
    assert calls[0] != calls[1]


def test_zk_failure_status_breaks_wait_instead_of_timing_out(accept_calls):
    """unsupported_model means the escrow is heading for a refund, not a
    release — surface it now rather than polling to the timeout."""
    client = _JobClient([_status("refunded")])

    final, _ = _run_release(client, _status("escrowed", zk_status="unsupported_model"))

    assert final["zk_status"] == "unsupported_model"
    assert accept_calls == []
    # The terminal check fires before any poll, so the scripted GET is unused.
    assert client.get_paths == []


def test_terminal_payment_status_breaks_wait(accept_calls):
    client = _JobClient([_status("released")])

    final, _ = _run_release(client, _status("refunded", zk_status="not_required"))

    assert final["payment_status"] == "refunded"
    assert accept_calls == []
    assert client.get_paths == []
