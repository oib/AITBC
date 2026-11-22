"""#2443 MARKET-DOWNLOAD-WAIT-UNBOUNDED-1: `market download --wait` must be
bounded by a user-settable ``--timeout``.

The old ``_cat_ipfs`` polled a fixed 59 attempts x (30s cat + 2s sleep) —
a missing CID could hang the command for ~30 minutes and the player had no
knob to cap it. ``--timeout`` (default 60s) now bounds the whole wait; each
cat attempt is capped at 30s and never exceeds the remaining budget.
"""

import time

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.host as host_mod
from aitbc_cli.commands.market import market


class _Cat500:
    """Kubo answers every /api/v0/cat with a 500 (CID unknown)."""

    status_code = 500

    def raise_for_status(self):
        raise RuntimeError("cat failed: 500")

    @property
    def content(self):
        return b""


@pytest.fixture
def runner():
    return CliRunner()


def _patch_daemon(monkeypatch, response=None):
    calls = []

    def fake_api_post(path, **kwargs):
        calls.append(kwargs.get("timeout"))
        return response if response is not None else _Cat500()

    monkeypatch.setattr(host_mod, "_api_post", fake_api_post)
    monkeypatch.setattr(host_mod, "_resolve_ipfs_api", lambda offer: "http://127.0.0.1:5002")
    monkeypatch.setattr(host_mod, "_daemon_available", lambda api: True)
    return calls


def test_cat_ipfs_wait_honors_timeout_budget(runner, monkeypatch):
    calls = _patch_daemon(monkeypatch)
    start = time.monotonic()
    data = host_mod._cat_ipfs("http://127.0.0.1:5002", "QmMissing", wait=True, timeout_seconds=0.2)
    elapsed = time.monotonic() - start
    assert data is None
    assert elapsed < 5, f"wait overshot its budget: {elapsed:.2f}s"
    # Each attempt's request timeout never exceeds the remaining budget.
    assert all(t is not None and t <= 30.0 for t in calls)
    assert calls, "expected at least one cat attempt"


def test_market_download_wait_missing_cid_exits_within_timeout(runner, monkeypatch):
    _patch_daemon(monkeypatch)
    start = time.monotonic()
    result = runner.invoke(
        market,
        ["download", "--cid", "QmMissing", "--wait", "--timeout", "0.2"],
        obj={"output_format": "json"},
    )
    elapsed = time.monotonic() - start
    assert result.exit_code != 0
    assert "Could not retrieve CID" in result.output
    assert elapsed < 10, f"download --wait overshot --timeout: {elapsed:.2f}s"


def test_market_download_rejects_nonpositive_timeout(runner, monkeypatch):
    _patch_daemon(monkeypatch)
    result = runner.invoke(market, ["download", "--cid", "QmX", "--timeout", "0"], obj={})
    assert result.exit_code != 0
    assert "--timeout must be greater than 0" in result.output


def test_market_download_no_wait_still_single_attempt(runner, monkeypatch):
    calls = _patch_daemon(monkeypatch)
    result = runner.invoke(market, ["download", "--cid", "QmMissing"], obj={})
    assert result.exit_code != 0
    assert len(calls) == 1


# --- #2515: job access route auth -------------------------------------------


def _fake_market_client(calls):
    class _Client:
        def get(self, url, params=None, headers=None):
            calls["url"] = url
            calls["params"] = params
            calls["headers"] = headers
            return {"cid": "QmResolved"}

    return _Client()


def test_resolve_download_cid_signs_job_access_request(monkeypatch):
    """#2515: --rental-id downloads carry a buyer/provider wallet signature."""
    calls: dict = {}
    monkeypatch.setattr(host_mod, "_market_client", lambda: _fake_market_client(calls))
    monkeypatch.setattr(host_mod, "get_chain_id", lambda: "chain-test")
    monkeypatch.setattr(host_mod, "sign_transaction_data", lambda msg, pk: "0xsig")
    seen_messages = []

    real_jobs_request_message = host_mod.jobs_request_message

    def spy(addr, chain_id, issued_at, route, binding=None):
        seen_messages.append((addr, chain_id, issued_at, route, binding))
        return real_jobs_request_message(addr, chain_id, issued_at, route, binding=binding)

    monkeypatch.setattr(host_mod, "jobs_request_message", spy)

    cid = host_mod._resolve_download_cid("http://127.0.0.1:5002", "job-9", None, None, None, signing=("0xBuyer", "0xKey"))
    assert cid == "QmResolved"
    assert calls["url"] == "/v1/market/jobs/job-9/access"
    assert calls["params"]["signer_address"] == "0xBuyer"
    assert calls["params"]["chain_id"] == "chain-test"
    assert calls["params"]["signature"] == "0xsig"
    assert calls["headers"] is None
    addr, chain_id, _iat, route, binding = seen_messages[0]
    assert (addr, chain_id, route, binding) == ("0xBuyer", "chain-test", "/v1/market/jobs/job-9/access", None)


def test_resolve_download_cid_sends_access_credential_headers(monkeypatch):
    """#2515: callers holding the job credential authenticate with headers."""
    calls: dict = {}
    monkeypatch.setattr(host_mod, "_market_client", lambda: _fake_market_client(calls))
    cid = host_mod._resolve_download_cid("http://127.0.0.1:5002", "job-9", "ak-1", "sec-1", None)
    assert cid == "QmResolved"
    assert calls["headers"] == {"X-Access-Key": "ak-1", "X-Access-Secret": "sec-1"}
    assert calls["params"] is None
