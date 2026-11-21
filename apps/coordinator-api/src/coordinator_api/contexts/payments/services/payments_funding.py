"""Payment funding: quote evaluation, payment creation, EVM receipt verification"""

from __future__ import annotations

import time

from aitbc_shared import JobPayment
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool


from aitbc.aitbc_logging import get_logger

from aitbc.market.energy_pricing import (
    EnergyQuote,
    EnergyPricingError,
    SettlementRoute,
    evaluate_quote,
)
from aitbc.utils.units import units_to_ait
from ....schemas import JobPaymentCreate
from ...infrastructure.domain.job import Job

from .payments_helpers import (
    _OPS_ERRORS,
    _bind_evm_agreement_or_fail,
    _fail_evm_payment,
    _resolve_authoritative_inputs,
    _validate_evm_receipt_target,
)

from .payments_escrow import PaymentEscrowMixin

logger = get_logger(__name__)


class PaymentFundingMixin(PaymentEscrowMixin):
    """Mixin: payment service methods (split from payments.py; pure code motion)."""

    def _payment_meta(self, payment_data: JobPaymentCreate) -> dict[str, Any]:
        """Collect the caller-supplied payment fields to persist in meta_data."""
        meta: dict[str, Any] = {}
        if payment_data.provider_address:
            meta["provider_address"] = payment_data.provider_address
        if payment_data.buyer_agent_id:
            meta["buyer_agent_id"] = payment_data.buyer_agent_id
        if payment_data.provider_agent_id:
            meta["provider_agent_id"] = payment_data.provider_agent_id
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
        # #2371: the buyer signs market_job_id into the ESCROW_LOCK payload;
        # the rebuilt tx must carry it verbatim or the signature never verifies.
        if payment_data.market_job_id:
            meta["market_job_id"] = payment_data.market_job_id
        return meta

    def _check_quote_job_binding(self, job: Job, quote: EnergyQuote) -> None:
        """§4.6: bind the quote to the actual GPU resource and job terms.

        The job's energy fields are set at quote time by the GPU quote
        endpoint; verifying them here prevents a buyer from swapping
        the quote for a different resource/duration after the job was
        created.
        """
        if not job.protected:
            return
        if job.resource_id and quote.resource_id != job.resource_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Energy quote resource_id {quote.resource_id} does not match job resource_id {job.resource_id}",
            )
        if job.model_id and quote.model_id != job.model_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Energy quote model_id {quote.model_id} does not match job model_id {job.model_id}",
            )
        if job.gpu_count is not None and quote.gpu_count != job.gpu_count:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Energy quote gpu_count {quote.gpu_count} does not match job gpu_count {job.gpu_count}",
            )
        if job.duration_seconds is not None and quote.duration_seconds != job.duration_seconds:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Energy quote duration {quote.duration_seconds}s does not match job duration {job.duration_seconds}s",
            )

    def _evaluate_energy_quote(self, quote: EnergyQuote, meta: dict[str, Any]) -> Decimal:
        """Verify the operator signature and evaluate against the oracle snapshot.

        Returns the exact buyer charge converted to AITBC for display.
        """
        # Resolve via the facade module: tests patch ``payments.settings``.
        from . import payments as _pm

        # A-4: Verify the operator signature against the configured operator
        # address so a self-attested quote cannot fund a rental.
        # Fail-closed: if ENERGY_OPERATOR_ADDRESS is not set, reject.
        if not _pm.settings.energy_operator_address:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ENERGY_OPERATOR_ADDRESS is not configured; refusing protected funding",
            )
        if not quote.verify_operator_signature(_pm.settings.energy_operator_address):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Energy quote operator signature is missing or invalid",
            )
        # Evaluate against the authoritative oracle snapshot rather than
        # the quote's embedded profile/rate. This prevents a caller from
        # embedding arbitrary terms and funding below the real floor.
        authoritative_profile, authoritative_rate = _resolve_authoritative_inputs(quote, self.session)
        result = evaluate_quote(
            quote=quote,
            profile=authoritative_profile,
            rate=authoritative_rate,
            now=int(time.time()),
            max_rate_age_seconds=_pm.settings.energy_max_rate_age_seconds,
        )
        if not result.approved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Quote refused: {result.refusal_reason} ({result.refusal_code})",
            )
        if result.breakdown is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Quote evaluation did not return a funding breakdown",
            )
        # The display amount is the exact buyer charge converted to AITBC.
        meta["energy_quote"] = quote.to_dict(include_signature=True)
        meta["energy_quote_digest"] = quote.digest_sha256().hex()
        meta["energy_buyer_charge_units"] = result.breakdown.buyer_charge_units
        meta["energy_provider_credit_units"] = result.breakdown.provider_credit_units
        meta["energy_platform_fee_units"] = result.breakdown.platform_fee_units
        meta["energy_net_floor_units"] = result.breakdown.net_units
        meta["energy_settlement_route"] = quote.settlement_route.value
        meta["energy_is_protected"] = True
        return units_to_ait(result.breakdown.buyer_charge_units)

    def _resolve_payment_quote(
        self,
        job: Job,
        job_id: str,
        payment_data: JobPaymentCreate,
        meta: dict[str, Any],
    ) -> tuple[Decimal, EnergyQuote | None]:
        """E1: validate the signed energy quote for fixed-duration GPU rentals.

        Returns the charge amount and the parsed quote (None when the payment
        is not protected/quote-backed).
        """
        if not (payment_data.protected or payment_data.energy_quote):
            return payment_data.amount, None
        if payment_data.payment_method not in ("aitbc_token", "evm"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Protected fixed-duration GPU rentals are only supported with aitbc_token or evm settlement",
            )
        if not payment_data.energy_quote:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Protected payment requires an energy quote",
            )
        try:
            quote = EnergyQuote.from_dict(payment_data.energy_quote)
        except EnergyPricingError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid energy quote: {exc}",
            ) from exc
        if quote.job_id != job_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Energy quote is bound to a different job",
            )
        self._check_quote_job_binding(job, quote)
        amount = self._evaluate_energy_quote(quote, meta)
        # The quote names the provider; fall back to it when the caller
        # did not supply an explicit provider_address.
        if not payment_data.provider_address and quote.provider:
            payment_data.provider_address = quote.provider
            meta["provider_address"] = quote.provider
        if not payment_data.buyer_address and quote.buyer:
            payment_data.buyer_address = quote.buyer
        return amount, quote

    async def _route_escrow(
        self,
        payment: JobPayment,
        payment_data: JobPaymentCreate,
        quote: EnergyQuote | None,
    ) -> None:
        """Create the escrow/verification appropriate to the payment method."""
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
            except _OPS_ERRORS as e:
                logger.warning("Token escrow not available, skipping payment: %s", e)
                payment.status = "skipped"
        elif payment_data.payment_method == "ethereum":
            escrow = await self._create_crypto_escrow(payment)
            if escrow is not None:
                self.session.add(escrow)
        elif payment_data.payment_method == "evm":
            # EVM protected rental: the buyer funds the rental directly
            # on-chain through AIPowerRental.startRental. The coordinator
            # verifies the transaction and records the agreement/escrow id
            # but does not sign or submit any transaction on the buyer's
            # behalf.
            # EVM payment creation is quote-gated upstream; callers guarantee it.
            await self._verify_evm_protected_payment(payment, payment_data, cast(EnergyQuote, quote))

    def _sync_job_payment(self, job: Job, payment: JobPayment, payment_data: JobPaymentCreate) -> None:
        """Keep the denormalized job row in step with the authoritative payment.

        G4: the dispatch gate in JobService reads job.payment_status, so every
        entry point that creates a payment has to leave it in step. Without this a
        client retrying a skipped escrow through POST /v1/payments would lock the
        funds but never clear the gate, and the job would sit queued until its TTL.
        """
        job.payment_id = payment.id
        job.payment_status = payment.status
        # D: keep the denormalized job row in sync with the authoritative
        # JobPayment row for display/listing purposes. Security and threshold
        # checks must use JobPayment.amount directly.
        job.payment_amount = payment.amount
        job.payment_token = payment_data.currency
        # E1: copy the protected rental binding to the job for dispatch.
        if payment_data.protected and payment_data.energy_quote:
            quote = EnergyQuote.from_dict(payment_data.energy_quote)
            job.protected = True
            job.resource_id = quote.resource_id
            job.model_id = quote.model_id
            job.gpu_count = quote.gpu_count
            job.duration_seconds = quote.duration_seconds
            job.energy_quote_snapshot = quote.to_dict(include_signature=False)

    async def create_payment(self, client_id: str, job_id: str, payment_data: JobPaymentCreate) -> JobPayment:
        """Create a new payment for a job with ACID compliance"""
        job = await run_in_threadpool(self._require_owned_job, job_id, client_id)
        # #2371: the signed lock binds this payment to a market job — it must
        # be the market job the coordinator job itself declared, or the alias
        # claim would authorize a token this job never asked for.
        declared_market_job = (job.payload or {}).get("market_job_id") if isinstance(job.payload, dict) else None
        if payment_data.market_job_id and payment_data.market_job_id != declared_market_job:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="market_job_id does not match the job's declared market job",
            )
        try:
            meta = self._payment_meta(payment_data)
            amount, quote = await run_in_threadpool(self._resolve_payment_quote, job, job_id, payment_data, meta)

            payment = JobPayment(
                job_id=job_id,
                amount=amount,
                currency=payment_data.currency,
                payment_method=payment_data.payment_method,
                expires_at=datetime.now(UTC) + timedelta(seconds=payment_data.escrow_timeout_seconds),
                meta_data=meta if meta else None,
            )
            self.session.add(payment)
            await self._route_escrow(payment, payment_data, quote)
            self._sync_job_payment(job, payment, payment_data)
            self.session.add(job)
            await run_in_threadpool(self.session.commit)
            await run_in_threadpool(self.session.refresh, payment)
            logger.info("Payment created successfully: %s", payment.id)
            return payment
        except _OPS_ERRORS as e:
            await run_in_threadpool(self.session.rollback)
            logger.error("Failed to create payment: %s", e)
            raise

    async def _verify_evm_protected_payment(
        self,
        payment: JobPayment,
        payment_data: JobPaymentCreate,
        quote: EnergyQuote,
    ) -> None:
        """Verify a buyer-submitted EVM rental transaction and record it.

        The buyer calls ``AIPowerRental.startRental(agreementId)`` directly
        on-chain, which transfers ERC-20 principal + fee from the buyer to
        the contract. The coordinator does **not** sign or submit this
        transaction; it only verifies the receipt and records the agreement
        and escrow ids so dispatch can proceed.

        Raises ``HTTPException`` if the transaction is missing, failed, or
        does not match the quote terms. The payment is left in ``pending``
        until the receipt confirms success, at which point it is marked
        ``confirmed``.
        """
        if not payment_data.evm_tx_hash:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="EVM protected payment requires evm_tx_hash",
            )
        if quote.settlement_route != SettlementRoute.EVM:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Energy quote settlement route is not evm",
            )
        # The agreement/escrow ids are optional but, when supplied, are
        # recorded for later release/refund coordination.
        meta = payment.meta_data or {}
        meta["evm_tx_hash"] = payment_data.evm_tx_hash
        meta["evm_chain_id"] = quote.evm_chain_id
        meta["evm_contract"] = quote.evm_contract
        if payment_data.evm_agreement_id is not None:
            meta["evm_agreement_id"] = payment_data.evm_agreement_id
        if payment_data.evm_escrow_id is not None:
            meta["evm_escrow_id"] = payment_data.evm_escrow_id
        meta["energy_settlement_route"] = quote.settlement_route.value
        meta["energy_is_protected"] = True
        payment.meta_data = meta

        await run_in_threadpool(self._verify_evm_receipt, payment, payment_data, quote)

    def _verify_evm_receipt(
        self,
        payment: JobPayment,
        payment_data: JobPaymentCreate,
        quote: EnergyQuote,
    ) -> None:
        """Verify the buyer-submitted EVM rental transaction's receipt.

        Verify the on-chain transaction when an EVM RPC is configured.
        If no RPC is available (e.g. local dev), the payment is left
        pending for manual verification.
        """
        # Callers reject missing evm_tx_hash before this runs — re-narrow for mypy.
        evm_tx_hash = cast(str, payment_data.evm_tx_hash)
        # Resolve via the facade module: tests patch ``payments.settings``.
        from . import payments as _pm

        rpc_url = _pm.settings.eth_rpc_url
        if not rpc_url:
            logger.warning(
                "EVM RPC not configured; leaving EVM payment %s pending for manual verification",
                payment.id,
            )
            payment.status = "pending"
            return

        try:
            from aitbc.ethereum_rpc import EthereumConfig, EthereumRPCClient

            rpc = EthereumRPCClient(EthereumConfig(rpc_url=rpc_url, network=str(_pm.settings.energy_pricing_chain_id)))
            receipt = rpc.get_transaction_receipt(evm_tx_hash)
            if receipt is None:
                payment.status = "pending"
                logger.info("EVM tx %s not yet mined; payment %s pending", evm_tx_hash, payment.id)
                return
            if int(receipt.get("status", 0)) != 1:
                _fail_evm_payment(
                    payment,
                    f"EVM transaction {evm_tx_hash} failed on-chain",
                )
            expected_contract = _validate_evm_receipt_target(payment, quote, receipt)
            _bind_evm_agreement_or_fail(payment, payment_data, quote, receipt, expected_contract)
            payment.status = "confirmed"
            logger.info("EVM protected payment %s confirmed for job %s", payment.id, payment.job_id)
        except HTTPException:
            raise
        except _OPS_ERRORS as exc:
            logger.warning("EVM receipt verification failed for %s: %s", evm_tx_hash, exc)
            payment.status = "pending"
