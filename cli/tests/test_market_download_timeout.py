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


# --- #2971: retrieval is not provider-hosting proof -------------------------


class _CatOk:
    status_code = 200

    @property
    def content(self):
        return b"retrieved-bytes"

    def raise_for_status(self):
        return None


class _MarketHostingClient:
    def __init__(self, job_rows=None):
        self.calls = []
        self.job_rows = list(job_rows or [])

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        if url == "/v1/market/jobs/job-1/access":
            return {"cid": "QmResolved"}
        if url == "/v1/market/access/ak-1":
            return {"job_id": "job-1", "cid": "QmResolved"}
        if url == "/v1/market/jobs/job-1":
            if self.job_rows:
                return self.job_rows.pop(0)
            return {
                "job_id": "job-1",
                "state": "RUNNING",
                "payload": {
                    "cid": "QmResolved",
                    "provider_confirmed": True,
                    "provider_confirmed_at": "2026-11-25T15:30:00",
                },
            }
        raise AssertionError(f"unexpected GET {url}")


def _patch_successful_download(monkeypatch, client):
    monkeypatch.setattr(host_mod, "_market_client", lambda: client)
    monkeypatch.setattr(host_mod, "_api_post", lambda path, **kwargs: _CatOk())
    monkeypatch.setattr(host_mod, "_resolve_ipfs_api", lambda offer: "http://127.0.0.1:5002")
    monkeypatch.setattr(host_mod, "_daemon_available", lambda api: True)
    monkeypatch.setattr(host_mod, "get_market_wallet", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no wallet")))


def test_download_output_separates_retrieval_from_provider_attestation(runner, monkeypatch, tmp_path):
    client = _MarketHostingClient()
    _patch_successful_download(monkeypatch, client)
    out = tmp_path / "downloaded.bin"
    result = runner.invoke(
        market,
        [
            "download",
            "--rental-id",
            "job-1",
            "--access-key",
            "ak-1",
            "--access-secret",
            "sec-1",
            "--output-path",
            str(out),
        ],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)
    assert payload["retrieval_source"] == "buyer-local-ipfs"
    assert payload["retrieval_proves_provider_hosting"] is False
    assert payload["job_state"] == "RUNNING"
    assert payload["provider_confirmed"] is True
    assert payload["provider_confirmed_at"] == "2026-11-25T15:30:00"


def _fast_clock(monkeypatch, step=0.02):
    now = {"value": 0.0}

    def monotonic():
        now["value"] += step
        return now["value"]

    monkeypatch.setattr(host_mod.time, "monotonic", monotonic)
    monkeypatch.setattr(host_mod.time, "sleep", lambda seconds: None)


def test_hosting_status_wait_polls_until_provider_confirmed(runner, monkeypatch):
    rows = [
        {"job_id": "job-1", "state": "QUEUED", "payload": {"cid": "QmResolved"}},
        {
            "job_id": "job-1",
            "state": "RUNNING",
            "payload": {"cid": "QmResolved", "provider_confirmed": True, "provider_confirmed_at": "t2"},
        },
    ]
    client = _MarketHostingClient(rows)
    monkeypatch.setattr(host_mod, "_market_client", lambda: client)
    monkeypatch.setattr(host_mod, "get_market_wallet", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no wallet")))
    _fast_clock(monkeypatch)

    result = runner.invoke(
        market,
        [
            "hosting-status",
            "--rental-id",
            "job-1",
            "--access-key",
            "ak-1",
            "--access-secret",
            "sec-1",
            "--wait",
            "--timeout",
            "1",
        ],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)
    assert payload["provider_confirmed"] is True
    assert payload["provider_confirmed_at"] == "t2"
    job_reads = [c for c in client.calls if c["url"] == "/v1/market/jobs/job-1"]
    assert len(job_reads) == 2
    assert job_reads[0]["headers"] == {"X-Access-Key": "ak-1", "X-Access-Secret": "sec-1"}


def test_hosting_status_wait_times_out_nonzero(runner, monkeypatch):
    client = _MarketHostingClient([{"job_id": "job-1", "state": "QUEUED", "payload": {"cid": "QmResolved"}}])
    # Keep returning the same unconfirmed row by copying it for each poll.
    client.job_rows = []
    monkeypatch.setattr(host_mod, "_market_client", lambda: client)
    monkeypatch.setattr(host_mod, "get_market_wallet", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no wallet")))
    _fast_clock(monkeypatch, step=0.04)

    def unconfirmed(url, params=None, headers=None):
        if url == "/v1/market/jobs/job-1":
            return {"job_id": "job-1", "state": "QUEUED", "payload": {"cid": "QmResolved"}}
        return _MarketHostingClient().get(url, params=params, headers=headers)

    monkeypatch.setattr(client, "get", unconfirmed)
    result = runner.invoke(
        market,
        [
            "hosting-status",
            "--rental-id",
            "job-1",
            "--access-key",
            "ak-1",
            "--access-secret",
            "sec-1",
            "--wait",
            "--timeout",
            "0.05",
        ],
        obj={"output_format": "json"},
    )
    assert result.exit_code != 0
    assert "Provider hosting was not confirmed" in result.output


def test_hosting_status_can_resolve_access_token_to_job_id(runner, monkeypatch):
    client = _MarketHostingClient()
    monkeypatch.setattr(host_mod, "_market_client", lambda: client)
    monkeypatch.setattr(host_mod, "get_market_wallet", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no wallet")))
    result = runner.invoke(
        market,
        ["hosting-status", "--access-key", "ak-1", "--access-secret", "sec-1"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    assert client.calls[0]["url"] == "/v1/market/access/ak-1"
    assert client.calls[1]["url"] == "/v1/market/jobs/job-1"
    import json

    assert json.loads(result.output)["provider_confirmed"] is True
