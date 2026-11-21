"""Core payment service: construction, ownership, CAS transition, read views"""

from __future__ import annotations

import os
from collections.abc import Collection

from aitbc_shared import JobPayment
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, col, select, update


from aitbc.aitbc_logging import get_logger
from aitbc.constants import WALLET_PORT

from aitbc.utils.chain_id import resolve_chain_id
from ....schemas import JobPaymentView
from ....storage import get_session
from ....utils.client_resolver import resolve_client
from ...infrastructure.domain.job import Job

logger = get_logger(__name__)


class PaymentCoreMixin:
    """Mixin: payment service methods (split from payments.py; pure code motion)."""

    def __init__(self, session: Annotated[Session, Depends(get_session)]):
        # Resolve via the facade module: tests patch ``payments.settings``.
        from . import payments as _pm

        self.session = session
        self.wallet_base_url = f"http://127.0.0.1:{WALLET_PORT}"
        self.exchange_base_url = "http://127.0.0.1:8106"
        self.blockchain_rpc_url = _pm.settings.blockchain_rpc_url.rstrip("/")
        self.blockchain_rpc_api_key = _pm.settings.blockchain_rpc_api_key
        self.blockchain_rpc_settlement_api_key = _pm.settings.blockchain_rpc_settlement_api_key

    def _settlement_headers(self) -> dict[str, str]:
        """X-Settlement-Key for the chain's escrow release/refund routes (#1917)."""
        return {"X-Settlement-Key": self.blockchain_rpc_settlement_api_key} if self.blockchain_rpc_settlement_api_key else {}

    def _require_owned_job(self, job_id: str, client_id: str) -> Job:
        """Fetch a job and verify it belongs to the requesting client."""
        job = self.session.get(Job, job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for this payment",
            )
        try:
            resolved_client_id, _ = resolve_client(self.session, client_id, auto_create=False)
        except ValueError:
            # Legacy/test path: the caller string may match the job's client_id
            # directly. The schema migration will normalize client_id to a users.id
            # foreign key, but old or test rows still carry raw strings.
            resolved_client_id = client_id
        if job.client_id != resolved_client_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for this payment",
            )
        return job

    def _get_chain_id(self) -> str:
        return resolve_chain_id()

    def _get_node_wallet_address(self) -> str:
        return os.getenv("NODE_WALLET_ADDRESS") or os.getenv("GENESIS_WALLET_ADDRESS") or ""

    def _cas_payment_transition(
        self,
        payment_id: str,
        from_states: Collection[str],
        values: dict[str, Any],
    ) -> bool:
        """#1797: conditional JobPayment write — the status predicate in WHERE
        is the compare-and-swap (same pattern as the market CAS, #1790).
        Returns True iff this call won the transition; False means another
        writer already moved the row and the caller must roll back."""
        claim = self.session.execute(
            update(JobPayment)
            .where(col(JobPayment.id) == payment_id, col(JobPayment.status).in_(tuple(from_states)))
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return getattr(claim, "rowcount", 0) == 1

    def get_payment(self, client_id: str, payment_id: str) -> JobPayment | None:
        """Get payment by ID"""
        payment = self.session.get(JobPayment, payment_id)
        if payment is None:
            return None
        self._require_owned_job(payment.job_id, client_id)
        return payment

    def get_job_payment(self, client_id: str, job_id: str) -> JobPayment | None:
        """Get payment for a specific job"""
        self._require_owned_job(job_id, client_id)
        return self.session.execute(select(JobPayment).where(JobPayment.job_id == job_id)).scalars().first()

    def to_view(self, payment: JobPayment) -> JobPaymentView:
        """Convert payment to view model"""
        meta = payment.meta_data or {}
        return JobPaymentView(
            job_id=payment.job_id,
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            payment_method=payment.payment_method,
            escrow_address=payment.escrow_address,
            refund_address=payment.refund_address,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            released_at=payment.released_at,
            refunded_at=payment.refunded_at,
            transaction_hash=payment.transaction_hash,
            refund_transaction_hash=payment.refund_transaction_hash,
            escrow_tx_hash=meta.get("escrow_lock_tx_hash"),
            protected=bool(meta.get("energy_is_protected")),
            energy_quote_id=meta.get("energy_quote", {}).get("quote_id") if meta.get("energy_quote") else None,
            energy_buyer_charge_units=meta.get("energy_buyer_charge_units"),
            energy_net_floor_units=meta.get("energy_net_floor_units"),
        )
