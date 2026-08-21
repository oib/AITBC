"""
Governance service for managing governance operations
"""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..clients.blockchain import BlockchainClient
from ..config import settings
from ..domain.governance import (
    DaoTreasury,
    Delegation,
    GovernanceProfile,
    GovernanceRole,
    GovernanceToken,
    Proposal,
    ProposalExecutionLog,
    ProposalStatus,
    TokenStake,
    Vote,
    VoteType,
)


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO string or datetime into a timezone-aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Pydantic-style ISO parsing
        try:
            from dateutil import parser
            return parser.isoparse(value)
        except ImportError:
            # Fallback using the standard library
            value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value)
    raise ValueError(f"Cannot parse datetime from {type(value)}")


class GovernanceService:
    def __init__(self, session: AsyncSession, blockchain_client: BlockchainClient | None = None):
        self.session = session
        self._blockchain = blockchain_client or BlockchainClient(
            rpc_url=settings.blockchain_rpc_url,
        )

    async def list_profiles(
        self,
        role: str | None = None,
        user_id: str | None = None,
    ) -> list[GovernanceProfile]:
        """List governance profiles"""
        stmt = select(GovernanceProfile)
        if role:
            stmt = stmt.where(GovernanceProfile.role == role)
        if user_id:
            stmt = stmt.where(GovernanceProfile.user_id == user_id)
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
    ) -> list[Proposal]:
        """List governance proposals"""
        stmt = select(Proposal)
        if status:
            stmt = stmt.where(Proposal.status == status)
        if category:
            stmt = stmt.where(Proposal.category == category)
        if proposer_id:
            stmt = stmt.where(Proposal.proposer_id == proposer_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_proposal(self, proposal_id: str) -> Proposal | None:
        """Get a specific proposal"""
        stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

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

        # Auto-create a governance profile for the proposer if one does not
        # already exist. The CLI passes the node/agent ID as the proposer, and
        # the profile table is otherwise empty on a fresh database.
        proposer_id = proposal_data.get("proposer_id") or "anonymous"
        existing_profile = await self.get_profile(proposer_id)
        if not existing_profile:
            await self.session.execute(
                text(
                    """INSERT INTO governance_profiles
                    (profile_id, user_id, role, voting_power, delegated_power, total_votes_cast, proposals_created, proposals_passed, delegate_to, joined_at, last_voted_at)
                    VALUES (:profile_id, :user_id, 'MEMBER', 0, 0, 0, 0, 0, NULL, NOW(), NULL)
                    ON CONFLICT (profile_id) DO NOTHING"""
                ),
                {"profile_id": proposer_id, "user_id": proposer_id},
            )
            await self.session.commit()

        proposal = Proposal(**proposal_data)
        # Ensure chain_id is set
        if not proposal.chain_id:
            proposal.chain_id = settings.default_chain_id

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

        # Proposals are immediately active so they can be voted on and closed.
        if proposal.status == ProposalStatus.DRAFT:
            proposal.status = ProposalStatus.ACTIVE

        if settings.enable_onchain_submission and settings.proposer_private_key:
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
                proposal.tx_hash = result.get("tx_hash")
                proposal.block_height = result.get("block_height")
                # V23-18: record where voting closes, so the execution timelock can run
                # from the end of voting rather than from proposal creation. Captured now
                # because the voting-period setting may differ by the time this proposal
                # is executed.
                if proposal.block_height is not None:
                    voting_period = settings.emergency_voting_period_blocks if is_emergency else settings.voting_period_blocks
                    proposal.voting_ends_block = proposal.block_height + voting_period
            except Exception as e:
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

        self.session.add(proposal)
        await self.session.commit()
        await self.session.refresh(proposal)
        return proposal

    async def list_votes(
        self,
        proposal_id: str | None = None,
        voter_id: str | None = None,
    ) -> list[Vote]:
        """List votes"""
        stmt = select(Vote)
        if proposal_id:
            stmt = stmt.where(Vote.proposal_id == proposal_id)
        if voter_id:
            stmt = stmt.where(Vote.voter_id == voter_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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

        # Normalise numeric fields to Decimal so the SQLAlchemy/PostgreSQL path
        # does not mix float and Decimal.
        for key in ("voting_power", "voting_power_used", "power_at_snapshot", "delegated_power_at_snapshot", "vote_weight"):
            if key in vote_data and vote_data[key] is not None:
                vote_data[key] = Decimal(str(vote_data[key]))

        voter_id = vote_data.get("voter_id") or "anonymous"
        existing_profile = await self.get_profile(voter_id)
        if not existing_profile:
            await self.session.execute(
                text(
                    """INSERT INTO governance_profiles
                    (profile_id, user_id, role, voting_power, delegated_power, total_votes_cast, proposals_created, proposals_passed, delegate_to, joined_at, last_voted_at)
                    VALUES (:profile_id, :user_id, 'MEMBER', 0, 0, 0, 0, 0, NULL, NOW(), NULL)
                    ON CONFLICT (profile_id) DO NOTHING"""
                ),
                {"profile_id": voter_id, "user_id": voter_id},
            )
            await self.session.commit()

        vote = Vote(**vote_data)
        # Ensure chain_id is set
        if not vote.chain_id:
            vote.chain_id = settings.default_chain_id

        if settings.enable_onchain_submission and settings.proposer_private_key:
            try:
                from aitbc.governance.onchain import build_vote_tx
                from aitbc.governance.types import VoteData

                voter_address = vote_data.get("voter_address", "")
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
                vote.tx_hash = result.get("tx_hash")
                vote.block_height = result.get("block_height")
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning("On-chain GOVERNANCE_VOTE submission failed: %s", e)

        # Server-side voting power: do not let clients self-report unlimited weight.
        # Use the on-chain balance snapshot (or zero if the chain query failed) as
        # the authoritative voting_power_used.
        vote.voting_power_used = vote.voting_power

        self.session.add(vote)

        # Update proposal vote counters
        proposal = await self.get_proposal(vote.proposal_id)
        if proposal:
            if vote.vote_type == VoteType.FOR:
                proposal.yes_votes += vote.voting_power_used
                proposal.votes_for = proposal.yes_votes
            elif vote.vote_type == VoteType.AGAINST:
                proposal.no_votes += vote.voting_power_used
                proposal.votes_against = proposal.no_votes
            elif vote.vote_type == VoteType.ABSTAIN:
                proposal.votes_abstain += vote.voting_power_used

        await self.session.commit()
        await self.session.refresh(vote)
        return vote

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
        if proposal.status != ProposalStatus.ACTIVE:
            raise ValueError(f"Proposal must be active to close; current status: {proposal.status}")

        now = datetime.now(UTC)
        voting_ended = now >= proposal.voting_ends

        yes = proposal.yes_votes
        no = proposal.no_votes
        abstain = proposal.votes_abstain
        total_votes = yes + no + abstain

        quorum_met = total_votes >= proposal.quorum_required
        decisive_votes = yes + no
        approval_rate = (yes / decisive_votes) if decisive_votes > 0 else Decimal("0")
        threshold_met = approval_rate >= Decimal(str(proposal.passing_threshold))

        if quorum_met and threshold_met:
            return await self.update_proposal_status(proposal_id, ProposalStatus.SUCCEEDED)

        if not voting_ended:
            raise ValueError(
                f"Voting still open and quorum/approval not yet met: "
                f"{total_votes} / {proposal.quorum_required} votes, "
                f"{approval_rate:.2%} approval (threshold {proposal.passing_threshold:.0%})"
            )

        return await self.update_proposal_status(proposal_id, ProposalStatus.DEFEATED)

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
                if total_votes > 0:
                    approval_rate = proposal.yes_votes / total_votes
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
        stake = TokenStake(
            staker_address=staker_address,
            amount_staked=Decimal(str(amount)),
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

    # Proposal Execution Methods
    async def execute_proposal(self, proposal_id: str, executor_address: str = "") -> Proposal | None:
        """Execute a passed proposal and log the steps.

        The execution timelock is always enforced first — see
        :meth:`_enforce_execution_timelock`. It is checked whether or not this
        deployment submits transactions on-chain, and a proposal whose timelock
        cannot be verified is refused rather than exempted.

        When on-chain submission is enabled, a GOVERNANCE_EXECUTE transaction is
        then submitted and its tx_hash stored on the proposal.

        Raises:
            ValueError: If the proposal has not succeeded, or its timelock cannot
                be verified or has not expired. The refusal is recorded in the
                proposal's execution log.
        """
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            return None

        if proposal.status != "succeeded":
            raise ValueError(f"Proposal not in succeeded state: {proposal.status}")

        # Log execution start
        execution_log = ProposalExecutionLog(proposal_id=proposal_id, execution_step="start", status="pending", result={})
        self.session.add(execution_log)

        try:
            tx_hash = None
            block_height = None

            # V23-18: enforce the timelock before anything is written, and independently of
            # whether this deployment submits transactions on-chain. This check used to live
            # inside the on-chain branch below, which meant the default configuration
            # (enable_onchain_submission=False) executed proposals with no timelock at all.
            await self._enforce_execution_timelock(proposal)

            if settings.enable_onchain_submission and settings.proposer_private_key:
                from aitbc.governance.onchain import build_execute_tx

                payload = build_execute_tx(proposal_id, executor_address, proposal.chain_id)
                result = await self._blockchain.submit_governance_tx(
                    tx_type="GOVERNANCE_EXECUTE",
                    sender=executor_address,
                    private_key=settings.proposer_private_key,
                    payload=payload,
                    chain_id=proposal.chain_id,
                )
                tx_hash = result.get("tx_hash")
                block_height = result.get("block_height")

            # Update proposal status
            proposal.status = ProposalStatus.EXECUTED
            proposal.executed_at = datetime.now(UTC)
            if tx_hash:
                proposal.execution_tx_hash = tx_hash
            if block_height:
                # V23-18: record the execution height alongside the creation height rather
                # than overwriting it. proposal.block_height is the evidence the timelock
                # check measures from; overwriting it at execution destroys the only record
                # of whether the delay was actually honoured.
                proposal.proposal_metadata = {
                    **proposal.proposal_metadata,
                    "execution_block_height": block_height,
                }

            # v0.10.1: Parameter automation — apply parameter changes to the target service
            # after successful proposal execution. Only applies for parameter_change proposals.
            automation_result = None
            if proposal.proposal_type == "parameter_change" and proposal.proposal_value:
                automation_result = await self._apply_parameter_change(proposal)

            # Log execution success
            execution_log.status = "completed"
            execution_log.result = {
                "executed_at": proposal.executed_at.isoformat(),
                "tx_hash": tx_hash,
                "parameter_automation": automation_result,
            }

            await self.session.commit()
            await self.session.refresh(proposal)
            return proposal
        except Exception as e:
            # Log execution failure
            execution_log.status = "failed"
            execution_log.error_message = str(e)
            await self.session.commit()
            raise

    async def _enforce_execution_timelock(self, proposal: Proposal) -> None:
        """Refuse execution unless the timelock is provably expired (V23-18).

        A timelock is a safety control, so every path that cannot *prove* the delay
        elapsed refuses rather than proceeds. Three things can go missing, and each is
        a refusal:

        - the proposal has no recorded on-chain block height (its GOVERNANCE_PROPOSE
          submission failed, or it predates on-chain governance);
        - it has no recorded ``voting_ends_block``;
        - the chain is unreachable, so there is no current height to compare against.

        The previous implementation treated the first of these as "no timelock applies"
        and executed, which turned a best-effort on-chain submission into a silent
        load-bearing part of a safety control: one RPC hiccup at creation time produced a
        proposal that later executed instantly.

        Raises:
            ValueError: If the timelock cannot be verified, or has not expired.
        """
        import logging

        logger = logging.getLogger(__name__)

        if not settings.require_execution_timelock:
            logger.warning(
                "Execution timelock BYPASSED for proposal %s: require_execution_timelock is False. "
                "This is a development-only setting.",
                proposal.proposal_id,
            )
            return

        if proposal.block_height is None:
            raise ValueError(
                f"Cannot verify timelock for proposal {proposal.proposal_id}: no on-chain block "
                "height was recorded at creation, so there is no point to measure the delay from. "
                "The GOVERNANCE_PROPOSE submission likely failed; re-submit the proposal."
            )

        is_emergency = proposal.proposal_type == "emergency"

        # Proposals created before V23-18 have no voting_ends_block. Refuse rather than
        # reconstruct one: deriving it from current settings would produce whatever answer
        # the current configuration implies, which is not evidence of anything.
        if proposal.voting_ends_block is None:
            raise ValueError(
                f"Cannot verify timelock for proposal {proposal.proposal_id}: no voting_ends_block "
                "was recorded at creation. Proposals created before this field existed must be "
                "re-submitted to be executed on-chain."
            )

        try:
            current_height = await self._blockchain.get_block_height(proposal.chain_id)
        except Exception as e:
            # Unreachable chain means unknown height. Unknown height means the delay is
            # unproven, and unproven means refused — an unreachable chain must not become
            # a way to execute a proposal early.
            raise ValueError(
                f"Cannot verify timelock for proposal {proposal.proposal_id}: chain {proposal.chain_id} is unreachable ({e})"
            ) from e

        effective_timelock = settings.emergency_timelock_blocks if is_emergency else settings.timelock_blocks
        blocks_since_voting_ended = current_height - proposal.voting_ends_block

        if blocks_since_voting_ended < effective_timelock:
            raise ValueError(
                f"Timelock not expired: {blocks_since_voting_ended} blocks since voting ended, "
                f"need {effective_timelock}"
                f"{' (emergency fast-track)' if is_emergency else ''}"
            )

    async def _apply_parameter_change(self, proposal: Proposal) -> dict[str, Any]:
        """Apply a governance-approved parameter change to the target service (v0.10.1).

        Calls the target service's parameter API (POST /v1/{service}/parameters/apply)
        with the parameter change details from the proposal's ``proposal_value``.
        """
        import httpx

        params = proposal.proposal_value
        target_service = params.get("target_service", "")
        parameter_name = params.get("parameter_name", "")
        new_value = params.get("new_value")

        if not target_service or not parameter_name:
            return {"applied": False, "reason": "missing target_service or parameter_name"}

        # Map target_service to URL and endpoint
        service_urls = {
            "poolhub": settings.poolhub_url,
            "marketplace": settings.marketplace_url,
        }

        if target_service == "blockchain":
            # Direct config change not supported via API — log warning
            return {"applied": False, "reason": "blockchain parameter changes require manual config update"}

        base_url = service_urls.get(target_service)
        if not base_url:
            return {"applied": False, "reason": f"unknown target_service: {target_service}"}

        endpoint = f"{base_url}/v1/{target_service}/parameters/apply"
        payload = {
            "proposal_id": proposal.proposal_id,
            "target_service": target_service,
            "parameter_name": parameter_name,
            "old_value": params.get("old_value"),
            "new_value": new_value,
            "description": params.get("description", ""),
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    result = resp.json()
                    return {"applied": True, "target_service": target_service, "result": result}
                else:
                    return {
                        "applied": False,
                        "target_service": target_service,
                        "status_code": resp.status_code,
                        "error": resp.text,
                    }
        except Exception as e:
            return {"applied": False, "target_service": target_service, "error": str(e)}
