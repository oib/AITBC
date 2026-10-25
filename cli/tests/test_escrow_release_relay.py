"""ESCROW-RELEASE-2: release call sites go through the coordinator JWT
release relay first; the rpc fallback fires only on auth/transport failures,
never on a relay business refusal.
"""

from types import SimpleNamespace
from typing import Any, cast

import click

import aitbc_cli.commands.market.escrow as esc_mod


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
        coordinator_api_url="http://localhost:8203",
    )


def _ctx():
    return cast(click.Context, SimpleNamespace(obj={"output_format": "json"}))


class _RelayClient:
    """Stand-in for the coordinator HTTP client the relay helper builds."""

    posts: list[dict] = []
    result: Any = None
    exc: Exception | None = None

    def __init__(self, **kw):
        self.kw = kw

    def post(self, endpoint, json=None):
        assert endpoint == "/v1/escrow/release"
        self.posts.append(dict(json))
        if self.exc is not None:
            raise self.exc
        return self.result


class _RpcClient:
    """Stand-in for the chain rpc client (posts + gets tracked)."""

    posts: list[dict] = []
    gets: list[str] = []
    post_result: Any = None
    post_exc: Exception | None = None
    get_result: Any = None
    get_exc: Exception | None = None

    def __init__(self, base_url, **kw):
        self.base_url = base_url

    def post(self, endpoint, json=None):
        self.posts.append({"endpoint": endpoint, "json": dict(json or {})})
        if self.post_exc is not None:
            raise self.post_exc
        return self.post_result

    def get(self, endpoint):
        self.gets.append(endpoint)
        if self.get_exc is not None:
            raise self.get_exc
        return self.get_result


def _wire(monkeypatch, relay_cls=None, rpc_cls=None, token="tok"):
    """Patch the client factories; return the class attributes for inspection."""
    relay = relay_cls or _RelayClient
    rpc = rpc_cls or _RpcClient
    relay.posts = []
    relay.result = {"success": True, "tx_hash": "0xrel", "released_amount": "0.5"}
    relay.exc = None
    rpc.posts = []
    rpc.gets = []
    rpc.post_result = {"tx_hash": "0xrpc", "released_amount": "0.5"}
    rpc.post_exc = None
    rpc.get_result = {"job_id": "j1", "amount": "1.0", "buyer": "0xB"}
    rpc.get_exc = None
    monkeypatch.setattr(esc_mod, "AITBCHTTPClient", relay)
    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: rpc(base_url))
    monkeypatch.setattr(esc_mod, "_client_token", lambda ctx: token)
    monkeypatch.setattr(esc_mod, "_coordinator_base_url", lambda ctx: "http://coord")
    return relay, rpc


# --- relay happy path --------------------------------------------------------


def test_release_via_relay_success_no_rpc(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5", job_tx_hash="0xj")
    assert result == {"success": True, "tx_hash": "0xrel", "released_amount": "0.5"}
    assert failures == []
    assert relay.posts == [{"job_id": "j1", "amount": "0.5", "job_tx_hash": "0xj"}]
    # The rpc path was never touched — the relay is authoritative.
    assert rpc.posts == []


def test_release_via_relay_reads_lock_amount_when_unset(monkeypatch):
    """The bare-release sites send no amount: the helper reads the escrow's
    locked amount (GET is not allowlist-blocked) to build the relay body."""
    relay, rpc = _wire(monkeypatch)
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1")
    assert result is not None
    assert relay.posts == [{"job_id": "j1", "amount": "1.0"}]
    assert "/rpc/escrow/j1" in rpc.gets


# --- business refusals are terminal (NO rpc fallback) ------------------------


def test_relay_buyer_mismatch_403_never_falls_back(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(403, "escrow buyer does not match the wallet bound to this credential")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is None
    assert rpc.posts == []
    assert len(failures) == 1
    assert "403" in failures[0] and "buyer" in failures[0]


def test_relay_already_refunded_409_never_falls_back(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(409, "Escrow for job_id=j1 has already been refunded")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is None
    assert rpc.posts == []
    assert "409" in failures[0]


def test_relay_amount_over_lock_400_never_falls_back(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(400, "release amount exceeds the escrow's locked amount")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="9")
    assert result is None
    assert rpc.posts == []
    assert "400" in failures[0]


# --- fallback classes ---------------------------------------------------------


def test_no_credential_falls_back_with_named_hint(monkeypatch):
    relay, rpc = _wire(monkeypatch, token=None)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert relay.posts == []  # relay never attempted
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"
    assert rpc.posts[0]["json"] == {"amount": "0.5"}
    assert any("no stored client credential" in f and "auth login" in f for f in failures)


def test_relay_502_falls_back_to_rpc(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(502, "the escrow release relay could not reach the settlement node")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"
    assert any("relay unavailable" in f and "502" in f for f in failures)


def test_relay_connection_error_falls_back(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = ConnectionError("refused")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert any("relay unavailable" in f for f in failures)


def test_relay_401_falls_back_expired_jwt(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(401, "token expired")
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is not None
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"


def test_relay_404_falls_back_undeployed_endpoint(monkeypatch):
    """An older coordinator without the relay route 404s — the rpc path keeps
    the release working until the fleet is upgraded."""
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(404, "Not Found")
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is not None
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"


def test_amount_unreadable_falls_back(monkeypatch):
    """No amount argument and no readable escrow row → straight to rpc."""
    relay, rpc = _wire(monkeypatch)
    rpc.get_exc = _StatusError(404, "escrow not found")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert relay.posts == []
    assert rpc.posts[0]["json"] == {}
    assert any("amount unreadable" in f for f in failures)


# --- command-level ------------------------------------------------------------


def test_escrow_release_command_relays(monkeypatch):
    from click.testing import CliRunner

    relay, rpc = _wire(monkeypatch)
    monkeypatch.setattr(esc_mod, "get_config", _config)
    result = CliRunner().invoke(esc_mod.escrow_release, ["--job-id", "j1"], obj={"output_format": "json"})
    assert result.exit_code == 0
    assert relay.posts == [{"job_id": "j1", "amount": "1.0"}]
    assert rpc.posts == []
