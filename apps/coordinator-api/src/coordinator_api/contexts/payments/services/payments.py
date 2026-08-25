"""Payment service for job payments"""

from __future__ import annotations

from aitbc_shared import JobPayment, PaymentEscrow
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlmodel import select

import os

from aitbc.aitbc_logging import get_logger
from aitbc.constants import WALLET_PORT
from aitbc.exceptions import NetworkError
from aitbc.network import AITBCHTTPClient
from aitbc_agent_core import get_active_brand

from ....config import settings
from ....schemas import JobPaymentCreate, JobPaymentView
from ....storage import get_session
from ...infrastructure.domain.job import Job
from ..acceptance import (
    DISPUTED,
    HELD_STATES,
    META_DISPUTE_REASON,
    META_DISPUTED_AT,
    PENDING_ACCEPTANCE,
    deadline_from,
    opened_window,
)
from ..provider_binding import same_address

logger = get_logger(__name__)
_brand = get_active_brand()

# P2.1: high-value jobs require a verified ZK receipt proof before escrow release.
_ZK_THRESHOLD_AIT = Decimal(os.getenv("COORDINATOR_ZK_HIGH_VALUE_THRESHOLD", "10"))
_ZK_REQUIRE_PROOF = os.getenv("COORDINATOR_ZK_REQUIRE", "false").lower() == "true"


def _parse_settled_at(value: object) -> datetime | None:
    """Parse the settlement time the chain RPC reports, if it reported a usable one."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        logger.warning("Ignoring unparseable released_at from escrow release: %r", value)
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _zk_required_for_payment(payment_amount: Decimal | None, job: Job | None) -> bool:
    """Return True when a job payment triggers the ZK-proof escrow gate."""
    if _ZK_THRESHOLD_AIT < 0:
        return False
    if job and job.constraints and job.constraints.get("zk_proof_required"):
        return True
    amount = payment_amount or Decimal("0")
    return _ZK_THRESHOLD_AIT == 0 or amount >= _ZK_THRESHOLD_AIT


class PaymentService:
    """Service for handling job payments"""

    def __init__(self, session: Annotated[Session, Depends(get_session)]):
        self.session = session
        self.wallet_base_url = f"http://127.0.0.1:{WALLET_PORT}"
        self.exchange_base_url = "http://127.0.0.1:8106"
        self.blockchain_rpc_url = settings.blockchain_rpc_url.rstrip("/")

    def _require_owned_job(self, job_id: str, client_id: str) -> Job:
        """Fetch a job and verify it belongs to the requesting client."""
        job = self.session.get(Job, job_id)
        if job is None or job.client_id != client_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for this payment",
            )
        return job

    async def create_payment(self, client_id: str, job_id: str, payment_data: JobPaymentCreate) -> JobPayment:
        """Create a new payment for a job with ACID compliance"""
        job = self._require_owned_job(job_id, client_id)
        try:
            meta = {}
            if payment_data.provider_address:
                meta["provider_address"] = payment_data.provider_address
            if payment_data.auto_reinvest_pct is not None:
                meta["auto_reinvest_pct"] = str(payment_data.auto_reinvest_pct)
            # G1: the advertised terms, stored as strings beside the payee they name.
            # Without them a released escrow records only the total, and there is no
            # way to check afterwards that it matched the offer the buyer saw.
            if payment_data.offer_id:
                meta["offer_id"] = payment_data.offer_id
            if payment_data.offer_unit_price is not None:
                meta["offer_unit_price"] = str(payment_data.offer_unit_price)
            if payment_data.offer_price_unit:
                meta["offer_price_unit"] = payment_data.offer_price_unit
            if payment_data.offer_quantity is not None:
                meta["offer_quantity"] = str(payment_data.offer_quantity)
            payment = JobPayment(
                job_id=job_id,
                amount=payment_data.amount,
                currency=payment_data.currency,
                payment_method=payment_data.payment_method,
                expires_at=datetime.now(UTC) + timedelta(seconds=payment_data.escrow_timeout_seconds),
                meta_data=meta if meta else None,
            )
            self.session.add(payment)
            if payment_data.payment_method == "aitbc_token":
                try:
                    escrow = await self._create_token_escrow(
                        payment,
                        payment_data,
                        buyer_address=payment_data.buyer_address,
                        provider_address=payment_data.provider_address,
                    )
                    if escrow is not None:
                        self.session.add(escrow)
                except Exception as e:
                    logger.warning("Token escrow not available, skipping payment: %s", e)
                    payment.status = "skipped"
            elif payment_data.payment_method == "ethereum":
                escrow = await self._create_crypto_escrow(payment)
                if escrow is not None:
                    self.session.add(escrow)
            # G4: the dispatch gate in JobService reads job.payment_status, so every
            # entry point that creates a payment has to leave it in step. Without this a
            # client retrying a skipped escrow through POST /v1/payments would lock the
            # funds but never clear the gate, and the job would sit queued until its TTL.
            job.payment_id = payment.id
            job.payment_status = payment.status
            self.session.add(job)
            self.session.commit()
            self.session.refresh(payment)
            logger.info("Payment created successfully: %s", payment.id)
            return payment
        except Exception as e:
            self.session.rollback()
            logger.error("Failed to create payment: %s", e)
            raise

    def _get_chain_id(self) -> str:
        return os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

    def _get_node_wallet_address(self) -> str:
        return os.getenv("NODE_WALLET_ADDRESS") or os.getenv("GENESIS_WALLET_ADDRESS") or ""

    async def _get_account_nonce(self, address: str) -> int:
        try:
            client = AITBCHTTPClient(timeout=5.0)
            r = client.get(f"{self.blockchain_rpc_url}/rpc/accounts/{address}")
            if isinstance(r, dict):
                return int(r.get("nonce", 0))
            if hasattr(r, "get") and not isinstance(r, dict):  # type: ignore[unreachable]
                return int(r.get("nonce", 0))
        except Exception as e:
            logger.warning("Failed to fetch nonce for %s: %s", address, e)
        return 0

    def _build_escrow_lock_tx(
        self,
        payment: JobPayment,
        buyer: str,
        provider: str,
        nonce: int,
        fee: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Build the canonical ESCROW_LOCK transaction. Amount is in compute-seconds."""
        amount_ait = payment.amount
        amount_seconds = int(amount_ait * 3600)
        if amount_seconds <= 0:
            amount_seconds = int(amount_ait)
        if fee is None:
            fee = max(36, amount_seconds // 100)
        node_wallet = self._get_node_wallet_address()
        if not node_wallet:
            raise ValueError("NODE_WALLET_ADDRESS or GENESIS_WALLET_ADDRESS not configured")
        return {
            "from": buyer,
            "to": node_wallet,
            "amount": amount_seconds,
            "fee": fee,
            "nonce": nonce,
            "type": "ESCROW_LOCK",
            "chain_id": self._get_chain_id(),
            "payload": {
                "action": "escrow_lock",
                "job_id": payment.job_id,
                "provider": provider,
            },
        }, amount_seconds

    async def _create_token_escrow(
        self,
        payment: JobPayment,
        payment_data: JobPaymentCreate,
        buyer_address: str | None = None,
        provider_address: str | None = None,
    ) -> PaymentEscrow | None:
        """Create an escrow for token payments using the blockchain escrow contract.

        Requires a buyer-signed ESCROW_LOCK transaction so the on-chain contract is
        backed by real funds. The hub never signs on behalf of the buyer; without a
        pre-signed lock, no escrow is created.
        """
        buyer = buyer_address or os.getenv("PAYMENT_BUYER_ADDRESS") or os.getenv("GENESIS_ADDRESS")
        # G2: there is deliberately no fallback to the buyer here. The chain pays the
        # address named at escrow creation and no other -- rpc/escrow/{job_id}/release
        # settles to the contract's agent_address -- so an escrow whose payee is the
        # buyer refunds the work to whoever ordered it and leaves a real miner unpaid.
        # With no provider named, no escrow is created; the payment then stays unsecured
        # and _payment_blocks_dispatch keeps the job out of the queue.
        provider = provider_address or os.getenv("PAYMENT_PROVIDER_ADDRESS")
        if not buyer or not provider:
            logger.warning("No buyer or provider address available for escrow; skipping payment")
            return None
        if same_address(buyer, provider):
            logger.warning(
                "Refusing escrow for job %s: the provider address is the buyer's own address (%s)",
                payment.job_id,
                provider,
            )
            return None

        if not self._get_node_wallet_address():
            logger.warning("No node wallet configured for escrow lock; skipping payment")
            return None

        try:
            nonce = payment_data.buyer_lock_nonce
            if nonce is None:
                nonce = await self._get_account_nonce(buyer)
            fee = payment_data.buyer_lock_fee
            lock_tx, _amount_seconds = self._build_escrow_lock_tx(payment, buyer, provider, nonce, fee)

            if payment_data.buyer_lock_signature:
                lock_tx["signature"] = payment_data.buyer_lock_signature
            else:
                logger.warning(
                    "No buyer lock signature supplied for job %s; the hub will not sign on behalf of the buyer",
                    payment.job_id,
                )
                return None

            client = AITBCHTTPClient(timeout=10.0)
            response = client.post(
                f"{self.blockchain_rpc_url}/rpc/escrow/create",
                json={
                    "job_id": payment.job_id,
                    "buyer": buyer,
                    "provider": provider,
                    "amount": str(payment.amount),
                    "lock_tx": lock_tx,
                },
            )
            escrow_data = response
            contract_id = escrow_data.get("contract_id")
            payment.escrow_address = contract_id
            payment.status = "escrowed"
            payment.escrowed_at = datetime.now(UTC)
            payment.updated_at = datetime.now(UTC)
            if payment.meta_data is None:
                payment.meta_data = {}
            payment.meta_data["buyer_address"] = buyer
            payment.meta_data["provider_address"] = provider
            escrow = PaymentEscrow(
                payment_id=payment.id,
                amount=payment.amount,
                currency=payment.currency,
                address=contract_id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            if escrow is not None:
                self.session.add(escrow)
            self.session.commit()
            logger.info("Created %s escrow for payment %s", _brand.token_symbol, payment.id)
            return escrow
        except NetworkError as e:
            logger.warning("Token escrow endpoint not available: %s", e)
            return None
        except Exception as e:
            logger.warning("Token escrow creation failed: %s", e)
            return None

    async def _create_crypto_escrow(self, payment: JobPayment) -> PaymentEscrow | None:
        """Create an escrow for crypto payments (exchange only)"""
        try:
            client = AITBCHTTPClient(timeout=30.0)
            try:
                escrow_data = client.post(
                    f"{self.wallet_base_url}/api/v1/escrow/create",
                    json={"amount": str(payment.amount), "currency": payment.currency, "timeout_seconds": 3600},
                )
                payment.escrow_address = escrow_data["address"]
                payment.status = "escrowed"
                payment.escrowed_at = datetime.now(UTC)
                payment.updated_at = datetime.now(UTC)
                escrow = PaymentEscrow(
                    payment_id=payment.id,
                    amount=payment.amount,
                    currency=payment.currency,
                    address=escrow_data["address"],
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
                if escrow is not None:
                    self.session.add(escrow)
                self.session.commit()
                logger.info("Created crypto escrow for payment %s", payment.id)
                return escrow
            except NetworkError as e:
                logger.error("Failed to create crypto escrow: %s", e)
                payment.status = "failed"
                payment.updated_at = datetime.now(UTC)
                self.session.commit()
                return None
        except Exception as e:
            logger.error("Error creating crypto escrow: %s", e)
            payment.status = "failed"
            payment.updated_at = datetime.now(UTC)
            self.session.commit()
            return None

    def open_acceptance_window(self, job_id: str, payment_id: str, window_seconds: int) -> datetime | None:
        """Hold a completed job's escrow for the customer to review it (G3).

        Returns the deadline the hold expires at, or None when there is nothing to
        hold -- no such payment, or one that is not escrowed -- so the caller can
        report a settlement failure rather than assume the money is waiting.

        The escrow itself is untouched: the funds stay locked on-chain exactly as
        they were, and only the coordinator's view of what happens next changes.
        """
        payment = self.session.get(JobPayment, payment_id)
        if payment is None or payment.job_id != job_id or payment.status != "escrowed":
            return None
        now = datetime.now(UTC)
        payment.meta_data = opened_window(payment.meta_data, window_seconds, now=now)
        payment.status = PENDING_ACCEPTANCE
        payment.updated_at = now
        self.session.add(payment)
        self.session.commit()
        deadline = deadline_from(payment.meta_data)
        logger.info("Payment %s held for acceptance on job %s until %s", payment_id, job_id, deadline)
        return deadline

    def dispute_payment(self, client_id: str, job_id: str, payment_id: str, reason: str) -> bool:
        """Record a customer's rejection of the result (G3).

        The escrow deliberately stays locked. Refunding on the customer's word alone
        would be the mirror image of the problem an acceptance window exists to fix --
        one party settling in its own favour -- so an operator or arbiter rules on it.
        """
        payment = self.session.get(JobPayment, payment_id)
        if payment is None or payment.job_id != job_id:
            return False
        self._require_owned_job(payment.job_id, client_id)
        if payment.status != PENDING_ACCEPTANCE:
            return False
        now = datetime.now(UTC)
        meta = dict(payment.meta_data or {})
        meta[META_DISPUTE_REASON] = reason
        meta[META_DISPUTED_AT] = now.isoformat()
        payment.meta_data = meta
        payment.status = DISPUTED
        payment.updated_at = now
        self.session.add(payment)
        self.session.commit()
        logger.info("Payment %s disputed on job %s: %s", payment_id, job_id, reason)
        return True

    async def release_payment(self, client_id: str, job_id: str, payment_id: str, reason: str | None = None) -> bool:
        """Release payment from escrow to miner using the blockchain escrow contract."""
        payment = self.session.get(JobPayment, payment_id)
        if payment is None or payment.job_id != job_id:
            return False
        self._require_owned_job(payment.job_id, client_id)
        # G3: "pending_acceptance" and "disputed" are escrowed money under another
        # name -- the funds are still locked -- so a release from either is the same
        # on-chain operation. Anything outside HELD_STATES has already settled.
        if payment.status not in HELD_STATES:
            return False
        job = self.session.get(Job, job_id)
        if _zk_required_for_payment(payment.amount if payment.amount else None, job):
            receipt = job.receipt if job else None
            if not receipt or receipt.get("zk_status") != "verified" or receipt.get("computation_correct") is False:
                logger.error(
                    "Escrow release blocked for job %s payment %s: verified ZK receipt proof with correct computation required (zk_status=%s, computation_correct=%s)",
                    job_id,
                    payment_id,
                    receipt.get("zk_status") if receipt else None,
                    receipt.get("computation_correct") if receipt else None,
                )
                return False
        try:
            client = AITBCHTTPClient(timeout=30.0)
            try:
                release_body = {"reason": reason or "Job completed successfully"}
                meta = payment.meta_data or {}
                provider_address = meta.get("provider_address")
                auto_reinvest_pct = meta.get("auto_reinvest_pct")
                # P2.4: if the payment was created before constraints stored reinvest, fall
                # back to the job's constraints.
                if auto_reinvest_pct is None and job and job.constraints:
                    auto_reinvest_pct = job.constraints.get("auto_reinvest_pct")
                if provider_address and auto_reinvest_pct:
                    release_body["provider_address"] = provider_address
                    release_body["auto_reinvest_pct"] = str(auto_reinvest_pct)
                    release_body["auto_reinvest_address"] = provider_address
                release_data = client.post(
                    f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}/release",
                    json=release_body,
                )
                # The RPC reports success only once the ESCROW_RELEASE transaction is
                # accepted on-chain. Leave the payment escrowed otherwise, so it can be
                # retried rather than recorded as paid with no settlement behind it.
                if release_data.get("success") is False or release_data.get("settlement_status") == "unsettled":
                    logger.error(
                        "Escrow release for job %s was not settled on-chain (%s); payment %s stays escrowed",
                        job_id,
                        release_data.get("message"),
                        payment_id,
                    )
                    return False
                # Prefer the settlement time the chain reports. On a reconciliation
                # retry that is the original settlement, not this retry, so the payment
                # keeps the time the provider was actually paid.
                settled_at = _parse_settled_at(release_data.get("released_at")) or datetime.now(UTC)
                payment.status = "released"
                payment.released_at = settled_at
                payment.updated_at = datetime.now(UTC)
                payment.transaction_hash = release_data.get("tx_hash") or release_data.get("transaction_hash")
                reinvest_stake_id = release_data.get("reinvest_stake_id")
                reinvest_amount = release_data.get("reinvest_amount")
                if reinvest_stake_id or reinvest_amount:
                    meta = dict(payment.meta_data or {})
                    if reinvest_stake_id:
                        meta["reinvest_stake_id"] = str(reinvest_stake_id)
                    if reinvest_amount:
                        meta["reinvest_amount"] = str(reinvest_amount)
                    meta["reinvest_status"] = "staked" if reinvest_stake_id else "scheduled"
                    payment.meta_data = meta
                escrow = (
                    self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
                )
                if escrow:
                    escrow.is_released = True
                    escrow.released_at = settled_at
                self.session.commit()
                logger.info("Released payment %s for job %s", payment_id, job_id)
                return True
            except NetworkError as e:
                logger.error("Failed to release payment: %s", e)
                return False
        except Exception as e:
            logger.error("Error releasing payment: %s", e)
            return False

    async def refund_payment(self, client_id: str, job_id: str, payment_id: str, reason: str) -> bool:
        """Refund payment to client"""
        payment = self.session.get(JobPayment, payment_id)
        if payment is None or payment.job_id != job_id:
            return False
        self._require_owned_job(payment.job_id, client_id)
        # G3: a held or disputed payment is still refundable; the escrow never moved.
        if payment.status not in HELD_STATES and payment.status != "pending":
            return False
        try:
            client = AITBCHTTPClient(timeout=30.0)
            # Check whether the on-chain escrow is already in a final state.
            escrow_state = None
            try:
                escrow_info = client.get(f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}")
                if isinstance(escrow_info, dict):
                    escrow_state = escrow_info.get("state")
                    refund_tx_hash = escrow_info.get("refund_tx_hash")
            except Exception as e:
                logger.warning("Could not fetch escrow state for %s: %s", job_id, e)

            if escrow_state == "refunded":
                payment.status = "refunded"
                payment.refunded_at = datetime.now(UTC)
                payment.updated_at = datetime.now(UTC)
                payment.refund_transaction_hash = refund_tx_hash
                escrow = (
                    self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
                )
                if escrow:
                    escrow.is_refunded = True
                    escrow.refunded_at = datetime.now(UTC)
                self.session.commit()
                logger.info("Marked payment %s as refunded (escrow already refunded) for job %s", payment_id, job_id)
                return True

            if escrow_state in {"released", "expired"}:
                logger.error("Escrow for job %s is in %s state, cannot refund", job_id, escrow_state)
                return False

            try:
                # V23-47: refund is an escrow contract operation, not a wallet endpoint.
                refund_data = client.post(
                    f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}/refund",
                    json={"reason": reason},
                )
                if not refund_data or not refund_data.get("success"):
                    logger.error("Blockchain escrow refund failed for %s: %s", job_id, refund_data)
                    return False
                payment.status = "refunded"
                payment.refunded_at = datetime.now(UTC)
                payment.updated_at = datetime.now(UTC)
                payment.refund_transaction_hash = refund_data.get("refund_tx_hash") or refund_data.get("transaction_hash")
                escrow = (
                    self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
                )
                if escrow:
                    escrow.is_refunded = True
                    escrow.refunded_at = datetime.now(UTC)
                self.session.commit()
                logger.info("Refunded payment %s for job %s", payment_id, job_id)
                return True
            except NetworkError as e:
                logger.error("Failed to refund payment: %s", e)
                return False
        except Exception as e:
            logger.error("Error refunding payment: %s", e)
            return False

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
        )
