"""Persistent, evidence-backed reward share ledger (#3058).

AUDIT-POOLHUB-REWARD-PIPELINE-1: ``PoolHubBlockchainClient.record_contribution``
accepts caller-asserted score/shares into an in-memory ``RewardPolicy`` —
shares that cannot survive a restart, are not shared between replicas, and
are not verified against anything. The payout path now reads ONLY the
``reward_shares`` table, and this module is the only writer.

``record_verified_share`` requires ``evidence_tx_hash``: a reference to
sealed chain data proving the work being paid for (e.g. the job's
escrow-release or receipt-claim transaction hash). The hash is stored
verbatim for audit; the caller is responsible for having verified the
evidence against the chain before calling — the function's contract is
that shares are derived from verified completion data, never self-reported.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import RewardShare

logger = logging.getLogger(__name__)

# Only this source is payout-eligible today. Future verified sources add
# their own constant; anything else must not set verified=True. The payout
# path enforces the same allowlist (clients/blockchain.py) so a caller
# passing a different ``source`` here cannot mint payable rows.
VERIFIED_CHAIN_SOURCE = "verified_chain"

# Evidence hashes are chain tx hashes: "0x" + 64 hex chars (sha256 digest,
# see aitbc_chain.mempool_common.compute_tx_hash). Shape-checked here;
# existence/seal verification against the chain remains the feed-writer's
# job — this function stores the reference, it does not dereference it.
_EVIDENCE_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


async def record_verified_share(
    session: AsyncSession,
    *,
    miner_id: str,
    chain_id: str,
    epoch_number: int,
    shares: int,
    evidence_tx_hash: str,
    jobs_completed: int = 1,
    source: str = VERIFIED_CHAIN_SOURCE,
) -> RewardShare:
    """Record verified shares for a miner in one epoch, accumulating on conflict.

    Args:
        session: Database session.
        miner_id: Pool-hub miner identifier.
        chain_id: Chain the evidence lives on.
        epoch_number: Reward epoch the shares count toward.
        shares: Verified share units contributed.
        evidence_tx_hash: Hash of the sealed chain transaction proving the
            completed work. REQUIRED and non-empty — this is what separates
            a verified share from a self-reported one.
        jobs_completed: Number of verified completions represented.
        source: Evidence source tag (default ``verified_chain``).

    Returns:
        The new or updated ``RewardShare`` row.

    Raises:
        ValueError: If ``shares``/``jobs_completed`` are negative,
            ``epoch_number`` is negative, or ``evidence_tx_hash`` is not a
            ``0x``+64-hex transaction hash — an unverifiable share is
            refused, not stored.
    """
    if shares < 0 or jobs_completed < 0:
        raise ValueError("shares and jobs_completed must be non-negative")
    if epoch_number < 0:
        raise ValueError("epoch_number must be >= 0")
    evidence_hash = str(evidence_tx_hash).strip()
    if not _EVIDENCE_TX_HASH_RE.match(evidence_hash):
        raise ValueError(
            "evidence_tx_hash must be a 0x-prefixed 64-hex transaction hash: shares must derive from verified chain data"
        )

    existing = (
        await session.execute(
            select(RewardShare).where(
                RewardShare.miner_id == miner_id,
                RewardShare.chain_id == chain_id,
                RewardShare.epoch_number == epoch_number,
                RewardShare.source == source,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.shares += shares
        existing.jobs_completed += jobs_completed
        existing.evidence_tx_hash = evidence_hash
        await session.flush()
        await session.commit()
        return existing

    row = RewardShare(
        miner_id=miner_id,
        chain_id=chain_id,
        epoch_number=epoch_number,
        shares=shares,
        jobs_completed=jobs_completed,
        source=source,
        evidence_tx_hash=evidence_hash,
        verified=True,
    )
    session.add(row)
    try:
        await session.flush()
        await session.commit()
    except IntegrityError:
        # Lost a concurrent insert race on the unique key — accumulate onto
        # the winner's row instead of failing the caller.
        await session.rollback()
        winner = (
            await session.execute(
                select(RewardShare).where(
                    RewardShare.miner_id == miner_id,
                    RewardShare.chain_id == chain_id,
                    RewardShare.epoch_number == epoch_number,
                    RewardShare.source == source,
                )
            )
        ).scalar_one_or_none()
        if winner is None:
            raise
        winner.shares += shares
        winner.jobs_completed += jobs_completed
        await session.flush()
        await session.commit()
        return winner
    return row
