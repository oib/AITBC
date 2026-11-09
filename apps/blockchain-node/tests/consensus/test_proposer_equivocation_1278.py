"""#1278 (EQUIV-RECORDER-GAP-1): the proposer records its own same-height equivocation.

Audit-Director acceptance criteria (#1278 comment 20234):
  1. proposer-side signing records the same evidence as the attester/verifier path;
  2. both signatures retained with identity, height, hash, round, format metadata;
  3. duplicate observations are idempotent;
  4. evidence survives the journal / restart path;
  5. a real pair is accepted by the on-chain verifier, signature checks untouched;
  6. legacy and round-bound pairs tested, proposer-as-equivocator included;
  7. no valid signing path silently bypasses recording.

The gap (D9b/D9c, #1268): a proposer sealing a rival after the journal valve
opened signed ``block.signature`` but was skipped as its own attester, so the
node that sealed the rival held no evidence.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc.crypto.signature_recovery import canonical_address
from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus import vote_journal
from aitbc_chain.consensus.equivocation_policy import PairClass, classify_attestation_pair
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.slashing import SlashingCondition, SlashingManager, event_signature_evidence
from aitbc_chain.consensus.vote_journal import KIND_ATTEST, KIND_PROPOSE, get_vote_journal, reset_vote_journals
from aitbc_chain.state.deactivation_evidence import verify_deactivation_evidence

from .test_deactivation_evidence_1263 import _v2_payload
from .test_vote_journal_1268 import CHAIN, T0, _Broker, _Clock, _counter, _env, _keys, _request  # noqa: F401

H = 100
HA = "0x" + "aa" * 32
HB = "0x" + "bb" * 32
OTHER = "0x" + "99" * 20  # a different proposer for the first block


def _setup(monkeypatch):
    our_addr, our_key, other_proposer = _keys()
    monkeypatch.setattr(ra_module.settings, "validator_set", json.dumps([{"address": our_addr}, {"address": other_proposer}]))
    broker = _Broker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    clock = _Clock()
    monkeypatch.setattr(ra_module, "time", clock)
    monkeypatch.setattr(vote_journal, "time", clock)
    monkeypatch.setattr(ra_module, "locate_voted_block", AsyncMock(return_value=None))
    svc = RemoteAttestationService(CHAIN, {our_addr: our_key})
    mgr = SlashingManager()
    monkeypatch.setattr(svc, "_equivocation_recorder", lambda: mgr)
    return svc, mgr, our_addr, our_key, other_proposer, clock


def _header(block_hash: str, proposer: str, *, height: int = H) -> dict:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": block_hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": proposer,
        "state_root": "0xroot",
        "bridge_state_root": "",
    }


def _seed_prior_attestation(svc, our_addr, our_key, block_hash, *, round_bound_round: int | None, now: float = T0):
    """An attestation vote this validator already cast: signed record + lock + journal vote."""
    message = _header(block_hash, OTHER)
    if round_bound_round is not None:
        message["round"] = round_bound_round
    signature = sign_consensus_message(message, our_key)
    svc._record_signed_attestation(
        H, block_hash, our_addr, message, round_bound_round, round_bound_round is not None, signature
    )
    svc._signed_once_add(H, block_hash, None)
    get_vote_journal(CHAIN).record(H, our_addr, block_hash, KIND_ATTEST, round_bound_round, OTHER, now=now)


def _proposal(our_addr, our_key, block_hash=HB):
    message = _header(block_hash, our_addr)
    return message, sign_consensus_message(message, our_key)


def _verdict(mgr: SlashingManager, validator: str) -> str | None:
    payload = _v2_payload(mgr, validator)
    return verify_deactivation_evidence(
        payload,
        chain_id=CHAIN,
        validator_addr=payload["validator_address"],
        evidence_hash=payload["evidence_hash"],
    )


class TestProposerAsEquivocator:
    @pytest.mark.parametrize(
        ("round_bound_round", "expected_class"),
        [(None, PairClass.LEGACY), (0, PairClass.MIXED_FORMAT), (5, PairClass.MIXED_FORMAT)],
        ids=["legacy_attestation", "round_bound_attestation_r0", "round_bound_attestation_r5"],
    )
    def test_rival_proposal_after_a_vote_records_a_verifier_accepted_pair(
        self, monkeypatch, round_bound_round, expected_class
    ):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=round_bound_round)
        message, signature = _proposal(our_addr, our_key)

        svc.record_proposal_equivocation(message, signature, 7)

        assert len(mgr.slashing_events) == 1
        event = mgr.slashing_events[0]
        assert event.condition is SlashingCondition.DOUBLE_SIGN
        evidence = event_signature_evidence(event)
        assert evidence is not None  # signature-bearing, not advisory
        assert classify_attestation_pair(evidence) is expected_class
        assert _verdict(mgr, our_addr) is None  # real pair accepted, signatures verified untouched

    def test_both_signatures_retained_with_full_metadata(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=5)
        message, signature = _proposal(our_addr, our_key)

        svc.record_proposal_equivocation(message, signature, 7)

        ep = json.loads(mgr.slashing_events[0].evidence)
        assert ep["kind"] == "attestation_equivocation"
        assert ep["height"] == H
        assert {ep["block_hash_a"], ep["block_hash_b"]} == {HA, HB}
        by_hash = {a["hash"]: a for a in ep["attestations"]}
        assert set(by_hash) == {HA, HB}
        for rec in by_hash.values():
            assert rec["signer"] == canonical_address(our_addr)
            assert rec["height"] == H
            assert rec["signature"]
            assert rec["chain_id"] == CHAIN
        # signature-format metadata: prior attestation is round-bound, the proposal is the fixed header
        assert by_hash[HA]["round_in_payload"] is True
        assert by_hash[HA]["request_round"] == 5
        assert by_hash[HB]["round_in_payload"] is False
        assert by_hash[HB]["request_round"] is None
        assert by_hash[HB]["signature"] == signature

    def test_two_proposals_pair_when_the_first_was_this_nodes_own_proposal(self, monkeypatch):
        """The prior vote may be this validator's earlier proposal, not an attestation."""
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        first, first_sig = _proposal(our_addr, our_key, HA)
        get_vote_journal(CHAIN).record(H, our_addr, HA, KIND_PROPOSE, 0, our_addr, now=T0)
        svc.record_proposal_equivocation(first, first_sig, 0)  # no prior except its own journal vote
        assert mgr.slashing_events == []

        rival, rival_sig = _proposal(our_addr, our_key, HB)
        get_vote_journal(CHAIN).record(H, our_addr, HB, KIND_PROPOSE, 0, our_addr, now=T0 + 400)
        svc.record_proposal_equivocation(rival, rival_sig, 0)

        assert len(mgr.slashing_events) == 1
        evidence = event_signature_evidence(mgr.slashing_events[0])
        assert evidence is not None
        assert classify_attestation_pair(evidence) is PairClass.LEGACY
        assert _verdict(mgr, our_addr) is None

    def test_round_lock_on_records_the_proposal_round(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        monkeypatch.setattr(ra_module.settings, "attestation_round_lock_enabled", True)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=0)
        message, signature = _proposal(our_addr, our_key)
        svc.record_proposal_equivocation(message, signature, 5)
        assert json.loads(mgr.slashing_events[0].evidence)["round"] == 5
        assert _verdict(mgr, our_addr) is None

    def test_round_lock_off_records_no_round(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        message, signature = _proposal(our_addr, our_key)
        svc.record_proposal_equivocation(message, signature, 5)
        assert json.loads(mgr.slashing_events[0].evidence)["round"] is None


class TestNoSpuriousEvidence:
    def test_first_proposal_at_a_height_records_nothing(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        message, signature = _proposal(our_addr, our_key)
        svc.record_proposal_equivocation(message, signature, 0)
        assert mgr.slashing_events == []

    def test_a_vote_at_another_height_is_not_a_prior(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        message = _header(HB, our_addr, height=H + 1)
        svc.record_proposal_equivocation(message, sign_consensus_message(message, our_key), 0)
        assert mgr.slashing_events == []

    def test_re_signing_the_voted_hash_is_not_an_equivocation(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        message, signature = _proposal(our_addr, our_key, HA)
        svc.record_proposal_equivocation(message, signature, 0)
        assert mgr.slashing_events == []

    def test_other_validators_votes_are_not_priors(self, monkeypatch):
        svc, mgr, our_addr, our_key, other, _ = _setup(monkeypatch)
        get_vote_journal(CHAIN).record(H, other, HA, KIND_ATTEST, None, other, now=T0)
        message, signature = _proposal(our_addr, our_key)
        svc.record_proposal_equivocation(message, signature, 0)
        assert mgr.slashing_events == []

    def test_unsigned_proposal_is_ignored_and_not_retained(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        message, _ = _proposal(our_addr, our_key)
        svc.record_proposal_equivocation(message, "", 0)
        assert mgr.slashing_events == []
        assert svc._signed_attestation_key(H, HB, our_addr) not in svc._signed_attestations


class TestIdempotenceAndRecovery:
    def test_duplicate_observation_is_one_record(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        message, signature = _proposal(our_addr, our_key)
        for _ in range(3):
            svc.record_proposal_equivocation(message, signature, 0)
        assert len(mgr.slashing_events) == 1

    def test_attester_and_proposer_observation_of_one_pair_dedup(self, monkeypatch):
        """The same unordered hash pair recorded twice (either order) stays one record."""
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        message, signature = _proposal(our_addr, our_key)
        svc.record_proposal_equivocation(message, signature, 0)
        svc._record_attestation_equivocation_evidence(H, HB, our_addr, our_addr, None)
        assert len(mgr.slashing_events) == 1

    def test_evidence_survives_a_restart_with_the_pair_intact(self, monkeypatch):
        """Journal + signature index are durable: a restarted node still records a full pair."""
        svc, mgr, our_addr, our_key, other_proposer, clock = _setup(monkeypatch)
        # a real attestation vote through the production path (journal + signed-attestation file)
        import asyncio

        asyncio.run(svc._handle_request(_request(H, HA, other_proposer, clock)))
        assert svc._signed_attestations_path.exists()

        reset_vote_journals()  # process gone: the journal reloads from disk
        restarted = RemoteAttestationService(CHAIN, {our_addr: our_key})  # empty memory
        mgr2 = SlashingManager()
        monkeypatch.setattr(restarted, "_equivocation_recorder", lambda: mgr2)
        assert restarted._signed_once == {}

        message, signature = _proposal(our_addr, our_key)
        restarted.record_proposal_equivocation(message, signature, 0)

        assert len(mgr2.slashing_events) == 1
        evidence = event_signature_evidence(mgr2.slashing_events[0])
        assert evidence is not None, "restart degraded the pair to hash-only advisory"
        assert _verdict(mgr2, our_addr) is None

    def test_unknown_prior_signature_degrades_to_advisory_like_the_attester_path(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        get_vote_journal(CHAIN).record(H, our_addr, HA, KIND_ATTEST, None, OTHER, now=T0)  # vote with no signature record
        message, signature = _proposal(our_addr, our_key)
        svc.record_proposal_equivocation(message, signature, 0)
        assert len(mgr.slashing_events) == 1
        assert event_signature_evidence(mgr.slashing_events[0]) is None  # advisory, cannot satisfy the gate

    def test_forged_proposal_signature_still_fails_the_gate(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        message, _ = _proposal(our_addr, our_key)
        forged = sign_consensus_message(message, "0x" + "77" * 32)  # not this validator's key
        svc.record_proposal_equivocation(message, forged, 0)
        assert _verdict(mgr, our_addr) == "attestation equivocation evidence failed signature verification"


def _proposer_with(service):
    config = ProposerConfig(
        chain_id=CHAIN, proposer_id="n", interval_seconds=1, max_block_size_bytes=1000, max_txs_per_block=100
    )
    proposer = PoAProposer(config=config, session_factory=lambda: None)
    proposer._remote_attestation = service
    return proposer


def _block(our_addr: str, signature: str, block_hash: str = HB):
    return SimpleNamespace(**_header(block_hash, our_addr), signature=signature)


class TestProposeWiring:
    """Criterion 7: the signing path itself triggers the recording, in order."""

    @pytest.mark.asyncio
    async def test_journaled_gates_record_before_the_attest_request_leaves(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        proposer = _proposer_with(svc)
        _, signature = _proposal(our_addr, our_key)
        block = _block(our_addr, signature)
        seen_at_gates: list[int] = []

        async def _gates(*_a, **_k):
            seen_at_gates.append(len(mgr.slashing_events))  # evidence must already exist here
            return True

        monkeypatch.setattr(proposer, "_run_consensus_gates", _gates)
        ok = await proposer._run_journaled_gates(None, block, HB, our_addr, 0, H, {}, [])

        assert ok is True
        assert seen_at_gates == [1]
        assert _verdict(mgr, our_addr) is None

    @pytest.mark.asyncio
    async def test_no_recording_when_the_proposal_vote_cannot_persist(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        _seed_prior_attestation(svc, our_addr, our_key, HA, round_bound_round=None)
        proposer = _proposer_with(svc)
        _, signature = _proposal(our_addr, our_key)
        monkeypatch.setattr(proposer, "_record_proposal_vote", lambda *_a, **_k: False)
        monkeypatch.setattr(proposer, "_run_consensus_gates", AsyncMock(side_effect=AssertionError("gates ran")))

        assert await proposer._run_journaled_gates(None, _block(our_addr, signature), HB, our_addr, 0, H, {}, []) is False
        assert mgr.slashing_events == []  # the signature never left, so no evidence is owed

    @pytest.mark.asyncio
    async def test_valve_route_proposal_after_a_real_attestation_vote(self, monkeypatch):
        """The D9b scenario at unit level: vote A, valve opens, propose rival B."""
        svc, mgr, our_addr, our_key, other_proposer, clock = _setup(monkeypatch)
        await svc._handle_request(_request(H, HA, other_proposer, clock))
        clock.advance(301)  # past vote_journal_unlock_seconds
        monkeypatch.setattr(poa_module, "locate_voted_block", AsyncMock(return_value=None))
        proposer = _proposer_with(svc)
        assert await proposer._honor_vote_journal(H, our_addr) is False  # valve opened -> may propose

        _, signature = _proposal(our_addr, our_key)
        monkeypatch.setattr(proposer, "_run_consensus_gates", AsyncMock(return_value=True))
        assert await proposer._run_journaled_gates(None, _block(our_addr, signature), HB, our_addr, 0, H, {}, [])

        assert len(mgr.slashing_events) == 1
        assert event_signature_evidence(mgr.slashing_events[0]) is not None
        assert _verdict(mgr, our_addr) is None

    def test_recording_failure_is_loud_not_silent_and_does_not_stall_the_proposal(self, monkeypatch):
        svc, _, our_addr, our_key, _, _ = _setup(monkeypatch)
        proposer = _proposer_with(svc)
        _, signature = _proposal(our_addr, our_key)

        def boom(*_a, **_k):
            raise RuntimeError("evidence store down")

        monkeypatch.setattr(svc, "record_proposal_equivocation", boom)
        proposer._record_proposal_equivocation(_block(our_addr, signature), our_addr, 0)  # must not raise
        assert _counter("proposal_equivocation_record_failed_total") == 1

    def test_no_service_or_no_signature_is_a_no_op(self, monkeypatch):
        svc, mgr, our_addr, our_key, _, _ = _setup(monkeypatch)
        proposer = _proposer_with(None)
        proposer._record_proposal_equivocation(_block(our_addr, "0xsig"), our_addr, 0)  # no service
        proposer = _proposer_with(svc)
        proposer._record_proposal_equivocation(_block(our_addr, ""), our_addr, 0)  # unsigned
        assert mgr.slashing_events == []
        assert _counter("proposal_equivocation_record_failed_total") == 0
