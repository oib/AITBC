"""Hub service URLs come from the node's env files, not a baked-in hostname."""

from __future__ import annotations

from pathlib import Path

import pytest

from aitbc.config.hub import (
    hub_agent_url,
    hub_coordinator_url,
    hub_discovery_host,
    hub_exchange_url,
    hub_origin,
    hub_service_url,
    is_hub_self,
    normalize_hub_base,
)


@pytest.fixture
def isolated_env(monkeypatch, tmp_path: Path):
    for name in (
        "HUB_DISCOVERY_URL",
        "HUB_AGENT_URL",
        "HUB_HERMES_URL",
        "HUB_EXCHANGE_URL",
        "EXCHANGE_SERVICE_URL",
        "HUB_COORDINATOR_URL",
        "COORDINATOR_API_URL",
        "HUB_P2P_HOST",
        "HUB_RPC_URL",
        "HUB_LOCAL_URL",
        "BLOCKCHAIN_MODE",
        "NODE_ID",
        "AITBC_HOSTNAME",
        "P2P_NODE_ID",
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
    assert hub_agent_url() == "https://hub.example.net/agent"
    assert hub_exchange_url() == "https://hub.example.net"


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
    monkeypatch.setenv("HUB_AGENT_URL", "https://hub.example.net/agent/")

    assert hub_agent_url() == "https://hub.example.net/agent"


def test_hermes_url_is_not_the_agent_coordinator(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HUB_HERMES_URL names the Hermes runner service (/api/v1/hermes), not the
    agent-coordinator — consulting it resolved agent calls at the wrong service
    on nodes that set it (hub1). It is ignored now; discovery still applies."""
    monkeypatch.setenv("HUB_HERMES_URL", "https://hub1.example.net/api/v1/hermes")
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")

    assert hub_agent_url() == "https://hub.example.net/agent"


def test_coordinator_url_defaults_to_public_c_mount(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GAP-18: the public nginx mount is /c/v1 — a bare /v1 hits the gateway."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")

    assert hub_coordinator_url() == "https://hub.example.net/c/v1"


def test_explicit_coordinator_url_is_kept_as_a_base(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_COORDINATOR_URL", "http://coordinator.internal:8203/v1/")

    assert hub_coordinator_url() == "http://coordinator.internal:8203/v1"


def test_exchange_url_defaults_to_bare_hub_origin(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OPS-6: /exchange/ is the wallet service's mount — the signed-order
    routes publish at their natural /api/* paths on the hub host, so the
    discovery-derived default is the bare origin."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")

    assert hub_exchange_url() == "https://hub.example.net"


def test_explicit_exchange_url_is_kept_as_a_base(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_EXCHANGE_URL", "http://exchange.internal:8106/")

    assert hub_exchange_url() == "http://exchange.internal:8106"


def test_explicit_http_scheme_in_discovery_is_honored(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """https is only the default — an explicit http:// is not upgraded."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "http://hub.example.net:8080")

    assert hub_origin() == "http://hub.example.net:8080"
    assert hub_service_url("rpc") == "http://hub.example.net:8080/rpc"


def test_bare_host_defaults_to_https(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")

    assert hub_origin() == "https://hub.example.net"


def test_normalize_hub_base_localhost_gets_http(isolated_env: Path) -> None:
    assert normalize_hub_base("localhost:8202") == "http://localhost:8202"
    assert normalize_hub_base("127.0.0.1") == "http://127.0.0.1"
    assert normalize_hub_base("hub.example.net") == "https://hub.example.net"
    assert normalize_hub_base(None) is None


def test_blockchain_mode_hub_resolves_locally(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """On the hub itself the public name hairpin-fails; every mounted path is
    served by local nginx on :80 with identical routing."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "hub")

    assert is_hub_self() is True
    assert hub_origin() == "http://127.0.0.1"
    assert hub_coordinator_url() == "http://127.0.0.1/c/v1"
    assert hub_agent_url() == "http://127.0.0.1/agent"
    assert hub_exchange_url() == "http://127.0.0.1"
    assert hub_service_url("rpc") == "http://127.0.0.1/rpc"


def test_node_id_match_resolves_locally(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The NODE_ID signal covers a hub whose node.env lost BLOCKCHAIN_MODE."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "follower")
    monkeypatch.setenv("NODE_ID", "hub.example.net")

    assert is_hub_self() is True
    assert hub_origin() == "http://127.0.0.1"


def test_follower_node_id_does_not_self_detect(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """hub1-style env: follower mode + its own NODE_ID — must keep https."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "follower")
    monkeypatch.setenv("NODE_ID", "hub1.example.net")

    assert is_hub_self() is False
    assert hub_origin() == "https://hub.example.net"
    assert hub_coordinator_url() == "https://hub.example.net/c/v1"


def test_node_id_match_needs_discovery_configured(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NODE_ID", "hub.example.net")

    assert is_hub_self() is False
    assert hub_origin() is None


def test_explicit_service_url_still_wins_on_the_hub(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Operator-pinned HUB_*_URL beats self-detection — an escape hatch for
    unusual deployments."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "hub")
    monkeypatch.setenv("HUB_AGENT_URL", "https://agents.example.net/agent")

    assert hub_agent_url() == "https://agents.example.net/agent"


def test_normalize_hub_base_self_rewrites_config_value(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Call sites that pass their own configured hub value get the local
    origin only when the value actually names this node's hub."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "hub")

    assert normalize_hub_base("hub.example.net") == "http://127.0.0.1"
    assert normalize_hub_base("https://hub.example.net") == "http://127.0.0.1"
    # A value naming a different host is not rewritten.
    assert normalize_hub_base("other.example.net") == "https://other.example.net"


def test_blockchain_mode_in_env_file_counts(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    (isolated_env / "node.env").write_text("BLOCKCHAIN_MODE=hub\n")

    assert is_hub_self() is True
    assert hub_origin() == "http://127.0.0.1"


def test_hub_local_url_overrides_the_default_origin(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A hub whose local gateway is not nginx-on-:80 can pin the origin."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "hub")
    monkeypatch.setenv("HUB_LOCAL_URL", "http://127.0.0.1:8002")

    assert hub_origin() == "http://127.0.0.1:8002"
    assert hub_service_url("rpc") == "http://127.0.0.1:8002/rpc"
    assert hub_coordinator_url() == "http://127.0.0.1:8002/c/v1"


def test_hub_local_url_ignored_on_followers(isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The local override only applies when this node is the hub."""
    monkeypatch.setenv("HUB_DISCOVERY_URL", "hub.example.net")
    monkeypatch.setenv("BLOCKCHAIN_MODE", "follower")
    monkeypatch.setenv("HUB_LOCAL_URL", "http://127.0.0.1:8002")

    assert hub_origin() == "https://hub.example.net"
