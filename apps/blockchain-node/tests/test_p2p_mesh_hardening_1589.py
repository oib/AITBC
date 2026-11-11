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
