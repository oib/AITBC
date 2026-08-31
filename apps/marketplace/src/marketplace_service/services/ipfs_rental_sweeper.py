"""Dedicated sweeper for IPFS rental escrow lifecycle.

This sweeper lives inside the marketplace service so it has direct access to
``IpfsRentalToken`` records and their ``expires_at`` / ``status`` state. It does
not belong to the coordinator's generic ``StuckEscrowSweeper`` because IPFS
rentals are not ``Job``/``JobPayment`` rows; they are marketplace rental tokens
with a separate lifecycle.

On each sweep the worker:

1. Finds active IPFS rental tokens whose ``expires_at`` has passed.
2. Marks the token as ``expired``.
3. If the rental was pinned/delivered, releases the on-chain escrow to the
   provider; otherwise refunds the buyer.
4. Records the resulting ``release_tx_hash`` or ``refund_tx_hash`` and updates
   the token status to ``released`` or ``refunded``.

All addresses are canonicalized to 0x EIP-55 before any blockchain RPC calls.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.marketplace import BlockchainRPCClient

from ..config import settings
from ..domain.marketplace import IpfsRentalToken
from ..storage import get_session_context

logger = get_logger(__name__)


class IpfsRentalSweeper:
    """Sweeper that drives IPFS rental escrow release/refund at expiration."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        batch_size: int | None = None,
        refund_grace_seconds: int | None = None,
        rpc_client: BlockchainRPCClient | None = None,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("IPFS_RENTAL_SWEEP_INTERVAL_SECONDS", 300)
        self.batch_size = batch_size or _env_int("IPFS_RENTAL_SWEEP_BATCH_SIZE", 50)
        # Extra grace after expires_at before we act, so a renewal/extension has
        # a small window to land without releasing/refunding the escrow.
        self.refund_grace_seconds = refund_grace_seconds or _env_int("IPFS_RENTAL_SWEEP_GRACE_SECONDS", 60)
        self._rpc_client = rpc_client or BlockchainRPCClient(rpc_url=settings.blockchain_rpc_url)
        self._session_factory = session_factory or _default_session_factory
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the background sweep loop."""
        if self._task is not None and not self._task.done():
            logger.warning("IpfsRentalSweeper is already running")
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("IpfsRentalSweeper started (interval=%ss, batch=%s)", self.interval_seconds, self.batch_size)

    async def stop(self) -> None:
        """Stop the background sweep loop."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._task = None
        logger.info("IpfsRentalSweeper stopped")

    async def _run(self) -> None:
        """Main loop; runs until ``stop`` is called."""
        while not self._stop_event.is_set():
            try:
                await self.sweep_once()
            except Exception:
                logger.exception("IpfsRentalSweeper iteration failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(self.interval_seconds),
                )
            except asyncio.TimeoutError:
                pass

    async def sweep_once(self) -> tuple[int, int, int]:
        """Run a single sweep and return (expired, released, refunded) counts."""
        expired_count = 0
        released_count = 0
        refunded_count = 0

        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self.refund_grace_seconds)

        async with self._session_factory() as session:
            stmt = (
                select(IpfsRentalToken)
                .where(col(IpfsRentalToken.status) == "active")
                .where(col(IpfsRentalToken.expires_at).is_not(None))
                .where(col(IpfsRentalToken.expires_at) < cutoff)
                .limit(self.batch_size)
            )
            result = await session.execute(stmt)
            tokens = list(result.scalars().all())

            for token in tokens:
                try:
                    released, refunded = await self._process_token(session, token)
                    if released:
                        released_count += 1
                    if refunded:
                        refunded_count += 1
                    if not released and not refunded:
                        # Still expired even if the RPC call failed; the next
                        # iteration will retry the release/refund.
                        expired_count += 1
                except Exception:
                    logger.exception("Failed to process IPFS rental token %s", token.access_key)
                    expired_count += 1

            await session.commit()

        logger.info(
            "IpfsRentalSweeper finished: expired=%s, released=%s, refunded=%s",
            expired_count,
            released_count,
            refunded_count,
        )
        return expired_count, released_count, refunded_count

    async def _process_token(self, session: AsyncSession, token: IpfsRentalToken) -> tuple[bool, bool]:
        """Expire a single token and release or refund its escrow.

        The default policy is release to the provider at normal expiration. A
        token is only refunded when it has been explicitly flagged with
        ``status == "refund_pending"`` or the rental was never successfully
        pinned (``pinned == False``). If neither condition is present, the
        provider is paid.
        """
        # Canonicalize addresses before touching any on-chain state.
        token.buyer_address = canonical_address(token.buyer_address or "")
        token.provider_address = canonical_address(token.provider_address or "")

        job_id = token.escrow_contract_id or token.rental_id
        should_refund = token.status == "refund_pending" or getattr(token, "pinned", True) is False

        # Mark the rental as expired first so concurrent access-key checks stop.
        token.status = "expired"
        token.updated_at = datetime.now(UTC)

        if should_refund:
            tx_hash = await self._refund_escrow(job_id)
            if tx_hash:
                token.status = "refunded"
                token.tx_hash = tx_hash
                return False, True
            return False, False

        tx_hash = await self._release_escrow(job_id)
        if tx_hash:
            token.status = "released"
            token.tx_hash = tx_hash
            return True, False
        return False, False

    async def _release_escrow(self, job_id: str) -> str | None:
        """Call the blockchain RPC to release escrow to the provider."""
        try:
            result = await self._rpc_client.release_escrow(job_id)
            if result and result.get("success"):
                return str(result.get("tx_hash", ""))
            logger.warning("Escrow release for %s was not successful: %s", job_id, result)
        except Exception as e:
            logger.error("Failed to release escrow %s: %s", job_id, e)
        return None

    async def _refund_escrow(self, job_id: str) -> str | None:
        """Call the blockchain RPC to refund escrow to the buyer."""
        try:
            result = await self._rpc_client.refund_escrow(job_id)
            if result and result.get("success"):
                return str(result.get("tx_hash", ""))
            logger.warning("Escrow refund for %s was not successful: %s", job_id, result)
        except Exception as e:
            logger.error("Failed to refund escrow %s: %s", job_id, e)
        return None


def _env_int(name: str, default: int) -> int:
    """Read an integer setting from the environment with a safe fallback."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def _default_session_factory() -> AbstractAsyncContextManager[AsyncSession]:
    """Return a context manager for a new marketplace database session."""
    return get_session_context()
