"""Hub service URLs come from the node's env files, not a baked-in hostname."""

from __future__ import annotations

from pathlib import Path

import pytest

from aitbc.config.hub import hub_agent_url, hub_discovery_host, hub_exchange_url, hub_service_url


@pytest.fixture
def isolated_env(monkeypatch, tmp_path: Path):
    for name in (
        "HUB_DISCOVERY_URL",
        "HUB_AGENT_URL",
        "HUB_HERMES_URL",
        "HUB_EXCHANGE_URL",
        "EXCHANGE_SERVICE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("aitbc.config.hub._env_files", lambda: (tmp_path / "blockchain.env", tmp_path / "node.env"))
    return tmp_path


def test_nothing_configured_returns_none(isolated_env: Path) -> None:
    assert hub_discovery_host() is None
    assert hub_agent_url() is None
    assert hub_exchange_url() is None


def test_process_env_wins(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")

    assert hub_discovery_host() == "hub.example.net"
    assert hub_agent_url() == "https://hub.example.net/api/v1/agent"
    assert hub_exchange_url() == "https://hub.example.net/exchange"


def test_blockchain_env_file_is_read(isolated_env: Path) -> None:
    (isolated_env / "blockchain.env").write_text("HUB_DISCOVERY_URL=hub.from-chain.net\n")

    assert hub_discovery_host() == "hub.from-chain.net"
    assert hub_service_url("api/v1/agent") == "https://hub.from-chain.net/api/v1/agent"


def test_node_env_overrides_blockchain_env(isolated_env: Path) -> None:
    (isolated_env / "blockchain.env").write_text("HUB_DISCOVERY_URL=hub.from-chain.net\n")
    (isolated_env / "node.env").write_text("HUB_DISCOVERY_URL=hub.from-node.net\n")

    assert hub_discovery_host() == "hub.from-node.net"


def test_scheme_is_stripped_from_discovery_host(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DISCOVERY_URL", "https://hub.example.net/unused")

    assert hub_discovery_host() == "hub.example.net"


def test_explicit_agent_url_is_kept_as_a_base(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_AGENT_URL", "https://hub.example.net/api/v1/agent/")

    assert hub_agent_url() == "https://hub.example.net/api/v1/agent"
