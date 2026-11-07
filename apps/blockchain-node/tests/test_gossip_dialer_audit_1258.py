"""#1258 (#1159 design v2, G6): every in-repo gossip dialer and peer-URL
consumer works against a host serving more than one gossip chain.

Audit table (what each consumer does, pinned below):

- tx fan-out (``rpc/transactions.py``): used to dial with no chain, which a
  multi-chain peer refuses (1008). Now binds to the chain it publishes for.
- ``/network-info``: advertised only a chain-less ``gossip_websocket_url``;
  now also lists a dialable ``?chain=`` URL per connectable chain.
- ``consensus/proposal_freshness.peer_base_url``: derives the HTTP origin
  from a mesh URL; tolerant of a ``?chain=`` query by construction.
- ``gossip/broker.py`` default-chain dialers already pass ``chain_id``.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from aitbc_chain.consensus.proposal_freshness import peer_base_url
from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend
from aitbc_chain.rpc import transactions as txmod
from aitbc_chain.rpc import websocket as websocket_module
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

DEFAULT = "bc-default"


@pytest.fixture(autouse=True)
def _multi_chain_host(monkeypatch: pytest.MonkeyPatch):
    websocket_module._chain_brokers.clear()
    monkeypatch.setattr(settings, "chain_id", DEFAULT)
    monkeypatch.setattr(settings, "supported_chains", f"{DEFAULT},chain-a,chain-b")
    monkeypatch.setattr(settings, "gossip_backends", "chain-a:memory,chain-b:memory")
    monkeypatch.setattr(settings, "gossip_auth_enabled", False)
    monkeypatch.setattr(settings, "gossip_max_concurrent_connections_per_ip", 1000)
    monkeypatch.setattr(settings, "gossip_max_messages_per_minute", 1_000_000)
    yield
    websocket_module._chain_brokers.clear()


# --- tx fan-out --------------------------------------------------------------


def test_dial_plan_default_chain_binds_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://p1/rpc/gossip/ws,chain-a:wss://pa/rpc/gossip/ws")
    assert txmod._fanout_dial_plan(DEFAULT) == (["wss://p1/rpc/gossip/ws"], DEFAULT)


def test_dial_plan_tagged_chain_uses_only_its_peers_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "gossip_mesh_peer_urls",
        "wss://p1/rpc/gossip/ws,chain-a:wss://pa/rpc/gossip/ws,wss://pb/rpc/gossip/ws?chain=chain-b",
    )
    assert txmod._fanout_dial_plan("chain-a") == (["wss://pa/rpc/gossip/ws"], "chain-a")
    assert txmod._fanout_dial_plan("chain-b") == (["wss://pb/rpc/gossip/ws?chain=chain-b"], "chain-b")


def test_dial_plan_untagged_non_default_chain_has_no_peers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strict #1260 convention, no union: a non-default chain with no tagged
    peers gets an empty peer set (the caller warns), never the default chain's
    untagged peers. The dial stays bound to the chain it is for."""
    monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://p1/rpc/gossip/ws")
    assert txmod._fanout_dial_plan("chain-z") == ([], "chain-z")


class _RecordingBackend:
    dials: list[tuple[str, str | None]] = []
    published: list[tuple[str, str]] = []

    def __init__(self, url: str, chain_id: str | None = None) -> None:
        self.url = url
        self.chain_id = chain_id
        type(self).dials.append((url, chain_id))

    async def start(self) -> None:
        pass

    async def publish(self, topic: str, message: dict) -> None:
        type(self).published.append((self.url, topic))

    async def shutdown(self) -> None:
        pass


@pytest.mark.anyio
@pytest.mark.asyncio
async def test_fanout_dials_are_chain_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    import aitbc_chain.gossip.backends.websocket as ws_mod

    _RecordingBackend.dials = []
    _RecordingBackend.published = []
    monkeypatch.setattr(ws_mod, "WebsocketGossipBackend", _RecordingBackend)
    monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://p1/rpc/gossip/ws,chain-a:wss://pa/rpc/gossip/ws")
    await txmod._fanout_transaction_to_peers(DEFAULT, {"from": "0x1"})
    await txmod._fanout_transaction_to_peers("chain-a", {"from": "0x1"})
    await txmod._fanout_transaction_to_peers("chain-z", {"from": "0x1"})
    assert _RecordingBackend.dials == [
        ("wss://p1/rpc/gossip/ws", DEFAULT),
        ("wss://pa/rpc/gossip/ws", "chain-a"),
    ]
    # chain-z has no tagged peers: strict #1260 convention, so no dial at all
    # (never a legacy unbound dial of the untagged peer).
    assert [t for _u, t in _RecordingBackend.published] == [
        f"transactions.{DEFAULT}",
        "transactions.chain-a",
    ]


def _dial_query(backend: WebsocketGossipBackend, topic: str) -> str:
    return urlsplit(backend._build_url(topic)).query


def test_real_backend_dial_url_carries_the_chain() -> None:
    bound = WebsocketGossipBackend("wss://peer/rpc/gossip/ws", chain_id="chain-a")
    assert parse_qs(_dial_query(bound, "transactions.chain-a"))["chain"] == ["chain-a"]
    legacy = WebsocketGossipBackend("wss://peer/rpc/gossip/ws")
    assert "chain" not in parse_qs(_dial_query(legacy, "transactions.chain-z"))


def test_multi_chain_server_accepts_bound_dial_and_refuses_unbound() -> None:
    """The reason the fan-out needed a chain: the exact query the real dialer
    builds is accepted on a multi-chain host only when it names a chain."""
    bound = WebsocketGossipBackend("wss://peer/rpc/gossip/ws", chain_id="chain-a")
    legacy = WebsocketGossipBackend("wss://peer/rpc/gossip/ws")
    with TestClient(create_app()) as client:
        with client.websocket_connect("/rpc/gossip/ws?" + _dial_query(bound, "transactions.chain-a")):
            pass
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/rpc/gossip/ws?" + _dial_query(legacy, "transactions.chain-a")):
                pass


# --- /network-info -----------------------------------------------------------


def test_network_info_lists_a_dialable_url_per_connectable_chain() -> None:
    with TestClient(create_app()) as client:
        info = client.get("/rpc/network-info").json()
        urls = info["gossip_websocket_urls"]
        assert set(urls) == {DEFAULT, "chain-a", "chain-b"}
        # The pre-existing field is unchanged (no ?chain=), for old consumers.
        assert info["gossip_websocket_url"].endswith("/rpc/gossip/ws")
        for chain, url in urls.items():
            parts = urlsplit(url)
            assert parts.path.endswith("/rpc/gossip/ws")
            assert parse_qs(parts.query) == {"chain": [chain]}
            # ...and the advertised URL actually connects.
            with client.websocket_connect(f"/rpc/gossip/ws?topic=transactions.{chain}&chain={chain}"):
                pass


def test_network_info_single_chain_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supported_chains", DEFAULT)
    monkeypatch.setattr(settings, "gossip_backends", "")
    with TestClient(create_app()) as client:
        info = client.get("/rpc/network-info").json()
    assert list(info["gossip_websocket_urls"]) == [DEFAULT]
    assert info["gossip_websocket_url"].endswith("/rpc/gossip/ws")


def test_network_info_omits_declared_but_unbacked_chains(monkeypatch: pytest.MonkeyPatch) -> None:
    """A chain in supported_chains without a gossip backend is not advertised:
    the server would refuse it."""
    monkeypatch.setattr(settings, "gossip_backends", "chain-a:memory")
    with TestClient(create_app()) as client:
        info = client.get("/rpc/network-info").json()
    assert set(info["gossip_websocket_urls"]) == {DEFAULT, "chain-a"}


# --- proposal_freshness peer_base_url ---------------------------------------


@pytest.mark.parametrize(
    ("gossip_url", "expected"),
    [
        ("wss://hub1.example/rpc/gossip/ws", "https://hub1.example"),
        ("wss://hub1.example/rpc/gossip/ws?chain=chain-a", "https://hub1.example"),
        ("ws://10.0.0.1:8202/rpc/gossip/ws?chain=bc-2.test&topic=blocks", "http://10.0.0.1:8202"),
        ("wss://node1.example/island/rpc/gossip/ws?chain=chain-a", "https://node1.example/island"),
        ("wss://node1.example/rpc/subscribe/ws?chain=chain-a", "https://node1.example"),
        ("wss://hub1.example/rpc/gossip/ws#frag", "https://hub1.example"),
    ],
)
def test_peer_base_url_tolerates_chain_query(gossip_url: str, expected: str) -> None:
    assert peer_base_url(gossip_url) == expected


@pytest.mark.parametrize("raw", ["chain-a:wss://hub1.example/rpc/gossip/ws", "wss://hub1.example/rpc/gossip/ws?chain=chain-a"])
def test_every_tag_form_a_peer_list_returns_maps_to_the_rpc_origin(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """Both chain-tag spellings survive ``mesh_peer_urls_for_chain`` and map to
    the same HTTP origin the freshness check queries."""
    monkeypatch.setattr(settings, "gossip_mesh_peer_urls", raw)
    urls = settings.mesh_peer_urls_for_chain("chain-a")
    assert len(urls) == 1
    assert peer_base_url(urls[0]) == "https://hub1.example"
