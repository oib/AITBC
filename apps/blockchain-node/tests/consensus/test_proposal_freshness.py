"""Pre-proposal freshness gate.

2026-09-27: a validator restarting on a stale head forked the fleet because
its sync source could not see peers ahead (hub's was itself). This gate asks
mesh peers for /rpc/head before building a block: peer ahead → pull and skip;
same height different hash → skip; all peers unreachable → propose anyway
(partition must not halt the chain) and bump proposal_freshness_unverified_total.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.proposal_freshness import (
    FreshnessVerdict,
    ProposalFreshnessChecker,
    peer_base_url,
)
from aitbc_chain.metrics import metrics_registry


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _proposer(sync_manager=None) -> PoAProposer:
    config = ProposerConfig(
        chain_id="test-chain",
        proposer_id="test-proposer",
        interval_seconds=1.0,
        max_txs_per_block=10,
        max_block_size_bytes=1_000_000,
    )
    p = PoAProposer(
        config=config,
        session_factory=lambda: Mock(),
        sync_manager=sync_manager if sync_manager is not None else Mock(),
    )
    return p


def _head(height: int, block_hash: str):
    return SimpleNamespace(height=height, hash=block_hash)


def _peers(monkeypatch, *urls: str):
    monkeypatch.setattr(settings, "gossip_mesh_peer_urls", ",".join(urls))


class TestPeerBaseUrl:
    def test_wss_maps_to_https_origin(self):
        assert peer_base_url("wss://hub1.example.com/rpc/gossip/ws") == "https://hub1.example.com"

    def test_ws_maps_to_http_with_port(self):
        assert peer_base_url("ws://10.1.2.3:8202/rpc/gossip/ws") == "http://10.1.2.3:8202"

    def test_non_ws_scheme_rejected(self):
        assert peer_base_url("https://example.com") is None
        assert peer_base_url("redis://127.0.0.1:6379/0") is None
        assert peer_base_url("not a url") is None


class TestChecker:
    async def test_peer_ahead_is_stale_and_reports_max_peer(self):
        async def fetch(base: str):
            return {
                "https://a.example": {"height": 100, "hash": "0xsame"},
                "https://b.example": {"height": 104, "hash": "0xb4"},
                "https://c.example": {"height": 103, "hash": "0xc3"},
            }[base]

        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=["wss://a.example/rpc/gossip/ws", "wss://b.example/rpc/gossip/ws", "wss://c.example/rpc/gossip/ws"],
            fetch=fetch,
        )
        result = await checker.check(100, "0xsame")
        assert result.verdict is FreshnessVerdict.STALE
        assert result.peer_url == "https://b.example"
        assert result.peer_height == 104

    async def test_same_height_same_hash_is_fresh(self):
        async def fetch(base: str):
            return {"height": 100, "hash": "0xsame"}

        checker = ProposalFreshnessChecker(chain_id="c", peer_urls=["wss://a.example/rpc/gossip/ws"], fetch=fetch)
        result = await checker.check(100, "0xsame")
        assert result.verdict is FreshnessVerdict.FRESH

    async def test_same_height_different_hash_is_mismatch(self):
        async def fetch(base: str):
            return {"height": 100, "hash": "0xother"}

        checker = ProposalFreshnessChecker(chain_id="c", peer_urls=["wss://a.example/rpc/gossip/ws"], fetch=fetch)
        result = await checker.check(100, "0xours")
        assert result.verdict is FreshnessVerdict.HASH_MISMATCH
        assert result.peer_url == "https://a.example"

    async def test_peer_behind_does_not_block(self):
        async def fetch(base: str):
            return {"height": 99, "hash": "0xold"}

        checker = ProposalFreshnessChecker(chain_id="c", peer_urls=["wss://a.example/rpc/gossip/ws"], fetch=fetch)
        result = await checker.check(100, "0xours")
        assert result.verdict is FreshnessVerdict.FRESH

    async def test_all_peers_unreachable_is_unverified(self):
        async def fetch(base: str):
            return None

        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=["wss://a.example/rpc/gossip/ws", "wss://b.example/rpc/gossip/ws"],
            fetch=fetch,
        )
        result = await checker.check(100, "0xours")
        assert result.verdict is FreshnessVerdict.UNVERIFIED

    async def test_no_peers_is_fresh(self):
        checker = ProposalFreshnessChecker(chain_id="c", peer_urls=[], fetch=Mock())
        result = await checker.check(100, "0xours")
        assert result.verdict is FreshnessVerdict.FRESH


class TestGate:
    async def test_stale_head_blocks_and_pulls_from_ahead_peer(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws", "wss://b.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        sync_manager = Mock()
        p = _proposer(sync_manager)

        async def fetch(base: str):
            if base == "https://b.example":
                return {"height": 105, "hash": "0xb105"}
            return {"height": 100, "hash": "0xours"}

        p._freshness_fetch = fetch
        ok = await p._passes_freshness_gate(_head(100, "0xours"))
        assert ok is False
        sync_manager.pull_from_peer.assert_called_once_with("test-chain", "https://b.example")
        assert metrics_registry._counters.get("proposal_freshness_stale_total") == 1.0

    async def test_fresh_head_proceeds(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        p = _proposer()

        async def fetch(base: str):
            return {"height": 100, "hash": "0xours"}

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is True

    async def test_hash_mismatch_blocks_without_pull(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        sync_manager = Mock()
        p = _proposer(sync_manager)

        async def fetch(base: str):
            return {"height": 100, "hash": "0xtheirs"}

        p._freshness_fetch = fetch
        ok = await p._passes_freshness_gate(_head(100, "0xours"))
        assert ok is False
        sync_manager.pull_from_peer.assert_not_called()
        assert metrics_registry._counters.get("proposal_freshness_hash_mismatch_total") == 1.0

    async def test_all_unreachable_proposes_and_counts_metric(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws", "wss://b.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        p = _proposer()

        async def fetch(base: str):
            return None

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is True
        assert metrics_registry._counters.get("proposal_freshness_unverified_total") == 1.0

    async def test_never_runs_when_production_disabled(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", False)
        p = _proposer()

        async def fetch(base: str):
            raise AssertionError("freshness check must not run with production disabled")

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is True

    async def test_no_peers_configured_proceeds(self, monkeypatch):
        _peers(monkeypatch)
        monkeypatch.setattr(settings, "enable_block_production", True)
        p = _proposer()
        assert await p._passes_freshness_gate(_head(100, "0xours")) is True

    async def test_verdict_cached_per_head(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        p = _proposer()
        calls = 0

        async def fetch(base: str):
            nonlocal calls
            calls += 1
            return {"height": 105, "hash": "0xahead"}

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is False
        assert await p._passes_freshness_gate(_head(100, "0xours")) is False
        assert calls == 1  # second check at the same head must not refetch
        # a new head re-checks
        assert await p._passes_freshness_gate(_head(105, "0xahead")) is True
        assert calls == 2

    async def test_stale_without_sync_manager_still_blocks(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        p = _proposer(sync_manager=None)
        p._sync_manager = None

        async def fetch(base: str):
            return {"height": 105, "hash": "0xahead"}

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is False
