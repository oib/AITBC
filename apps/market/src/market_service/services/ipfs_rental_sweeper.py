"""Dedicated sweeper for IPFS rental escrow lifecycle.

This sweeper lives inside the market service so it has direct access to
``IpfsRentalToken`` records and their ``expires_at`` / ``status`` state. It does
not belong to the coordinator's generic ``StuckEscrowSweeper`` because IPFS
rentals are not ``Job``/``JobPayment`` rows; they are market rental tokens
with a separate lifecycle.

On each sweep the worker:

1. Finds active IPFS rental tokens whose ``expires_at`` has passed.
2. Marks the token as ``expired``.
3. If the bound market job carries the provider's signed delivery
   attestation (``payload.provider_confirmed``, #1922), releases the
   on-chain escrow to the provider; otherwise refunds the buyer. An open
   dispute freezes settlement entirely until it is cleared.
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

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market import BlockchainRPCClient
from aitbc.utils.tx_status import tx_sealed_for_money

from ..config import settings
from ..domain.market import IpfsRentalToken, MarketJob
from ..storage import get_session_context

logger = get_logger(__name__)

# Expected failure surface for the escrow RPC probes below: HTTP/transport
# errors from the blockchain RPC client (httpx), its ValueError guards, and
# data-shape errors. RuntimeError covers abort-style raises; genuine
# BaseExceptions (incl. asyncio.CancelledError) still propagate (#1862).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    httpx.HTTPError,
)


class IpfsRentalSweeper:
    """Sweeper that drives IPFS rental escrow release/refund at expiration."""

    def __init__(
        self,
        interval_seconds: int | None = None,
        batch_size: int | None = None,
        refund_grace_seconds: int | None = None,
        settle_max_seconds: int | None = None,
        rpc_client: BlockchainRPCClient | None = None,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds or _env_int("IPFS_RENTAL_SWEEP_INTERVAL_SECONDS", 300)
        self.batch_size = batch_size or _env_int("IPFS_RENTAL_SWEEP_BATCH_SIZE", 50)
        self.settle_max_seconds = settle_max_seconds or _env_int("IPFS_RENTAL_SWEEP_SETTLE_MAX_SECONDS", 6 * 3600)
        # Extra grace after expires_at before we act, so a renewal/extension has
        # a small window to land without releasing/refunding the escrow.
        self.refund_grace_seconds = refund_grace_seconds or _env_int("IPFS_RENTAL_SWEEP_GRACE_SECONDS", 60)
        self._rpc_client = rpc_client or BlockchainRPCClient(
            rpc_url=settings.blockchain_rpc_url,
            api_key=settings.blockchain_rpc_api_key,
            settlement_api_key=settings.blockchain_rpc_settlement_api_key,
        )
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
        self._stop_event.set()  # noqa: unawaited-async
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
        # expires_at is a naive-UTC column (domain default_factory strips
        # tzinfo); bind a naive cutoff so the comparison does not depend on
        # dialect-specific tz coercion of an aware datetime (#1575).
        cutoff = (now - timedelta(seconds=self.refund_grace_seconds)).replace(tzinfo=None)

        async with self._session_factory() as session:
            stmt = (
                select(IpfsRentalToken)
                # 'expired' without a settlement hash is an unsettled escrow:
                # a token the last pass marked expired but could not release or
                # refund (e.g. a 425 'lock not sealed yet') must be retried, not
                # stranded — the sweep only ever finished with a tx_hash.
                .where(col(IpfsRentalToken.status).in_({"active", "expired", "refund_pending"}))
                .where(col(IpfsRentalToken.tx_hash).is_(None))
                .where(col(IpfsRentalToken.expires_at).is_not(None))
                .where(col(IpfsRentalToken.expires_at) < cutoff)
                .where((col(IpfsRentalToken.rental_id) != "") | (col(IpfsRentalToken.escrow_contract_id) != ""))
                # Least-recently-processed first: _process_token bumps
                # updated_at every pass, so a permanently-stuck token rotates
                # to the back of the queue and >batch_size stuck rows cannot
                # starve eligible ones behind a fixed limit.
                .order_by(col(IpfsRentalToken.updated_at).asc())
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

        The default policy is release to the provider at normal expiration,
        but only on verified delivery evidence: the provider-signed pin
        attestation (``payload.provider_confirmed``) on the bound market
        job — the same proof ``active_rental_token_covers`` requires before
        exempting the job's payment from the refund pass (#2491). Without
        it (or without a resolvable job at all) the buyer is refunded: the
        token rail must never pay a provider that cannot prove delivery.
        ``status == "refund_pending"`` or ``pinned == False`` also force a
        refund. An open dispute freezes settlement until cleared (#1835 F1).
        """
        # Canonicalize addresses before touching any on-chain state.
        token.buyer_address = canonical_address(token.buyer_address or "")
        token.provider_address = canonical_address(token.provider_address or "")

        # Ownership binding (#815): settle the escrow id this token was paid
        # against — prefer escrow_contract_id over the free-form rental_id,
        # and refuse to act when they disagree (a rental_id pointing at a
        # foreign escrow is a steering row, not a rental).
        job_id = token.escrow_contract_id or token.rental_id
        if token.rental_id and token.escrow_contract_id and token.rental_id != token.escrow_contract_id:
            logger.warning(
                "Skipping token %s: rental_id %r disagrees with escrow_contract_id %r — refusing to settle a mismatched escrow",
                token.access_key,
                token.rental_id,
                token.escrow_contract_id,
            )
            return False, False
        # Capture the flag before the status flip below overwrites it.
        refund_flagged = token.status == "refund_pending"

        # #2850: resolve the bound market job for delivery evidence and the
        # dispute freeze. ``job_id`` is the on-chain escrow key — for
        # job-bound tokens it is the market job id (#2348/#2623).
        job = await session.get(MarketJob, str(job_id)) if job_id else None
        delivered = bool(job is not None and (job.payload or {}).get("provider_confirmed"))
        dispute_open = job is not None and job.disputed_at is not None and job.dispute_cleared_at is None

        # Mark the rental as expired first so concurrent access-key checks stop.
        token.status = "expired"
        token.updated_at = datetime.now(UTC)

        if dispute_open:
            # Mirror the job sweeper's freeze: neither release nor refund
            # while a dispute is open — the token stays expired-but-unsettled
            # and the next pass re-checks. Deliberate freezes must not burn
            # the settle_max_seconds deferral bound.
            logger.info("Rental %s under open dispute; escrow settlement deferred", job_id)
            return False, False

        should_refund = refund_flagged or not token.pinned or not delivered

        if should_refund:
            outcome = await self._refund_escrow(job_id)
            if outcome is not None:
                tx_hash, verdict = outcome
                token.status = "refunded" if verdict == "refunded" else "released"
                token.tx_hash = tx_hash
                token.settle_deferral_first_at = None
                return verdict == "released", verdict == "refunded"
            await self._settle_deferred(token, job_id, "refund")
            return False, False

        outcome = await self._release_escrow(job_id)
        if outcome is not None:
            tx_hash, verdict = outcome
            token.status = "released" if verdict == "released" else "refunded"
            token.tx_hash = tx_hash
            token.settle_deferral_first_at = None
            return verdict == "released", verdict == "refunded"
        await self._settle_deferred(token, job_id, "release")
        return False, False

    async def _settle_deferred(self, token: IpfsRentalToken, job_id: str, direction: str) -> None:
        """A settle that did not land defers, bounded by ``settle_max_seconds``.

        Same pattern as the job sweeper's 'not yet' handling: falsy answers
        (404, ``{success: false}``) and raised errors (425, 409, 5xx,
        transport) all mean 'try again next pass', so the first deferral
        stamps ``settle_deferral_first_at`` and the row stays in the sweep
        set. Past the bound the token goes terminal (``settlement_failed``)
        with an error log -- a row that never settles must not loop every
        interval forever.
        """
        now = datetime.now(UTC).replace(tzinfo=None)
        if token.settle_deferral_first_at is None:
            token.settle_deferral_first_at = now
            logger.warning(
                "Escrow %s for rental %s deferred; retrying on next sweep",
                direction,
                job_id,
            )
            return
        # The chain writes the Escrow row when the lock is admitted, so a
        # job_id with no row at all can never release or refund: the only
        # absent-row case that could heal is a raw lock still in mempool,
        # and that lands inside one sweep interval. From the second deferred
        # pass on, a still-absent row is a phantom (e.g. a rental recorded
        # on a chain that was later reset) -- fail it now instead of burning
        # the full settle_max_seconds bound on retries.
        if await self._escrow_absent(job_id):
            token.status = "settlement_failed"
            token.settle_deferral_first_at = None
            logger.error(
                "Escrow %s for rental %s impossible: chain has no escrow row for job_id=%s; marking settlement_failed",
                direction,
                job_id,
                job_id,
            )
            return
        elapsed = (now - token.settle_deferral_first_at).total_seconds()
        if elapsed <= self.settle_max_seconds:
            logger.warning(
                "Escrow %s for rental %s still deferred after %.0fs",
                direction,
                job_id,
                elapsed,
            )
            return
        token.status = "settlement_failed"
        token.settle_deferral_first_at = None
        logger.error(
            "Escrow %s for rental %s deferred %.0fs past the %ss bound -- marking settlement_failed",
            direction,
            job_id,
            elapsed,
            self.settle_max_seconds,
        )

    async def _escrow_absent(self, job_id: str) -> bool:
        """True when the chain reports no escrow record at all for job_id."""
        try:
            return await self._rpc_client.verify_escrow(job_id) is None
        except Exception as e:  # noqa: BLE001 - probe containment — an unreadable escrow is transient, never absent
            logger.warning("Escrow presence probe for %s failed: %s; treating as transient", job_id, e)
            return False

    async def _release_escrow(self, job_id: str) -> tuple[str, str] | None:
        """Release escrow to the provider; returns ``(tx_hash, escrow state)``."""
        try:
            result = await self._rpc_client.release_escrow(job_id)
            if result and result.get("success"):
                tx_hash = result.get("tx_hash")
                if isinstance(tx_hash, str) and tx_hash:
                    return tx_hash, "released"
                return await self._adopt_sealed_verdict(job_id)
            logger.warning("Escrow release for %s was not successful: %s", job_id, result)
        except _OPS_ERRORS as e:
            logger.error("Failed to release escrow %s: %s", job_id, e)
        return None

    async def _refund_escrow(self, job_id: str) -> tuple[str, str] | None:
        """Refund escrow to the buyer; returns ``(tx_hash, escrow state)``."""
        try:
            result = await self._rpc_client.refund_escrow(job_id)
            if result and result.get("success"):
                tx_hash = result.get("tx_hash")
                if isinstance(tx_hash, str) and tx_hash:
                    return tx_hash, "refunded"
                return await self._adopt_sealed_verdict(job_id)
            logger.warning("Escrow refund for %s was not successful: %s", job_id, result)
        except _OPS_ERRORS as e:
            logger.error("Failed to refund escrow %s: %s", job_id, e)
        return None

    async def _adopt_sealed_verdict(self, job_id: str) -> tuple[str, str] | None:
        """Adopt the escrow row's settled verdict when the settle response
        carried ``success`` but no ``tx_hash`` (#2860).

        Same rule as the job sweeper's ``_settlement_verdict``: a hashless
        success is not proof nothing settled — the chain may have recorded
        the verdict and its tx hash on the escrow row. Adopt only a
        released/refunded verdict whose hash is proven sealed-for-money
        (``tx_sealed_for_money`` on ``GET /rpc/transaction/{hash}`` —
        confirmed AND a block height; a failed-sealed row carries a
        height but moved no value, #3049); anything else stays deferred
        for the next pass.
        """
        try:
            escrow = await self._rpc_client.verify_escrow(job_id)
        except _OPS_ERRORS as e:
            logger.warning("Escrow verdict read for %s failed (%s); still deferring", job_id, e)
            return None
        if not escrow:
            return None
        state = escrow.get("state")
        if state not in {"released", "refunded"}:
            return None
        tx_hash = escrow.get("release_tx_hash") if state == "released" else escrow.get("refund_tx_hash")
        if not isinstance(tx_hash, str) or not tx_hash:
            logger.error(
                "Escrow %s reports %s but carries no tx hash; still deferring",
                job_id,
                state,
            )
            return None
        try:
            tx = await self._rpc_client.get_transaction(tx_hash)
        except _OPS_ERRORS as e:
            logger.warning("Seal check for escrow %s tx %s failed (%s); still deferring", job_id, tx_hash, e)
            return None
        if tx is None or not tx_sealed_for_money(tx):
            logger.warning(
                "Escrow %s reports %s but tx %s is not sealed-for-money (status=%r); still deferring",
                job_id,
                state,
                tx_hash,
                (tx or {}).get("status"),
            )
            return None
        logger.warning(
            "Escrow %s settle response lacked tx_hash; adopted sealed %s verdict %s",
            job_id,
            state,
            tx_hash,
        )
        return tx_hash, state


def _env_int(name: str, default: int) -> int:
    """Read an integer setting from the environment with a safe fallback."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid %s; falling back to %s", name, default)
        return default


def _default_session_factory() -> AbstractAsyncContextManager[AsyncSession]:
    """Return a context manager for a new market database session."""
    return get_session_context()
