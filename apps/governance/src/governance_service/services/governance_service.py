"""
Governance service for managing governance operations
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
from typing import Any, cast

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from ..clients.blockchain import BlockchainClient
from ..config import settings
from ..domain.governance import (
    DaoTreasury,
    Delegation,
    GovernanceProfile,
    GovernanceToken,
    Proposal,
    ProposalExecutionLog,
    ProposalStatus,
    TokenStake,
    Vote,
)
from .governance_service_common import (
    _OPS_ERRORS,
    _RECONCILE_NEG_CACHE_SECONDS,
    _RECONCILE_PROBE_CONCURRENCY,
    _VOTE_UNIQUE_INDEX,  # noqa: F401 - re-exported; lives in governance_service_common now
    _parse_datetime,
)
from .governance_service_execution import _ExecutionMixin
from .governance_service_votes import _VotesMixin

logger = logging.getLogger(__name__)


class GovernanceService(_VotesMixin, _ExecutionMixin):
    def __init__(self, session: AsyncSession, blockchain_client: BlockchainClient | None = None):
        self.session = session
        self._blockchain = blockchain_client or BlockchainClient(
            rpc_url=settings.blockchain_rpc_url,
        )

    @staticmethod
    def _verify_client_signed_tx(
        signed_tx: dict[str, Any],
        tx_type: str,
        expected_signer: str,
        expected_payload_fields: dict[str, Any],
    ) -> None:
        """Reject a client-signed governance tx that does not match the action.

        Checks the self-consistency the record layer relies on: the tx type,
        that ``from``/``to`` equal the claimed acting address (signature
        recovery itself happens in ``submit_signed_governance_tx``), and that
        the payload fields the node validates name this specific action —
        otherwise a signature made for a different proposal/vote could be
        re-attached to this request.

        Raises ValueError on any mismatch.
        """
        if not isinstance(signed_tx, dict):
            raise ValueError("signed_tx must be an object")
        if signed_tx.get("type") != tx_type:
            raise ValueError(f"signed_tx.type must be {tx_type}")
        for field in ("from", "to"):
            if str(signed_tx.get(field, "")).lower() != expected_signer.lower():
                raise ValueError(f"signed_tx.{field} must equal the acting address")
        payload = signed_tx.get("payload") or {}
        for key, expected in expected_payload_fields.items():
            actual = payload.get(key)
            if isinstance(expected, (int, float, Decimal)) and isinstance(actual, (int, float, Decimal)):
                if Decimal(str(actual)) != Decimal(str(expected)):
                    raise ValueError(f"signed_tx.payload.{key} does not match the request")
            elif str(actual or "").lower() != str(expected).lower():
                raise ValueError(f"signed_tx.payload.{key} does not match the request")

    async def list_profiles(
        self,
        role: str | None = None,
        user_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[GovernanceProfile]:
        """List governance profiles.

        ``limit`` is opt-in: internal callers (e.g. dedup scans) must not
        silently truncate, so ``None`` keeps the unbounded read.
        """
        stmt = select(GovernanceProfile)
        if role:
            stmt = stmt.where(GovernanceProfile.role == role)
        if user_id:
            stmt = stmt.where(GovernanceProfile.user_id == user_id)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_profile(self, profile_id: str) -> GovernanceProfile | None:
        """Get a specific governance profile"""
        stmt = select(GovernanceProfile).where(GovernanceProfile.profile_id == profile_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_profile(self, profile_data: dict[str, Any]) -> GovernanceProfile:
        """Create a new governance profile"""
        profile = GovernanceProfile(**profile_data)
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def list_proposals(
        self,
        status: str | None = None,
        category: str | None = None,
        proposer_id: str | None = None,
        limit: int = 100,
    ) -> list[Proposal]:
        """List governance proposals.

        ``limit`` bounds the SQL read *before* the on-chain reconcile probes —
        one GET used to scan every proposal and fire an RPC probe per row
        (#1406)."""
        stmt = select(Proposal)
        if status:
            stmt = stmt.where(Proposal.status == status)
        if category:
            stmt = stmt.where(Proposal.category == category)
        if proposer_id:
            stmt = stmt.where(Proposal.proposer_id == proposer_id)
        result = await self.session.execute(stmt.limit(limit))
        proposals = list(result.scalars().all())
        # Probes are one RPC call per proposal: run them bounded-concurrent
        # (a list over N stale proposals used to serialize N RPCs), then
        # stamp serially — AsyncSession is not safe for concurrent writes.
        semaphore = asyncio.Semaphore(_RECONCILE_PROBE_CONCURRENCY)

        async def _probe(p: Proposal) -> dict[str, Any] | None:
            async with semaphore:
                return await self._reconcile_probe_onchain(p)

        sealed_answers = await asyncio.gather(*(_probe(p) for p in proposals))
        for proposal, sealed in zip(proposals, sealed_answers, strict=True):
            if sealed and sealed.get("executed"):
                await self._stamp_executed_from_chain(proposal, sealed)
        return proposals

    async def get_proposal(self, proposal_id: str) -> Proposal | None:
        """Get a specific proposal"""
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalars().first()
        if proposal is not None:
            await self._reconcile_executed_onchain(proposal)
        return proposal

    _reconcile_neg_cache: dict[tuple[str | None, str], float] = {}

    async def _reconcile_executed_onchain(self, proposal: Proposal) -> Proposal:
        """Probe the chain for a sealed EXECUTE and stamp the row when found.

        Kept thin: the probe half is shared with list_proposals (which runs it
        bounded-concurrent and stamps serially).
        """
        sealed = await self._reconcile_probe_onchain(proposal)
        if not sealed or not sealed.get("executed"):
            return proposal
        return await self._stamp_executed_from_chain(proposal, sealed)

    async def _reconcile_probe_onchain(self, proposal: Proposal) -> dict[str, Any] | None:
        """Ask the node's sealed-proposal view whether an EXECUTE exists.

        A GOVERNANCE_EXECUTE submitted straight to the blockchain RPC seals
        without this service ever seeing it (prop_76855f71, 28 Oct), and the
        service row then reports ``active`` forever.

        Returns the sealed answer dict, or None when the proposal is already
        EXECUTED, still inside its voting window, answered "not executed"
        recently (negative cache), the probe failed, or the answer carries no
        execute. Failure-soft: an unreachable RPC or a missing record returns
        None — a list/get must never fail on a reconcile probe. Probe failures
        are NOT cached, so the next call retries the node.
        """
        if proposal.status == ProposalStatus.EXECUTED:
            return None
        voting_ends = proposal.voting_ends
        if voting_ends is not None:
            if voting_ends.tzinfo is None:
                voting_ends = voting_ends.replace(tzinfo=UTC)
            if datetime.now(UTC) < voting_ends:
                return None
        cache = type(self)._reconcile_neg_cache
        key = (proposal.chain_id, proposal.proposal_id)
        now = time.monotonic()
        for k, expiry in list(cache.items()):
            if expiry <= now:
                del cache[k]
        if cache.get(key, 0.0) > now:
            return None
        try:
            sealed = await self._blockchain.get_sealed_governance_proposal(proposal.proposal_id, proposal.chain_id)
        except _OPS_ERRORS as e:
            logger.warning("chain execute reconcile probe failed for %s: %s", proposal.proposal_id, e)
            return None
        if not sealed or not sealed.get("executed"):
            cache[key] = now + _RECONCILE_NEG_CACHE_SECONDS
            return None
        return sealed

    async def _stamp_executed_from_chain(self, proposal: Proposal, sealed: dict[str, Any]) -> Proposal:
        """Apply the chain's sealed-EXECUTE verdict to the row and log it.

        The status write is a conditional UPDATE (``status != executed``): two
        callers racing the same reconcile both see the sealed verdict, but only
        the winner's update lands and adds the ``reconcile`` log row — the
        loser just refreshes its view. A plain ORM assignment let both write
        and double the audit trail (GOV-LIST-RECONCILE-COST-1).
        """
        height = sealed.get("execute_block_height")
        sealed_at = await self._sealing_block_time(proposal, int(height)) if height is not None else None
        metadata = (
            {**(proposal.proposal_metadata or {}), "execution_block_height": height}
            if height is not None
            else proposal.proposal_metadata
        )
        values: dict[str, Any] = {
            "status": ProposalStatus.EXECUTED,
            "execution_tx_hash": sealed.get("execute_tx_hash"),
        }
        if height is not None:
            values["proposal_metadata"] = metadata
        if sealed_at is not None:
            values["executed_at"] = sealed_at
        result = await self.session.execute(
            update(Proposal)
            .where(
                col(Proposal.proposal_id) == proposal.proposal_id,
                col(Proposal.status) != ProposalStatus.EXECUTED,
            )
            .values(**values)
        )
        # Test stubs and SELECT results carry no rowcount; only an explicit 0
        # means another writer already stamped the row.
        if getattr(result, "rowcount", None) == 0:
            await self.session.refresh(proposal)
            return proposal
        proposal.status = ProposalStatus.EXECUTED
        proposal.execution_tx_hash = sealed.get("execute_tx_hash")
        if height is not None:
            proposal.proposal_metadata = metadata
            if sealed_at is not None:
                proposal.executed_at = sealed_at
        self.session.add(
            ProposalExecutionLog(
                proposal_id=proposal.proposal_id,
                execution_step="reconcile",
                status="completed",
                result={
                    "execute_tx_hash": proposal.execution_tx_hash,
                    "execute_block_height": height,
                    "source": "chain transaction table (sealed-proposal)",
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(proposal)
        return proposal

    async def _stamp_executed_after_execute(
        self,
        proposal_id: str,
        proposal: Proposal,
        execution_log: ProposalExecutionLog,
        *,
        tx_hash: str | None,
        block_height: int | None,
        automation_result: dict[str, Any] | None,
    ) -> Proposal:
        """Conditionally move a SUCCEEDED proposal to EXECUTED (#1803)."""
        executed_at = datetime.now(UTC)
        metadata = proposal.proposal_metadata
        if block_height is not None:
            metadata = {
                **(proposal.proposal_metadata or {}),
                "execution_block_height": block_height,
            }
        values: dict[str, Any] = {
            "status": ProposalStatus.EXECUTED,
            "executed_at": executed_at,
        }
        if tx_hash:
            values["execution_tx_hash"] = tx_hash
        if block_height is not None:
            values["proposal_metadata"] = metadata
        stamp = await self.session.execute(
            update(Proposal)
            .where(
                col(Proposal.proposal_id) == proposal_id,
                col(Proposal.status) == ProposalStatus.SUCCEEDED,
            )
            .values(**values)
        )
        if getattr(stamp, "rowcount", None) == 0:
            await self.session.refresh(proposal)
            execution_log.status = "failed"
            execution_log.error_message = "proposal no longer in succeeded state (concurrent execute)"
            await self.session.commit()
            return proposal

        proposal.status = ProposalStatus.EXECUTED
        proposal.executed_at = executed_at
        if tx_hash:
            proposal.execution_tx_hash = tx_hash
        if block_height is not None:
            proposal.proposal_metadata = metadata

        await self.session.commit()

        execution_log.status = "completed"
        execution_log.result = {
            "executed_at": executed_at.isoformat(),
            "tx_hash": tx_hash,
            "parameter_automation": automation_result,
        }

        await self.session.commit()
        await self.session.refresh(proposal)
        return proposal

    async def _sealing_block_time(self, proposal: Proposal, height: int) -> datetime | None:
        """Timestamp of the block that sealed the EXECUTE, or None if unreadable —
        the status write stays honest without it rather than inventing a time."""
        try:
            block = await self._blockchain.get_block(height, proposal.chain_id)
            sealed_at = _parse_datetime((block or {}).get("timestamp"))
        except _OPS_ERRORS as e:
            logger.warning("chain execute reconcile could not read block %s for %s: %s", height, proposal.proposal_id, e)
            return None
        if sealed_at is not None and sealed_at.tzinfo is None:
            # The chain stores naive UTC timestamps.
            sealed_at = sealed_at.replace(tzinfo=UTC)
        return sealed_at

    @staticmethod
    def _apply_emergency_overrides(proposal: Proposal, now: datetime) -> None:
        """v0.7.4: accelerated timelock/quorum for emergency proposals."""
        # Override voting period and quorum for emergency proposals
        proposal.voting_starts = now
        proposal.voting_ends = now + timedelta(
            seconds=settings.emergency_voting_period_blocks * 2  # ~2s block time
        )
        proposal.quorum_required = Decimal(str(settings.emergency_quorum_percent))
        proposal.passing_threshold = settings.emergency_approval_percent / 100.0
        # Store emergency metadata
        proposal.proposal_metadata = {
            **proposal.proposal_metadata,
            "is_emergency": True,
            "emergency_timelock_blocks": settings.emergency_timelock_blocks,
            "normal_timelock_blocks": settings.timelock_blocks,
        }

    async def _ensure_governance_profile(self, user_id: str) -> None:
        """Auto-create a governance profile for a user if one does not
        already exist (fresh databases start with an empty profile table)."""
        existing_profile = await self.get_profile(user_id)
        if existing_profile:
            return
        await self.session.execute(
            text(
                """INSERT INTO governance_profiles
                (profile_id, user_id, role, voting_power, delegated_power, total_votes_cast, proposals_created, proposals_passed, delegate_to, joined_at, last_voted_at)
                VALUES (:profile_id, :user_id, 'MEMBER', 0, 0, 0, 0, 0, NULL, CURRENT_TIMESTAMP, NULL)
                ON CONFLICT (profile_id) DO NOTHING"""
            ),
            {"profile_id": user_id, "user_id": user_id},
        )
        await self.session.commit()

    @staticmethod
    def _assert_voting_window(proposal_status: Proposal, vote_proposal_id: str) -> None:
        """Reject votes outside the proposal's voting window (mirrors
        close_proposal's tz handling)."""
        now = datetime.now(UTC)
        for bound, too_late in (
            (proposal_status.voting_starts, False),
            (proposal_status.voting_ends, True),
        ):
            if bound.tzinfo is None:
                bound = bound.replace(tzinfo=UTC)
            if (too_late and now > bound) or (not too_late and now < bound):
                verb = "has ended" if too_late else "has not started"
                raise ValueError(f"Voting period {verb} for proposal {vote_proposal_id}")

    async def _submit_proposal_onchain(
        self, proposal: Proposal, proposal_data: dict[str, Any], signed_tx: Any, is_emergency: bool
    ) -> bool:
        """Best-effort on-chain GOVERNANCE_PROPOSE submission. Returns True
        when the submission failed (proposal keeps no block height)."""
        if not settings.enable_onchain_submission:
            return False
        if signed_tx is not None:
            try:
                proposer_address = proposal_data.get("proposer_address", "")
                self._verify_client_signed_tx(
                    signed_tx,
                    "GOVERNANCE_PROPOSE",
                    proposer_address,
                    {"proposal_id": proposal.proposal_id, "proposer": proposer_address, "chain_id": proposal.chain_id},
                )
                result = await self._blockchain.submit_signed_governance_tx(signed_tx)
                proposal.tx_hash = result.get("tx_hash") or result.get("transaction_hash")
                proposal.block_height = result.get("block_height")
                if proposal.block_height is not None:
                    voting_period = settings.emergency_voting_period_blocks if is_emergency else settings.voting_period_blocks
                    proposal.voting_ends_block = proposal.block_height + voting_period
            except _OPS_ERRORS as e:
                import logging

                logging.getLogger(__name__).warning(
                    "Client-signed GOVERNANCE_PROPOSE submission failed for %s: %s — proposal has no "
                    "recorded block height and will be refused execution while "
                    "require_execution_timelock is set",
                    proposal.proposal_id,
                    e,
                )
                return True
            return False
        if not settings.proposer_private_key:
            return False
        try:
            from aitbc.governance.onchain import build_proposal_tx
            from aitbc.governance.types import ProposalData

            proposer_address = proposal_data.get("proposer_address", "")
            proposal_data_obj = ProposalData(
                proposal_id=proposal.proposal_id,
                proposer=proposer_address,
                title=proposal.title,
                description=proposal.description,
                proposal_type=proposal.proposal_type,
                parameters=proposal.proposal_value,
            )
            payload = build_proposal_tx(proposal_data_obj)
            result = await self._blockchain.submit_governance_tx(
                tx_type="GOVERNANCE_PROPOSE",
                sender=proposer_address,
                private_key=settings.proposer_private_key,
                payload=payload,
                chain_id=proposal.chain_id,
            )
            # The node's /rpc/transaction response uses transaction_hash
            # (mempool admission); tx_hash is accepted as a fallback for
            # peers that already return the mined form.
            proposal.tx_hash = result.get("tx_hash") or result.get("transaction_hash")
            proposal.block_height = result.get("block_height")
            # V23-18: record where voting closes, so the execution timelock can run
            # from the end of voting rather than from proposal creation. Captured now
            # because the voting-period setting may differ by the time this proposal
            # is executed.
            if proposal.block_height is not None:
                voting_period = settings.emergency_voting_period_blocks if is_emergency else settings.voting_period_blocks
                proposal.voting_ends_block = proposal.block_height + voting_period
        except _OPS_ERRORS as e:
            # On-chain submission stays best-effort: a chain hiccup must not stop a
            # proposal being recorded. It does, however, leave the proposal without a
            # block height — and execute_proposal refuses to execute such a proposal,
            # because the timelock cannot be verified without one. Warn accordingly.
            import logging

            logging.getLogger(__name__).warning(
                "On-chain GOVERNANCE_PROPOSE submission failed for %s: %s — proposal has no "
                "recorded block height and will be refused execution while "
                "require_execution_timelock is set",
                proposal.proposal_id,
                e,
            )
            return True
        return False

    async def _submit_vote_onchain(self, vote: Vote, vote_data: dict[str, Any], signed_tx: Any, voter_address: str) -> None:
        """Best-effort on-chain GOVERNANCE_VOTE submission (client-signed or
        proposer-key); failures are logged, never raised."""
        if not settings.enable_onchain_submission:
            return
        if signed_tx is not None:
            try:
                voting_power = await self._blockchain.get_voting_power(voter_address, vote.chain_id)
                self._verify_client_signed_tx(
                    signed_tx,
                    "GOVERNANCE_VOTE",
                    voter_address,
                    {
                        "proposal_id": vote.proposal_id,
                        "voter": voter_address,
                        "vote_type": str(vote.vote_type),
                        "voting_power": voting_power,
                        "chain_id": vote.chain_id,
                    },
                )
                vote.voting_power = voting_power
                vote.power_at_snapshot = voting_power
                result = await self._blockchain.submit_signed_governance_tx(signed_tx)
                vote.tx_hash = result.get("tx_hash") or result.get("transaction_hash")
                vote.block_height = result.get("block_height")
            except _OPS_ERRORS as e:
                import logging

                logging.getLogger(__name__).warning(
                    "Client-signed GOVERNANCE_VOTE submission failed for %s: %s",
                    vote.proposal_id,
                    e,
                )
            return
        if not settings.proposer_private_key:
            return
        try:
            from aitbc.governance.onchain import build_vote_tx
            from aitbc.governance.types import VoteData

            # Query on-chain balance for voting power snapshot
            voting_power = await self._blockchain.get_voting_power(voter_address, vote.chain_id)
            vote.voting_power = voting_power
            vote.power_at_snapshot = voting_power

            vote_data_obj = VoteData(
                proposal_id=vote.proposal_id,
                voter=voter_address,
                vote_type=str(vote.vote_type),
                voting_power=float(voting_power),
                reason=vote.reason or "",
                chain_id=vote.chain_id,
            )
            payload = build_vote_tx(vote_data_obj)
            result = await self._blockchain.submit_governance_tx(
                tx_type="GOVERNANCE_VOTE",
                sender=voter_address,
                private_key=settings.proposer_private_key,
                payload=payload,
                chain_id=vote.chain_id,
            )
            vote.tx_hash = result.get("tx_hash") or result.get("transaction_hash")
            vote.block_height = result.get("block_height")
        except _OPS_ERRORS as e:
            import logging

            logging.getLogger(__name__).warning("On-chain GOVERNANCE_VOTE submission failed: %s", e)

    async def create_proposal(self, proposal_data: dict[str, Any]) -> Proposal:
        """Create a new proposal.

        When on-chain submission is enabled (``enable_onchain_submission``),
        submits a GOVERNANCE_PROPOSE transaction to the blockchain and stores
        the resulting tx_hash and block_height on the proposal.

        v0.7.4: Emergency proposals get an accelerated timelock (4h vs 24h),
        shorter voting period (2h vs 4h), and higher quorum (80% vs 30%).
        """
        for key in ("voting_starts", "voting_ends", "created_at", "executed_at", "snapshot_timestamp", "execution_timestamp"):
            if key in proposal_data and proposal_data[key] is not None:
                proposal_data[key] = _parse_datetime(proposal_data[key])

        # Client-signed on-chain submission (GAP-50): the caller's wallet signs
        # the GOVERNANCE_PROPOSE tx; this service verifies and relays it. Kept
        # out of the model kwargs — signed_tx is not a Proposal column.
        signed_tx = proposal_data.pop("signed_tx", None)

        # Auto-create a governance profile for the proposer if one does not
        # already exist. The CLI passes the node/agent ID as the proposer, and
        # the profile table is otherwise empty on a fresh database.
        proposer_id = proposal_data.get("proposer_id") or "anonymous"
        await self._ensure_governance_profile(proposer_id)

        proposal = Proposal(**proposal_data)
        # Ensure chain_id is set. If the proposal body did not provide one, the
        # model default is "ait-hub", which may not match the blockchain service's
        # fully-qualified chain id. Use the service default so block-height and
        # timelock queries resolve to the correct chain database.
        proposal.chain_id = settings.default_chain_id or proposal.chain_id

        # Set voting period if not already provided
        from datetime import timedelta

        now = datetime.now(UTC)
        if not proposal.voting_starts:
            proposal.voting_starts = now
        if not proposal.voting_ends:
            proposal.voting_ends = now + timedelta(
                seconds=settings.voting_period_blocks * 2  # ~2s block time
            )

        # v0.7.4: Emergency proposal fast-track
        is_emergency = proposal.proposal_type == "emergency"
        if is_emergency:
            self._apply_emergency_overrides(proposal, now)

        # Proposals are immediately active so they can be voted on and closed.
        if proposal.status == ProposalStatus.DRAFT:
            proposal.status = ProposalStatus.ACTIVE

        submission_failed = await self._submit_proposal_onchain(proposal, proposal_data, signed_tx, is_emergency)

        # V23-18 off-chain fallback: the mempool-admission response carries no
        # block_height even when on-chain submission succeeds, so a proposal
        # still missing a height — submission off, or on but the tx is only
        # queued — queries the chain directly and records voting_ends_block so
        # the timelock can be measured from the end of voting. A submission that
        # *failed* is deliberately excluded: its missing heights are what block
        # the proposal from executing while require_execution_timelock is set.
        if proposal.block_height is None and not submission_failed:
            try:
                proposal.block_height = await self._blockchain.get_block_height(proposal.chain_id)
                voting_period = settings.emergency_voting_period_blocks if is_emergency else settings.voting_period_blocks
                proposal.voting_ends_block = proposal.block_height + voting_period
                logger.info(
                    "Recorded off-chain block height for proposal %s: height=%s, voting_ends_block=%s",
                    proposal.proposal_id,
                    proposal.block_height,
                    proposal.voting_ends_block,
                )
            except _OPS_ERRORS as e:
                logger.warning(
                    "Could not record off-chain block height for proposal %s: %s",
                    proposal.proposal_id,
                    e,
                )

        self.session.add(proposal)
        await self.session.commit()
        await self.session.refresh(proposal)
        return proposal

    async def close_proposal(self, proposal_id: str) -> Proposal:
        """Close an active proposal and tally the result.

        A proposal succeeds when the total participation is at least the
        configured quorum and the approval rate (yes / (yes + no)) meets or
        exceeds the passing threshold. Abstain votes count toward quorum but
        not toward the approval rate.

        If the voting period has ended and the quorum/approval was not met,
        the proposal is marked ``defeated``. If the voting period is still open
        and neither condition is met, closing raises ``ValueError``.
        """
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal not found: {proposal_id}")
        # #1646: EXPIRED means the voting window ended unswept/uncalled — it is
        # still closable; the tally below resolves it to SUCCEEDED/DEFEATED.
        if proposal.status not in (ProposalStatus.ACTIVE, ProposalStatus.EXPIRED):
            raise ValueError(f"Proposal must be active to close; current status: {proposal.status}")

        now = datetime.now(UTC)
        voting_ends = proposal.voting_ends
        if voting_ends.tzinfo is None:
            voting_ends = voting_ends.replace(tzinfo=UTC)
        voting_ended = now >= voting_ends

        yes = proposal.yes_votes
        no = proposal.no_votes
        abstain = proposal.votes_abstain
        total_votes = yes + no + abstain

        quorum_met = total_votes >= proposal.quorum_required
        decisive_votes = yes + no
        approval_rate = (yes / decisive_votes) if decisive_votes > 0 else Decimal("0")
        threshold_met = approval_rate >= Decimal(str(proposal.passing_threshold))

        # V23-18: off-chain proposals may not have voting_ends_block set yet if the
        # creation-time block height query failed. Try once more at close time so the
        # execution timelock has an anchor. Failure here is logged but does not prevent
        # closing; execute_proposal will still refuse to run without the block.
        if proposal.voting_ends_block is None:
            try:
                proposal.voting_ends_block = await self._blockchain.get_block_height(proposal.chain_id)
                await self.session.commit()
                logger.info(
                    "Recorded voting_ends_block at close for proposal %s: %s",
                    proposal.proposal_id,
                    proposal.voting_ends_block,
                )
            except _OPS_ERRORS as e:
                logger.warning(
                    "Could not record voting_ends_block at close for proposal %s: %s",
                    proposal.proposal_id,
                    e,
                )

        if quorum_met and threshold_met:
            updated = await self.update_proposal_status(proposal_id, ProposalStatus.SUCCEEDED)
            return updated if updated is not None else proposal

        if not voting_ended:
            raise ValueError(
                f"Voting still open and quorum/approval not yet met: "
                f"{total_votes} / {proposal.quorum_required} votes, "
                f"{approval_rate:.2%} approval (threshold {proposal.passing_threshold:.0%})"
            )

        updated = await self.update_proposal_status(proposal_id, ProposalStatus.DEFEATED)
        return updated if updated is not None else proposal

    async def expire_stale_proposals(self) -> int:
        """Mark ACTIVE proposals whose voting window has ended as EXPIRED (#1646).

        ``create_vote`` already refuses votes outside the window and tallies are
        frozen at ``voting_ends``, so this changes only the stored status — it
        does not touch any tally. ``close_proposal`` still accepts EXPIRED and
        resolves it to SUCCEEDED/DEFEATED, so an expired proposal is never
        stranded. Returns the number of proposals transitioned.
        """
        now = datetime.now(UTC)
        stmt = (
            update(Proposal)
            .where(col(Proposal.status) == ProposalStatus.ACTIVE)
            .where(col(Proposal.voting_ends) < now)
            .values(status=ProposalStatus.EXPIRED)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return cast(Any, result).rowcount or 0

    async def get_treasury(self) -> DaoTreasury | None:
        """Get DAO treasury"""
        stmt = select(DaoTreasury).where(DaoTreasury.treasury_id == "main_treasury")
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_analytics(self, period: str = "monthly") -> dict[str, Any]:
        """Get governance analytics"""
        return {
            "period": period,
            "total_proposals": 0,
            "active_proposals": 0,
            "passed_proposals": 0,
            "total_votes": 0,
        }

    async def update_proposal_status(self, proposal_id: str, status: str) -> Proposal | None:
        """Update proposal status.

        v0.7.4: When transitioning to ``succeeded``, emergency proposals must
        meet the 80% emergency quorum and 2/3 supermajority approval.
        """
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalars().first()

        if proposal:
            # v0.7.4: Emergency proposal quorum enforcement on transition to succeeded
            if status == "succeeded" and proposal.proposal_type == "emergency":
                total_votes = proposal.yes_votes + proposal.no_votes + proposal.votes_abstain
                # #1647: same formula as close_proposal — abstentions count toward
                # quorum but not the approval denominator (yes / (yes + no)).
                decisive_votes = proposal.yes_votes + proposal.no_votes
                if total_votes > 0:
                    approval_rate = (proposal.yes_votes / decisive_votes) if decisive_votes > 0 else Decimal("0")
                    if approval_rate < settings.emergency_approval_percent / 100.0:
                        raise ValueError(
                            f"Emergency proposal approval {approval_rate:.1%} below "
                            f"required {settings.emergency_approval_percent:.1%} supermajority"
                        )
                    # Check quorum — emergency requires 80%
                    quorum_met = total_votes >= proposal.quorum_required
                    if not quorum_met:
                        raise ValueError(
                            f"Emergency proposal quorum not met: {total_votes} / {proposal.quorum_required} (80% required)"
                        )

            proposal.status = ProposalStatus(status)
            await self.session.commit()
            await self.session.refresh(proposal)

        return proposal

    def get_current_timestamp(self) -> int:
        """Get current Unix timestamp"""
        return int(time.time())

    # Token Staking Methods
    async def stake_tokens(self, staker_address: str, amount: Decimal, lock_period_days: int) -> TokenStake:
        """Stake tokens for enhanced voting power"""
        # #1644: amounts feed staked_tokens → voting power, and vote tallies.
        # A negative or zero amount is never legitimate — it would drive
        # voting power (and voting_power_used) negative and subtract from
        # proposal tallies.
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError(f"Stake amount must be positive, got {amount}")
        if lock_period_days < 0:
            raise ValueError(f"lock_period_days must be non-negative, got {lock_period_days}")
        stake = TokenStake(
            staker_address=staker_address,
            amount_staked=amount,
            lock_period_days=lock_period_days,
            staked_at=datetime.now(UTC).replace(tzinfo=None),
            unstakes_at=(datetime.now(UTC) + timedelta(days=lock_period_days)).replace(tzinfo=None),
            is_active=True,
        )
        self.session.add(stake)

        # Update governance token record
        token_record = await self._get_or_create_token_record(staker_address)
        token_record.staked_tokens += amount
        token_record.voting_power = await self.calculate_voting_power(staker_address)

        await self.session.commit()
        return stake

    async def calculate_voting_power(self, address: str) -> Decimal:
        """Calculate total voting power for address"""
        token_record = await self._get_token_record(address)
        if not token_record:
            return Decimal("0")

        # Formula: balance + (staked * 2)
        base_power = token_record.token_balance
        staking_bonus = token_record.staked_tokens * 2
        return Decimal(base_power + staking_bonus)

    async def _get_or_create_token_record(self, address: str) -> GovernanceToken:
        """Get or create governance token record for address"""
        token_record = await self._get_token_record(address)
        if not token_record:
            token_record = GovernanceToken(
                holder_address=address,
                token_balance=Decimal("0"),
                staked_tokens=Decimal("0"),
                voting_power=Decimal("0"),
            )
            self.session.add(token_record)
            await self.session.commit()
            await self.session.refresh(token_record)
        return token_record

    async def _get_token_record(self, address: str) -> GovernanceToken | None:
        """Get governance token record for address"""
        stmt = select(GovernanceToken).where(GovernanceToken.holder_address == address)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    # Delegation Methods
    async def delegate_voting_power(self, delegator_address: str, delegate_address: str, amount: Decimal) -> Delegation:
        """Delegate voting power to another address"""
        # Verify delegator has enough power
        delegator_power = await self.calculate_voting_power(delegator_address)
        amount_dec = Decimal(str(amount))
        # #1644: the power check only rejects amount > power — a zero or
        # negative amount slipped through and stored a meaningless (or
        # tally-subtracting) delegation row.
        if amount_dec <= 0:
            raise ValueError(f"Delegation amount must be positive, got {amount_dec}")
        if delegator_power < amount_dec:
            raise ValueError(f"Insufficient voting power: {delegator_power} < {amount_dec}")

        delegation = Delegation(
            delegator_address=delegator_address,
            delegate_address=delegate_address,
            voting_power=amount_dec,
            is_active=True,
        )
        self.session.add(delegation)
        await self.session.commit()
        return delegation
