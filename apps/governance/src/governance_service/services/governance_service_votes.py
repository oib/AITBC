"""Vote listing/persistence and vote creation for ``GovernanceService`` (#1860 Phase 6 split).

Pure-move split of the vote-side methods of
``governance_service.governance_service``: ``list_votes``,
``_persist_vote``, ``_assert_not_duplicate_vote`` and ``create_vote`` now
live on the ``_VotesMixin`` base class. ``governance_service.py`` composes
``GovernanceService`` from this mixin and the execution mixin, so the
method surface — including ``GovernanceService.<method>`` attribute access
used by tests — is unchanged. Moved code is byte-identical; shared module
names (``_OPS_ERRORS``, ``_parse_datetime``, ``_VOTE_UNIQUE_INDEX``) come
from ``governance_service_common``.

Import ``governance_service.governance_service`` (or
``governance_service.services``); this module is not meant to be imported
directly.
"""

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from ..config import settings
from ..domain.governance import Proposal, ProposalStatus, Vote, VoteType
from .governance_service_common import _OPS_ERRORS, _VOTE_UNIQUE_INDEX, _parse_datetime

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Caller-settable fields on POST /v1/governance/votes (and the transaction
# relay). Everything else — weight snapshots, delegated_from, signature,
# block_height, tx_hash, created_at, vote_id — is server-controlled (#2934).
_VOTE_CALLER_FIELDS = frozenset(
    {
        "proposal_id",
        "voter_id",
        "voter_address",
        "vote_type",
        "reason",
        "chain_id",
    }
)


class _VotesMixin:
    if TYPE_CHECKING:
        # Attributes and sibling methods supplied by ``GovernanceService``
        # (and the execution mixin) once the bases are composed — declared
        # here so mypy can check the moved bodies.
        session: AsyncSession

        async def get_proposal(self, proposal_id: str) -> Proposal | None: ...

        @staticmethod
        def _assert_voting_window(proposal_status: Proposal, vote_proposal_id: str) -> None: ...

        async def _ensure_governance_profile(self, user_id: str) -> None: ...

        async def _submit_vote_onchain(
            self, vote: Vote, vote_data: dict[str, Any], signed_tx: Any, voter_address: str
        ) -> None: ...

        async def calculate_voting_power(self, address: str) -> Decimal: ...

    async def list_votes(
        self,
        proposal_id: str | None = None,
        voter_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Vote]:
        """List votes.

        ``limit`` is opt-in: the duplicate-vote scan in ``create_vote`` and
        the ``aggregate-votes`` tally need every row, so ``None`` keeps the
        unbounded read; only the HTTP list endpoint passes a bound.
        """
        stmt = select(Vote)
        if proposal_id:
            stmt = stmt.where(Vote.proposal_id == proposal_id)
        if voter_id:
            stmt = stmt.where(Vote.voter_id == voter_id)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _persist_vote(self, vote: Vote, voter_id: str, vote_proposal_id: str) -> None:
        """Insert the vote, bump proposal counters, commit — mapping the
        unique-index IntegrityError to the sequential-path duplicate error."""
        try:
            self.session.add(vote)

            # #3064 (AUDIT-GOV-TALLY-RACE-1): bump the proposal counters with
            # a single atomic UPDATE — ``col + :weight`` evaluates inside the
            # database, so concurrent voters on separate sessions can no
            # longer interleave a read-modify-write and silently drop each
            # other's increments (the ORM read this replaces also ran the
            # reconcile probe — an await point — between fetch and write,
            # which is exactly where the lost updates happened). The
            # votes_for / votes_against legacy mirrors move with yes/no.
            # synchronize_session=False keeps this a pure single-statement
            # write; this proposal's in-session copy is reloaded below so
            # attribute reads see the post-increment tally instead of the
            # stale pre-vote counters.
            # ``or`` also guards a NULL weight — ``col + NULL`` would zero
            # the counter column rather than skip the bump.
            weight = vote.voting_power_used or Decimal("0")
            values: dict[str, Any] = {}
            if vote.vote_type == VoteType.FOR:
                values = {
                    "yes_votes": col(Proposal.yes_votes) + weight,
                    "votes_for": col(Proposal.votes_for) + weight,
                }
            elif vote.vote_type == VoteType.AGAINST:
                values = {
                    "no_votes": col(Proposal.no_votes) + weight,
                    "votes_against": col(Proposal.votes_against) + weight,
                }
            elif vote.vote_type == VoteType.ABSTAIN:
                values = {"votes_abstain": col(Proposal.votes_abstain) + weight}
            if values:
                await self.session.execute(
                    update(Proposal)
                    .where(col(Proposal.proposal_id) == vote.proposal_id)
                    .values(**values)
                    .execution_options(synchronize_session=False)
                )
                # The UPDATE bypassed the ORM: reload this proposal's
                # in-session copy (create_vote's validation read already
                # loaded it) so attribute reads see the post-increment
                # tally. refresh() is awaited here — expiring instead would
                # defer a lazy load that async attribute access cannot
                # serve, breaking callers that reuse the object.
                for obj in self.session.sync_session.identity_map.values():
                    if isinstance(obj, Proposal) and obj.proposal_id == vote.proposal_id:
                        await self.session.refresh(obj)
                        break

            await self.session.commit()
        except IntegrityError as exc:
            # GOV-VOTE-RACE-1 (#1610): the duplicate-vote scan above is
            # check-then-insert; _VOTE_UNIQUE_INDEX is the DB backstop for a
            # racer that passed the same scan. Roll back (which also reverts
            # the proposal vote-counter bump) and surface the same "already
            # voted" error the sequential path raises. Matching on the index
            # name keeps unrelated integrity failures (FK, PK) visible.
            await self.session.rollback()
            if _VOTE_UNIQUE_INDEX in str(exc):
                raise ValueError(f"voter {voter_id} has already voted on proposal {vote_proposal_id}") from None
            raise

    async def _assert_not_duplicate_vote(self, vote_proposal_id: str, voter_id: str) -> None:
        """One vote per voter per proposal — repeats used to stack weight (#1091)."""
        for prior in await self.list_votes(proposal_id=vote_proposal_id):
            if str(prior.voter_id or "").lower() == voter_id.lower():
                raise ValueError(f"voter {voter_id} has already voted on proposal {vote_proposal_id}")

    async def create_vote(self, vote_data: dict[str, Any]) -> Vote:
        """Create a new vote.

        When on-chain submission is enabled, queries the voter's on-chain
        balance for voting power and submits a GOVERNANCE_VOTE transaction.
        The on-chain balance at the current block serves as the voting power
        snapshot.
        """
        for key in ("created_at",):
            if key in vote_data and vote_data[key] is not None:
                vote_data[key] = _parse_datetime(vote_data[key])

        # Client-signed on-chain submission (GAP-50) — not a Vote column.
        signed_tx = vote_data.pop("signed_tx", None)

        # #2934: caller-settable fields only. The request signature proves key
        # ownership, not field sanity — everything else (weight snapshots,
        # delegated_from, signature, block_height, tx_hash, created_at,
        # vote_id) is server-controlled. Weight fields were already popped
        # for #1091; the allowlist makes that structural instead of a list.
        dropped = sorted(set(vote_data) - _VOTE_CALLER_FIELDS)
        if dropped:
            logger.info("create_vote ignoring non-caller fields: %s", ", ".join(dropped))
        vote_data = {k: v for k, v in vote_data.items() if k in _VOTE_CALLER_FIELDS}

        voter_id = vote_data.get("voter_id") or "anonymous"
        vote_proposal_id = str(vote_data.get("proposal_id") or "")

        # One vote per voter per proposal — repeats used to stack weight (#1091).
        proposal_status = await self.get_proposal(vote_proposal_id)
        if proposal_status is None:
            raise ValueError(f"Proposal not found: {vote_proposal_id}")
        if proposal_status.status != ProposalStatus.ACTIVE:
            raise ValueError(f"Proposal is not active (status: {proposal_status.status})")
        # The status stays ACTIVE until close_proposal runs, so without a
        # window check a vote cast after voting_ends still lands in the
        # tallies close_proposal reads — late weight can flip a decided
        # result (#v11 item 11). Mirror close_proposal's tz handling.
        self._assert_voting_window(proposal_status, vote_proposal_id)
        await self._assert_not_duplicate_vote(vote_proposal_id, voter_id)

        await self._ensure_governance_profile(voter_id)

        vote = Vote(**vote_data)
        # Match create_proposal: the service default wins over the model's
        # "ait-hub" fallback so chain queries hit the real chain database.
        vote.chain_id = settings.default_chain_id or vote.chain_id

        voter_address = vote_data.get("voter_address", "")
        if not voter_address:
            voter_address = voter_id
        # #3062: persist the address the weight was computed from — close-time
        # backing re-verification keys on it (voter_id is a profile id).
        vote.voter_address = voter_address

        await self._submit_vote_onchain(vote, vote_data, signed_tx, voter_address)

        # #3062: the tally weight is stake-backed power re-verified at vote
        # time — the raw on-chain balance is movable (no snapshot, no lock)
        # and no longer counts toward any tally. calculate_voting_power
        # fails closed to zero when the chain cannot be queried; the
        # on-chain submission above remains evidence-only.
        try:
            tally_power = await self.calculate_voting_power(voter_address)
        except _OPS_ERRORS as e:
            logger.warning("Could not calculate voting power for %s: %s", voter_address, e)
            tally_power = Decimal("0")
        vote.voting_power = tally_power
        vote.power_at_snapshot = tally_power
        # Server-side voting power: do not let clients self-report unlimited weight.
        vote.voting_power_used = tally_power
        # #2213: vote_weight is the "calculated weight" the record claims was
        # applied — it was write-never and serialized as 0 next to a nonzero
        # voting_power_used, reading as "the vote did not count" when the
        # tally had already counted it.
        vote.vote_weight = tally_power

        await self._persist_vote(vote, voter_id, vote_proposal_id)
        await self.session.refresh(vote)
        return vote
