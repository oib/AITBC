"""P2P dormant TCP mesh hardening (#1589; caps/rate from #1630/#1631)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from aitbc_chain.config import settings
from aitbc_chain.p2p_network import P2PNetworkService


def _service() -> P2PNetworkService:
    return P2PNetworkService(host="127.0.0.1", port=7070, node_id="self", chain_id="c")


def test_inbound_capacity_counts_pending_handshakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "p2p_max_connections", 2)
    monkeypatch.setattr(settings, "p2p_max_connections_per_ip", 8)
    svc = _service()
    svc._pending_inbound_by_ip["10.0.0.1"] = 2
    assert not svc._inbound_capacity_ok("10.0.0.9")


def test_inbound_capacity_per_ip_includes_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "p2p_max_connections", 64)
    monkeypatch.setattr(settings, "p2p_max_connections_per_ip", 2)
    svc = _service()
    svc._pending_inbound_by_ip["10.0.0.1"] = 2
    assert not svc._inbound_capacity_ok("10.0.0.1")


def test_inbound_capacity_ok_with_room(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "p2p_max_connections", 64)
    monkeypatch.setattr(settings, "p2p_max_connections_per_ip", 8)
    svc = _service()
    assert svc._inbound_capacity_ok("10.0.0.5")


def test_prune_peer_session_state_drops_response_maps() -> None:
    svc = _service()
    svc._join_response["peer-a"] = {"type": "join_response"}
    svc._gpu_provider_responses["peer-a"] = {"type": "gpu_provider_response"}
    svc._legacy_peers.add("peer-a")
    svc._prune_peer_session_state("peer-a")
    assert "peer-a" not in svc._join_response
    assert "peer-a" not in svc._gpu_provider_responses
    assert "peer-a" not in svc._legacy_peers


@pytest.mark.asyncio
async def test_listen_stream_rate_limit_breaks_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "p2p_peer_messages_per_second", 1.0)
    monkeypatch.setattr(settings, "p2p_stream_read_timeout_seconds", 5.0)
    svc = _service()

    reader = MagicMock()
    reader.readline = AsyncMock(side_effect=[b'{"type":"ping"}\n'] * 5)

    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=None)
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    monkeypatch.setattr(svc, "_send_message", AsyncMock())
    await svc._listen_to_stream(reader, writer, ("127.0.0.1", 7071), outbound=False, peer_id="flooder")
    assert reader.readline.call_count == 2


def _peer_record(node_id: str = "peer-a", **over) -> dict:
    peer = {
        "node_id": node_id,
        "listen_port": 7071,
        "island_id": "",
        "is_hub": False,
        "chain_id": "c",
        "public_address": None,
        "public_port": None,
        "protocol_version": 1,
        "block_height": 5,
        "block_range": [0, 5],
    }
    peer.update(over)
    return peer


@pytest.mark.asyncio
async def test_inbound_registration_rolls_back_when_reply_send_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUDIT-BN-P2P-INBOUND-FAILED-HANDSHAKE-LEAKS-SLOT-1: a peer registered
    in active_connections whose handshake reply cannot be sent must not
    leave a dead slot squatting the node_id / counting against the caps."""
    svc = _service()
    writer = MagicMock()
    writer.close = MagicMock()
    monkeypatch.setattr(svc, "_send_message", AsyncMock(side_effect=RuntimeError("dead socket")))
    listen = AsyncMock()
    monkeypatch.setattr(svc, "_listen_to_stream", listen)

    with pytest.raises(RuntimeError):
        await svc._register_inbound_peer(MagicMock(), writer, ("10.0.0.9", 5000), _peer_record())

    assert "peer-a" not in svc.active_connections
    assert ("10.0.0.9", 7071) not in svc.connected_endpoints
    assert "peer-a" not in svc._legacy_peers
    listen.assert_not_awaited()


@pytest.mark.asyncio
async def test_inbound_registration_rolls_back_when_capability_callback_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same leak via the sync-layer capability callback raising after the
    slot was taken."""
    svc = _service()

    def _boom(*args, **kwargs):
        raise ValueError("callback blew up")

    svc._peer_capability_callback = _boom
    writer = MagicMock()
    writer.close = MagicMock()
    monkeypatch.setattr(svc, "_send_message", AsyncMock())
    monkeypatch.setattr(svc, "_listen_to_stream", AsyncMock())

    with pytest.raises(ValueError):
        await svc._register_inbound_peer(MagicMock(), writer, ("10.0.0.9", 5000), _peer_record())

    assert "peer-a" not in svc.active_connections
    assert ("10.0.0.9", 7071) not in svc.connected_endpoints
    assert "peer-a" not in svc._legacy_peers
