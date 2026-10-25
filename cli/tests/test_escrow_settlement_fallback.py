"""PLAY3 escrow settlement fallback: a 503 naming the settlement node
must retry /rpc/escrow/create on that node instead of aborting (SCENARIO-PLAY-3 P4).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

import aitbc_cli.commands.market.escrow as esc_mod

DETAIL = (
    "Settlement key/address is not configured correctly on this node"
    "; the settlement node is at https://hub.aitbc.bubuit.net/rpc"
)


class _Resp:
    def __init__(self, detail: str):
        self.status_code = 503
        self._detail = detail

    def json(self):
        return {"detail": self._detail}


class _HttpError(RuntimeError):
    def __init__(self, detail: str):
        super().__init__("503")
        self.response = _Resp(detail)


class _RefuseLocal:
    """Local RPC refuses with the settlement detail; settlement node accepts."""

    def __init__(self, base_url, **kw):
        self.base_url = base_url

    def post(self, endpoint, json=None):
        assert endpoint == "/rpc/escrow/create"
        if "hub.aitbc" in self.base_url:
            return {"contract_id": "contract-9"}
        raise _HttpError(DETAIL)


def test_settlement_node_url_extracted():
    assert esc_mod._settlement_node_url(DETAIL) == "https://hub.aitbc.bubuit.net"
    assert esc_mod._settlement_node_url("some other refusal") is None


def test_escrow_create_retries_on_settlement_node(monkeypatch):
    calls = []
    orig_post = _RefuseLocal.post

    def post(self, endpoint, json=None):
        calls.append(self.base_url)
        return orig_post(self, endpoint, json=json)

    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _RefuseLocal(base_url))
    monkeypatch.setattr(_RefuseLocal, "post", post)
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    monkeypatch.setattr(
        "aitbc_cli.utils.escrow.create_signed_escrow_lock",
        lambda *a, **kw: ({"tx": "x"}, "sig"),
    )
    monkeypatch.setattr("aitbc_cli.commands.market.get_chain_id", lambda: "bc-2")

    config = SimpleNamespace(
        hub_proposer_id="0xPROP", blockchain_rpc_api_key=None, hub_discovery_url="https://hub.aitbc.bubuit.net"
    )
    contract = esc_mod._escrow_create(
        SimpleNamespace(),
        job_id="j1",
        buyer="0xB",
        provider="0xP",
        amount=Decimal("0.002"),
        config=config,
        private_key="deadbeef",
        node_wallet="0xPROP",
    )
    assert contract == "contract-9"
    assert calls == ["http://127.0.0.1:8202", "https://hub.aitbc.bubuit.net"]


def test_escrow_create_refusal_without_settlement_url_aborts(monkeypatch):
    class _RefuseAll:
        def __init__(self, base_url, **kw):
            pass

        def post(self, endpoint, json=None):
            raise _HttpError("Settlement key/address is not configured correctly on this node")

    import click

    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _RefuseAll(base_url))
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    monkeypatch.setattr(
        "aitbc_cli.utils.escrow.create_signed_escrow_lock",
        lambda *a, **kw: ({"tx": "x"}, "sig"),
    )
    monkeypatch.setattr("aitbc_cli.commands.market.get_chain_id", lambda: "bc-2")
    config = SimpleNamespace(
        hub_proposer_id="0xPROP", blockchain_rpc_api_key=None, hub_discovery_url="https://hub.aitbc.bubuit.net"
    )
    with pytest.raises(click.Abort):
        esc_mod._escrow_create(
            SimpleNamespace(),
            job_id="j1",
            buyer="0xB",
            provider="0xP",
            amount=Decimal("0.002"),
            config=config,
            private_key="deadbeef",
            node_wallet="0xPROP",
        )


def test_escrow_create_refuses_foreign_settlement_url(monkeypatch):
    """A 503 naming a non-hub, non-loopback URL must NOT be retried."""
    import click

    foreign = "https://evil.example.net"

    class _RefuseForeign:
        def __init__(self, base_url, **kw):
            self.base_url = base_url

        def post(self, endpoint, json=None):
            raise _HttpError(f"x; the settlement node is at {foreign}")

    calls = []
    orig = _RefuseForeign.post

    def post(self, endpoint, json=None):
        calls.append(self.base_url)
        return orig(self, endpoint, json=json)

    monkeypatch.setattr(_RefuseForeign, "post", post)
    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _RefuseForeign(base_url))
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    monkeypatch.setattr("aitbc_cli.utils.escrow.create_signed_escrow_lock", lambda *a, **kw: ({"tx": "x"}, "sig"))
    monkeypatch.setattr("aitbc_cli.commands.market.get_chain_id", lambda: "bc-2")
    config = SimpleNamespace(
        hub_proposer_id="0xPROP",
        blockchain_rpc_api_key=None,
        hub_discovery_url="https://hub.aitbc.bubuit.net",
    )
    with pytest.raises(click.Abort):
        esc_mod._escrow_create(
            SimpleNamespace(),
            job_id="j1",
            buyer="0xB",
            provider="0xP",
            amount=Decimal("0.002"),
            config=config,
            private_key="deadbeef",
            node_wallet="0xPROP",
        )
    assert calls == ["http://127.0.0.1:8202"]  # never touched the foreign URL


# --- ESCROW-ROUTE-1: coordinator relay ------------------------------------
#
# Market escrows carry a locally-minted job_id with no coordinator job row,
# so POST /v1/payments cannot serve them. The CLI relays the buyer-signed
# lock to POST /v1/escrow/relay when a client credential exists — the
# coordinator submits /rpc/escrow/create from the hub, inside the nginx
# allowlist. A 404 (older coordinator without the endpoint) falls through
# to the settlement-node retry.


class _RespStatus:
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self._detail = detail

    def json(self):
        return {"detail": self._detail}


class _StatusError(RuntimeError):
    def __init__(self, status_code: int, detail: str = ""):
        super().__init__(f"HTTP {status_code}")
        self.response = _RespStatus(status_code, detail)


class _RelayClient:
    """Stub AITBCHTTPClient for the coordinator relay; records posts."""

    instances: list = []

    def __init__(self, base_url, **kw):
        self.base_url = base_url
        self.kw = kw
        self.posts = []
        _RelayClient.instances.append(self)

    def post(self, endpoint, json=None):
        self.posts.append((endpoint, json))
        if endpoint == "/v1/escrow/relay":
            return {"contract_id": "contract-relay"}
        raise AssertionError(f"unexpected endpoint {endpoint}")


def _ctx(api_key="tok", url="http://coord:8203"):
    return SimpleNamespace(obj={"api_key": api_key, "url": url})


def _config():
    return SimpleNamespace(
        hub_proposer_id="0xPROP", blockchain_rpc_api_key=None, hub_discovery_url="https://hub.aitbc.bubuit.net"
    )


def _patch_lock_signing(monkeypatch):
    monkeypatch.setattr(
        "aitbc_cli.utils.escrow.create_signed_escrow_lock",
        lambda *a, **kw: ({"tx": "x"}, "sig"),
    )
    monkeypatch.setattr("aitbc_cli.commands.market.get_chain_id", lambda: "bc-2")


def test_escrow_create_relays_via_coordinator(monkeypatch):
    """Local RPC refuses; coordinator relay creates the escrow — the node
    RPC and the settlement node are never needed beyond the first try."""

    class _RefuseLocalOnly:
        def __init__(self, base_url, **kw):
            self.base_url = base_url

        def post(self, endpoint, json=None):
            raise _StatusError(503, DETAIL)

    _RelayClient.instances = []
    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _RefuseLocalOnly(base_url))
    monkeypatch.setattr(esc_mod, "AITBCHTTPClient", _RelayClient)
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    _patch_lock_signing(monkeypatch)

    contract = esc_mod._escrow_create(
        _ctx(),
        job_id="sw_job_1",
        buyer="0xB",
        provider="0xP",
        amount=Decimal("0.002"),
        config=_config(),
        private_key="deadbeef",
        node_wallet="0xPROP",
    )
    assert contract == "contract-relay"
    assert len(_RelayClient.instances) == 1
    relay = _RelayClient.instances[0]
    assert relay.base_url == "http://coord:8203"
    assert relay.posts[0][0] == "/v1/escrow/relay"
    assert relay.posts[0][1]["job_id"] == "sw_job_1"
    assert relay.posts[0][1]["lock_tx"]["signature"] == "sig"


def test_escrow_create_relay_404_falls_back_to_settlement(monkeypatch):
    """A coordinator that does not serve /v1/escrow/relay (404) falls
    through to the settlement-node retry unchanged."""

    class _NoRelay(_RelayClient):
        def post(self, endpoint, json=None):
            self.posts.append((endpoint, json))
            raise _StatusError(404, "Not Found")

    class _RefuseLocal:
        def __init__(self, base_url, **kw):
            self.base_url = base_url

        def post(self, endpoint, json=None):
            assert endpoint == "/rpc/escrow/create"
            if "hub.aitbc" in self.base_url:
                return {"contract_id": "contract-9"}
            raise _StatusError(503, DETAIL)

    _RelayClient.instances = []
    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _RefuseLocal(base_url))
    monkeypatch.setattr(esc_mod, "AITBCHTTPClient", _NoRelay)
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    _patch_lock_signing(monkeypatch)

    contract = esc_mod._escrow_create(
        _ctx(),
        job_id="j1",
        buyer="0xB",
        provider="0xP",
        amount=Decimal("0.002"),
        config=_config(),
        private_key="deadbeef",
        node_wallet="0xPROP",
    )
    assert contract == "contract-9"


def test_escrow_create_no_token_skips_relay(monkeypatch):
    """Without a client credential the relay is skipped entirely — no
    coordinator client is constructed."""

    class _RefuseLocal:
        def __init__(self, base_url, **kw):
            self.base_url = base_url

        def post(self, endpoint, json=None):
            if "hub.aitbc" in self.base_url:
                return {"contract_id": "contract-9"}
            raise _StatusError(503, DETAIL)

    _RelayClient.instances = []
    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _RefuseLocal(base_url))
    monkeypatch.setattr(esc_mod, "AITBCHTTPClient", _RelayClient)
    # No stored client credential either — _client_token must return None.
    monkeypatch.setattr(esc_mod, "AuthManager", lambda: SimpleNamespace(get_credential=lambda name: None))
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    _patch_lock_signing(monkeypatch)

    contract = esc_mod._escrow_create(
        _ctx(api_key=None),
        job_id="j1",
        buyer="0xB",
        provider="0xP",
        amount=Decimal("0.002"),
        config=_config(),
        private_key="deadbeef",
        node_wallet="0xPROP",
    )
    assert contract == "contract-9"
    assert _RelayClient.instances == []


def test_escrow_create_relay_error_still_tries_settlement(monkeypatch):
    """A relay failure (non-404) warns and still retries the settlement
    node named in the 503 detail."""

    class _BadRelay(_RelayClient):
        def post(self, endpoint, json=None):
            self.posts.append((endpoint, json))
            raise _StatusError(502, "bad gateway")

    class _RefuseLocal:
        def __init__(self, base_url, **kw):
            self.base_url = base_url

        def post(self, endpoint, json=None):
            if "hub.aitbc" in self.base_url:
                return {"contract_id": "contract-9"}
            raise _StatusError(503, DETAIL)

    _RelayClient.instances = []
    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _RefuseLocal(base_url))
    monkeypatch.setattr(esc_mod, "AITBCHTTPClient", _BadRelay)
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    _patch_lock_signing(monkeypatch)

    contract = esc_mod._escrow_create(
        _ctx(),
        job_id="j1",
        buyer="0xB",
        provider="0xP",
        amount=Decimal("0.002"),
        config=_config(),
        private_key="deadbeef",
        node_wallet="0xPROP",
    )
    assert contract == "contract-9"


def test_node_wallet_prefers_health_over_hub_proposer_id(monkeypatch):
    """When hub_proposer_id and /health disagree, /health must win.

    The escrow `to` is the settlement custody wallet, not the consensus
    proposer id — node0's HUB_PROPOSER_ID is set yet /health names the
    right address (director ruling on #442).
    """
    calls = {}

    class _Rpc:
        def __init__(self, base_url, **kw):
            pass

        def post(self, endpoint, json=None):
            calls["payload"] = json
            return {"contract_id": "c1"}

    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _Rpc(base_url))
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    captured = {}

    def lock(ctx, rpc_url, job_id, buyer, provider, amount, pk, chain_id=None, fee=None, node_wallet=None, **kw):
        captured["node_wallet"] = node_wallet
        return {"tx": "x"}, "sig"

    monkeypatch.setattr("aitbc_cli.utils.escrow.create_signed_escrow_lock", lock)
    monkeypatch.setattr("aitbc_cli.utils.escrow.get_node_wallet", lambda ctx, url: "0xHEALTH")
    monkeypatch.setattr("aitbc_cli.commands.market.get_chain_id", lambda: "bc-2")

    config = SimpleNamespace(
        hub_proposer_id="0xPROP", blockchain_rpc_api_key=None, hub_discovery_url="https://hub.aitbc.bubuit.net"
    )
    esc_mod._escrow_create(
        SimpleNamespace(),
        job_id="j",
        buyer="0xB",
        provider="0xP",
        amount=Decimal("0.001"),
        config=config,
        private_key="dead",
        node_wallet=None,
    )
    assert captured["node_wallet"] == "0xHEALTH"


def test_node_wallet_warned_fallback_to_hub_proposer(monkeypatch, capsys):
    """When /health yields nothing, HUB_PROPOSER_ID is used with a warning."""
    captured = {}

    def lock(ctx, rpc_url, job_id, buyer, provider, amount, pk, chain_id=None, fee=None, node_wallet=None, **kw):
        captured["node_wallet"] = node_wallet
        return {"tx": "x"}, "sig"

    class _Rpc:
        def __init__(self, base_url, **kw):
            pass

        def post(self, endpoint, json=None):
            return {"contract_id": "c1"}

    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: _Rpc(base_url))
    monkeypatch.setattr(esc_mod, "_get_blockchain_rpc_url", lambda config: "http://127.0.0.1:8202")
    monkeypatch.setattr("aitbc_cli.utils.escrow.create_signed_escrow_lock", lock)
    monkeypatch.setattr("aitbc_cli.utils.escrow.get_node_wallet", lambda ctx, url: None)
    monkeypatch.setattr("aitbc_cli.commands.market.get_chain_id", lambda: "bc-2")

    config = SimpleNamespace(
        hub_proposer_id="0xPROP", blockchain_rpc_api_key=None, hub_discovery_url="https://hub.aitbc.bubuit.net"
    )
    esc_mod._escrow_create(
        SimpleNamespace(),
        job_id="j",
        buyer="0xB",
        provider="0xP",
        amount=Decimal("0.001"),
        config=config,
        private_key="dead",
        node_wallet=None,
    )
    assert captured["node_wallet"] == "0xPROP"
    assert "consensus proposer" in capsys.readouterr().out
