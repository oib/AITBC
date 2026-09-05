from __future__ import annotations

from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def _network_info_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix public endpoint values for a deterministic network-info test."""
    monkeypatch.setattr(settings, "chain_id", "ait-hub.aitbc.bubuit.net")
    monkeypatch.setattr(settings, "island_id", "ait-hub.aitbc.bubuit.net-island")
    monkeypatch.setattr(settings, "p2p_node_id", "hub.aitbc.bubuit.net")
    monkeypatch.setattr(settings, "is_hub", True)
    monkeypatch.setenv("AITBC_PROTOCOL", "https")
    monkeypatch.setenv("AITBC_HOSTNAME", "hub.aitbc.bubuit.net")


def _fetch_network_info() -> dict:
    with TestClient(create_app()) as client:
        response = client.get(
            "/rpc/network-info",
            headers={"Host": "hub.aitbc.bubuit.net", "X-Forwarded-Proto": "https"},
        )
        assert response.status_code == 200
        return response.json()


def test_network_info_schema(_network_info_settings) -> None:
    data = _fetch_network_info()
    assert data["node_id"] == "hub.aitbc.bubuit.net"
    assert data["p2p_node_id"] == "hub.aitbc.bubuit.net"
    assert data["chain_id"] == "ait-hub.aitbc.bubuit.net"
    assert data["island_id"] == "ait-hub.aitbc.bubuit.net-island"
    assert data["is_hub"] is True
    assert data["role"] == "hub"
    assert data["public_rpc_url"] == "https://hub.aitbc.bubuit.net/rpc"
    assert data["rpc_endpoint"] == "https://hub.aitbc.bubuit.net/rpc"
    assert data["public_peer_endpoint"].startswith("https://")
    assert "0.0.0.0" not in data["public_peer_endpoint"]
    assert data["subscription_websocket_url"].startswith("wss://")
    assert data["wss_subscription_endpoint"].startswith("wss://")
    assert data["gossip_websocket_url"].startswith("wss://")
    assert data["gossip_auth_required"] is True
    assert data["bootstrap"]["blockchain_env_url"].startswith("https://")
    assert data["bootstrap"]["genesis_json_url"].startswith("https://")
    assert "join" in data


def test_network_info_does_not_leak_secrets(_network_info_settings) -> None:
    data = _fetch_network_info()
    flat = str(data)
    for secret in ("REDIS_URL", "COORDINATOR_API_KEY", "SECRET_KEY", "proposer_key"):
        assert secret not in flat
