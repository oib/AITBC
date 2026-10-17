"""Hub-ward URL fields in CLIConfig resolve to the local nginx on the hub.

The hub's public discovery name terminates TLS at the edge and cannot be
reached from the hub itself (no hairpin). ``aitbc.config.hub`` detects the
self case and answers ``http://127.0.0.1`` — nginx on :80 mounts the same
paths — so every resolved field stays reachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aitbc_cli.config import CLIConfig

_URL_ENVS = (
    "HUB_DISCOVERY_URL",
    "HUB_AGENT_URL",
    "HUB_EXCHANGE_URL",
    "EXCHANGE_SERVICE_URL",
    "HUB_COORDINATOR_URL",
    "COORDINATOR_API_URL",
    "AGENT_COORDINATOR_URL",
    "HUB_P2P_HOST",
    "HUB_RPC_URL",
    "HUB_LOCAL_URL",
    "HUB_BLOCKCHAIN_RPC_URL",
    "BLOCKCHAIN_MODE",
    "NODE_ID",
    "AITBC_HOSTNAME",
    "P2P_NODE_ID",
)


@pytest.fixture
def isolated_hub_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No hub-related env; aitbc.config.hub reads scratch env files."""
    for name in _URL_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "aitbc.config.hub._env_files",
        lambda: (tmp_path / "blockchain.env", tmp_path / "node.env"),
    )
    return tmp_path


def _config(**overrides) -> CLIConfig:
    return CLIConfig(_env_file=[], **overrides)


def test_follower_resolution_uses_public_https(isolated_hub_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "follower")
    monkeypatch.setenv("NODE_ID", "node0.example.net")

    config = _config()

    assert config.coordinator_api_url == "https://hub.example.net/c/v1"
    assert config.agent_coordinator_url == "https://hub.example.net/agent"
    assert config.exchange_service_url == "https://hub.example.net"
    assert config.hub_blockchain_rpc_url == "https://hub.example.net/rpc"


def test_hub_resolution_uses_local_nginx(isolated_hub_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "hub")
    monkeypatch.setenv("NODE_ID", "hub.example.net")

    config = _config()

    assert config.coordinator_api_url == "http://127.0.0.1/c/v1"
    assert config.agent_coordinator_url == "http://127.0.0.1/agent"
    assert config.exchange_service_url == "http://127.0.0.1"
    assert config.hub_blockchain_rpc_url == "http://127.0.0.1/rpc"


def test_unconfigured_hub_invents_nothing(isolated_hub_env: Path) -> None:
    config = _config()

    assert config.hub_blockchain_rpc_url == ""
    assert config.coordinator_api_url == ""
    # exchange falls back to the local blockchain RPC mount, not a made-up host
    assert config.exchange_service_url.endswith("/rpc")


def test_explicit_hub_blockchain_rpc_url_wins(isolated_hub_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    config = _config(hub_blockchain_rpc_url="http://internal:9999/rpc")
    assert config.hub_blockchain_rpc_url == "http://internal:9999/rpc"


def test_discovery_with_explicit_scheme_is_honored(isolated_hub_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """nginx-side deployments can pin http:// without it being upgraded."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "http://hub.example.net:8080")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "follower")

    config = _config()

    assert config.hub_blockchain_rpc_url == "http://hub.example.net:8080/rpc"
    assert config.coordinator_api_url == "http://hub.example.net:8080/c/v1"
