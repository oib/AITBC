"""#1260: chain-aware mesh peer resolution for proposer/fan-out paths.

Strict convention (Director ruling): the default chain's peers are the
UNTAGGED ``GOSSIP_MESH_PEER_URLS`` entries; any other chain's peers are the
entries tagged with that chain (``<chain>:`` prefix or ``?chain=<id>``).
Before the fix, the freshness gate, the attestation-lock peer scan and the
REST tx fan-out all used the untagged list — chain-tagged peers were
invisible and an empty list failed open silently.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aitbc_chain.config import settings
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.rpc import transactions as txmod

DEFAULT_CHAIN = "ait-default"
OTHER_CHAIN = "ait-other"


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture
def peer_env(monkeypatch):
    """Default chain + one tagged chain's peers + one untagged peer."""
    monkeypatch.setattr(settings, "chain_id", DEFAULT_CHAIN)
    monkeypatch.setattr(
        settings,
        "gossip_mesh_peer_urls",
        "ws://untagged:8202/rpc/gossip/ws,"
        f"{OTHER_CHAIN}:wss://tagged-a/rpc/gossip/ws,"
        f"wss://tagged-b.example/rpc/gossip/ws?chain={OTHER_CHAIN},"
        "ws://tagged-c:8202/rpc/gossip/ws?chain=unrelated",
    )


def _urls(chain_id):
    return settings.mesh_peer_urls_for_service(chain_id)


class TestServiceResolver:
    def test_default_chain_gets_untagged_only(self, peer_env):
        assert _urls(DEFAULT_CHAIN) == ["ws://untagged:8202/rpc/gossip/ws"]

    def test_none_resolves_to_default(self, peer_env):
        assert _urls(None) == ["ws://untagged:8202/rpc/gossip/ws"]

    def test_tagged_prefix_and_query_both_match(self, peer_env):
        assert set(_urls(OTHER_CHAIN)) == {
            "wss://tagged-a/rpc/gossip/ws",
            "wss://tagged-b.example/rpc/gossip/ws?chain=ait-other",
        }

    def test_unknown_chain_gets_empty(self, peer_env):
        assert _urls("no-such-chain") == []

    def test_default_chain_does_not_honor_its_own_tag(self, peer_env, monkeypatch):
        # Strict convention: a <default>: tagged entry is NOT unioned in.
        monkeypatch.setattr(
            settings,
            "gossip_mesh_peer_urls",
            f"{DEFAULT_CHAIN}:ws://tagged-default/rpc/gossip/ws",
        )
        assert _urls(DEFAULT_CHAIN) == []


class _FakeBackend:
    def __init__(self, url: str):
        self.url = url

    async def start(self) -> None:
        pass

    async def publish(self, topic: str, message: dict) -> None:
        published.append((self.url, topic, message))

    async def shutdown(self) -> None:
        pass


published: list[tuple[str, str, dict]] = []


class TestTxFanoutResolution:
    @pytest.mark.asyncio
    async def test_non_default_chain_fans_out_to_tagged_peers_only(self, peer_env, monkeypatch):
        published.clear()
        monkeypatch.setattr(
            "aitbc_chain.gossip.backends.websocket.WebsocketGossipBackend",
            _FakeBackend,
        )
        import aitbc_chain.gossip.backends.websocket as ws_mod

        monkeypatch.setattr(ws_mod, "WebsocketGossipBackend", _FakeBackend)
        await txmod._fanout_transaction_to_peers(OTHER_CHAIN, {"from": "0x1"})
        urls = {u for u, _, _ in published}
        assert "wss://tagged-a/rpc/gossip/ws" in urls
        assert all("untagged" not in u for u in urls)

    @pytest.mark.asyncio
    async def test_default_chain_still_uses_untagged(self, peer_env, monkeypatch):
        published.clear()
        monkeypatch.setattr(
            "aitbc_chain.gossip.backends.websocket.WebsocketGossipBackend",
            _FakeBackend,
        )
        import aitbc_chain.gossip.backends.websocket as ws_mod

        monkeypatch.setattr(ws_mod, "WebsocketGossipBackend", _FakeBackend)
        await txmod._fanout_transaction_to_peers(DEFAULT_CHAIN, {"from": "0x1"})
        assert {u for u, _, _ in published} == {"ws://untagged:8202/rpc/gossip/ws"}


def _proposer(chain_id: str) -> PoAProposer:
    prop = PoAProposer.__new__(PoAProposer)
    prop._config = SimpleNamespace(chain_id=chain_id)
    prop._logger = Mock()
    prop._monotonic = time.monotonic
    prop._no_peers_warned = {}
    prop._freshness_cache_key = None
    prop._freshness_cache_ok = True
    prop._freshness_cache_expires = 0.0
    prop._freshness_pulls = {}
    prop._freshness_quarantined = {}
    prop._freshness_fetch = None
    prop._sync_manager = Mock()
    prop._remote_attestation = None
    return prop


class TestFreshnessGateResolution:
    @pytest.mark.asyncio
    async def test_non_default_chain_queries_tagged_peers(self, peer_env, monkeypatch):
        seen: list[str] = []

        async def fake_check(self, local_height, local_hash, *, quarantined=None):
            seen.extend(self._peer_urls)
            from aitbc_chain.consensus.proposal_freshness import FreshnessResult, FreshnessVerdict

            return FreshnessResult(FreshnessVerdict.FRESH)

        monkeypatch.setattr(
            "aitbc_chain.consensus.proposal_freshness.ProposalFreshnessChecker.check",
            fake_check,
        )
        monkeypatch.setattr(settings, "enable_block_production", True)
        monkeypatch.setattr(settings, "proposal_freshness_check_enabled", True)
        monkeypatch.setattr(settings, "proposal_freshness_cache_ttl_seconds", 0)
        prop = _proposer(OTHER_CHAIN)
        head = SimpleNamespace(height=5, hash="0xhead")
        assert await prop._passes_freshness_gate(head) is True
        assert set(seen) == {
            "wss://tagged-a/rpc/gossip/ws",
            "wss://tagged-b.example/rpc/gossip/ws?chain=ait-other",
        }

    @pytest.mark.asyncio
    async def test_empty_tagged_peers_warns_once_and_proceeds(self, peer_env, monkeypatch):
        monkeypatch.setattr(
            settings,
            "gossip_mesh_peer_urls",
            "ws://untagged:8202/rpc/gossip/ws",
        )
        monkeypatch.setattr(settings, "enable_block_production", True)
        monkeypatch.setattr(settings, "proposal_freshness_check_enabled", True)
        prop = _proposer(OTHER_CHAIN)
        head = SimpleNamespace(height=5, hash="0xhead")
        assert await prop._passes_freshness_gate(head) is True
        assert await prop._passes_freshness_gate(head) is True
        warns = [c for c in prop._logger.warning.call_args_list if "no peers" in str(c)]
        assert len(warns) == 1
        assert metrics_registry._counters.get("proposal_freshness_no_peers_total") == 1

    @pytest.mark.asyncio
    async def test_empty_peers_on_default_chain_stays_quiet(self, peer_env, monkeypatch):
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "")
        monkeypatch.setattr(settings, "enable_block_production", True)
        monkeypatch.setattr(settings, "proposal_freshness_check_enabled", True)
        prop = _proposer(DEFAULT_CHAIN)
        assert await prop._passes_freshness_gate(SimpleNamespace(height=1, hash="0xh")) is True
        warns = [c for c in prop._logger.warning.call_args_list if "no peers" in str(c)]
        assert warns == []
        assert not metrics_registry._counters.get("proposal_freshness_no_peers_total")


class TestAttestationLockPeerScan:
    @pytest.mark.asyncio
    async def test_scan_queries_tagged_peer_for_locked_block(self, peer_env, monkeypatch):
        """The lock-held peer scan must look on the chain's own tagged peers,
        not the default chain's untagged ones."""
        locked_hash = "0x" + "aa" * 32
        prop = _proposer(OTHER_CHAIN)
        prop._remote_attestation = SimpleNamespace(
            attestation_lock=lambda h, w: (locked_hash, "0xproposer"),
        )

        calls: list[str] = []

        class _Resp:
            status_code = 200

            def json(self):
                return {"hash": locked_hash}

        async def fake_get(url, **kwargs):
            calls.append(url)
            return _Resp()

        monkeypatch.setattr(poa_module.SharedHttpClient, "get", fake_get)
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)
        monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
        monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)

        assert await prop._honor_attestation_lock(10) is True
        assert calls == ["https://tagged-a/rpc/block/10"]
        assert prop._sync_manager.pull_from_peer.called

    @pytest.mark.asyncio
    async def test_empty_tagged_peers_warns_once(self, peer_env, monkeypatch):
        prop = _proposer(OTHER_CHAIN)
        prop._remote_attestation = SimpleNamespace(
            attestation_lock=lambda h, w: ("0x" + "bb" * 32, "0xproposer"),
        )
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)
        monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
        monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)

        monkeypatch.setattr(
            settings,
            "gossip_mesh_peer_urls",
            "ws://untagged:8202/rpc/gossip/ws",
        )
        assert await prop._honor_attestation_lock(11) is True
        assert await prop._honor_attestation_lock(11) is True
        assert await prop._honor_attestation_lock(12) is True
        warns = [c for c in prop._logger.warning.call_args_list if "no peers" in str(c)]
        assert len(warns) == 2  # once per height, not per call
        assert metrics_registry._counters.get("poa_attestation_lock_no_peers_total") == 2
