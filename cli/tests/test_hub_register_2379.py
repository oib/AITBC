"""#2379 r5: `node hub register|unregister` must not hard-fail on a missing
validator keystore, must accept --island-id/--island-name, and must not
print an empty error reason."""

import sys

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.node import node

# ``node.hub`` on the package is the click Group, not the module — pull the
# real module out of sys.modules.
hub_mod = sys.modules["aitbc_cli.commands.node.hub"]


class _FakeHubManager:
    registered: list[tuple[str, str]] = []
    unregistered: list[str] = []

    def __init__(self, node_id, address, port, island_id, island_name, redis_url):
        self.node_id = node_id
        self.island_id = island_id

    async def register_as_hub(self, public_address, public_port):
        type(self).registered.append((self.node_id, self.island_id))
        return True

    async def unregister_as_hub(self):
        type(self).unregistered.append(self.node_id)
        return True


class _FakeDiscovery:
    def __init__(self, url, port):
        pass

    async def register_hub(self, info):
        return True

    async def unregister_hub(self, node_id):
        return True


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("ISLAND_ID", "ISLAND_NAME"):
        monkeypatch.delenv(var, raising=False)
    # Deterministic missing keystore regardless of host state.
    monkeypatch.setenv("AITBC_VALIDATOR_KEYSTORE", str(tmp_path / "no-such-keystore.json"))
    _FakeHubManager.registered = []
    _FakeHubManager.unregistered = []


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def wired(monkeypatch):
    async def _no_ping(redis_url):
        return None

    monkeypatch.setattr(hub_mod, "_ping_redis", _no_ping)
    monkeypatch.setattr("aitbc_chain.network.hub_manager.HubManager", _FakeHubManager)
    monkeypatch.setattr("aitbc_chain.network.hub_discovery.HubDiscovery", _FakeDiscovery)


def test_register_requires_island_id_flag_or_env(runner):
    result = runner.invoke(node, obj={}, args=["hub", "register", "--public-address", "1.2.3.4"])
    assert result.exit_code != 0
    assert "--island-id" in result.output
    assert "ISLAND_ID" in result.output
    # No empty "Error registering as hub: " tail from a swallowed Abort.
    assert "Error registering as hub:" not in result.output
    assert "Traceback" not in result.output


def test_register_env_island_id_still_works(runner, monkeypatch):
    monkeypatch.setenv("ISLAND_ID", "env-island")
    result = runner.invoke(node, obj={}, args=["hub", "register", "--public-address", "1.2.3.4"])
    # Reaches past island resolution; fails later on unmocked redis ping —
    # the point is it does NOT stop at ISLAND_ID or the keystore.
    assert "ISLAND_ID environment variable not set" not in result.output
    assert "Keystore not found" not in result.output


def test_register_missing_keystore_warns_and_succeeds(runner, wired):
    result = runner.invoke(
        node,
        obj={},
        args=[
            "hub",
            "register",
            "--public-address",
            "1.2.3.4",
            "--island-id",
            "scen05-island",
            "--island-name",
            "test-island",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "validator key" in result.output.lower() or "keystore" in result.output.lower()
    assert "Successfully registered as hub" in result.output
    assert _FakeHubManager.registered and _FakeHubManager.registered[0][1] == "scen05-island"


def test_unregister_missing_keystore_warns_and_succeeds(runner, wired):
    result = runner.invoke(node, obj={}, args=["hub", "unregister", "--island-id", "scen05-island"])
    assert result.exit_code == 0, result.output
    assert "Successfully unregistered as hub" in result.output
    assert _FakeHubManager.unregistered


def test_unregister_requires_island_id(runner):
    result = runner.invoke(node, obj={}, args=["hub", "unregister"])
    assert result.exit_code != 0
    assert "--island-id" in result.output
    assert "Error unregistering as hub:" not in result.output
