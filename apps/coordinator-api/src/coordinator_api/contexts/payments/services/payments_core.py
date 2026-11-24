"""Core payment service: construction, ownership, CAS transition, read views"""

from __future__ import annotations

import os
from collections.abc import Collection
from datetime import UTC, datetime, timedelta

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
from ..acceptance import DISPUTED, PENDING_ACCEPTANCE, SETTLEMENT_FAILED

logger = get_logger(__name__)

# Payment states whose row still represents money committed to (or in flight
# for) the job. ``create_payment`` returns the existing row instead of opening
# a second escrow when one of these is present; terminal states
# (``failed`` / ``refunded`` / ``skipped``) still allow a fresh payment.
# ``pending`` only counts while fresh — a request that dies between the
# pending-row commit and ``_route_escrow`` leaves an orphan that must not
# wedge every later payment attempt (#2812).
_LIVE_PAYMENT_STATUSES = frozenset({"pending", "escrowed", "released", PENDING_ACCEPTANCE, DISPUTED, SETTLEMENT_FAILED})
_PENDING_LIVE_WINDOW = timedelta(minutes=15)


def _payment_order_key(payment: JobPayment) -> tuple[datetime, str]:
    """(created_at, id) ordering key, tz-normalized for cross-backend compares."""
    created = payment.created_at
    if created.tzinfo is not None:
        created = created.replace(tzinfo=None)
    return (created, payment.id)


def _is_live_payment(payment: JobPayment, now: datetime) -> bool:
    if payment.status not in _LIVE_PAYMENT_STATUSES:
        return False
    if payment.status != "pending":
        return True
    created = payment.created_at
    if created.tzinfo is not None:
        created = created.replace(tzinfo=None)
    return created > (now - _PENDING_LIVE_WINDOW).replace(tzinfo=None)


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
        live = self.live_payment_for_job(job_id)
        if live is not None:
            return live
        return (
            self.session.execute(
                select(JobPayment)
                .where(JobPayment.job_id == job_id)
                .order_by(col(JobPayment.created_at).desc(), col(JobPayment.id).desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def live_payment_for_job(self, job_id: str) -> JobPayment | None:
        """The payment row that still holds this job's funds, if any.

        Terminal rows (``failed`` / ``refunded`` / ``skipped``) and stale
        ``pending`` orphans do not count — a fresh ``create_payment`` is
        allowed for those (#2812).
        """
        now = datetime.now(UTC)
        rows = (
            self.session.execute(
                select(JobPayment).where(
                    JobPayment.job_id == job_id,
                    col(JobPayment.status).in_(tuple(_LIVE_PAYMENT_STATUSES)),
                )
            )
            .scalars()
            .all()
        )
        live: list[JobPayment] = [p for p in rows if _is_live_payment(p, now)]
        if not live:
            return None
        return max(live, key=_payment_order_key)

    def earlier_live_payment(self, job_id: str, self_id: str, self_key: tuple[datetime, str]) -> JobPayment | None:
        """A live sibling payment sorting before ``self_key``.

        Two concurrent ``create_payment`` calls can both pass the pre-insert
        check and commit their pending rows inside the same window; exactly
        one — the row whose ``(created_at, id)`` sorts first — may proceed to
        escrow. Losers delete their pending row and return the winner.
        """
        now = datetime.now(UTC)
        siblings = (
            self.session.execute(
                select(JobPayment).where(
                    JobPayment.job_id == job_id,
                    JobPayment.id != self_id,
                    col(JobPayment.status).in_(tuple(_LIVE_PAYMENT_STATUSES)),
                )
            )
            .scalars()
            .all()
        )
        earlier: list[JobPayment] = [s for s in siblings if _is_live_payment(s, now) and _payment_order_key(s) < self_key]
        if not earlier:
            return None
        return min(earlier, key=_payment_order_key)

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
            payment_error=meta.get("escrow_error") if payment.status == "failed" else None,
            energy_quote_id=meta.get("energy_quote", {}).get("quote_id") if meta.get("energy_quote") else None,
            energy_buyer_charge_units=meta.get("energy_buyer_charge_units"),
            energy_net_floor_units=meta.get("energy_net_floor_units"),
        )
