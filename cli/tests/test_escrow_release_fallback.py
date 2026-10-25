"""ESCROW-RELEASE-1: release/refund reach the settlement node via the hub
fallback and surface real errors; the job-record leg retries an occupied
nonce slot once at nonce+1.
"""

from types import SimpleNamespace
from typing import cast

import aitbc_cli.commands.market.escrow as esc_mod
import aitbc_cli.commands.market.jobs as jobs_mod


class _Resp:
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self._detail = detail

    def json(self):
        return {"detail": self._detail}


class _StatusError(RuntimeError):
    def __init__(self, status_code: int, detail: str = ""):
        super().__init__(f"HTTP {status_code}")
        self.response = _Resp(status_code, detail)


def _config():
    return SimpleNamespace(
        hub_proposer_id="0xPROP",
        blockchain_rpc_api_key=None,
        hub_discovery_url="https://hub.aitbc.bubuit.net",
        blockchain_rpc_url="http://127.0.0.1:8202",
    )


# --- _post_escrow_rpc: local → hub fallback, failures named -----------------


def test_post_escrow_rpc_falls_back_to_hub(monkeypatch):
    """A settlement-incapable local node (503) falls back to the hub."""

    class _Rpc:
        def __init__(self, base_url, **kw):
            self.base_url = base_url

        def post(self, endpoint, json=None):
            if "hub.aitbc" in self.base_url:
                return {"tx_hash": "0xrel"}
            raise _StatusError(503, "Settlement key/address is not configured correctly")

    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _Rpc(base_url))
    result, failures = esc_mod._post_escrow_rpc(_config(), "/rpc/escrow/j1/release", {})
    assert result == {"tx_hash": "0xrel"}
    assert len(failures) == 1
    assert "HTTP 503" in failures[0]


def test_post_escrow_rpc_names_api_key_refusal(monkeypatch):
    """A 403 refusal must name the API-key cause, not look like an outage."""

    class _Rpc:
        def __init__(self, base_url, **kw):
            pass

        def post(self, endpoint, json=None):
            raise _StatusError(403, "Forbidden")

    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _Rpc(base_url))
    result, failures = esc_mod._post_escrow_rpc(_config(), "/rpc/escrow/j1/release", {})
    assert result is None
    # Both endpoints refused; each failure carries the status and the hint.
    assert len(failures) == 2
    assert all("HTTP 403" in f for f in failures)
    assert all("API key" in f for f in failures)


def test_escrow_release_surfaces_refusal(monkeypatch, capsys):
    """market escrow release prints the real refusal instead of a bare failure."""
    from click.testing import CliRunner

    monkeypatch.setattr(esc_mod, "get_config", _config)
    monkeypatch.setattr(
        esc_mod,
        "_post_escrow_rpc",
        lambda config, path, payload, timeout=10: (None, ["http://x: HTTP 403 Forbidden (RPC requires an API key)"]),
    )
    runner = CliRunner()
    result = runner.invoke(esc_mod.escrow_release, ["--job-id", "j1"], obj={"output_format": "json"})
    assert "HTTP 403" in result.output
    assert "API key" in result.output


def test_refund_escrow_falls_back_with_info_and_error(monkeypatch):
    """Coordinator refund unavailable → info line names the chain fallback;
    a hard RPC refusal → a real error, never a silent None."""
    infos: list[str] = []
    errors: list[str] = []
    monkeypatch.setattr(esc_mod, "get_config", _config)
    monkeypatch.setattr(esc_mod, "_coordinator_refund", lambda ctx, job_id, reason: None)
    monkeypatch.setattr(esc_mod, "info", lambda m: infos.append(m))
    monkeypatch.setattr(esc_mod, "error", lambda m: errors.append(m))
    monkeypatch.setattr(
        esc_mod,
        "_post_escrow_rpc",
        lambda config, path, payload, timeout=10: (None, ["http://x: HTTP 403 Forbidden (RPC requires an API key)"]),
    )
    import click

    out = esc_mod.refund_escrow(cast(click.Context, SimpleNamespace(obj={})), "j1", "buyer_requested")
    assert out is None
    assert any("falling back to the chain rpc" in m for m in infos)
    assert any("HTTP 403" in m and "API key" in m for m in errors)


# --- _record_job_on_chain: occupied-slot retry ------------------------------


class _MarketTxClient:
    """First post refuses with the occupied-slot 400; second accepts."""

    def __init__(self, base_url, **kw):
        self.posts = []

    def post(self, endpoint, json=None):
        self.posts.append(dict(json))
        if len(self.posts) == 1:
            raise _StatusError(400, "nonce slot (0xB, 4) already occupied by 0x4e68 with fee 360000 >= 360000")
        return {"transaction_hash": "0xrecorded"}


def test_record_job_retries_occupied_nonce(monkeypatch):
    client = _MarketTxClient("http://hub")
    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", lambda **kw: client)
    signed: list[dict] = []

    def _sign(data, pk):
        signed.append(dict(data))
        return "sig"

    monkeypatch.setattr(jobs_mod, "sign_transaction_data", _sign)

    job_data = {"from": "0xB", "nonce": 4, "type": "GPU_MARKET", "payload": {"action": "software_job"}}
    tx_hash = jobs_mod._record_job_on_chain(SimpleNamespace(hub_discovery_url="http://hub"), job_data, "deadbeef")
    assert tx_hash == "0xrecorded"
    # Retried exactly once, at nonce+1, re-signed (the signature covers nonce).
    assert [p["nonce"] for p in client.posts] == [4, 5]
    assert [s["nonce"] for s in signed] == [4, 5]


def test_record_job_other_400_not_retried(monkeypatch):
    """A different 400 detail must NOT bump the nonce — one attempt only."""

    class _BadClient:
        def __init__(self, base_url, **kw):
            self.posts = []

        def post(self, endpoint, json=None):
            self.posts.append(dict(json))
            raise _StatusError(400, "Signature required")

    client = _BadClient("http://hub")
    monkeypatch.setattr(jobs_mod, "AITBCHTTPClient", lambda **kw: client)
    monkeypatch.setattr(jobs_mod, "sign_transaction_data", lambda data, pk: "sig")

    job_data = {"from": "0xB", "nonce": 4, "type": "GPU_MARKET", "payload": {}}
    assert jobs_mod._record_job_on_chain(SimpleNamespace(hub_discovery_url="http://hub"), job_data, "dead") is None
    assert len(client.posts) == 1


# --- jobs.py release sites route via the hub fallback ------------------------


def test_run_ollama_release_uses_hub_fallback(monkeypatch):
    """The paid-job release leg must try the hub when the local node 503s —
    not abort the command after the work is done and paid."""
    calls: list[str] = []

    class _Rpc:
        def __init__(self, base_url, **kw):
            self.base_url = base_url

        def post(self, endpoint, json=None):
            calls.append(self.base_url)
            if "hub.aitbc" in self.base_url:
                return {"tx_hash": "0xrel", "released_amount": "0.5"}
            raise _StatusError(503, "Settlement key/address is not configured correctly")

    import urllib.request

    class _FakeResp:
        def read(self):
            import json as _json

            return _json.dumps({"response": "hi", "eval_count": 10}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _Rpc(base_url))
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    monkeypatch.setattr(esc_mod, "_escrow_create", lambda *a, **kw: "contract-1")
    monkeypatch.setattr(jobs_mod, "_escrow_create", lambda *a, **kw: "contract-1")
    monkeypatch.setattr(jobs_mod, "get_chain_id", lambda: "bc-2")
    monkeypatch.setattr(jobs_mod, "get_config", _config)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _FakeResp())

    offer = {
        "service_type": "ollama",
        "model": "m",
        "price": "1",
        "price_unit": "per_1k_tokens",
        "provider_address": "0xP",
        "offer_id": "o1",
    }
    import click

    jobs_mod._run_ollama(
        cast(click.Context, SimpleNamespace(obj={})),
        offer,
        "prompt",
        "0xB",
        "dead",
        512,
        False,
        "json",
        node_wallet="0xW",
    )
    assert calls == ["http://127.0.0.1:8202", "https://hub.aitbc.bubuit.net"]
