"""Tests for the market host (IPFS rental) CLI helpers."""

from unittest.mock import patch

from aitbc_cli.commands.market import host as host_module


class TestResolveIpfsApi:
    """The buyer's local daemon is used, never the provider's offer endpoint."""

    def test_env_wins(self, monkeypatch):
        monkeypatch.setenv("IPFS_API_URL", "http://10.0.0.9:5002")
        offer = {"endpoint": "http://localhost:5001"}
        assert host_module._resolve_ipfs_api(offer) == "http://10.0.0.9:5002"

    def test_ignores_offer_endpoint_and_probes_island_first(self, monkeypatch):
        monkeypatch.delenv("IPFS_API_URL", raising=False)
        offer = {"endpoint": "http://localhost:5001"}
        with patch.object(host_module, "_daemon_available", side_effect=lambda url: url.endswith("5002")):
            assert host_module._resolve_ipfs_api(offer) == "http://127.0.0.1:5002"

    def test_falls_back_to_legacy_kubo(self, monkeypatch):
        monkeypatch.delenv("IPFS_API_URL", raising=False)
        offer = {"endpoint": "http://localhost:5002"}
        with patch.object(host_module, "_daemon_available", side_effect=lambda url: url.endswith("5001")):
            assert host_module._resolve_ipfs_api(offer) == "http://127.0.0.1:5001"

    def test_defaults_to_island_when_nothing_reachable(self, monkeypatch):
        monkeypatch.delenv("IPFS_API_URL", raising=False)
        with patch.object(host_module, "_daemon_available", return_value=False):
            assert host_module._resolve_ipfs_api({}) == "http://127.0.0.1:5002"
