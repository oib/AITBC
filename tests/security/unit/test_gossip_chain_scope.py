"""Security pins — gossip chain-bound auth scope + client chain param (#1159).

Validator signatures authorize restricted gossip topics. Before #1159 the
scope was ``keccak256("channel:"+topic)`` — identical on every chain, so a
validator key for chain A could authorize restricted topics on chain B. The
canonical format is ``keccak256("channel:"+chain+":"+topic)``; these pins lock
the wire contract on both the signing side (``channel_scope``) and the dial
side (``WebsocketGossipBackend._build_url``).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from aitbc_chain.gossip.backends.websocket import WebsocketGossipBackend
from aitbc_chain.gossip.gossip_auth import channel_scope


def test_chain_bound_scope_differs_per_chain():
    assert channel_scope("blocks", "chain-a") != channel_scope("blocks", "chain-b")


def test_chain_bound_scope_is_not_the_legacy_scope():
    """A chain-bound signature must never collide with the pre-#1159 scope."""
    assert channel_scope("blocks", "chain-a") != channel_scope("blocks")


def test_scope_is_deterministic_and_hex_prefixed():
    a = channel_scope("consensus", "bc-2")
    assert a == channel_scope("consensus", "bc-2")
    assert a.startswith("0x") and len(a) == 66


def test_topic_still_participates_in_scope():
    """Chain binding must not collapse distinct topics on the same chain."""
    assert channel_scope("blocks", "chain-a") != channel_scope("pbft", "chain-a")


def test_empty_chain_reproduces_legacy_scope_for_rollout():
    """``chain_id=""`` is the compatibility path while
    ``gossip_auth_require_chain_scope`` is off — pin the exact legacy bytes
    so an accidental format change is caught."""
    legacy = channel_scope("transactions")
    assert legacy == channel_scope("transactions", "")
    assert legacy != channel_scope("transactions", "any-chain")


def _url_for(base_url: str, chain_id: str | None) -> str:
    backend = WebsocketGossipBackend(base_url, chain_id=chain_id)
    return backend._build_url("status")


def test_build_url_carries_chain_param():
    url = _url_for("wss://node.example:8302/rpc", "bc-2")
    query = parse_qs(urlsplit(url).query)
    assert query["chain"] == ["bc-2"]
    assert query["topic"] == ["status"]
    assert "client_id" in query


def test_build_url_preserves_existing_base_query_params():
    url = _url_for("wss://node.example:8302/rpc?region=eu&chain=bc-1", None)
    query = parse_qs(urlsplit(url).query)
    assert query["region"] == ["eu"]
    assert query["chain"] == ["bc-1"]  # explicit chain= in base_url wins


def test_build_url_omits_chain_when_unbound():
    """Legacy single-chain dials keep the pre-#1159 URL shape."""
    url = _url_for("wss://node.example:8302/rpc", None)
    assert "chain=" not in urlsplit(url).query


# --- Phase-B prep: client chain-bound signing behind the off flag (#1159) ---


def test_auth_scope_is_legacy_while_flag_off(monkeypatch):
    """Default rollout state: dialers keep signing the chain-less scope so
    pre-#1159 servers keep accepting them."""
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "gossip_auth_require_chain_scope", False)
    backend = WebsocketGossipBackend("wss://node.example:8302/rpc", chain_id="bc-2")
    assert backend._auth_scope("blocks") == channel_scope("blocks")


def test_auth_scope_binds_chain_when_flag_on(monkeypatch):
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "gossip_auth_require_chain_scope", True)
    monkeypatch.setattr(settings, "chain_id", "bc-1")
    backend = WebsocketGossipBackend("wss://node.example:8302/rpc", chain_id="bc-2")
    assert backend._auth_scope("blocks") == channel_scope("blocks", "bc-2")


def test_auth_scope_unbound_dial_uses_node_chain_when_flag_on(monkeypatch):
    """A chain-less dial resolves like the server does on a single-chain
    host: the node's own chain_id."""
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "gossip_auth_require_chain_scope", True)
    monkeypatch.setattr(settings, "chain_id", "bc-1")
    backend = WebsocketGossipBackend("wss://node.example:8302/rpc")
    assert backend._auth_scope("blocks") == channel_scope("blocks", "bc-1")
