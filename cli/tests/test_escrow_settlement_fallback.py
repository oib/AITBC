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
