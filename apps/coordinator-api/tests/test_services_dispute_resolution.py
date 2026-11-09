"""Service-layer tests for governance/services/dispute_resolution.py (#1289 residual).

The dispute service is the in-memory arbitration core behind the
/v1/disputes router (identity binding fixed in #1333/#1334/#1335). These
tests pin its lifecycle contract directly: filing, evidence-phase
membership rules, arbitrator registration, quorum resolution, outcome
accounting, and deadline transitions — including the documented
limitations (in-memory store, asserted-not-escrowed stake).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coordinator_api.contexts.governance.services.dispute_resolution import (
    DisputeOutcome,
    DisputeResolutionService,
    DisputeStatus,
)

CLIENT = "0x" + "11" * 20
PROVIDER = "0x" + "22" * 20
STRANGER = "0x" + "33" * 20


def _service() -> DisputeResolutionService:
    return DisputeResolutionService()


def _file(svc: DisputeResolutionService, **over) -> str:
    kwargs = {
        "job_id": "job-1",
        "client": CLIENT,
        "provider": PROVIDER,
        "amount": 10_000,
        "reason": "work not delivered",
        "filed_by": CLIENT,
    }
    kwargs.update(over)
    return svc.file_dispute(**kwargs).dispute_id


def _register(svc: DisputeResolutionService, *addrs: str) -> None:
    for a in addrs:
        svc.register_arbitrator(a)


class TestFiling:
    def test_file_creates_evidence_phase_with_deadlines(self) -> None:
        svc = _service()
        d = svc.file_dispute(job_id="j1", client=CLIENT, provider=PROVIDER, amount=500, reason="r", filed_by=CLIENT)
        assert d.status == DisputeStatus.evidence_phase
        assert d.dispute_id.startswith("0x")
        assert d.evidence_deadline is not None and d.evidence_deadline > d.created_at
        assert d.voting_deadline is not None and d.voting_deadline > d.evidence_deadline

    def test_initial_evidence_attributed_to_filer(self) -> None:
        svc = _service()
        d = svc.file_dispute(
            job_id="j1",
            client=CLIENT,
            provider=PROVIDER,
            amount=500,
            reason="r",
            filed_by=PROVIDER,
            initial_evidence="logs attached",
        )
        assert len(d.evidence) == 1
        assert d.evidence[0].submitted_by == PROVIDER
        assert d.evidence[0].evidence_type == "initial"

    def test_dispute_ids_unique_per_filing(self) -> None:
        svc = _service()
        ids = {_file(svc, job_id="j1"), _file(svc, job_id="j1")}
        assert len(ids) == 2


class TestEvidence:
    def test_party_can_submit(self) -> None:
        svc = _service()
        did = _file(svc)
        assert svc.submit_evidence(did, PROVIDER, "log", "provider logs") is True
        d = svc.get_dispute(did)
        assert d is not None and d.evidence[-1].submitted_by == PROVIDER

    def test_non_party_rejected(self) -> None:
        svc = _service()
        did = _file(svc)
        with pytest.raises(ValueError, match="Only involved parties"):
            svc.submit_evidence(did, STRANGER, "log", "sneaky")

    def test_unknown_dispute_rejected(self) -> None:
        svc = _service()
        with pytest.raises(ValueError, match="not found"):
            svc.submit_evidence("0xnope", CLIENT, "log", "x")

    def test_evidence_deadline_enforced(self) -> None:
        svc = _service()
        did = _file(svc)
        d = svc.get_dispute(did)
        assert d is not None
        d.evidence_deadline = datetime.now(UTC) - timedelta(seconds=1)
        with pytest.raises(ValueError, match="deadline has passed"):
            svc.submit_evidence(did, CLIENT, "log", "late")

    def test_evidence_rejected_after_voting_phase(self) -> None:
        svc = _service()
        did = _file(svc)
        d = svc.get_dispute(did)
        assert d is not None
        d.status = DisputeStatus.voting_phase
        with pytest.raises(ValueError, match="Cannot submit evidence"):
            svc.submit_evidence(did, CLIENT, "log", "x")


class TestVoting:
    def test_unregistered_arbitrator_rejected(self) -> None:
        svc = _service()
        did = _file(svc)
        with pytest.raises(ValueError, match="Not a registered arbitrator"):
            svc.cast_vote(did, STRANGER, "client_wins", "r", 5000)

    def test_min_stake_enforced(self) -> None:
        svc = _service()
        did = _file(svc)
        _register(svc, STRANGER)
        with pytest.raises(ValueError, match="Minimum stake"):
            svc.cast_vote(did, STRANGER, "client_wins", "r", svc.MIN_STAKE_AMOUNT - 1)

    def test_invalid_outcome_rejected(self) -> None:
        svc = _service()
        did = _file(svc)
        _register(svc, STRANGER)
        with pytest.raises(ValueError, match="Invalid outcome"):
            svc.cast_vote(did, STRANGER, "everyone_wins", "r", 5000)

    def test_duplicate_vote_rejected(self) -> None:
        svc = _service()
        did = _file(svc)
        _register(svc, STRANGER)
        svc.cast_vote(did, STRANGER, "client_wins", "r", 5000)
        with pytest.raises(ValueError, match="already voted"):
            svc.cast_vote(did, STRANGER, "provider_wins", "r", 5000)

    def test_voting_deadline_enforced(self) -> None:
        svc = _service()
        did = _file(svc)
        d = svc.get_dispute(did)
        assert d is not None
        d.voting_deadline = datetime.now(UTC) - timedelta(seconds=1)
        _register(svc, STRANGER)
        with pytest.raises(ValueError, match="Voting deadline"):
            svc.cast_vote(did, STRANGER, "client_wins", "r", 5000)

    def test_evidence_deadline_expiry_flips_to_voting(self) -> None:
        svc = _service()
        did = _file(svc)
        d = svc.get_dispute(did)
        assert d is not None
        d.evidence_deadline = datetime.now(UTC) - timedelta(seconds=1)
        _register(svc, STRANGER)
        assert svc.cast_vote(did, STRANGER, "split", "r", 5000) is True
        assert d.status == DisputeStatus.voting_phase

    def test_resolved_dispute_rejects_votes(self) -> None:
        svc = _service()
        did = _file(svc)
        _register(svc, "0xarb1", "0xarb2", "0xarb3", STRANGER)
        for a in ("0xarb1", "0xarb2", "0xarb3"):
            svc.cast_vote(did, a, "client_wins", "r", 5000)
        d = svc.get_dispute(did)
        assert d is not None and d.status == DisputeStatus.resolved
        with pytest.raises(ValueError, match="Cannot vote"):
            svc.cast_vote(did, STRANGER, "provider_wins", "r", 5000)


class TestResolution:
    @pytest.mark.parametrize(
        "outcome,refund,payout",
        [
            ("client_wins", 10_000, 0),
            ("provider_wins", 0, 10_000),
            ("split", 5_000, 5_000),
        ],
    )
    def test_outcome_accounting(self, outcome: str, refund: int, payout: int) -> None:
        svc = _service()
        did = _file(svc, amount=10_000)
        _register(svc, "0xarb1", "0xarb2", "0xarb3")
        for a in ("0xarb1", "0xarb2", "0xarb3"):
            svc.cast_vote(did, a, outcome, "r", 5000)
        d = svc.get_dispute(did)
        assert d is not None
        assert d.status == DisputeStatus.resolved
        assert d.outcome == DisputeOutcome(outcome)
        assert d.refund_amount == refund
        assert d.payout_amount == payout
        assert d.resolved_at is not None

    def test_quorum_is_min_arbitrators(self) -> None:
        svc = _service()
        did = _file(svc)
        _register(svc, "0xarb1", "0xarb2")
        svc.cast_vote(did, "0xarb1", "client_wins", "r", 5000)
        svc.cast_vote(did, "0xarb2", "client_wins", "r", 5000)
        d = svc.get_dispute(did)
        assert d is not None and d.status != DisputeStatus.resolved

    def test_stake_weighted_winner(self) -> None:
        # 2 votes client_wins (low stake) vs 1 vote provider_wins (high stake)
        # — winner is decided by total stake, not vote count
        svc = _service()
        did = _file(svc, amount=10_000)
        _register(svc, "0xarb1", "0xarb2", "0xarb3")
        svc.cast_vote(did, "0xarb1", "client_wins", "r", 1000)
        svc.cast_vote(did, "0xarb2", "client_wins", "r", 1000)
        svc.cast_vote(did, "0xarb3", "provider_wins", "r", 9000)
        d = svc.get_dispute(did)
        assert d is not None
        assert d.outcome == DisputeOutcome.provider_wins


class TestRegistrationAndQueries:
    def test_register_and_check(self) -> None:
        svc = _service()
        assert svc.is_arbitrator(STRANGER) is False
        svc.register_arbitrator(STRANGER)
        assert svc.is_arbitrator(STRANGER) is True

    def test_get_and_list(self) -> None:
        svc = _service()
        did = _file(svc)
        assert svc.get_dispute(did) is not None
        assert svc.get_dispute("0xmissing") is None
        all_disputes = svc.list_disputes()
        assert len(all_disputes) == 1
        assert svc.list_disputes(status="resolved") == []
        assert len(svc.list_disputes(status="evidence_phase")) == 1
        assert len(svc.list_disputes(party=CLIENT)) == 1
        assert svc.list_disputes(party=STRANGER) == []

    def test_to_dict_shape(self) -> None:
        svc = _service()
        did = _file(svc)
        d = svc.get_dispute(did)
        assert d is not None
        body = d.to_dict()
        assert body["dispute_id"] == did
        assert body["status"] == "evidence_phase"
        assert body["outcome"] is None
        assert body["evidence_count"] == 0
        assert body["vote_count"] == 0
