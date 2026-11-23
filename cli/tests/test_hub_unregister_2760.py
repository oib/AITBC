"""#2760 — `node hub register|unregister` report registry-vs-DNS outcomes
honestly: a persisted/removed Redis row with a failed DNS discovery call is
partial success (exit 0 + warning), not a flat failure that hides the write.
"""

import sys

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.node import node

hub_mod = sys.modules["aitbc_cli.commands.node.hub"]


class _FakeHubManager:
    registered: list[str] = []
    unregistered: list[str] = []

    def __init__(self, node_id, address, port, island_id, island_name, redis_url):
        self.node_id = node_id
        self.island_id = island_id

    async def register_as_hub(self, public_address, public_port):
        type(self).registered.append(self.node_id)
        return True

    async def unregister_as_hub(self):
        type(self).unregistered.append(self.node_id)
        return True


class _FakeDiscovery:
    dns_ok = True

    def __init__(self, url, port):
        pass

    async def register_hub(self, info):
        return type(self).dns_ok

    async def unregister_hub(self, node_id):
        return type(self).dns_ok


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("ISLAND_ID", "ISLAND_NAME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AITBC_VALIDATOR_KEYSTORE", str(tmp_path / "no-such-keystore.json"))
    _FakeHubManager.registered = []
    _FakeHubManager.unregistered = []
    _FakeDiscovery.dns_ok = True


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


REGISTER_ARGS = [
    "hub",
    "register",
    "--public-address",
    "1.2.3.4",
    "--island-id",
    "scen05-island",
    "--island-name",
    "test-island",
]


class TestPartialReporting:
    def test_register_dns_failure_is_partial_success(self, runner, wired, monkeypatch):
        _FakeDiscovery.dns_ok = False
        result = runner.invoke(node, obj={}, args=REGISTER_ARGS)
        assert result.exit_code == 0, result.output
        assert "Successfully registered as hub" in result.output
        assert "DNS discovery registration failed" in result.output
        assert _FakeHubManager.registered  # the Redis row was written

    def test_register_full_success_has_no_warning(self, runner, wired):
        result = runner.invoke(node, obj={}, args=REGISTER_ARGS)
        assert result.exit_code == 0, result.output
        assert "Successfully registered as hub" in result.output
        assert "DNS discovery registration failed" not in result.output

    def test_unregister_dns_failure_is_partial_success(self, runner, wired):
        _FakeDiscovery.dns_ok = False
        result = runner.invoke(node, obj={}, args=["hub", "unregister", "--island-id", "scen05-island"])
        assert result.exit_code == 0, result.output
        assert "Successfully unregistered as hub" in result.output
        assert "DNS discovery unregistration failed" in result.output
        assert _FakeHubManager.unregistered

    def test_unregister_registry_failure_still_fails(self, runner, wired, monkeypatch):
        async def _no_unregister(self):
            return False

        monkeypatch.setattr(_FakeHubManager, "unregister_as_hub", _no_unregister)
        result = runner.invoke(node, obj={}, args=["hub", "unregister", "--island-id", "scen05-island"])
        assert result.exit_code != 0
        assert "Failed to unregister as hub" in result.output
