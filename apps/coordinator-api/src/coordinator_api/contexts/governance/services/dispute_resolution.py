"""
Dispute Resolution Service - On-chain arbitration for market conflicts

Provides:
- Dispute filing by clients or providers
- Evidence submission
- Arbitrator voting
- Automated resolution
- Appeal handling
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import delete
from sqlmodel import col, select

from aitbc.aitbc_logging import get_logger

from ..domain.dispute import (
    DisputeArbitratorRow,
    DisputeCaseRow,
    DisputeEvidenceRow,
    DisputeVoteRow,
)

logger = get_logger(__name__)


class DisputeStatus(Enum):
    """Status of a dispute"""

    pending = "pending"
    under_review = "under_review"
    evidence_phase = "evidence_phase"
    voting_phase = "voting_phase"
    resolved = "resolved"
    appealed = "appealed"
    closed = "closed"


class DisputeOutcome(Enum):
    """Possible outcomes of a dispute"""

    client_wins = "client_wins"
    provider_wins = "provider_wins"
    split = "split"
    canceled = "canceled"


@dataclass
class DisputeEvidence:
    """Evidence submitted for a dispute"""

    submitted_by: str
    evidence_type: str
    description: str
    ipfs_hash: str | None
    timestamp: datetime
    tx_hash: str | None = None


@dataclass
class ArbitratorVote:
    """Vote by an arbitrator"""

    arbitrator: str
    outcome: DisputeOutcome
    reasoning: str
    stake_amount: int
    timestamp: datetime


class DisputeCase:
    """A dispute case"""

    def __init__(self, dispute_id: str, job_id: str, client: str, provider: str, amount: int, reason: str, filed_by: str):
        self.dispute_id = dispute_id
        self.job_id = job_id
        self.client = client
        self.provider = provider
        self.amount = amount
        self.reason = reason
        self.filed_by = filed_by
        self.status = DisputeStatus.pending
        self.outcome: DisputeOutcome | None = None
        self.created_at = datetime.now(UTC)
        self.evidence_deadline: datetime | None = None
        self.voting_deadline: datetime | None = None
        self.resolved_at: datetime | None = None
        self.evidence: list[DisputeEvidence] = []
        self.votes: list[ArbitratorVote] = []
        self.refund_amount: int = 0
        self.payout_amount: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispute_id": self.dispute_id,
            "job_id": self.job_id,
            "client": self.client,
            "provider": self.provider,
            "amount": self.amount,
            "reason": self.reason,
            "filed_by": self.filed_by,
            "status": self.status.value,
            "outcome": self.outcome.value if self.outcome else None,
            "created_at": self.created_at.isoformat(),
            "evidence_deadline": self.evidence_deadline.isoformat() if self.evidence_deadline else None,
            "voting_deadline": self.voting_deadline.isoformat() if self.voting_deadline else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "evidence_count": len(self.evidence),
            "vote_count": len(self.votes),
        }


class DisputeResolutionService:
    """
    Dispute resolution service for market conflicts.

    Handles the full lifecycle of disputes:
    1. Filing - Client or provider opens a dispute
    2. Evidence - Both parties submit evidence
    3. Voting - Arbitrators review and vote
    4. Resolution - Outcome determined and executed
    5. Appeal - Optional second round if appealed
    """

    EVIDENCE_PERIOD_HOURS = 48
    VOTING_PERIOD_HOURS = 24
    MIN_ARBITRATORS = 3
    # Compute-units (AgentStake.amount is denominated in ait_to_units, 1 AIT =
    # 36,000,000 units) — NOT AIT. This is a nonzero-stake sanity check, not
    # the economic floor: AgentStake rows only exist for stakes meeting the
    # upstream >=100 AIT staking requirement, so any ACTIVE row already
    # clears it. Do not "fix" this by multiplying — the unit mismatch was
    # the finding (#1879).
    MIN_STAKE_AMOUNT = 1000

    def __init__(self, session_factory: Any = None) -> None:
        self._session_factory = session_factory
        self._disputes: dict[str, DisputeCase] = {}
        self._arbitrators: set[str] = set()
        if session_factory is not None:
            self._hydrate()

    @contextmanager
    def _session(self) -> Iterator[Any]:
        """Yield a short-lived DB session for one persistence operation.

        ``session_factory`` may be a context-manager factory (e.g.
        ``storage.db.session_scope`` or ``lambda: Session(engine)``) or a
        FastAPI-style generator dependency (``storage.db.get_session``);
        both are driven to yield exactly one session. Yields ``None`` when
        no factory is wired so callers keep pure in-memory behavior.
        """
        if self._session_factory is None:
            yield None
            return
        produced = self._session_factory()
        if hasattr(produced, "__enter__"):
            with produced as session:
                yield session
            return
        # Generator-style dependency: drive it like contextlib does.
        gen = iter(produced)
        try:
            session = next(gen)
        except StopIteration as exc:
            raise RuntimeError("session_factory produced no session") from exc
        try:
            yield session
            try:
                next(gen)
            except StopIteration:
                pass
        finally:
            gen.close()

    @staticmethod
    def _to_db_dt(value: datetime | None) -> datetime | None:
        """Strip tzinfo for storage — SQLite/Postgres DateTime columns are naive."""
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    @staticmethod
    def _from_db_dt(value: datetime | None) -> datetime | None:
        """Re-attach UTC on read so hydrated cases behave like fresh ones."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def _hydrate(self) -> None:
        """Load persisted disputes/arbitrators into the in-memory caches.

        Best-effort: if the tables do not exist yet (migration pending) or
        the DB is unreachable, the service still boots with an empty cache —
        writes remain best-effort too, so behavior never regresses below the
        previous pure in-memory mode.
        """
        try:
            with self._session() as session:
                if session is None:
                    return
                case_rows = session.exec(select(DisputeCaseRow)).all()
                evidence_rows = session.exec(select(DisputeEvidenceRow).order_by(col(DisputeEvidenceRow.id))).all()
                vote_rows = session.exec(select(DisputeVoteRow).order_by(col(DisputeVoteRow.id))).all()
                arb_rows = session.exec(select(DisputeArbitratorRow)).all()
        except Exception as e:  # noqa: BLE001 - boot must survive a missing migration
            logger.warning("Dispute service hydration failed; starting with empty cache: %s", e)
            return

        evidence_by_dispute: dict[str, list[DisputeEvidence]] = {}
        for row in evidence_rows:
            evidence_by_dispute.setdefault(row.dispute_id, []).append(
                DisputeEvidence(
                    submitted_by=row.submitted_by,
                    evidence_type=row.evidence_type,
                    description=row.description,
                    ipfs_hash=row.ipfs_hash,
                    timestamp=self._from_db_dt(row.timestamp) or datetime.now(UTC),
                    tx_hash=row.tx_hash,
                )
            )
        votes_by_dispute: dict[str, list[ArbitratorVote]] = {}
        for row in vote_rows:
            votes_by_dispute.setdefault(row.dispute_id, []).append(
                ArbitratorVote(
                    arbitrator=row.arbitrator,
                    outcome=DisputeOutcome(row.outcome),
                    reasoning=row.reasoning,
                    stake_amount=int(row.stake_amount),
                    timestamp=self._from_db_dt(row.timestamp) or datetime.now(UTC),
                )
            )
        for row in case_rows:
            dispute = DisputeCase(
                dispute_id=row.dispute_id,
                job_id=row.job_id,
                client=row.client,
                provider=row.provider,
                amount=int(row.amount),
                reason=row.reason,
                filed_by=row.filed_by,
            )
            dispute.status = DisputeStatus(row.status)
            dispute.outcome = DisputeOutcome(row.outcome) if row.outcome else None
            dispute.created_at = self._from_db_dt(row.created_at) or dispute.created_at
            dispute.evidence_deadline = self._from_db_dt(row.evidence_deadline)
            dispute.voting_deadline = self._from_db_dt(row.voting_deadline)
            dispute.resolved_at = self._from_db_dt(row.resolved_at)
            dispute.refund_amount = int(row.refund_amount)
            dispute.payout_amount = int(row.payout_amount)
            dispute.evidence = evidence_by_dispute.get(row.dispute_id, [])
            dispute.votes = votes_by_dispute.get(row.dispute_id, [])
            self._disputes[row.dispute_id] = dispute
        self._arbitrators = {row.address for row in arb_rows}
        if case_rows or arb_rows:
            logger.info(
                "Dispute service hydrated: %d disputes, %d arbitrators",
                len(case_rows),
                len(arb_rows),
            )

    def _save_dispute(self, dispute: DisputeCase) -> None:
        """Write-through persist of a dispute and its evidence/votes.

        Children are rewritten wholesale (delete + reinsert in list order) so
        one code path covers filing, evidence, votes, phase flips, and
        resolution. No-op without a session factory; failures are logged and
        never break the in-memory contract.
        """
        if self._session_factory is None:
            return
        try:
            with self._session() as session:
                if session is None:
                    return
                row = session.get(DisputeCaseRow, dispute.dispute_id)
                if row is None:
                    row = DisputeCaseRow(dispute_id=dispute.dispute_id)
                    session.add(row)
                row.job_id = dispute.job_id
                row.client = dispute.client
                row.provider = dispute.provider
                row.amount = dispute.amount
                row.reason = dispute.reason
                row.filed_by = dispute.filed_by
                row.status = dispute.status.value
                row.outcome = dispute.outcome.value if dispute.outcome else None
                row.created_at = self._to_db_dt(dispute.created_at) or dispute.created_at
                row.evidence_deadline = self._to_db_dt(dispute.evidence_deadline)
                row.voting_deadline = self._to_db_dt(dispute.voting_deadline)
                row.resolved_at = self._to_db_dt(dispute.resolved_at)
                row.refund_amount = dispute.refund_amount
                row.payout_amount = dispute.payout_amount

                session.exec(delete(DisputeEvidenceRow).where(col(DisputeEvidenceRow.dispute_id) == dispute.dispute_id))
                for item in dispute.evidence:
                    session.add(
                        DisputeEvidenceRow(
                            dispute_id=dispute.dispute_id,
                            submitted_by=item.submitted_by,
                            evidence_type=item.evidence_type,
                            description=item.description,
                            ipfs_hash=item.ipfs_hash,
                            tx_hash=item.tx_hash,
                            timestamp=self._to_db_dt(item.timestamp) or item.timestamp,
                        )
                    )
                session.exec(delete(DisputeVoteRow).where(col(DisputeVoteRow.dispute_id) == dispute.dispute_id))
                for vote in dispute.votes:
                    session.add(
                        DisputeVoteRow(
                            dispute_id=dispute.dispute_id,
                            arbitrator=vote.arbitrator,
                            outcome=vote.outcome.value,
                            reasoning=vote.reasoning,
                            stake_amount=vote.stake_amount,
                            timestamp=self._to_db_dt(vote.timestamp) or vote.timestamp,
                        )
                    )
                session.commit()
        except Exception as e:  # noqa: BLE001 - persistence must not break arbitration
            logger.error("Failed to persist dispute %s: %s", dispute.dispute_id, e)

    def _save_arbitrator(self, address: str) -> None:
        """Persist an arbitrator registration (idempotent)."""
        if self._session_factory is None:
            return
        try:
            with self._session() as session:
                if session is None:
                    return
                if session.get(DisputeArbitratorRow, address) is None:
                    session.add(
                        DisputeArbitratorRow(
                            address=address,
                            registered_at=self._to_db_dt(datetime.now(UTC)) or datetime.now(UTC),
                        )
                    )
                    session.commit()
        except Exception as e:  # noqa: BLE001 - persistence must not break arbitration
            logger.error("Failed to persist arbitrator %s: %s", address, e)

    def file_dispute(
        self,
        job_id: str,
        client: str,
        provider: str,
        amount: int,
        reason: str,
        filed_by: str,
        initial_evidence: str | None = None,
    ) -> DisputeCase:
        """
        File a new dispute.

        Args:
            job_id: The job being disputed
            client: Client address
            provider: Provider/miner address
            amount: Amount in dispute
            reason: Reason for dispute
            filed_by: Who filed (client or provider)
            initial_evidence: Optional initial evidence

        Returns:
            Created dispute case
        """
        dispute_id = self._generate_dispute_id(job_id, filed_by)
        dispute = DisputeCase(
            dispute_id=dispute_id,
            job_id=job_id,
            client=client,
            provider=provider,
            amount=amount,
            reason=reason,
            filed_by=filed_by,
        )
        now = datetime.now(UTC)
        dispute.evidence_deadline = now + timedelta(hours=self.EVIDENCE_PERIOD_HOURS)
        dispute.voting_deadline = dispute.evidence_deadline + timedelta(hours=self.VOTING_PERIOD_HOURS)
        dispute.status = DisputeStatus.evidence_phase
        if initial_evidence:
            evidence = DisputeEvidence(
                submitted_by=filed_by, evidence_type="initial", description=initial_evidence, ipfs_hash=None, timestamp=now
            )
            dispute.evidence.append(evidence)
        self._disputes[dispute_id] = dispute
        self._save_dispute(dispute)
        logger.info("Dispute filed: %s for job %s by %s", dispute_id, job_id, filed_by)
        return dispute

    def submit_evidence(
        self,
        dispute_id: str,
        submitted_by: str,
        evidence_type: str,
        description: str,
        ipfs_hash: str | None = None,
        caller_identities: set[str] | None = None,
    ) -> bool:
        """Submit evidence for a dispute.

        ``caller_identities`` lets the router pass the caller's full
        identity set (sub + wallet addresses) so a provider whose dispute
        party is stored as a wallet address still matches (#1854).
        """
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute {dispute_id} not found")
        if dispute.status != DisputeStatus.evidence_phase:
            raise ValueError(f"Cannot submit evidence, dispute is {dispute.status.value}")
        if dispute.evidence_deadline and datetime.now(UTC) > dispute.evidence_deadline:
            raise ValueError("Evidence submission deadline has passed")
        parties = {dispute.client.lower(), dispute.provider.lower()}
        identities = {str(i).lower() for i in caller_identities} if caller_identities else set()
        if submitted_by.lower() not in parties and not (parties & identities):
            raise ValueError("Only involved parties can submit evidence")
        evidence = DisputeEvidence(
            submitted_by=submitted_by,
            evidence_type=evidence_type,
            description=description,
            ipfs_hash=ipfs_hash,
            timestamp=datetime.now(UTC),
        )
        dispute.evidence.append(evidence)
        self._save_dispute(dispute)
        logger.info("Evidence submitted for dispute %s by %s", dispute_id, submitted_by)
        return True

    def _dispute_for_voting(self, dispute_id: str) -> DisputeCase:
        """Fetch the dispute and enforce the voting-phase preconditions.

        Advances an evidence-phase dispute to voting_phase once its evidence
        deadline has passed, exactly as ``cast_vote`` did inline.
        """
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute {dispute_id} not found")
        if dispute.status not in [DisputeStatus.voting_phase, DisputeStatus.evidence_phase]:
            raise ValueError(f"Cannot vote, dispute is {dispute.status.value}")
        if dispute.status == DisputeStatus.evidence_phase:
            if dispute.evidence_deadline and datetime.now(UTC) >= dispute.evidence_deadline:
                dispute.status = DisputeStatus.voting_phase
                self._save_dispute(dispute)
        if dispute.voting_deadline and datetime.now(UTC) > dispute.voting_deadline:
            raise ValueError("Voting deadline has passed")
        return dispute

    def _validate_vote_participant(
        self, dispute: DisputeCase, arbitrator: str, outcome: str, stake_amount: int
    ) -> DisputeOutcome:
        """Enforce arbitrator registration, minimum stake, valid outcome,
        and the no-double-vote rule; returns the parsed outcome."""
        if arbitrator not in self._arbitrators:
            raise ValueError("Not a registered arbitrator")
        if stake_amount < self.MIN_STAKE_AMOUNT:
            raise ValueError(f"Minimum stake is {self.MIN_STAKE_AMOUNT}")
        try:
            outcome_enum = DisputeOutcome(outcome)
        except ValueError:
            raise ValueError(f"Invalid outcome: {outcome}") from None
        for vote in dispute.votes:
            if vote.arbitrator == arbitrator:
                raise ValueError("Arbitrator has already voted")
        return outcome_enum

    def cast_vote(self, dispute_id: str, arbitrator: str, outcome: str, reasoning: str, stake_amount: int) -> bool:
        """
        Cast a vote as an arbitrator.

        Args:
            dispute_id: Dispute being voted on
            arbitrator: Arbitrator address
            outcome: "client_wins", "provider_wins", or "split"
            reasoning: Explanation for vote
            stake_amount: Amount staked on this vote
        """
        dispute = self._dispute_for_voting(dispute_id)
        outcome_enum = self._validate_vote_participant(dispute, arbitrator, outcome, stake_amount)
        vote = ArbitratorVote(
            arbitrator=arbitrator,
            outcome=outcome_enum,
            reasoning=reasoning,
            stake_amount=stake_amount,
            timestamp=datetime.now(UTC),
        )
        dispute.votes.append(vote)
        logger.info("Vote cast for dispute %s by %s: %s", dispute_id, arbitrator, outcome)
        if len(dispute.votes) >= self.MIN_ARBITRATORS:
            self._resolve_dispute(dispute)
        self._save_dispute(dispute)
        return True

    def _resolve_dispute(self, dispute: DisputeCase) -> None:
        """Resolve dispute based on votes"""
        if not dispute.votes:
            return
        votes_by_outcome: dict[DisputeOutcome, int] = {}
        total_stake: dict[DisputeOutcome, int] = {}
        for vote in dispute.votes:
            votes_by_outcome[vote.outcome] = votes_by_outcome.get(vote.outcome, 0) + 1
            total_stake[vote.outcome] = total_stake.get(vote.outcome, 0) + vote.stake_amount
        winner = max(total_stake.items(), key=lambda x: x[1])[0]
        dispute.outcome = winner
        dispute.resolved_at = datetime.now(UTC)
        dispute.status = DisputeStatus.resolved
        if winner == DisputeOutcome.client_wins:
            dispute.refund_amount = dispute.amount
            dispute.payout_amount = 0
        elif winner == DisputeOutcome.provider_wins:
            dispute.refund_amount = 0
            dispute.payout_amount = dispute.amount
        elif winner == DisputeOutcome.split:
            split_amount = dispute.amount // 2
            dispute.refund_amount = split_amount
            dispute.payout_amount = split_amount
        logger.info(
            "Dispute %s resolved: %s (refund: %s, payout: %s)",
            dispute.dispute_id,
            winner.value,
            dispute.refund_amount,
            dispute.payout_amount,
        )

    def get_dispute(self, dispute_id: str) -> DisputeCase | None:
        """Get dispute by ID"""
        return self._disputes.get(dispute_id)

    def list_disputes(self, status: str | None = None, party: str | None = None) -> list[DisputeCase]:
        """List disputes with optional filters"""
        result = list(self._disputes.values())
        if status:
            result = [d for d in result if d.status.value == status]
        if party:
            result = [d for d in result if d.client == party or d.provider == party]
        return result

    def register_arbitrator(self, address: str) -> bool:
        """Register an arbitrator"""
        self._arbitrators.add(address)
        self._save_arbitrator(address)
        logger.info("Arbitrator registered: %s", address)
        return True

    def is_arbitrator(self, address: str) -> bool:
        """Check if address is a registered arbitrator"""
        return address in self._arbitrators

    def _generate_dispute_id(self, job_id: str, filed_by: str) -> str:
        """Generate unique dispute ID"""
        data = f"{job_id}:{filed_by}:{datetime.now(UTC).isoformat()}"
        return "0x" + hashlib.sha256(data.encode()).hexdigest()[:32]


_dispute_service: DisputeResolutionService | None = None


def init_dispute_service(session_factory: Any) -> DisputeResolutionService:
    """Initialize global dispute service"""
    global _dispute_service
    _dispute_service = DisputeResolutionService(session_factory)
    return _dispute_service


def get_dispute_service() -> DisputeResolutionService | None:
    """Get global dispute service"""
    return _dispute_service
