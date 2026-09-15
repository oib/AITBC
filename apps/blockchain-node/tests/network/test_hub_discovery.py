"""Tests for HubDiscovery fallback hub configuration."""

import pytest

from aitbc_chain.network.hub_discovery import HubDiscovery


@pytest.fixture()
def discovery() -> HubDiscovery:
    return HubDiscovery("https://discovery.example.net", default_port=7070)


class TestFallbackHubs:
    def test_default_is_empty(self, discovery: HubDiscovery, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(HubDiscovery.FALLBACK_HUBS_ENV, raising=False)
        assert discovery._get_fallback_hubs() == []

    def test_configured_pairs(self, discovery: HubDiscovery, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(HubDiscovery.FALLBACK_HUBS_ENV, "hub1.example.net:7171, hub2.example.net:7272")
        hubs = discovery._get_fallback_hubs()
        assert [(h.address, h.port, h.source) for h in hubs] == [
            ("hub1.example.net", 7171, "fallback"),
            ("hub2.example.net", 7272, "fallback"),
        ]

    def test_default_port_when_omitted(self, discovery: HubDiscovery, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(HubDiscovery.FALLBACK_HUBS_ENV, "hub1.example.net")
        hubs = discovery._get_fallback_hubs()
        assert [(h.address, h.port) for h in hubs] == [("hub1.example.net", 7070)]

    def test_malformed_entries_skipped(
        self, discovery: HubDiscovery, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(HubDiscovery.FALLBACK_HUBS_ENV, "good.example.net:7070,bad:xx,:9999,")
        hubs = discovery._get_fallback_hubs()
        assert [(h.address, h.port) for h in hubs] == [("good.example.net", 7070)]
