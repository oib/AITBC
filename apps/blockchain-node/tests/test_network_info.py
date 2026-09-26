from __future__ import annotations

from aitbc_chain.app import create_app
from aitbc_chain.config import settings
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def _network_info_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix public endpoint values for a deterministic network-info test."""
    monkeypatch.setattr(settings, "chain_id", "ait-testchain.local")
    monkeypatch.setattr(settings, "island_id", "ait-testchain.local-island")
    monkeypatch.setattr(settings, "p2p_node_id", "hub.example.net")
    monkeypatch.setattr(settings, "is_hub", True)
    monkeypatch.setenv("AITBC_PROTOCOL", "https")
    monkeypatch.setenv("AITBC_HOSTNAME", "hub.example.net")


def _fetch_network_info() -> dict:
    with TestClient(create_app()) as client:
        response = client.get(
            "/rpc/network-info",
            headers={"Host": "hub.example.net", "X-Forwarded-Proto": "https"},
        )
        assert response.status_code == 200
        return response.json()


def test_network_info_schema(_network_info_settings) -> None:
    data = _fetch_network_info()
    assert data["node_id"] == "hub.example.net"
    assert data["p2p_node_id"] == "hub.example.net"
    assert data["chain_id"] == "ait-testchain.local"
    assert data["island_id"] == "ait-testchain.local-island"
    assert data["is_hub"] is True
    assert data["role"] == "hub"
    assert data["public_rpc_url"] == "https://hub.example.net/rpc"
    assert data["rpc_endpoint"] == "https://hub.example.net/rpc"
    assert data["public_peer_endpoint"].startswith("https://")
    assert "0.0.0.0" not in data["public_peer_endpoint"]
    assert data["subscription_websocket_url"].startswith("wss://")
    assert data["wss_subscription_endpoint"].startswith("wss://")
    assert data["gossip_websocket_url"].startswith("wss://")
    assert data["gossip_auth_required"] is True
    # Self-serve bootstrap: the sanitized env + genesis are advertised again,
    # plus the /rpc/join issuance endpoint. The node's real env file stays
    # private — bootstrap.env is a sanitized copy (V23-58).
    assert data["bootstrap"]["bootstrap_env_url"].endswith("/agent/bootstrap.env")
    assert data["bootstrap"]["genesis_json_url"].endswith("/agent/genesis.json")
    assert data["bootstrap"]["join_url"].endswith("/rpc/join")
    assert data["bootstrap"]["docs_url"].startswith("https://")
    assert data["bootstrap"]["provisioning"] == "self_serve"
    assert "join" in data
    assert "/agent/blockchain.env" not in str(data["join"])
    assert "/rpc/join" in str(data["join"])


def test_network_info_does_not_leak_secrets(_network_info_settings) -> None:
    data = _fetch_network_info()
    flat = str(data)
    for secret in ("REDIS_URL", "COORDINATOR_API_KEY", "SECRET_KEY", "proposer_key"):
        assert secret not in flat
