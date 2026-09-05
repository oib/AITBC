"""Payment service for job payments"""

from __future__ import annotations

import httpx
import os

from aitbc_shared import JobPayment, PaymentEscrow
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger
from aitbc.constants import WALLET_PORT
from aitbc.exceptions import NetworkError
from aitbc.network import AsyncAITBCHTTPClient
from aitbc_agent_core import get_active_brand

from ....config import settings
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils.units import ait_to_units
from aitbc.utils.validation import validate_address
from ....custom_types import JobState
from ....schemas import JobPaymentCreate, JobPaymentView
from ....storage import get_session
from ....utils.client_resolver import resolve_client
from ...infrastructure.domain.job import Job
from ...infrastructure.domain.job_receipt import JobReceipt
from ...zk_applications.services import model_registry
from ..acceptance import (
    DISPUTED,
    HELD_STATES,
    META_DISPUTE_REASON,
    META_DISPUTED_AT,
    META_RELEASE_ATTEMPTS,
    META_RELEASE_BLOCKED_AT,
    PENDING_ACCEPTANCE,
    REFUNDABLE_STATES,
    SETTLEMENT_FAILED,
    deadline_from,
    max_release_attempts,
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


async def _lookup_chain_refund(blockchain_rpc_url: str, client: AsyncAITBCHTTPClient, job_id: str) -> str | None:
    """Return the on-chain ESCROW_REFUND tx hash for job_id, if one exists.

    Raises on transport or non-2xx responses so callers do not mistake
    "could not tell" for "does not exist".
    """
    # The RPC client declares a dict return, but /transactions returns a list.
    txs: Any = await client.get(
        f"{blockchain_rpc_url}/rpc/transactions?transaction_type=ESCROW_REFUND&job_id={job_id}&limit=10"
    )
    if isinstance(txs, list):
        for tx in txs:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                tx_hash = tx.get("tx_hash")
                return str(tx_hash) if tx_hash is not None else None
    return None


async def _lookup_chain_lock(blockchain_rpc_url: str, client: AsyncAITBCHTTPClient, job_id: str) -> str | None:
    """Return the on-chain ESCROW_LOCK tx hash for job_id, if one exists.

    Raises on transport or non-2xx responses so callers do not mistake
    "could not tell" for "does not exist".
    """
    # The RPC client declares a dict return, but /transactions returns a list.
    txs: Any = await client.get(f"{blockchain_rpc_url}/rpc/transactions?transaction_type=ESCROW_LOCK&job_id={job_id}&limit=10")
    if isinstance(txs, list):
        for tx in txs:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                tx_hash = tx.get("tx_hash")
                return str(tx_hash) if tx_hash is not None else None
    return None


def _tee_attests_computation(receipt: dict[str, Any] | None, job: Job | None) -> bool:
    """Return True when a registered TEE quote attests a model with no Groth16 circuit.

    Groth16 remains mandatory for registered circuits such as ``linear-1``. A
    TEE quote is only a substitute when the model cannot be proven in-circuit.
    """
    if not receipt or job is None:
        return False
    if receipt.get("tee_status") != "verified":
        return False
    if receipt.get("zk_status") != "tee_attested":
        return False
    if receipt.get("computation_correct") is not True:
        return False
    model_id = model_registry.resolve_model_id(job, job.result if isinstance(job.result, dict) else None)
    return model_id is not None and model_registry.get_model(model_id) is None


def _computation_is_correct(receipt: dict[str, Any] | None, job: Job | None) -> bool:
    """Return True when escrow may release because computation was attested."""
    if not receipt:
        return False
    if receipt.get("computation_correct") is not True:
        return False
    zk_status = receipt.get("zk_status")
    if zk_status in ("verified", "not_required", "tee_attested"):
        return True
    return _tee_attests_computation(receipt, job)


def get_receipt_of_record(session: Session, job: Job | None) -> dict[str, Any] | None:
    """Return the canonical receipt for a job.

    Prefer the ``JobReceipt`` row (indexed by ``job.receipt_id``) because it is the
    authoritative, signed record; fall back to the denormalised ``Job.receipt`` JSON.
    """
    if job is None:
        return None
    if job.receipt_id:
        row = session.execute(select(JobReceipt).where(JobReceipt.receipt_id == job.receipt_id)).scalars().first()
        if row and row.payload:
            payload: dict[str, Any] = row.payload
            return payload
    return job.receipt if job.receipt else None


def _zk_required_for_payment(payment_amount: Decimal | None, job: Job | None) -> bool:
    """Return True when a job payment triggers the ZK-proof escrow gate.

    The gate applies when COORDINATOR_ZK_REQUIRE=true, the job explicitly
    requires a ZK proof, or the payment amount crosses the high-value
    threshold. Whether the requested model actually has a registered circuit
    is decided later when the receipt is generated/verified; the gate must
    not silently downgrade a required proof just because the model is missing.
    """
    if _ZK_THRESHOLD_AIT < 0:
        return False
    if _ZK_REQUIRE_PROOF:
        return True
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
        self.blockchain_rpc_api_key = settings.blockchain_rpc_api_key

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
            # D: keep the denormalized job row in sync with the authoritative
            # JobPayment row for display/listing purposes. Security and threshold
            # checks must use JobPayment.amount directly.
            job.payment_amount = payment_data.amount
            job.payment_token = payment_data.currency
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
            client = AsyncAITBCHTTPClient(timeout=5.0, api_key=self.blockchain_rpc_api_key)
            r = await client.get(f"{self.blockchain_rpc_url}/rpc/accounts/{address}")
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
        """Build the canonical ESCROW_LOCK transaction. Amount is in compute-units."""
        amount_ait = payment.amount
        amount_units = ait_to_units(amount_ait)
        if amount_units <= 0:
            amount_units = ait_to_units(Decimal("1"))
        if fee is None:
            # v0.25.6: 1% fee with dust floor; the flat DEFAULT_TX_FEE_UNITS
            # (0.01 AIT) made small escrow locks cost 100% of the value.
            fee = max(36, amount_units // 100)
        node_wallet = self._get_node_wallet_address()
        if not node_wallet:
            raise ValueError("NODE_WALLET_ADDRESS or GENESIS_WALLET_ADDRESS not configured")
        try:
            node_wallet = canonical_address(node_wallet)
        except Exception as e:
            raise ValueError(f"Invalid node wallet address {node_wallet}: {e}") from e
        if not validate_address(node_wallet):
            raise ValueError(f"Invalid node wallet address {node_wallet}: not a valid 0x address")
        return {
            "from": buyer,
            "to": node_wallet,
            "amount": amount_units,
            "fee": fee,
            "nonce": nonce,
            "type": "ESCROW_LOCK",
            "chain_id": self._get_chain_id(),
            "payload": {
                "action": "escrow_lock",
                "job_id": payment.job_id,
                "provider": provider,
            },
        }, amount_units

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
        # G2: the buyer must be explicit. Never fall back to GENESIS_ADDRESS; in this
        # environment GENESIS_ADDRESS is the legacy proposer/node wallet and using it
        # as a buyer would create self-send escrow locks.
        buyer = buyer_address or os.getenv("PAYMENT_BUYER_ADDRESS")
        if not buyer:
            logger.error("No buyer address for escrow: set payment_data.buyer_address or PAYMENT_BUYER_ADDRESS")
            return None
        # G2: there is deliberately no fallback to the buyer here. The chain pays the
        # address named at escrow creation and no other -- rpc/escrow/{job_id}/release
        # settles to the contract's agent_address -- so an escrow whose payee is the
        # buyer refunds the work to whoever ordered it and leaves a real miner unpaid.
        # With no provider named, no escrow is created; the payment then stays unsecured
        # and _payment_blocks_dispatch keeps the job out of the queue.
        provider = provider_address or os.getenv("PAYMENT_PROVIDER_ADDRESS")
        if buyer:
            try:
                buyer = canonical_address(buyer)
            except Exception:
                logger.warning("Invalid buyer address for escrow: %s", buyer)
                return None
            if not validate_address(buyer):
                logger.warning("Invalid buyer address for escrow: %s", buyer)
                return None
        if provider:
            try:
                provider = canonical_address(provider)
            except Exception:
                logger.warning("Invalid provider address for escrow: %s", provider)
                return None
            if not validate_address(provider):
                logger.warning("Invalid provider address for escrow: %s", provider)
                return None
        if not buyer or not provider:
            logger.warning("No buyer or provider address available for escrow; skipping payment")
            return None

        node_wallet = self._get_node_wallet_address()
        if not node_wallet:
            logger.warning("No node wallet configured for escrow lock; skipping payment")
            return None

        if same_address(buyer, provider):
            logger.warning(
                "Refusing escrow for job %s: the provider address is the buyer's own address (%s)",
                payment.job_id,
                provider,
            )
            return None
        if same_address(buyer, node_wallet):
            logger.error(
                "Refusing escrow for job %s: buyer address %s is the node wallet",
                payment.job_id,
                buyer,
            )
            return None
        if same_address(provider, node_wallet):
            logger.error(
                "Refusing escrow for job %s: provider address %s is the node wallet",
                payment.job_id,
                provider,
            )
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

            client = AsyncAITBCHTTPClient(timeout=10.0, api_key=self.blockchain_rpc_api_key)
            response = await client.post(
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
            client = AsyncAITBCHTTPClient(timeout=30.0, api_key=self.blockchain_rpc_api_key)
            try:
                escrow_data = await client.post(
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
        job = self.session.get(Job, job_id)
        if job is not None:
            job.payment_status = payment.status
            self.session.add(job)
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
        job = self._require_owned_job(payment.job_id, client_id)
        job.payment_status = payment.status
        self.session.add(job)
        self.session.add(payment)
        self.session.commit()
        logger.info("Payment %s disputed on job %s: %s", payment_id, job_id, reason)
        return True

    def _get_receipt_of_record(self, job: Job | None) -> dict[str, Any] | None:
        """Return the canonical receipt for a job.

        The ``Job`` row's ``receipt`` JSON may lag the ``jobreceipt`` table (JSON
        ``MutableDict`` does not always track in-place updates, and the row may be
        written before ZK/TEE fields are added). Prefer ``JobReceipt.payload`` when a
        ``receipt_id`` is present; fall back to the denormalised ``Job.receipt``.
        """
        return get_receipt_of_record(self.session, job)

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
        # A held payment that keeps failing release is retried by every sweeper at
        # every interval forever. Count attempts in meta_data (reassigned, not
        # mutated -- the column is plain JSON) and, past the bound, move the
        # payment to `settlement_failed` so no automatic path picks it up again.
        # The escrow stays funded and refundable; an operator resets the counter
        # through the admin retry-release route once the blocker is fixed.
        meta = dict(payment.meta_data or {})
        attempts = int(meta.get(META_RELEASE_ATTEMPTS) or 0)
        if attempts >= max_release_attempts():
            now = datetime.now(UTC)
            payment.status = SETTLEMENT_FAILED
            payment.updated_at = now
            meta[META_RELEASE_BLOCKED_AT] = now.isoformat()
            payment.meta_data = meta
            stuck_job = self.session.get(Job, job_id)
            if stuck_job is not None:
                stuck_job.payment_status = SETTLEMENT_FAILED
                self.session.add(stuck_job)
            self.session.add(payment)
            self.session.commit()
            logger.critical(
                "Escrow release for job %s payment %s failed %s times; marking settlement_failed "
                "and stopping automatic retries (refund and the admin retry route still work)",
                job_id,
                payment_id,
                attempts,
            )
            return False
        meta[META_RELEASE_ATTEMPTS] = attempts + 1
        payment.meta_data = meta
        self.session.add(payment)
        self.session.commit()
        job = self.session.get(Job, job_id)
        if job is None:
            logger.error("Escrow release blocked for job %s: job not found", job_id)
            return False
        if job.state != JobState.completed.value:
            logger.error(
                "Escrow release blocked for job %s payment %s: job state is %s, expected %s",
                job_id,
                payment_id,
                job.state,
                JobState.completed.value,
            )
            return False
        receipt = self._get_receipt_of_record(job)
        if not _computation_is_correct(receipt, job):
            logger.error(
                "Escrow release blocked for job %s payment %s: computation not attested (zk_status=%s, computation_correct=%s)",
                job_id,
                payment_id,
                receipt.get("zk_status") if receipt else None,
                receipt.get("computation_correct") if receipt else None,
            )
            return False
        try:
            client = AsyncAITBCHTTPClient(timeout=30.0, api_key=self.blockchain_rpc_api_key)
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
                release_data = await client.post(
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
                if not release_data.get("tx_hash"):
                    logger.error(
                        "Escrow release for job %s succeeded without a settlement hash; payment %s stays escrowed",
                        job_id,
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
                if job is not None:
                    job.payment_status = payment.status
                    self.session.add(job)
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
        job = self._require_owned_job(payment.job_id, client_id)
        # B-residue: already-refunded rows may carry a pre-5b0455921 local hash.
        # Fix the denormalised cache, but continue so the chain can return the
        # authoritative on-chain hash.
        if payment.status == "refunded":
            if job.payment_status != "refunded":
                job.payment_status = "refunded"
                self.session.add(job)
                self.session.commit()
        # G3: a held or disputed payment is still refundable; the escrow never moved.
        # B-residue: already-refunded rows are allowed through so stale hashes can
        # be reconciled against the real on-chain transaction.
        # A payment that was never escrowed cannot be refunded; gating on escrowed_at
        # rather than status prevents the audit invariant from being broken by pending
        # or otherwise non-escrowed rows.
        elif payment.escrowed_at is None or payment.status not in REFUNDABLE_STATES:
            return False
        try:
            client = AsyncAITBCHTTPClient(timeout=30.0, api_key=self.blockchain_rpc_api_key)
            # Check whether the on-chain escrow is already in a final state.
            escrow_state = None
            escrow_not_found = False
            try:
                escrow_info = await client.get(f"{self.blockchain_rpc_url}/rpc/escrow/{job_id}")
                if isinstance(escrow_info, dict):
                    escrow_state = escrow_info.get("state")
            except NetworkError as e:
                cause = e.__cause__
                if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 404:
                    escrow_not_found = True
                else:
                    logger.error("Could not fetch escrow state for %s: %s", job_id, e)
                    raise

            # H1: unbacked escrow guard. A payment row may be 'escrowed' but the
            # ESCROW_LOCK transaction was never persisted on-chain. No funds moved,
            # so the safe recovery is to mark it refunded and stop retrying.
            # The correct check is whether an ESCROW_LOCK tx exists on-chain, not
            # whether the payment has been released (transaction_hash is a release hash).
            # Only run this for held states; a 'pending' payment has no lock by construction.
            if (
                payment.status in HELD_STATES
                and escrow_not_found
                and not await _lookup_chain_lock(self.blockchain_rpc_url, client, job_id)
            ):
                logger.warning(
                    "Escrow for job %s not found on-chain and payment %s has no lock tx; "
                    "treating as unbacked escrow and marking refunded",
                    job_id,
                    payment_id,
                )
                payment.status = "refunded"
                payment.refunded_at = datetime.now(UTC)
                payment.updated_at = datetime.now(UTC)
                payment.refund_transaction_hash = None
                job.payment_status = "refunded"
                self.session.add(job)
                escrow = (
                    self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
                )
                if escrow:
                    escrow.is_refunded = True
                    escrow.is_active = False
                    escrow.refunded_at = datetime.now(UTC)
                self.session.commit()
                logger.info("Marked unbacked payment %s as refunded for job %s", payment_id, job_id)
                return True

            if escrow_state == "refunded":
                # B-residue: do not trust a pre-5b0455921 local SHA-256 string.
                # Only accept the DB marker when the same hash is visible on-chain.
                chain_refund_hash = await _lookup_chain_refund(self.blockchain_rpc_url, client, job_id)
                if chain_refund_hash:
                    payment.status = "refunded"
                    payment.refunded_at = datetime.now(UTC)
                    payment.updated_at = datetime.now(UTC)
                    payment.refund_transaction_hash = chain_refund_hash
                    job.payment_status = payment.status
                    self.session.add(job)
                    escrow = (
                        self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id))
                        .scalars()
                        .first()
                    )
                    if escrow:
                        escrow.is_refunded = True
                        escrow.is_active = False
                        escrow.refunded_at = datetime.now(UTC)
                    self.session.commit()
                    logger.info("Marked payment %s as refunded (escrow already refunded) for job %s", payment_id, job_id)
                    return True
                # No on-chain refund exists yet; fall through to submit a real one.

            if escrow_state in {"released", "expired"}:
                logger.error("Escrow for job %s is in %s state, cannot refund", job_id, escrow_state)
                return False

            try:
                # V23-47: refund is an escrow contract operation, not a wallet endpoint.
                refund_data = await client.post(
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
                job.payment_status = payment.status
                self.session.add(job)
                escrow = (
                    self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment_id)).scalars().first()
                )
                if escrow:
                    escrow.is_refunded = True
                    escrow.is_active = False
                    escrow.refunded_at = datetime.now(UTC)
                self.session.commit()
                logger.info("Refunded payment %s for job %s", payment_id, job_id)
                return True
            except NetworkError as e:
                logger.error("Failed to submit refund transaction: %s", e)
                raise
        except Exception as e:
            logger.error("Error refunding payment: %s", e)
            raise

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
