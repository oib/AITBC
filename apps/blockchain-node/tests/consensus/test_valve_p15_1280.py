"""#1280 VALVE-P15-1 pins — three-way ``locate_voted_block`` verdict.

A peer serving a DIFFERENT block at the voted height is positive contention
evidence: it suppresses the re-vote path (delay only, never a signature
outside the journal/UC path) while the sighting is fresh and under the fixed
600 s cap. Sealed rivals (self-authenticating attestation quorum in
``block_metadata``) may additionally be pulled when
``vote_journal_sealed_rival_pull`` is armed.

Coverage: the scan's three verdicts, contention bookkeeping (freshness,
cap, sealed detection, throttle), and both gate wirings (attester +
proposer) including the accelerant.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus import vote_fetch
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.vote_fetch import ContentionInfo, contention_hold
from aitbc_chain.consensus.vote_journal import KIND_ATTEST, get_vote_journal, reset_vote_journals
from aitbc_chain.metrics import metrics_registry

from .test_vote_journal_1268 import CHAIN, T0, _Clock, _counter, _request, _service


def _resp(block: dict | None, status: int = 200) -> SimpleNamespace:
    return SimpleNamespace(status_code=status, json=lambda: block if block is not None else {})


def _block(height: int, hash_: str, attestations: int = 0) -> dict:
    return {
        "height": height,
        "hash": hash_,
        "block_metadata": json.dumps({"attestations": [{"validator": f"0xv{i}"} for i in range(attestations)]}),
    }


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    reset_vote_journals()
    vote_fetch.reset_throttle()
    from aitbc_chain.consensus import vote_journal as _vj

    monkeypatch.setattr(_vj, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)
    monkeypatch.setattr(settings, "attestation_lock_enabled", True)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
    monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
    monkeypatch.setattr(settings, "proposal_freshness_peer_timeout_seconds", 0.5)
    monkeypatch.setattr(settings, "multi_validator_min_attestations", 2)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_unlock_seconds", 300.0)
    monkeypatch.setattr(settings, "vote_journal_contention_fresh_seconds", 60.0)
    monkeypatch.setattr(settings, "vote_journal_sealed_rival_pull", False)
    yield
    reset_vote_journals()
    vote_fetch.reset_throttle()
    metrics_registry.reset()


class TestLocateThreeWay:
    @pytest.mark.asyncio
    async def test_found_returns_the_serving_peer(self, monkeypatch):
        get = AsyncMock(return_value=_resp(_block(100, "0xaaaa")))
        monkeypatch.setattr(vote_fetch.SharedHttpClient, "get", get)
        assert await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"}) == "https://peer1.example"
        assert _counter("vote_fetch_found_total") == 1
        assert contention_hold(CHAIN, 100) is None

    @pytest.mark.asyncio
    async def test_rival_at_height_is_contention_not_miss(self, monkeypatch):
        get = AsyncMock(return_value=_resp(_block(100, "0xrival", attestations=0)))
        monkeypatch.setattr(vote_fetch.SharedHttpClient, "get", get)
        assert await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"}) is None
        assert _counter("vote_fetch_contention_total") == 1
        hold = contention_hold(CHAIN, 100)
        assert hold is not None
        assert hold.rival_hash == "0xrival"
        assert hold.sealed is False
        assert hold.base == "https://peer1.example"

    @pytest.mark.asyncio
    async def test_quorum_attestations_mark_the_rival_sealed(self, monkeypatch):
        get = AsyncMock(return_value=_resp(_block(100, "0xrival", attestations=2)))
        monkeypatch.setattr(vote_fetch.SharedHttpClient, "get", get)
        await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"})
        hold = contention_hold(CHAIN, 100)
        assert hold is not None and hold.sealed is True

    @pytest.mark.asyncio
    async def test_no_block_at_height_is_empty(self, monkeypatch):
        get = AsyncMock(return_value=_resp(None, status=404))
        monkeypatch.setattr(vote_fetch.SharedHttpClient, "get", get)
        assert await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"}) is None
        assert _counter("vote_fetch_missing_total") == 1
        assert contention_hold(CHAIN, 100) is None

    @pytest.mark.asyncio
    async def test_contention_is_throttled_like_a_miss(self, monkeypatch):
        get = AsyncMock(return_value=_resp(_block(100, "0xrival")))
        monkeypatch.setattr(vote_fetch.SharedHttpClient, "get", get)
        await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"})
        await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"})
        assert get.await_count == 1
        assert _counter("vote_fetch_contention_total") == 1


class TestContentionHold:
    def _seed(self, monkeypatch, *, now: float = T0):
        clock = _Clock(now)
        monkeypatch.setattr(vote_fetch, "time", clock)
        vote_fetch._note_contention(CHAIN, 100, "0xrival", True, "https://peer1.example", 1)
        return clock

    def test_fresh_sighting_holds(self, monkeypatch):
        self._seed(monkeypatch)
        hold = contention_hold(CHAIN, 100)
        assert hold is not None and hold.sealed is True

    def test_stale_sighting_releases(self, monkeypatch):
        clock = self._seed(monkeypatch)
        clock.advance(61)  # past the 60 s freshness window
        assert contention_hold(CHAIN, 100) is None

    def test_fixed_cap_releases_even_while_fresh(self, monkeypatch):
        clock = self._seed(monkeypatch)
        # Refresh last_seen so freshness never lapses, then cross the 600 s cap.
        clock.advance(590)
        vote_fetch._note_contention(CHAIN, 100, "0xrival", True, "https://peer1.example", 1)
        clock.advance(11)
        assert contention_hold(CHAIN, 100) is None, "600 s contended cap must release"

    def test_sealed_evidence_is_sticky(self, monkeypatch):
        self._seed(monkeypatch)
        vote_fetch._note_contention(CHAIN, 100, "0xunsealed", False, "https://peer2.example", 1)
        hold = contention_hold(CHAIN, 100)
        assert hold is not None
        assert hold.sealed is True, "a later unsealed sighting must not downgrade sealed evidence"
        assert hold.rival_hash == "0xrival"


class TestAttesterContentionGate:
    @pytest.mark.asyncio
    async def test_aged_valve_is_suppressed_by_fresh_contention(self, monkeypatch):
        svc, broker, clock, proposer, _, locate = _service(monkeypatch)
        locate.return_value = None
        monkeypatch.setattr(
            ra_module,
            "contention_hold",
            lambda chain, height, now=None: ContentionInfo("0xrival", False, "https://peer1.example", clock.now, clock.now, 1),
        )
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))
        clock.advance(301)  # past the 300 s valve
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock))

        assert len(broker.published) == 1, "contention must suppress the re-vote"
        assert _counter("vote_journal_contention_hold_total") == 1
        assert _counter("vote_journal_valve_opened_total") == 0

    @pytest.mark.asyncio
    async def test_expired_contention_lets_the_valve_open(self, monkeypatch):
        svc, broker, clock, proposer, _, locate = _service(monkeypatch)
        locate.return_value = None
        monkeypatch.setattr(ra_module, "contention_hold", lambda *a, **k: None)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))
        clock.advance(301)
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock))

        assert len(broker.published) == 2
        assert _counter("vote_journal_valve_opened_total") == 1

    @pytest.mark.asyncio
    async def test_sealed_rival_pull_only_when_flagged(self, monkeypatch):
        svc, broker, clock, proposer, our_addr, locate = _service(monkeypatch)
        pulled: list[tuple[str, str]] = []
        svc.pull_hook = lambda chain, base: pulled.append((chain, base))
        locate.return_value = None
        hold = ContentionInfo("0xrival", True, "https://peer1.example", clock.now, clock.now, 1)
        monkeypatch.setattr(ra_module, "contention_hold", lambda *a, **k: hold)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))
        clock.advance(301)
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock))

        assert pulled == [], "unflagged: no accelerant pull"
        assert _counter("vote_journal_sealed_rival_pull_total") == 0

        # Flag armed: a fresh aged conflict at the same height pulls the sealed rival.
        monkeypatch.setattr(settings, "vote_journal_sealed_rival_pull", True)
        get_vote_journal(CHAIN).record(100, our_addr, "0xcccc", KIND_ATTEST, now=clock.now)
        clock.advance(400)  # age every conflicting vote past the valve
        await svc._handle_request(_request(100, "0xdddd", proposer, clock))
        assert pulled == [(CHAIN, "https://peer1.example")]
        assert _counter("vote_journal_sealed_rival_pull_total") == 1


class TestProposerContentionGate:
    def _proposer(self):
        sm = Mock()
        sm.pull_from_peer.return_value = True
        from aitbc_chain.config import ProposerConfig

        config = ProposerConfig(
            chain_id=CHAIN,
            proposer_id="test-proposer",
            interval_seconds=1.0,
            max_txs_per_block=10,
            max_block_size_bytes=1_000_000,
        )
        return PoAProposer(config=config, session_factory=lambda: Mock(), sync_manager=sm), sm

    @pytest.mark.asyncio
    async def test_contention_suppresses_the_proposal_release(self, monkeypatch):
        from aitbc_chain.consensus import vote_journal

        p, sm = self._proposer()
        clock = _Clock(T0)
        monkeypatch.setattr(vote_journal, "time", clock)
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value=None))
        monkeypatch.setattr(
            poa_module,
            "contention_hold",
            lambda chain, height, now=None: ContentionInfo("0xrival", False, None, T0, T0, 1),
        )
        get_vote_journal(CHAIN).record(100, "0xme", "0xvoted", KIND_ATTEST, now=T0)
        clock.advance(301)  # past the 300 s valve — contention must still hold
        assert await p._honor_vote_journal(100, "0xme") is True
        assert _counter("vote_journal_contention_hold_total") == 1
        assert _counter("vote_journal_valve_opened_total") == 0
        sm.pull_from_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_contention_lets_the_valve_release(self, monkeypatch):
        from aitbc_chain.consensus import vote_journal

        p, _ = self._proposer()
        clock = _Clock(T0)
        monkeypatch.setattr(vote_journal, "time", clock)
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value=None))
        monkeypatch.setattr(poa_module, "contention_hold", lambda *a, **k: None)
        get_vote_journal(CHAIN).record(100, "0xme", "0xvoted", KIND_ATTEST, now=T0)
        clock.advance(301)
        assert await p._honor_vote_journal(100, "0xme") is False
        assert _counter("vote_journal_valve_opened_total") == 1
