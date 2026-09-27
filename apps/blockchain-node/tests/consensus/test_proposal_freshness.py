"""Pre-proposal freshness gate.

2026-09-27: a validator restarting on a stale head forked the fleet because
its sync source could not see peers ahead (hub's was itself). This gate asks
mesh peers for /rpc/head before building a block: peer ahead → pull and skip;
same height → hash vote (rival must strictly outvote us to hold; ties
proceed); all peers unreachable → propose anyway and bump
proposal_freshness_unverified_total. Verdicts cache per head for a few
seconds only — UNVERIFIED never caches — and ahead peers whose pulls don't
move the head get quarantined out of the ahead check.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus import proposal_freshness
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
    return PoAProposer(
        config=config,
        session_factory=lambda: Mock(),
        sync_manager=sync_manager if sync_manager is not None else Mock(),
    )


def _sync_manager() -> Mock:
    sm = Mock()
    sm.pull_from_peer.return_value = True
    sm.pull_in_flight.return_value = False
    return sm


def _head(height: int, block_hash: str):
    return SimpleNamespace(height=height, hash=block_hash)


def _peers(monkeypatch, *urls: str):
    monkeypatch.setattr(settings, "gossip_mesh_peer_urls", ",".join(urls))


def _clock() -> tuple[list[float], object]:
    now = [1000.0]
    return now, lambda: now[0]


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

    async def test_hash_split_minority_holds_majority_proceeds(self):
        """1v3 split: the side holding the minority hash holds, majority proceeds."""
        majority_peers = {
            "https://a.example": {"height": 100, "hash": "0xmaj"},
            "https://b.example": {"height": 100, "hash": "0xmaj"},
            "https://c.example": {"height": 100, "hash": "0xmin"},
        }

        async def fetch(base: str):
            return majority_peers[base]

        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=[f"wss://{h}.example/rpc/gossip/ws" for h in ("a", "b", "c")],
            fetch=fetch,
        )
        # We are the majority: 1 (self) + 2 agreeing peers vs 1 rival.
        result = await checker.check(100, "0xmaj")
        assert result.verdict is FreshnessVerdict.FRESH
        assert result.rival_votes == 1
        assert result.our_votes == 3

        # We are the minority in a 4-validator fleet: all 3 peers hold the
        # rival hash, so it is 1 vs 3 — hold.
        minority_peers = {
            "https://a.example": {"height": 100, "hash": "0xmaj"},
            "https://b.example": {"height": 100, "hash": "0xmaj"},
            "https://c.example": {"height": 100, "hash": "0xmaj"},
        }

        async def fetch_maj(base: str):
            return minority_peers[base]

        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=[f"wss://{h}.example/rpc/gossip/ws" for h in ("a", "b", "c")],
            fetch=fetch_maj,
        )
        result = await checker.check(100, "0xmin")
        assert result.verdict is FreshnessVerdict.HASH_MISMATCH
        assert result.rival_votes == 3
        assert result.our_votes == 1
        assert result.peer_hash == "0xmaj"

    async def test_hash_tie_proceeds(self):
        """A hash vote split must not halt the chain: ties proceed."""
        # 1 (self) + 1 agreeing vs 2 rivals — strictly outvoted → hold
        peers = {
            "https://a.example": {"height": 100, "hash": "0xsame"},
            "https://b.example": {"height": 100, "hash": "0xother"},
            "https://c.example": {"height": 100, "hash": "0xother"},
        }

        async def fetch(base: str):
            return peers[base]

        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=[f"wss://{h}.example/rpc/gossip/ws" for h in ("a", "b", "c")],
            fetch=fetch,
        )
        result = await checker.check(100, "0xsame")
        assert result.verdict is FreshnessVerdict.HASH_TIE  # 2v2: rivals must win STRICTLY
        assert result.our_votes == 2 and result.rival_votes == 2

        # self + one agreeing peer vs one rival → 2v1 minority rival → FRESH
        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=["wss://a.example/rpc/gossip/ws", "wss://b.example/rpc/gossip/ws"],
            fetch=fetch,
        )
        result = await checker.check(100, "0xsame")
        assert result.verdict is FreshnessVerdict.FRESH
        assert result.our_votes == 2 and result.rival_votes == 1

        # self vs one rival only → 1v1 tie → proceed
        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=["wss://b.example/rpc/gossip/ws"],
            fetch=fetch,
        )
        result = await checker.check(100, "0xsame")
        assert result.verdict is FreshnessVerdict.HASH_TIE
        assert result.our_votes == 1 and result.rival_votes == 1

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

    async def test_quarantined_peer_excluded_from_ahead_check(self):
        async def fetch(base: str):
            return {
                "https://a.example": {"height": 105, "hash": "0xa5"},
                "https://b.example": {"height": 100, "hash": "0xsame"},
            }[base]

        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=["wss://a.example/rpc/gossip/ws", "wss://b.example/rpc/gossip/ws"],
            fetch=fetch,
        )
        result = await checker.check(100, "0xsame", quarantined={"https://a.example"})
        assert result.verdict is FreshnessVerdict.QUARANTINED
        assert result.peer_url == "https://a.example"

    async def test_quarantined_peer_still_votes_on_hash(self):
        """Quarantine only affects the ahead check, not same-height hash votes."""
        peers = {
            "https://a.example": {"height": 100, "hash": "0xother"},  # quarantined but at our height
            "https://b.example": {"height": 100, "hash": "0xother"},
            "https://c.example": {"height": 100, "hash": "0xother"},
        }

        async def fetch(base: str):
            return peers[base]

        checker = ProposalFreshnessChecker(
            chain_id="c",
            peer_urls=[f"wss://{h}.example/rpc/gossip/ws" for h in ("a", "b", "c")],
            fetch=fetch,
        )
        result = await checker.check(100, "0xours", quarantined={"https://a.example"})
        assert result.verdict is FreshnessVerdict.HASH_MISMATCH
        assert result.rival_votes == 3

    async def test_malformed_height_counts_as_unreachable(self, monkeypatch):
        """Non-numeric height must not crash check() — the peer is unreachable."""

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"height": "not-a-number", "hash": "0xabc"}

        async def fake_get(url, **kwargs):
            return _Resp()

        monkeypatch.setattr(proposal_freshness.SharedHttpClient, "get", staticmethod(fake_get))
        checker = ProposalFreshnessChecker(chain_id="c", peer_urls=["wss://a.example/rpc/gossip/ws"])
        result = await checker.check(100, "0xours")
        assert result.verdict is FreshnessVerdict.UNVERIFIED


class TestGate:
    async def test_stale_head_blocks_and_pulls_from_ahead_peer(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws", "wss://b.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        sync_manager = _sync_manager()
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

    async def test_minority_hash_blocks_without_pull(self, monkeypatch):
        _peers(
            monkeypatch,
            "wss://a.example/rpc/gossip/ws",
            "wss://b.example/rpc/gossip/ws",
            "wss://c.example/rpc/gossip/ws",
        )
        monkeypatch.setattr(settings, "enable_block_production", True)
        sync_manager = _sync_manager()
        p = _proposer(sync_manager)

        async def fetch(base: str):
            return {"height": 100, "hash": "0xtheirs"}

        p._freshness_fetch = fetch
        ok = await p._passes_freshness_gate(_head(100, "0xours"))
        assert ok is False
        sync_manager.pull_from_peer.assert_not_called()
        assert metrics_registry._counters.get("proposal_freshness_hash_mismatch_total") == 1.0

    async def test_hash_tie_proceeds_and_counts_metric(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        p = _proposer()

        async def fetch(base: str):
            return {"height": 100, "hash": "0xtheirs"}  # 1v1 — tie

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is True
        assert metrics_registry._counters.get("proposal_freshness_hash_tie_total") == 1.0

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

    async def test_unverified_is_never_cached(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        p = _proposer()
        calls = 0

        async def fetch(base: str):
            nonlocal calls
            calls += 1
            return None

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is True
        assert await p._passes_freshness_gate(_head(100, "0xours")) is True
        assert calls == 2  # rechecked, not reused
        assert metrics_registry._counters.get("proposal_freshness_unverified_total") == 2.0

    async def test_cached_fresh_expires_after_ttl(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        monkeypatch.setattr(settings, "proposal_freshness_cache_ttl_seconds", 5.0)
        p = _proposer()
        now, fake_clock = _clock()
        p._monotonic = fake_clock
        calls = 0

        async def fetch(base: str):
            nonlocal calls
            calls += 1
            return {"height": 100, "hash": "0xours"}

        p._freshness_fetch = fetch
        head = _head(100, "0xours")
        assert await p._passes_freshness_gate(head) is True
        assert await p._passes_freshness_gate(head) is True
        assert calls == 1
        now[0] += 6.0  # past the 5 s TTL
        assert await p._passes_freshness_gate(head) is True
        assert calls == 2

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

    async def test_stale_rechecks_and_rekicks_pull_after_ttl(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        monkeypatch.setattr(settings, "proposal_freshness_cache_ttl_seconds", 5.0)
        sync_manager = _sync_manager()
        sync_manager.pull_in_flight.return_value = True  # pull keeps running
        p = _proposer(sync_manager)
        now, fake_clock = _clock()
        p._monotonic = fake_clock

        async def fetch(base: str):
            return {"height": 105, "hash": "0xahead"}

        p._freshness_fetch = fetch
        head = _head(100, "0xours")
        assert await p._passes_freshness_gate(head) is False
        now[0] += 6.0
        assert await p._passes_freshness_gate(head) is False
        # pull re-kicked on each fresh check while stale (deduped inside)
        assert sync_manager.pull_from_peer.call_count == 2

    async def test_failed_pull_quarantines_peer_then_expires(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        monkeypatch.setattr(settings, "proposal_freshness_cache_ttl_seconds", 5.0)
        monkeypatch.setattr(settings, "proposal_freshness_peer_quarantine_seconds", 60.0)
        sync_manager = _sync_manager()
        p = _proposer(sync_manager)
        now, fake_clock = _clock()
        p._monotonic = fake_clock

        async def fetch(base: str):
            return {"height": 105, "hash": "0xahead"}

        p._freshness_fetch = fetch
        head = _head(100, "0xours")

        # 1) peer ahead → STALE, pull kicked and recorded at height 100
        assert await p._passes_freshness_gate(head) is False
        assert p._freshness_pulls == {"https://a.example": 100}

        # 2) pull finished, head unmoved → quarantine → only ahead peer is
        #    excluded → QUARANTINED → proceed
        now[0] += 6.0
        assert await p._passes_freshness_gate(head) is True
        assert metrics_registry._counters.get("proposal_freshness_peer_quarantined_total") == 1.0
        assert "https://a.example" in p._freshness_quarantined

        # 3) quarantine expired → peer counts again → STALE
        now[0] += 70.0
        assert await p._passes_freshness_gate(head) is False
        assert metrics_registry._counters.get("proposal_freshness_stale_total") == 2.0

    async def test_successful_pull_does_not_quarantine(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        monkeypatch.setattr(settings, "proposal_freshness_cache_ttl_seconds", 5.0)
        sync_manager = _sync_manager()
        p = _proposer(sync_manager)
        now, fake_clock = _clock()
        p._monotonic = fake_clock

        heads = {100: {"height": 105, "hash": "0xahead"}, 105: {"height": 105, "hash": "0xahead"}}
        state = {"height": 100}

        async def fetch(base: str):
            return heads[state["height"]]

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is False
        # pull moved the head → peer cleared, no quarantine
        state["height"] = 105
        now[0] += 6.0
        assert await p._passes_freshness_gate(_head(105, "0xahead")) is True
        assert p._freshness_quarantined == {}

    async def test_deduped_pull_is_not_blamed(self, monkeypatch):
        """If pull_from_peer did not start (another pull in flight), the peer is not recorded."""
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        sync_manager = _sync_manager()
        sync_manager.pull_from_peer.return_value = False  # deduped
        sync_manager.pull_in_flight.return_value = True
        p = _proposer(sync_manager)

        async def fetch(base: str):
            return {"height": 105, "hash": "0xahead"}

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is False
        assert p._freshness_pulls == {}  # not recorded → cannot be quarantined

    async def test_stale_without_sync_manager_still_blocks(self, monkeypatch):
        _peers(monkeypatch, "wss://a.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "enable_block_production", True)
        p = _proposer()
        p._sync_manager = None

        async def fetch(base: str):
            return {"height": 105, "hash": "0xahead"}

        p._freshness_fetch = fetch
        assert await p._passes_freshness_gate(_head(100, "0xours")) is False
