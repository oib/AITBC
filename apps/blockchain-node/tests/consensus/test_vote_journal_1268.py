"""#1268 Phase 1: durable per-height vote journal, fetch-before-unlock.

Pins the approved scope (operator ruling, #1268 comment 19781):

* every vote (attestation or proposal) is durable before it is released and is
  kept until the height is below the local tip, not until a timer (G3, G4);
* a rival at a height where a different-hash vote is live is refused even after
  the legacy 60 s lock lapsed (G1) and after a restart (G3);
* before the liveness valve may open the voted block is looked up on the mesh
  and pulled (fetch-before-unlock); the valve needs BOTH age and a miss;
* flag off is byte-identical to the pre-#1268 behaviour.

Time is a fake clock injected into both the attester and the journal.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus import vote_fetch, vote_journal
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.vote_journal import (
    KIND_ATTEST,
    KIND_PROPOSE,
    VoteJournal,
    VoteJournalError,
    get_vote_journal,
    reset_vote_journals,
    valve_open,
)
from aitbc_chain.metrics import metrics_registry

T0 = 1_800_000_000.0
CHAIN = "test-chain"


class _Clock:
    def __init__(self, now: float = T0) -> None:
        self.now = now

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Broker:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: str, message: dict) -> None:
        self.published.append(message)


def _keys() -> tuple[str, str, str]:
    from eth_keys import keys

    our_key = "0x" + "11" * 32
    proposer_key = "0x" + "22" * 32
    our_addr = keys.PrivateKey(bytes.fromhex(our_key[2:])).public_key.to_checksum_address()
    proposer_addr = keys.PrivateKey(bytes.fromhex(proposer_key[2:])).public_key.to_checksum_address()
    return our_addr, our_key, proposer_addr


def _ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).replace(tzinfo=None).isoformat()


def _request(height: int, block_hash: str, proposer: str, clock: _Clock) -> dict:
    return {
        "header": {
            "chain_id": CHAIN,
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
            "timestamp": _ts(clock.now),
        },
        "timestamp": clock.now,
    }


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    reset_vote_journals()
    vote_fetch.reset_throttle()
    # Every persisted file lands in tmp: the journal and the attestation
    # stores must not leak between tests (the A/E conftest-isolation lesson).
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)
    monkeypatch.setattr(settings, "attestation_lock_enabled", True)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_unlock_seconds", 300.0)
    yield
    reset_vote_journals()
    metrics_registry.reset()


def _service(monkeypatch, *, miss: bool = True):
    our_addr, our_key, proposer = _keys()
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": our_addr}, {"address": proposer}]))
    broker = _Broker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    clock = _Clock()
    monkeypatch.setattr(ra_module, "time", clock)
    monkeypatch.setattr(vote_journal, "time", clock)
    locate = AsyncMock(return_value=None)
    monkeypatch.setattr(ra_module, "locate_voted_block", locate)
    svc = RemoteAttestationService(CHAIN, {our_addr: our_key})
    return svc, broker, clock, proposer, our_addr, locate


class TestJournalUnit:
    def test_vote_survives_a_restart(self, tmp_path):
        path = tmp_path / "vj.json"
        VoteJournal(CHAIN, path).record(100, "0xAbC", "0xaaaa", KIND_ATTEST, 3, "0xprop", now=T0)
        reloaded = VoteJournal(CHAIN, path)
        votes = reloaded.votes_at(100, "0xabc")
        assert [(v.block_hash, v.kind, v.round) for v in votes] == [("0xaaaa", KIND_ATTEST, 3)]
        assert reloaded.conflicting(100, "0xabc", "0xbbbb")[0].block_hash == "0xaaaa"
        assert reloaded.conflicting(100, "0xabc", "0xaaaa") == []

    def test_repeat_of_the_same_vote_is_a_no_op(self, tmp_path):
        j = VoteJournal(CHAIN, tmp_path / "vj.json")
        assert j.record(7, "0xv", "0xaaaa", KIND_ATTEST) is True
        assert j.record(7, "0xv", "0xaaaa", KIND_ATTEST) is False
        assert len(j.votes_at(7, "0xv")) == 1

    def test_persist_failure_refuses_the_vote_and_leaves_no_trace(self, tmp_path, monkeypatch):
        j = VoteJournal(CHAIN, tmp_path / "vj.json")

        def boom() -> None:
            raise OSError("disk full")

        monkeypatch.setattr(j, "_persist", boom)
        with pytest.raises(VoteJournalError):
            j.record(7, "0xv", "0xaaaa", KIND_ATTEST)
        assert j.votes_at(7, "0xv") == []
        assert j.height_count() == 0
        assert _counter("vote_journal_persist_failed_total") == 1

    def test_prune_is_by_height_never_by_clock(self, tmp_path):
        j = VoteJournal(CHAIN, tmp_path / "vj.json")
        for h in (98, 99, 100):
            j.record(h, "0xv", f"0x{h}", KIND_ATTEST, now=T0 - 10_000_000)  # ancient by wall clock
        assert j.prune_below(None) == 0  # no tip: nothing is dropped, however old
        assert j.votes_at(100, "0xv") and j.votes_at(99, "0xv")
        assert j.prune_below(100) == 2  # strictly below the tip
        assert j.votes_at(100, "0xv")
        assert j.votes_at(99, "0xv") == []
        # and the prune is durable
        assert VoteJournal(CHAIN, tmp_path / "vj.json").height_count() == 1

    def test_retract_voids_only_the_named_hash(self, tmp_path):
        j = VoteJournal(CHAIN, tmp_path / "vj.json")
        j.record(5, "0xv", "0xaaaa", KIND_PROPOSE)
        j.record(5, "0xv", "0xbbbb", KIND_PROPOSE)
        assert j.retract(5, "0xv", "0xaaaa") is True
        assert [v.block_hash for v in j.votes_at(5, "0xv")] == ["0xbbbb"]
        assert j.retract(5, "0xv", "0xaaaa") is False

    def test_corrupt_file_degrades_to_empty_and_is_counted(self, tmp_path):
        path = tmp_path / "vj.json"
        path.write_text("{not json")
        assert VoteJournal(CHAIN, path).votes_at(1, "0xv") == []
        assert _counter("vote_journal_load_failed_total") == 1

    def test_wrong_chain_file_is_ignored(self, tmp_path):
        path = tmp_path / "vj.json"
        VoteJournal("other-chain", path).record(1, "0xv", "0xaaaa", KIND_ATTEST)
        assert VoteJournal(CHAIN, path).votes_at(1, "0xv") == []

    def test_valve_needs_age_and_a_positive_window(self):
        rec = VoteJournal(CHAIN, None).record  # noqa: F841 - constructed only to prove no I/O at init
        v = SimpleNamespace(at=T0)
        assert valve_open(v, 300.0, now=T0 + 299) is False
        assert valve_open(v, 300.0, now=T0 + 300) is True
        assert valve_open(v, 0.0, now=T0 + 10**9) is False  # 0 = never opens


class TestAttesterGate:
    @pytest.mark.asyncio
    async def test_rival_refused_after_the_legacy_lock_lapses(self, monkeypatch):
        """G1: the 60 s lock expired and the voter never imported the first
        block. Pre-#1268 this signed the rival."""
        svc, broker, clock, proposer, _, _ = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))
        assert len(broker.published) == 1

        clock.advance(61)  # legacy window gone
        assert svc.attestation_lock(100, 60.0) is None
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock))

        assert len(broker.published) == 1, "rival was signed after the legacy lock lapsed"
        assert _counter("vote_journal_refused_rival_total") == 1

    @pytest.mark.asyncio
    async def test_rival_refused_after_a_restart(self, monkeypatch):
        """G3: a fresh process (new service, journal cache dropped) still knows."""
        svc, broker, clock, proposer, our_addr, _ = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))

        reset_vote_journals()  # "restart": only the file remains
        svc2 = RemoteAttestationService(CHAIN, {our_addr: _keys()[1]})
        await svc2._handle_request(_request(100, "0xbbbb", proposer, clock))

        assert len(broker.published) == 1
        assert _counter("vote_journal_refused_rival_total") == 1

    @pytest.mark.asyncio
    async def test_same_hash_republish_is_unaffected(self, monkeypatch):
        svc, broker, clock, proposer, _, _ = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock)
        await svc._handle_request(req)
        await svc._handle_request(req)
        assert len(broker.published) == 2
        assert len(get_vote_journal(CHAIN).votes_at(100, _keys()[0])) == 1

    @pytest.mark.asyncio
    async def test_proposers_own_vote_blocks_attesting_a_rival(self, monkeypatch):
        """G4: we proposed B1 at h (vote recorded) and now a peer asks us to
        attest a rival B2 at h."""
        svc, broker, clock, proposer, our_addr, _ = _service(monkeypatch)
        get_vote_journal(CHAIN).record(100, our_addr, "0xmine", KIND_PROPOSE, 0, our_addr, now=clock.now)

        await svc._handle_request(_request(100, "0xrival", proposer, clock))

        assert broker.published == []
        assert _counter("vote_journal_refused_rival_total") == 1

    @pytest.mark.asyncio
    async def test_fetch_before_unlock_pulls_and_refuses_even_past_the_valve(self, monkeypatch):
        svc, broker, clock, proposer, our_addr, locate = _service(monkeypatch)
        pulled: list[tuple[str, str]] = []
        svc.pull_hook = lambda chain, base: pulled.append((chain, base))
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))

        clock.advance(10_000)  # far beyond the unlock window
        locate.return_value = "https://peer1.example"  # but a peer serves the voted block
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock))

        assert len(broker.published) == 1
        assert pulled == [(CHAIN, "https://peer1.example")]
        assert locate.await_args.args == (CHAIN, 100, {"0xaaaa"})

    @pytest.mark.asyncio
    async def test_valve_opens_only_on_age_and_miss_and_records_evidence(self, monkeypatch):
        svc, broker, clock, proposer, our_addr, locate = _service(monkeypatch)
        recorder = Mock()
        monkeypatch.setattr(svc, "_equivocation_recorder", lambda: recorder)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))

        clock.advance(299)  # not old enough, nobody serves it
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock))
        assert len(broker.published) == 1

        clock.advance(2)  # now old enough AND no peer serves the voted block
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock))
        assert len(broker.published) == 2
        assert _counter("vote_journal_valve_opened_total") == 1
        # the rival signing is certified against the journal's prior vote
        recorder.record_attestation_equivocation.assert_called_once()
        kwargs = recorder.record_attestation_equivocation.call_args.kwargs
        assert {kwargs["block_hash_a"], kwargs["block_hash_b"]} == {"0xaaaa", "0xbbbb"}

    @pytest.mark.asyncio
    async def test_journal_write_failure_means_no_signature(self, monkeypatch):
        svc, broker, clock, proposer, _, _ = _service(monkeypatch)
        monkeypatch.setattr(VoteJournal, "_persist", lambda self: (_ for _ in ()).throw(OSError("read-only filesystem")))
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))
        assert broker.published == [], "a signature left the process without a durable vote"

    @pytest.mark.asyncio
    async def test_flag_off_is_the_pre_1268_behaviour(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "vote_journal_enabled", False)
        svc, broker, clock, proposer, our_addr, locate = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock))
        clock.advance(61)  # legacy window lapses -> the old rival-after-expiry behaviour
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock))

        assert len(broker.published) == 2
        locate.assert_not_awaited()
        assert not list(tmp_path.rglob("vote_journal.json")), "flag off must not create a journal file"
        assert _counter("vote_journal_recorded_attest_total") == 0


class TestProposerGate:
    def _proposer(self):
        sm = Mock()
        sm.pull_from_peer.return_value = True
        config = ProposerConfig(
            chain_id=CHAIN,
            proposer_id="test-proposer",
            interval_seconds=1.0,
            max_txs_per_block=10,
            max_block_size_bytes=1_000_000,
        )
        return PoAProposer(config=config, session_factory=lambda: Mock(), sync_manager=sm), sm

    @pytest.mark.asyncio
    async def test_prior_vote_suppresses_proposal_and_pulls_the_voted_block(self, monkeypatch):
        p, sm = self._proposer()
        get_vote_journal(CHAIN).record(100, "0xme", "0xvoted", KIND_ATTEST, now=T0)
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value="https://peer1.example"))

        assert await p._honor_vote_journal(100, "0xme") is True
        sm.pull_from_peer.assert_called_once_with(CHAIN, "https://peer1.example")

    @pytest.mark.asyncio
    async def test_unserved_young_vote_holds_and_old_vote_releases(self, monkeypatch):
        p, _ = self._proposer()
        clock = _Clock()
        monkeypatch.setattr(vote_journal, "time", clock)
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value=None))
        get_vote_journal(CHAIN).record(100, "0xme", "0xvoted", KIND_PROPOSE, now=clock.now)

        clock.advance(100)
        assert await p._honor_vote_journal(100, "0xme") is True
        clock.advance(201)
        assert await p._honor_vote_journal(100, "0xme") is False
        assert _counter("vote_journal_valve_opened_total") == 1

    @pytest.mark.asyncio
    async def test_no_vote_and_flag_off_do_not_suppress(self, monkeypatch):
        p, _ = self._proposer()
        locate = AsyncMock(return_value=None)
        monkeypatch.setattr(poa_module, "locate_voted_block", locate)
        assert await p._honor_vote_journal(100, "0xme") is False
        get_vote_journal(CHAIN).record(100, "0xme", "0xvoted", KIND_ATTEST, now=T0)
        monkeypatch.setattr(settings, "vote_journal_enabled", False)
        assert await p._honor_vote_journal(100, "0xme") is False
        locate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_decided_height_is_pruned_when_the_tip_passes_it(self, monkeypatch):
        p, _ = self._proposer()
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value=None))
        get_vote_journal(CHAIN).record(100, "0xme", "0xvoted", KIND_ATTEST, now=T0)
        # proposing at 102 means the tip is 101: height 100 is decided history
        assert await p._honor_vote_journal(102, "0xme") is False
        assert get_vote_journal(CHAIN).votes_at(100, "0xme") == []

    def test_record_and_retract_proposal_vote(self):
        p, _ = self._proposer()
        assert p._record_proposal_vote(None, 100, "0xmine", "0xme", 2) is True
        assert [v.kind for v in get_vote_journal(CHAIN).votes_at(100, "0xme")] == [KIND_PROPOSE]
        p._retract_proposal_vote(100, "0xmine", "0xme")
        assert get_vote_journal(CHAIN).votes_at(100, "0xme") == []

    def test_unwritable_journal_aborts_the_proposal(self, monkeypatch):
        p, _ = self._proposer()
        monkeypatch.setattr(VoteJournal, "_persist", lambda self: (_ for _ in ()).throw(OSError("ro")))
        session = Mock()
        assert p._record_proposal_vote(session, 100, "0xmine", "0xme", 2) is False
        session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_failed_gates_retract_the_proposal_vote_and_success_keeps_it(monkeypatch):
    """The wiring pin: a rolled-back proposal can never seal, so its vote is
    voided; a sealed one stays so the proposer cannot attest a rival."""

    @contextmanager
    def _null_session():
        yield None

    config = ProposerConfig(
        chain_id=CHAIN, proposer_id="test-node", interval_seconds=1, max_block_size_bytes=1000, max_txs_per_block=100
    )
    me = "0x" + "0" * 40

    async def run(gates_ok: bool) -> PoAProposer:
        proposer = PoAProposer(config=config, session_factory=_null_session)
        head = SimpleNamespace(timestamp=datetime.now(UTC))
        block = SimpleNamespace(block_metadata="")

        async def _gates(*_a, **_k):
            return gates_ok

        async def _early(*_a, **_k):
            return SimpleNamespace()

        async def _bcast(*_a, **_k):
            return True

        monkeypatch.setattr(proposer, "_passes_early_gates", _early)
        monkeypatch.setattr(proposer, "_resolve_proposal_head", lambda *_: (head, 100, "0xparent", 1))
        monkeypatch.setattr(proposer, "_select_round_proposer", lambda *_: (me, 0))
        monkeypatch.setattr(proposer, "_collect_proposal_txs", lambda *_, **__: ([], {}, {}, set()))
        monkeypatch.setattr(proposer, "_process_proposal_txs", lambda *_: ([], set(), True))
        monkeypatch.setattr(proposer, "_reject_if_all_invalid", lambda *_: False)
        monkeypatch.setattr(proposer, "_assemble_proposal_block", lambda *_: (block, "0xnewhash"))
        monkeypatch.setattr(proposer, "_run_consensus_gates", _gates)
        monkeypatch.setattr(proposer, "_sign_block_hash_for", lambda *_: "sig")
        monkeypatch.setattr(proposer, "_commit_and_record_block", lambda *_: None)
        monkeypatch.setattr(proposer, "_broadcast_block", _bcast)
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value=None))
        await proposer._propose_block()
        return proposer

    await run(gates_ok=False)
    assert get_vote_journal(CHAIN).votes_at(100, me) == [], "a rolled-back proposal kept its vote"

    await run(gates_ok=True)
    assert [v.block_hash for v in get_vote_journal(CHAIN).votes_at(100, me)] == ["0xnewhash"]


class TestFetchHelper:
    @pytest.mark.asyncio
    async def test_locates_a_serving_peer_and_throttles(self, monkeypatch):
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
        get = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {"height": 100, "hash": "0xaaaa"}))
        monkeypatch.setattr(vote_fetch.SharedHttpClient, "get", get)

        assert await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"}) == "https://peer1.example"
        assert await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"}) == "https://peer1.example"
        assert get.await_count == 1  # second call served from the throttle

    @pytest.mark.asyncio
    async def test_wrong_hash_is_contention_and_empty_set_is_a_miss(self, monkeypatch):
        """#1280: a peer serving a DIFFERENT block at the height is positive
        contention evidence (recorded, returns None like a miss); an empty
        hash set and peers with nothing at the height stay plain misses."""
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
        get = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {"height": 100, "hash": "0xother"}))
        monkeypatch.setattr(vote_fetch.SharedHttpClient, "get", get)
        assert await vote_fetch.locate_voted_block(CHAIN, 100, {"0xaaaa"}) is None
        assert _counter("vote_fetch_contention_total") == 1
        assert vote_fetch.contention_hold(CHAIN, 100) is not None
        get.return_value = SimpleNamespace(status_code=404, json=lambda: {})
        vote_fetch.reset_throttle()
        assert await vote_fetch.locate_voted_block(CHAIN, 100, {"0xbbbb"}) is None
        assert await vote_fetch.locate_voted_block(CHAIN, 100, set()) is None
        assert _counter("vote_fetch_missing_total") == 1


class TestProposeBlockWiring:
    """Pin gap (Validator, #1268): `_propose_block` -> `_honor_prior_votes` ->
    `_honor_vote_journal` was only covered by unit-calling the pieces."""

    def _stubbed(self, monkeypatch, *, lock: bool = False):
        @contextmanager
        def _null_session():
            yield None

        config = ProposerConfig(
            chain_id=CHAIN, proposer_id="n", interval_seconds=1, max_block_size_bytes=1000, max_txs_per_block=100
        )
        proposer = PoAProposer(config=config, session_factory=_null_session)
        head = SimpleNamespace(timestamp=datetime.now(UTC))
        reached: list[str] = []

        async def _early(*_a, **_k):
            return SimpleNamespace()

        def _collect(*_a, **_k):
            reached.append("collect")
            raise AssertionError("proposal went past the vote gates")

        async def _lock(*_a, **_k):
            return lock

        monkeypatch.setattr(proposer, "_passes_early_gates", _early)
        monkeypatch.setattr(proposer, "_resolve_proposal_head", lambda *_: (head, 100, "0xparent", 1))
        monkeypatch.setattr(proposer, "_select_round_proposer", lambda *_: ("0xme", 0))
        monkeypatch.setattr(proposer, "_honor_attestation_lock", _lock)
        monkeypatch.setattr(proposer, "_collect_proposal_txs", _collect)
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value=None))
        return proposer, reached

    @pytest.mark.asyncio
    async def test_propose_block_stops_at_a_live_journal_vote(self, monkeypatch):
        proposer, reached = self._stubbed(monkeypatch)
        get_vote_journal(CHAIN).record(100, "0xme", "0xvoted", KIND_ATTEST, now=T0)
        monkeypatch.setattr(vote_journal, "time", _Clock(T0 + 10))
        assert await proposer._propose_block() is False
        assert reached == []

    @pytest.mark.asyncio
    async def test_propose_block_stops_at_the_legacy_lock_without_a_journal(self, monkeypatch):
        proposer, reached = self._stubbed(monkeypatch, lock=True)
        assert await proposer._propose_block() is False
        assert reached == []

    @pytest.mark.asyncio
    async def test_propose_block_proceeds_when_neither_gate_holds(self, monkeypatch):
        proposer, reached = self._stubbed(monkeypatch)
        with pytest.raises(AssertionError, match="went past the vote gates"):
            await proposer._propose_block()
        assert reached == ["collect"]

    @pytest.mark.asyncio
    async def test_honor_prior_votes_is_either_gate(self, monkeypatch):
        proposer, _ = self._stubbed(monkeypatch)
        assert await proposer._honor_prior_votes(100, 0, "0xme") is False
        get_vote_journal(CHAIN).record(100, "0xme", "0xvoted", KIND_ATTEST, now=T0)
        monkeypatch.setattr(vote_journal, "time", _Clock(T0 + 10))
        assert await proposer._honor_prior_votes(100, 0, "0xme") is True
