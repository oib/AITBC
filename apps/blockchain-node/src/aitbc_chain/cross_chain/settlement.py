"""Cross-chain atomic settlement service using HTLC (v0.9.0 B3 + B4).

.. deprecated::
    #2385: the inter-chain HTLC settlement rail is retired. HTLC emissions
    carry no ``payload.auth`` and cannot seal at block version ≥ 9 — unlike
    the v17-revived staking/bounty surfaces there is no unarmed-then-live
    path; a revival would need a new consensus version. Every lifecycle
    mutator (``create_escrow``, ``lock_escrow``, ``verify_lock``,
    ``execute_trade``, ``settle``, ``refund``, ``extend_timeout``) therefore
    fails fast with ``RetiredProtocolTransfer`` before touching state, and
    the pre-retirement bodies were removed rather than left as dead code.

    The read methods (``get_escrow``, ``get_escrow_status``,
    ``get_proof_chain``) stay live so existing escrow records remain
    inspectable, and ``check_timeouts`` drives any legacy non-terminal row
    to a terminal ``failed`` state instead of hot-looping the monitor.

Historical lifecycle (no longer reachable)::

    pending → locked → verified → executing → completed
                                            ↘ refunded (timeout)

Each lifecycle step used to persist a ``CrossChainEscrowRecord`` update and
an ``EscrowProofRecord`` anchoring the event to a block, forming a
tamper-evident proof chain (lock → verification → execution → release →
settlement).
"""

from __future__ import annotations

import json
import time

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from aitbc.settlement.types import EscrowStatus

from ..base_models import CrossChainEscrowRecord, EscrowProofRecord
from ..config import settings
from ..database import session_scope
from ..logger import get_logger
from ..rpc.retired import RetiredProtocolTransfer, raise_for_retired_settlement_contract

logger = get_logger(__name__)


def _escrow_to_dict(record: CrossChainEscrowRecord, *, include_secret: bool = False) -> dict:
    """Serialize a CrossChainEscrowRecord to a plain dict.

    The HTLC preimage (``secret``) is only included when ``include_secret`` is
    set — i.e. the create response to the escrow's own initiator. Public reads
    (``GET /settlement/{id}``) must never expose it: the preimage is what the
    destination leg is claimed with, and leaking it before settlement lets any
    reader front-run the release.
    """
    result = {
        "escrow_id": record.escrow_id,
        "trade_id": record.trade_id,
        "source_chain": record.source_chain,
        "dest_chain": record.dest_chain,
        "sender": record.sender,
        "recipient": record.recipient,
        "amount": record.amount,
        "asset": record.asset,
        "status": record.status,
        "secret_hash": record.secret_hash,
        "source_timelock": record.source_timelock,
        "dest_timelock": record.dest_timelock,
        "source_lock_tx_hash": record.source_lock_tx_hash,
        "dest_execution_tx_hash": record.dest_execution_tx_hash,
        "source_release_tx_hash": record.source_release_tx_hash,
        "dest_release_tx_hash": record.dest_release_tx_hash,
        "timeout_seconds": record.timeout_seconds,
        "timeout_extended": record.timeout_extended,
        "created_at": record.created_at.timestamp() if record.created_at else 0.0,
        "locked_at": record.locked_at.timestamp() if record.locked_at else 0.0,
        "settled_at": record.settled_at.timestamp() if record.settled_at else 0.0,
        "refunded_at": record.refunded_at.timestamp() if record.refunded_at else 0.0,
    }
    if include_secret:
        result["secret"] = record.secret
    return result


def _proof_to_dict(record: EscrowProofRecord) -> dict:
    """Serialize an EscrowProofRecord to a plain dict."""
    return {
        "id": record.id,
        "escrow_id": record.escrow_id,
        "proof_type": record.proof_type,
        "chain_id": record.chain_id,
        "block_height": record.block_height,
        "block_hash": record.block_hash,
        "tx_hash": record.tx_hash,
        "proposer_signature": record.proposer_signature,
        "validator_signatures": json.loads(record.validator_signatures_json) if record.validator_signatures_json else [],
        "merkle_proof": json.loads(record.merkle_proof_json) if record.merkle_proof_json else [],
        "previous_proof_hash": record.previous_proof_hash,
        "timestamp": record.timestamp,
    }


class CrossChainSettlementService:
    """Cross-chain atomic settlement service using HTLC (v0.9.0 B3).

    #2385: the HTLC rail is retired — every lifecycle mutator fails fast
    with ``RetiredProtocolTransfer``. Only the read methods and the
    ``check_timeouts`` sweeper (which retires legacy non-terminal rows to
    ``failed``) remain functional.
    """

    def __init__(self, chain_id: str):
        self.chain_id = chain_id

    async def create_escrow(
        self,
        trade_id: str,
        source_chain: str,
        dest_chain: str,
        sender: str,
        recipient: str,
        amount: int,
        timeout_seconds: int | None = None,
    ) -> dict:
        """Retired (#2385): refuses before minting a never-lockable record."""
        if not settings.escrow_enabled:
            raise RuntimeError("Settlement not enabled")
        raise_for_retired_settlement_contract()

    async def lock_escrow(self, escrow_id: str) -> dict:
        """Retired (#2385): the HTLC lock it drove can never seal at block v9."""
        if not settings.escrow_enabled:
            raise RuntimeError("Settlement not enabled")
        raise_for_retired_settlement_contract()

    async def verify_lock(self, escrow_id: str) -> dict:
        """Retired (#2385): no escrow can ever reach ``locked``."""
        if not settings.escrow_enabled:
            raise RuntimeError("Settlement not enabled")
        raise_for_retired_settlement_contract()

    async def execute_trade(self, escrow_id: str) -> dict:
        """Retired (#2385): no escrow can ever reach ``verified``."""
        if not settings.escrow_enabled:
            raise RuntimeError("Settlement not enabled")
        raise_for_retired_settlement_contract()

    async def settle(self, escrow_id: str, secret: str) -> dict:
        """Retired (#2385): HTLC complete_swap emits no payload.auth."""
        if not settings.escrow_enabled:
            raise RuntimeError("Settlement not enabled")
        raise_for_retired_settlement_contract()

    async def refund(self, escrow_id: str) -> dict:
        """Retired (#2385): HTLC refund_swap emits no payload.auth.

        ``check_timeouts`` relies on this unconditional refusal to drive
        legacy non-terminal rows to ``failed``.
        """
        if not settings.escrow_enabled:
            raise RuntimeError("Settlement not enabled")
        raise_for_retired_settlement_contract()

    async def check_timeouts(self) -> list[str]:
        """Check all pending/locked escrows for timeout.

        Returns:
            List of escrow_ids that were refunded due to timeout — always
            empty since #2385 retired the rail. Expired non-terminal rows
            are instead driven to terminal ``failed`` (they can never
            settle or refund) so the monitor does not retry-log them.
        """
        if not settings.escrow_enabled:
            raise RuntimeError("Settlement not enabled")

        expired: list[str] = []
        now = time.time()
        active_statuses = {
            EscrowStatus.PENDING.value,
            EscrowStatus.LOCKED.value,
            EscrowStatus.VERIFIED.value,
            EscrowStatus.EXECUTING.value,
        }

        with session_scope(self.chain_id) as session:
            stmt = select(CrossChainEscrowRecord).where(
                CrossChainEscrowRecord.status.in_(active_statuses)  # type: ignore[attr-defined]
            )
            records = session.execute(stmt).scalars().all()

            for record in records:
                # Measure the timeout from the lock time when the escrow has
                # been locked — an escrow that sat pending before locking
                # should not expire early. Fall back to created_at.
                timeout_base = record.locked_at or record.created_at
                created = timeout_base.timestamp() if timeout_base else 0.0
                if now - created > record.timeout_seconds:
                    logger.warning(
                        "Escrow %s timed out (status=%s, age=%ds, timeout=%ds)",
                        record.escrow_id,
                        record.status,
                        int(now - created),
                        record.timeout_seconds,
                    )
                    expired.append(record.escrow_id)

        # #2385: refund() refuses unconditionally with RetiredProtocolTransfer,
        # so an expired non-terminal row can never leave the active set on its
        # own — retire it to terminal ``failed`` (honest: it can never settle
        # or refund) instead of retry-logging every 10s tick.
        for escrow_id in expired:
            try:
                await self.refund(escrow_id)
            except RetiredProtocolTransfer as e:
                logger.warning("Retiring escrow %s with the HTLC settlement rail (#2385): %s", escrow_id, e)
                self._mark_escrow_failed(escrow_id)
            except ValueError as e:
                logger.info("Escrow %s not refundable yet: %s", escrow_id, e)
            except (
                ImportError,
                SQLAlchemyError,
                ArithmeticError,
                OSError,
                RuntimeError,
                TypeError,
                AttributeError,
                KeyError,
            ) as e:
                logger.error("Failed to refund timed-out escrow %s: %s", escrow_id, e)

        return []

    def _mark_escrow_failed(self, escrow_id: str) -> None:
        """Drive a legacy non-terminal escrow to terminal ``failed`` (#2385).

        Called by ``check_timeouts`` when ``refund`` refuses with
        ``RetiredProtocolTransfer``: the row can never settle or refund on
        the retired HTLC rail, so ``failed`` is the honest terminal state.
        Already-terminal rows are left untouched.
        """
        terminal = {EscrowStatus.COMPLETED.value, EscrowStatus.REFUNDED.value, EscrowStatus.FAILED.value}
        with session_scope(self.chain_id) as session:
            record = (
                session.execute(select(CrossChainEscrowRecord).where(CrossChainEscrowRecord.escrow_id == escrow_id))
                .scalars()
                .first()
            )
            if record is None or record.status in terminal:
                return
            record.status = EscrowStatus.FAILED.value
            session.add(record)
            session.commit()  # noqa: unawaited-async — sync Session via session_scope
            session.refresh(record)  # noqa: unawaited-async — sync Session via session_scope
        logger.info("Escrow %s marked failed: HTLC settlement rail retired (#2385)", escrow_id)

    async def extend_timeout(self, escrow_id: str, extension_seconds: int) -> dict:
        """Retired (#2385): extending a timeout on a rail that cannot settle."""
        if not settings.escrow_enabled:
            raise RuntimeError("Settlement not enabled")
        raise_for_retired_settlement_contract()

    async def get_escrow(self, escrow_id: str) -> dict | None:
        """Get escrow record as dict.

        Returns:
            Escrow dict, or ``None`` if not found.
        """
        with session_scope(self.chain_id) as session:
            record = (
                session.execute(select(CrossChainEscrowRecord).where(CrossChainEscrowRecord.escrow_id == escrow_id))
                .scalars()
                .first()
            )
            if record is None:
                return None
            return _escrow_to_dict(record)

    async def get_escrow_status(self, escrow_id: str) -> str:
        """Get escrow status string.

        Returns:
            The status string (e.g., ``"pending"``, ``"locked"``).

        Raises:
            ValueError: If the escrow is not found.
        """
        with session_scope(self.chain_id) as session:
            record = (
                session.execute(select(CrossChainEscrowRecord).where(CrossChainEscrowRecord.escrow_id == escrow_id))
                .scalars()
                .first()
            )
            if record is None:
                raise ValueError(f"Escrow {escrow_id} not found")
            return str(record.status)

    async def get_proof_chain(self, escrow_id: str) -> list[dict]:
        """Return all proofs for an escrow, ordered by creation.

        Returns:
            List of proof dicts in insertion order (lock → verification →
            execution → release → settlement).
        """
        with session_scope(self.chain_id) as session:
            stmt = (
                select(EscrowProofRecord).where(EscrowProofRecord.escrow_id == escrow_id).order_by(EscrowProofRecord.id.asc())  # type: ignore[union-attr]
            )
            records = session.execute(stmt).scalars().all()
            return [_proof_to_dict(r) for r in records]
