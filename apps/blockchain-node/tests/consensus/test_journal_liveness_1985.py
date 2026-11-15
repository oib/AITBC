"""#1985: vote-journal liveness hardening (bc-2 halt at h28508, 15 Nov 2026).

A proposal that misses quorum pinned every voter to its hash; no abandon was
ever published (flag off), and the valve + UC release then re-pinned each
validator on a different hash at staggered times. These pins cover the dormant,
flag-gated hardening of the abandon path (``vote_journal_liveness_enabled``):

* a dropped proposal's abandon is re-announced, so a voter that restarted or
  lost the single gossip publish is released end to end (real proposer, real
  attester);
* a restarted proposer abandons and retracts its own orphaned journal
  proposals above the tip (nothing in flight after a start), and leaves the
  decided height, other validators' votes and other kinds alone;
* a same-hash retry stops being announced as dead;
* a refused rival no longer mints a lock for a hash this validator never signed;
* flag OFF is the pre-#1985 behaviour, asserted against an armed control.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from aitbc_chain.config import ChainSettings, settings, uc_combo_findings
from aitbc_chain.consensus import abandon, vote_fetch, vote_journal
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.abandon import AbandonLedger
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.vote_journal import (
    KIND_ATTEST,
    KIND_PROPOSE,
    get_vote_journal,
    reset_vote_journals,
)
from aitbc_chain.metrics import metrics_registry

from .test_vote_journal_1268 import _Broker, _Clock, _keys, _request

CHAIN = "test-chain"
H = 100
HASH_A = "0x" + "aa" * 32
HASH_B = "0x" + "bb" * 32
HASH_C = "0x" + "cc" * 32
PROP_KEY = "0x" + "22" * 32


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    reset_vote_journals()
    vote_fetch.reset_throttle()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)
    monkeypatch.setattr(settings, "attestation_lock_enabled", True)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_liveness_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_abandon_reannounce_seconds", 30.0)
    monkeypatch.setattr(settings, "vote_journal_unlock_seconds", 300.0)
    yield
    reset_vote_journals()
    metrics_registry.reset()


# ── ledger (pure) ─────────────────────────────────────────────────────────────


class TestLedger:
    def test_due_is_paced_per_entry(self):
        ledger = AbandonLedger()
        ledger.record(H, HASH_A, None, "0xP", now=1000.0)
        assert ledger.due(tip_height=H - 1, every=30.0, now=1010.0) == []
        assert ledger.due(H - 1, 30.0, 1030.0) == [(H, HASH_A, None, "0xP")]
        assert len(ledger.due(H - 1, 30.0, 1031.0)) == 1, "an unconfirmed send is retried, not stamped as sent"
        ledger.mark_sent(H, HASH_A, 1031.0)
        assert ledger.due(H - 1, 30.0, 1040.0) == [], "re-published without waiting out the interval"
        assert len(ledger.due(H - 1, 30.0, 1061.0)) == 1

    def test_decided_heights_are_dropped(self):
        ledger = AbandonLedger()
        ledger.record(H, HASH_A, None, "0xP", 0.0)
        ledger.record(H + 1, HASH_B, None, "0xP", 0.0)
        assert [e[0] for e in ledger.due(tip_height=H, every=30.0, now=100.0)] == [H + 1]
        assert len(ledger) == 1

    def test_forget_and_bound(self):
        ledger = AbandonLedger(max_entries=3)
        for i in range(5):
            ledger.record(H + i, HASH_A, None, "0xP", 0.0)
        assert len(ledger) == 3 and ledger.due(H - 1, 30.0, 100.0)[0][0] == H + 2
        ledger.forget(H + 2, HASH_A)
        assert [e[0] for e in ledger.due(H - 1, 0.0, 200.0)] == [H + 3, H + 4]


class TestLedgerPersistence:
    def test_obligations_survive_a_reload_and_are_due_at_once(self, tmp_path):
        path = tmp_path / "abandon_ledger.json"
        first = AbandonLedger(path=path)
        first.record(H, HASH_A, 2, "0xP", now=1000.0)
        first.mark_sent(H, HASH_A, 1000.0)
        reloaded = AbandonLedger(path=path)
        assert len(reloaded) == 1
        assert reloaded.due(H - 1, 30.0, 1001.0) == [(H, HASH_A, 2, "0xP")], "a restart owes the abandon immediately"

    def test_forget_and_decided_heights_are_persisted(self, tmp_path):
        path = tmp_path / "abandon_ledger.json"
        ledger = AbandonLedger(path=path)
        ledger.record(H, HASH_A, None, "0xP", 0.0)
        ledger.record(H + 1, HASH_B, None, "0xP", 0.0)
        ledger.record(H + 2, HASH_C, None, "0xP", 0.0)
        ledger.forget(H + 2, HASH_C)
        ledger.due(tip_height=H, every=30.0, now=100.0)  # H decided
        assert [e[0] for e in AbandonLedger(path=path).due(0, 0.0, 1.0)] == [H + 1]

    def test_unreadable_file_degrades_to_empty_and_is_rewritten(self, tmp_path):
        path = tmp_path / "abandon_ledger.json"
        path.write_text("{not json")
        ledger = AbandonLedger(path=path)
        assert len(ledger) == 0 and _counter("vote_journal_abandon_ledger_load_failed_total") == 1
        ledger.record(H, HASH_A, None, "0xP", 0.0)
        assert len(AbandonLedger(path=path)) == 1

    def test_persist_failure_keeps_the_obligation_in_memory(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("a file where a directory is needed")
        ledger = AbandonLedger(path=blocker / "sub" / "abandon_ledger.json")
        ledger.record(H, HASH_A, None, "0xP", 0.0)
        assert len(ledger.due(H - 1, 30.0, 100.0)) == 1
        assert _counter("vote_journal_abandon_ledger_persist_failed_total") >= 1


@pytest.mark.parametrize(
    ("journal", "abandon_flag", "liveness", "expected"),
    [
        (True, True, True, True),
        (True, True, False, False),
        (True, False, True, False),
        (False, True, True, False),
    ],
)
def test_liveness_needs_journal_abandon_and_its_own_flag(monkeypatch, journal, abandon_flag, liveness, expected):
    monkeypatch.setattr(settings, "vote_journal_enabled", journal)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", abandon_flag)
    monkeypatch.setattr(settings, "vote_journal_liveness_enabled", liveness)
    assert abandon.liveness_enabled() is expected


# ── proposer: re-announce, end to end against a real attester ────────────────


class _Session:
    """Just enough of a session for the loop tick's tip read."""

    def __init__(self, stub):
        self._stub = stub

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def exec(self, _statement):
        return SimpleNamespace(first=lambda: SimpleNamespace(height=self._stub._tip))


def _restarted(stub):
    """A fresh proposer process: new in-memory state, same data dir and keys."""
    fresh = SimpleNamespace(
        _config=stub._config,
        _validator_keys=stub._validator_keys,
        _logger=stub._logger,
        _abandon_ledger=AbandonLedger(path=abandon.ledger_path(CHAIN)),
        _abandon_orphans_done=False,
        _tip=stub._tip,
    )
    fresh._session_factory = lambda: _Session(fresh)
    for name in ("_abandon_liveness_tick", "_recover_orphaned_proposals", "_abandon_tick_from_loop"):
        setattr(fresh, name, getattr(PoAProposer, name).__get__(fresh))
    return fresh


def _proposer_stub(monkeypatch, clock: _Clock):
    """A real-method proposer around the minimum state the abandon path reads."""
    broker = _Broker()
    monkeypatch.setattr(poa_module, "gossip_broker", broker)
    monkeypatch.setattr(poa_module, "time", clock)
    _, _, proposer_addr = _keys()
    logged: list[str] = []
    stub = SimpleNamespace(
        _config=SimpleNamespace(chain_id=CHAIN),
        _validator_keys={proposer_addr: PROP_KEY},
        _logger=SimpleNamespace(warning=lambda *a, **k: logged.append(str(a[0]))),
        _abandon_ledger=AbandonLedger(path=abandon.ledger_path(CHAIN)),
        _abandon_orphans_done=False,
        _tip=H - 1,
    )
    stub._session_factory = lambda: _Session(stub)
    # bind the real methods onto the stub so the test drives production code, not a copy
    for name in ("_abandon_liveness_tick", "_recover_orphaned_proposals", "_abandon_tick_from_loop"):
        setattr(stub, name, getattr(PoAProposer, name).__get__(stub))
    return stub, broker, proposer_addr


@pytest.mark.asyncio
async def test_lost_abandon_is_reannounced_and_releases_the_pinned_voter(monkeypatch):
    """The h28508 shape: a voter is pinned to a hash whose proposer dropped it and never
    heard the single abandon. The proposer's re-announce releases it without the valve."""
    clock = _Clock()
    monkeypatch.setattr(ra_module, "time", clock)
    monkeypatch.setattr(vote_journal, "time", clock)
    our_addr, our_key, _ = _keys()
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": our_addr}, {"address": _keys()[2]}]))
    monkeypatch.setattr(ra_module, "gossip_broker", _Broker())

    async def _no_peer(chain_id, height, hashes):
        return None

    monkeypatch.setattr(ra_module, "locate_voted_block", _no_peer)
    voter = RemoteAttestationService(CHAIN, {our_addr: our_key})
    stub, broker, proposer_addr = _proposer_stub(monkeypatch, clock)

    # voter signs HASH_A, then the proposer drops it; that first abandon never reaches the voter
    get_vote_journal(CHAIN).record(H, our_addr, HASH_A, KIND_ATTEST, None, proposer_addr, now=clock.now)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=proposer_addr, height=H), HASH_A)
    assert len(broker.published) == 1
    first_lost = broker.published.pop()
    assert first_lost["hash"] == HASH_A
    assert await voter._journal_refuses(H, HASH_B, our_addr, proposer_addr, None) is True, "voter must be pinned"

    # 10 s later nothing is re-sent; after the interval the statement goes out again
    clock.advance(10)
    await stub._abandon_liveness_tick(H - 1)
    assert broker.published == []
    clock.advance(25)
    await stub._abandon_liveness_tick(H - 1)
    assert len(broker.published) == 1
    assert _counter("vote_journal_abandon_reannounced_total") == 1

    # the re-announced statement is the real, verifiable one: the voter releases and signs the rival
    assert voter.handle_abandon(broker.published[0]) == 1
    assert await voter._journal_refuses(H, HASH_B, our_addr, proposer_addr, None) is False


@pytest.mark.asyncio
async def test_reannounce_stops_once_the_height_is_decided(monkeypatch):
    clock = _Clock()
    stub, broker, proposer_addr = _proposer_stub(monkeypatch, clock)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=proposer_addr, height=H), HASH_A)
    broker.published.clear()
    clock.advance(60)
    await stub._abandon_liveness_tick(H)  # tip reached H: decided
    assert broker.published == [] and len(stub._abandon_ledger) == 0


@pytest.mark.asyncio
async def test_flag_off_publishes_once_and_never_reannounces(monkeypatch):
    """Armed-control twin of the test above: same harness, liveness OFF."""
    monkeypatch.setattr(settings, "vote_journal_liveness_enabled", False)
    clock = _Clock()
    stub, broker, proposer_addr = _proposer_stub(monkeypatch, clock)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=proposer_addr, height=H), HASH_A)
    assert len(broker.published) == 1 and len(stub._abandon_ledger) == 0
    clock.advance(600)
    await stub._abandon_liveness_tick(H - 1)
    assert len(broker.published) == 1
    assert _counter("vote_journal_abandon_reannounced_total") == 0


@pytest.mark.asyncio
async def test_failed_first_send_is_still_owed_and_retried_on_the_next_tick(monkeypatch):
    clock = _Clock()
    stub, broker, proposer_addr = _proposer_stub(monkeypatch, clock)
    keys = stub._validator_keys
    stub._validator_keys = {}  # a signing/gossip outage at drop time
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=proposer_addr, height=H), HASH_A)
    assert broker.published == [] and len(stub._abandon_ledger) == 1
    stub._validator_keys = keys
    await stub._abandon_liveness_tick(H - 1)  # same instant: owed at once, not after a full interval
    assert [m["hash"] for m in broker.published] == [HASH_A]


@pytest.mark.asyncio
async def test_failed_reannounce_is_retried_next_tick_not_after_a_full_interval(monkeypatch):
    clock = _Clock()
    stub, broker, proposer_addr = _proposer_stub(monkeypatch, clock)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=proposer_addr, height=H), HASH_A)
    broker.published.clear()
    keys = stub._validator_keys
    stub._validator_keys = {}
    clock.advance(31)
    await stub._abandon_liveness_tick(H - 1)  # due, but the send fails
    assert broker.published == []
    stub._validator_keys = keys
    clock.advance(1)
    await stub._abandon_liveness_tick(H - 1)
    assert len(broker.published) == 1, "an unconfirmed send must not consume the pacing interval"


@pytest.mark.asyncio
async def test_clean_drop_obligation_survives_a_proposer_restart(monkeypatch):
    """Validator FAIL on d93a51a8fb: the quorum-miss drop retracts the journal proposal, so the
    only record of the owed abandon was in memory. A restart between drop and decision (hub
    restarted 7 times during the bc-2 halt) lost it."""
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)
    journal = get_vote_journal(CHAIN)
    journal.record(H, me, HASH_A, KIND_PROPOSE, 0, me, now=clock.now)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=me, height=H), HASH_A)
    journal.retract(H, me, HASH_A)  # what _run_journaled_gates does after the failed gates
    assert journal.proposals_above(me, H - 1) == [], "no journal trace is left: orphan recovery cannot help"
    broker.published.clear()

    restarted = _restarted(stub)  # the process restarts; the first publish was lost on the mesh
    clock.advance(5)
    await restarted._abandon_liveness_tick(H - 1)
    assert [(m["hash"], m["height"]) for m in broker.published] == [(HASH_A, H)]

    # and once the height is decided the obligation is gone for good, including on disk
    await restarted._abandon_liveness_tick(H)
    assert len(AbandonLedger(path=abandon.ledger_path(CHAIN))) == 0


@pytest.mark.asyncio
async def test_loop_tick_runs_outside_proposal_slots_and_reads_the_tip(monkeypatch):
    """The re-announce no longer waits for this validator's own proposer window."""
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)
    await PoAProposer._publish_abandon(stub, SimpleNamespace(proposer=me, height=H), HASH_A)
    broker.published.clear()
    clock.advance(31)
    await stub._abandon_tick_from_loop()
    assert [m["hash"] for m in broker.published] == [HASH_A]
    stub._tip = H  # decided
    clock.advance(31)
    broker.published.clear()
    await stub._abandon_tick_from_loop()
    assert broker.published == [] and len(stub._abandon_ledger) == 0


@pytest.mark.asyncio
async def test_loop_tick_never_raises(monkeypatch):
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)

    def _boom():
        raise RuntimeError("db gone")

    stub._session_factory = _boom
    stub._logger = SimpleNamespace(warning=lambda *a, **k: None)
    await stub._abandon_tick_from_loop()  # must not propagate into the proposer loop
    monkeypatch.setattr(settings, "vote_journal_liveness_enabled", False)
    await stub._abandon_tick_from_loop()


# ── proposer restart: orphaned journal proposals ─────────────────────────────


@pytest.mark.asyncio
async def test_start_abandons_and_retracts_orphaned_proposals_above_the_tip_only(monkeypatch):
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)
    other = _keys()[0]
    journal = get_vote_journal(CHAIN)
    journal.record(H - 1, me, HASH_C, KIND_PROPOSE, 0, me, now=clock.now)  # at the tip: sealed/decided
    journal.record(H, me, HASH_A, KIND_PROPOSE, 1, me, now=clock.now)  # orphan above the tip
    journal.record(H, me, HASH_B, KIND_ATTEST, 2, other, now=clock.now)  # an attestation, not a proposal
    journal.record(H, other, HASH_C, KIND_PROPOSE, 0, other, now=clock.now)  # someone else's proposal

    await stub._abandon_liveness_tick(H - 1)

    assert [m["hash"] for m in broker.published] == [HASH_A]
    assert [v.block_hash for v in journal.votes_at(H, me)] == [HASH_B], "only the orphaned proposal is voided"
    assert [v.block_hash for v in journal.votes_at(H - 1, me)] == [HASH_C], "decided height untouched"
    assert [v.block_hash for v in journal.votes_at(H, other)] == [HASH_C], "another validator's vote untouched"
    assert _counter("vote_journal_orphan_proposal_retracted_total") == 1

    # the scan is once per start: a proposal journaled by THIS process later is never mistaken for an orphan
    journal.record(H + 1, me, HASH_A, KIND_PROPOSE, 0, me, now=clock.now)
    broker.published.clear()
    clock.advance(31)
    await stub._abandon_liveness_tick(H - 1)
    assert [v.block_hash for v in journal.votes_at(H + 1, me)] == [HASH_A]
    assert all(m["hash"] != HASH_A or m["height"] != H + 1 for m in broker.published)


@pytest.mark.asyncio
async def test_orphan_recovery_is_inert_with_the_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "vote_journal_liveness_enabled", False)
    clock = _Clock()
    stub, broker, me = _proposer_stub(monkeypatch, clock)
    get_vote_journal(CHAIN).record(H, me, HASH_A, KIND_PROPOSE, 1, me, now=clock.now)
    await stub._abandon_liveness_tick(H - 1)
    assert broker.published == []
    assert [v.block_hash for v in get_vote_journal(CHAIN).votes_at(H, me)] == [HASH_A]


def test_same_hash_retry_stops_being_announced_as_dead(monkeypatch):
    clock = _Clock()
    stub, _, me = _proposer_stub(monkeypatch, clock)
    stub._abandon_ledger.record(H, HASH_A, None, me, 0.0)
    stub._unlock_justifications = {}
    stub._logger = SimpleNamespace(error=lambda *a, **k: None)
    proposer = PoAProposer.__new__(PoAProposer)
    proposer.__dict__.update(stub.__dict__)
    proposer._config = SimpleNamespace(chain_id=CHAIN)
    assert proposer._record_proposal_vote(None, H, HASH_A, me, 3) is True
    assert len(proposer._abandon_ledger) == 0
    assert len(AbandonLedger(path=abandon.ledger_path(CHAIN))) == 0, "the forget is persisted too"
    assert [v.block_hash for v in get_vote_journal(CHAIN).votes_at(H, me)] == [HASH_A]


# ── attester: lock ordering ──────────────────────────────────────────────────


async def _rival_after_lock_lapse(monkeypatch):
    our_addr, our_key, proposer = _keys()
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": our_addr}, {"address": proposer}]))
    monkeypatch.setattr(ra_module, "gossip_broker", broker := _Broker())
    clock = _Clock()
    monkeypatch.setattr(ra_module, "time", clock)
    monkeypatch.setattr(vote_journal, "time", clock)

    async def _no_peer(chain_id, height, hashes):
        return None

    monkeypatch.setattr(ra_module, "locate_voted_block", _no_peer)
    svc = RemoteAttestationService(CHAIN, {our_addr: our_key})
    await svc._handle_request(_request(H, HASH_A, proposer, clock))
    assert len(broker.published) == 1
    clock.advance(61)  # the legacy 60 s lock has lapsed, the journal vote has not
    await svc._handle_request(_request(H, HASH_B, proposer, clock))
    return svc, broker


@pytest.mark.asyncio
async def test_refused_rival_leaves_no_lock_record_when_armed(monkeypatch):
    svc, broker = await _rival_after_lock_lapse(monkeypatch)
    assert len(broker.published) == 1, "the journal must still refuse the rival"
    assert _counter("vote_journal_refused_rival_total") == 1
    hashes = {k[1] for k in svc._attested_lock_records}
    assert hashes == {HASH_A}, f"a lock was minted for a hash this validator never signed: {hashes}"


@pytest.mark.asyncio
async def test_refused_rival_mints_a_lock_when_flag_off(monkeypatch):
    """Control: pre-#1985 ordering is unchanged with the flag off, so the pin above is not vacuous."""
    monkeypatch.setattr(settings, "vote_journal_liveness_enabled", False)
    svc, broker = await _rival_after_lock_lapse(monkeypatch)
    assert len(broker.published) == 1
    assert {k[1] for k in svc._attested_lock_records} == {HASH_A, HASH_B}


@pytest.mark.asyncio
async def test_accepted_vote_still_mints_its_lock_when_armed(monkeypatch):
    our_addr, our_key, proposer = _keys()
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": our_addr}, {"address": proposer}]))
    monkeypatch.setattr(ra_module, "gossip_broker", broker := _Broker())
    clock = _Clock()
    monkeypatch.setattr(ra_module, "time", clock)
    monkeypatch.setattr(vote_journal, "time", clock)
    svc = RemoteAttestationService(CHAIN, {our_addr: our_key})
    await svc._handle_request(_request(H, HASH_A, proposer, clock))
    assert len(broker.published) == 1
    assert {k[1] for k in svc._attested_lock_records} == {HASH_A}, "no signature may leave without its lock record"


# ── startup guard ────────────────────────────────────────────────────────────


def test_guard_warns_when_the_journal_is_armed_without_abandon():
    _, warnings = uc_combo_findings(ChainSettings(vote_journal_enabled=True))
    assert any("without vote_journal_abandon_enabled" in w and "#1985" in w for w in warnings)
    _, warnings = uc_combo_findings(ChainSettings(vote_journal_enabled=True, vote_journal_abandon_enabled=True))
    assert warnings == []
    assert uc_combo_findings(ChainSettings()) == ([], [])


def test_guard_flags_liveness_without_abandon_and_without_journal():
    _, warnings = uc_combo_findings(ChainSettings(vote_journal_enabled=True, vote_journal_liveness_enabled=True))
    assert any("liveness_enabled needs vote_journal_abandon_enabled" in w for w in warnings)
    _, warnings = uc_combo_findings(ChainSettings(vote_journal_liveness_enabled=True))
    assert any("vote_journal_liveness_enabled is set but vote_journal_enabled is off" in w for w in warnings)


def test_proposer_loop_drives_the_reannounce_tick_before_each_proposal():
    """Structural pin: the tick is wired into ``_run_loop`` ahead of the proposal, so it runs
    every iteration and is not gated behind this validator's own slot or the mempool gates."""
    import inspect

    src = inspect.getsource(PoAProposer._run_loop)
    assert "_abandon_tick_from_loop" in src
    assert src.index("_abandon_tick_from_loop") < src.index("_propose_block_with_watchdog")
    assert "_abandon_liveness_tick" not in inspect.getsource(PoAProposer._propose_block)
