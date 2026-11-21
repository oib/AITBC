"""Escrow creation: lock transactions, token/native escrow, ambiguity recovery"""

from __future__ import annotations

import asyncio
import os

from aitbc_shared import JobPayment, PaymentEscrow
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from starlette.concurrency import run_in_threadpool
from sqlmodel import select


from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc_agent_core import get_active_brand

from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils.units import ait_to_units
from aitbc.utils.validation import validate_address
from ....schemas import JobPaymentCreate
from .escrow_agent_binding import assert_agent_address_binding, default_resolve_chain_id
from ..provider_binding import same_address

from .payments_helpers import (
    _OPS_ERRORS,
    _escrow_failure_reason,
    _escrow_record_is_settled,
    _lookup_chain_lock,
    _lookup_escrow_record,
)


from .payments_core import PaymentCoreMixin

_brand = get_active_brand()
logger = get_logger(__name__)


class PaymentEscrowMixin(PaymentCoreMixin):
    """Mixin: payment service methods (split from payments.py; pure code motion)."""

    async def _get_account_nonce(self, address: str) -> int:
        # Resolve via the facade module: tests patch ``payments.AsyncAITBCHTTPClient``.
        from . import payments as _pm

        try:
            client = _pm.AsyncAITBCHTTPClient(timeout=5.0, api_key=self.blockchain_rpc_api_key)
            r = await client.get(f"{self.blockchain_rpc_url}/rpc/accounts/{address}")
            if isinstance(r, dict):
                return int(r.get("nonce", 0))
            if hasattr(r, "get") and not isinstance(r, dict):  # type: ignore[unreachable]
                return int(r.get("nonce", 0))
        except _OPS_ERRORS as e:
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
        meta = payment.meta_data or {}
        # E1: protected rentals use the exact signed buyer charge, not a rounded
        # display amount reconstructed from payment.amount.
        if meta.get("energy_is_protected"):
            amount_units = int(meta["energy_buyer_charge_units"])
        else:
            amount_units = ait_to_units(payment.amount)
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
        except _OPS_ERRORS as e:
            raise ValueError(f"Invalid node wallet address {node_wallet}: {e}") from e
        if not validate_address(node_wallet):
            raise ValueError(f"Invalid node wallet address {node_wallet}: not a valid 0x address")
        tx: dict[str, Any] = {
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
        }
        if meta.get("energy_is_protected"):
            self._mirror_energy_lock_payload(tx["payload"], meta)
        return tx, amount_units

    def _mirror_energy_lock_payload(self, payload: dict[str, Any], meta: dict[str, Any]) -> None:
        """Mirror the energy-quote settlement metadata in the lock payload (E1)
        so it matches the transaction the buyer signed locally."""
        payload["energy_quote_id"] = meta["energy_quote"]["quote_id"]
        payload["energy_quote_digest"] = meta["energy_quote_digest"]
        eq = meta["energy_quote"]
        if eq.get("settlement_route"):
            payload["settlement_route"] = eq["settlement_route"]
        if eq.get("settlement_asset"):
            payload["settlement_asset"] = eq["settlement_asset"]
        if eq.get("settlement_unit_scale") is not None:
            payload["settlement_unit_scale"] = eq["settlement_unit_scale"]

    def _canonicalize_escrow_party(self, role: str, address: str | None) -> str | None:
        if not address:
            return None
        try:
            canonical = canonical_address(address)
        except _OPS_ERRORS:
            logger.warning("Invalid %s address for escrow: %s", role, address)
            return None
        if not validate_address(canonical):
            logger.warning("Invalid %s address for escrow: %s", role, canonical)
            return None
        return canonical

    def _resolve_escrow_parties(
        self,
        payment: JobPayment,
        buyer_address: str | None,
        provider_address: str | None,
    ) -> tuple[str, str] | None:
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
        buyer = self._canonicalize_escrow_party("buyer", buyer)
        if buyer is None:
            return None
        provider = self._canonicalize_escrow_party("provider", provider)
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
        return buyer, provider

    async def _submit_escrow_create(
        self,
        payment: JobPayment,
        buyer: str,
        provider: str,
        lock_tx: dict[str, Any],
        meta: dict[str, Any],
    ) -> PaymentEscrow | None:
        """POST the buyer-signed lock to the chain and persist the resulting escrow row.

        ``/rpc/escrow/create`` returning 2xx only means the lock was accepted
        into the mempool — a tx that can never seal (e.g. insufficient buyer
        balance) must not stamp ``escrowed``: ``escrowed`` is the single
        dispatchable payment state and every downstream path trusts it
        (#2297). Wait for the sealed ESCROW_LOCK before recording; on timeout
        mark the payment failed so the purchase can be retried.
        """
        # Resolve via the facade module: tests patch ``payments.AsyncAITBCHTTPClient``.
        from . import payments as _pm

        client = _pm.AsyncAITBCHTTPClient(timeout=10.0, api_key=self.blockchain_rpc_api_key)
        payload = {
            "job_id": payment.job_id,
            "buyer": buyer,
            "provider": provider,
            "amount": str(payment.amount),
            "lock_tx": lock_tx,
        }
        if meta.get("energy_is_protected"):
            payload["energy_quote"] = meta["energy_quote"]
            payload["energy_quote_digest"] = meta["energy_quote_digest"]
        buyer_agent_id = meta.get("buyer_agent_id")
        provider_agent_id = meta.get("provider_agent_id")
        if buyer_agent_id:
            payload["buyer_agent_id"] = buyer_agent_id
        if provider_agent_id:
            payload["provider_agent_id"] = provider_agent_id
        escrow_data = await client.post(
            f"{self.blockchain_rpc_url}/rpc/escrow/create",
            json=payload,
        )
        lock_tx_hash = await self._wait_for_lock_seal(client, payment.job_id)
        if lock_tx_hash is None:
            self._mark_escrow_failed(
                payment,
                "unsealed",
                "the escrow lock did not seal on-chain; the purchase can be retried",
            )
            return None
        escrow = await run_in_threadpool(
            self._record_escrowed,
            payment,
            buyer,
            provider,
            contract_id=escrow_data.get("contract_id"),
            lock_tx_hash=lock_tx_hash,
        )
        logger.info("Created %s escrow for payment %s", _brand.token_symbol, payment.id)
        return escrow

    async def _wait_for_lock_seal(self, client: Any, job_id: str) -> str | None:
        """Poll the sealed transaction table until the job's ESCROW_LOCK appears.

        Returns the lock tx hash once sealed, or None when the bounded wait
        expires — including when the probe itself keeps failing, which is
        fail-closed: an unverifiable lock is treated as unsealed.
        """
        wait_seconds = float(os.getenv("ESCROW_LOCK_SEAL_WAIT_SECONDS", "30"))
        poll_seconds = float(os.getenv("ESCROW_LOCK_SEAL_POLL_SECONDS", "2"))
        deadline = asyncio.get_running_loop().time() + wait_seconds
        while True:
            try:
                lock_tx_hash = await _lookup_chain_lock(self.blockchain_rpc_url, client, job_id)
            except _OPS_ERRORS as e:
                logger.warning("Lock-seal probe failed for job %s: %s", job_id, e)
                lock_tx_hash = None
            if lock_tx_hash is not None:
                return lock_tx_hash
            if asyncio.get_running_loop().time() >= deadline:
                logger.warning("Escrow lock for job %s did not seal within %.0fs", job_id, wait_seconds)
                return None
            await asyncio.sleep(poll_seconds)

    def _record_escrowed(
        self,
        payment: JobPayment,
        buyer: str,
        provider: str,
        contract_id: str | None,
        lock_tx_hash: str | None = None,
        recovered: bool = False,
    ) -> PaymentEscrow:
        """Persist the escrowed state and its escrow row for a confirmed lock.

        Shared by the normal create path and the ambiguous-failure recovery:
        once a lock is confirmed on the node the local bookkeeping is the same
        either way. ``recovered`` marks rows whose lock was found after the
        create response was lost, so an operator can tell them apart.
        """
        payment.escrow_address = contract_id
        payment.status = "escrowed"
        payment.escrowed_at = datetime.now(UTC)
        payment.updated_at = datetime.now(UTC)
        # A fresh dict: re-assigning the same object would not flag the JSON
        # column dirty and the party addresses would be lost on commit.
        meta = dict(payment.meta_data) if isinstance(payment.meta_data, dict) else {}
        meta["buyer_address"] = buyer
        meta["provider_address"] = provider
        if lock_tx_hash:
            meta["escrow_lock_tx_hash"] = lock_tx_hash
        if recovered:
            meta["escrow_recovered"] = True
        payment.meta_data = meta
        escrow = PaymentEscrow(
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            # NOT NULL column; a chain-only recovery has no contract id yet —
            # the lock tx hash in meta_data is the link until the node heals.
            address=contract_id or "",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.session.add(escrow)
        self.session.commit()
        return escrow

    async def _recover_ambiguous_escrow(
        self,
        payment: JobPayment,
        buyer: str,
        provider: str,
    ) -> tuple[PaymentEscrow | None, bool]:
        """Resolve an escrow POST whose response was lost before marking failure.

        Returns ``(escrow, absence_confirmed)``. A lost response does not mean
        a lost lock — the node's /escrow/create may already have submitted it,
        and a retried *purchase* creates a new job_id, so the chain's per-job
        dedup cannot rescue it. The escrow record is checked first (the route
        writes it synchronously at submit, so it covers a mempool-pending
        lock); a miss then falls back to the chain itself, which catches a
        lock whose row write never ran. ``(None, True)`` means nothing was
        submitted and the purchase is safe to retry. When neither lookup can
        say, the payment is marked ``funding_unknown`` here — the buyer must
        be told the funding state is unknown, not that the purchase failed
        cleanly.
        """
        # Resolve via the facade module: tests patch ``payments.AsyncAITBCHTTPClient``.
        from . import payments as _pm

        client = _pm.AsyncAITBCHTTPClient(timeout=10.0, api_key=self.blockchain_rpc_api_key)
        try:
            record = await _lookup_escrow_record(self.blockchain_rpc_url, client, payment.job_id)
            if record is not None and _escrow_record_is_settled(record):
                # A record already released or refunded is stale evidence from
                # an earlier escrow for this job_id — a lock submitted moments
                # ago cannot already be settled. Adopting it would mark this
                # payment escrowed on somebody else's escrow, so our lock's
                # fate is genuinely unknown here.
                settled_as = record.get("state") or record.get("status")
                if not settled_as:
                    # Settled by timestamp only — name the leg rather than
                    # interpolating a missing field as "None".
                    settled_as = "released" if record.get("released_at") else "refunded"
                self._mark_escrow_failed(
                    payment,
                    "funding_unknown",
                    f"the node reports job {payment.job_id}'s escrow as already "
                    f"{settled_as}; the funding "
                    "state of this purchase is unknown — check the job's escrow "
                    "record before retrying",
                )
                return None, False
            # #2359: the record's lock_tx_hash is written when /escrow/create
            # submits the lock to the *mempool* — it is not proof of seal.
            # Adopting it marked the payment "escrowed" while the lock could
            # still be pending (or never land), opening the dispatch gate
            # before funds existed on-chain. Only a sealed ESCROW_LOCK tx
            # (the same source _wait_for_lock_seal polls) may escrow the
            # payment; a submitted-but-unsealed lock is a retryable failure.
            contract_id = (record or {}).get("contract_id")
            lock_submitted = record is not None and record.get("lock_tx_hash") is not None
            if lock_submitted:
                lock_tx_hash = await self._wait_for_lock_seal(client, payment.job_id)
                if lock_tx_hash is None:
                    self._mark_escrow_failed(
                        payment,
                        "unsealed",
                        "the escrow lock was submitted but did not seal on-chain; "
                        "the purchase can be retried once it confirms or is dropped",
                    )
                    return None, False
            else:
                lock_tx_hash = await _lookup_chain_lock(self.blockchain_rpc_url, client, payment.job_id)
        except _OPS_ERRORS:
            self._mark_escrow_failed(
                payment,
                "funding_unknown",
                f"the escrow funding state for job {payment.job_id} could not be "
                "determined — the lock may have landed; check the job's escrow "
                "record before retrying",
            )
            return None, False
        if lock_tx_hash is None:
            return None, True
        return await run_in_threadpool(
            self._record_escrowed, payment, buyer, provider, contract_id, lock_tx_hash=lock_tx_hash, recovered=True
        ), False

    def _mark_escrow_failed(self, payment: JobPayment, kind: str, detail: str) -> None:
        """Mark a payment whose escrow never landed as ``failed`` with a
        buyer-safe reason.

        Leaving it ``pending`` makes the failure silent: ``_route_escrow``
        only overwrites on an *escaping* exception, so a swallowed refusal
        used to surface as a successful purchase with no escrow behind it
        (market_gpu rolls the booking back only on ``failed``/``skipped``).
        ``failed`` is correct even for the retryable kinds: the purchase is
        the retry unit, and a retried buy creates a *new* job_id — the
        chain's per-job ESCROW_LOCK dedup cannot resolve a lock that landed
        after a lost response, which is why the ambiguous kinds go through
        ``_recover_ambiguous_escrow`` before this is called.
        """
        payment.status = "failed"
        payment.updated_at = datetime.now(UTC)
        # A fresh dict: re-assigning the same object would not flag the JSON
        # column dirty and the failure reason would be lost on commit.
        meta = dict(payment.meta_data) if isinstance(payment.meta_data, dict) else {}
        meta["escrow_error_kind"] = kind
        meta["escrow_error"] = detail
        payment.meta_data = meta
        logger.warning("Escrow funding for payment %s failed (%s): %s", payment.id, kind, detail)

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
        # Idempotency: a payment that already has an escrow must not POST a second
        # /rpc/escrow/create. The chain side also guards (an existing ESCROW_LOCK for
        # the job short-circuits the route), but stopping here avoids the round-trip
        # and keeps the coordinator ledger authoritative about what it already did.
        existing_escrow = await run_in_threadpool(
            lambda: self.session.execute(select(PaymentEscrow).where(PaymentEscrow.payment_id == payment.id)).scalars().first()
        )
        if existing_escrow is not None or payment.escrowed_at is not None or payment.escrow_address:
            logger.warning(
                "Refusing to double-lock payment %s for job %s: escrow already exists",
                payment.id,
                payment.job_id,
            )
            return existing_escrow

        parties = self._resolve_escrow_parties(payment, buyer_address, provider_address)
        if parties is None:
            return None
        buyer, provider = parties

        resolve_chain = default_resolve_chain_id()
        if payment_data.buyer_agent_id:
            await assert_agent_address_binding(
                self.session, payment_data.buyer_agent_id, buyer, role="buyer", chain_id=resolve_chain
            )
        if payment_data.provider_agent_id:
            await assert_agent_address_binding(
                self.session, payment_data.provider_agent_id, provider, role="provider", chain_id=resolve_chain
            )

        return await self._submit_token_escrow_lock(payment, payment_data, buyer, provider)

    async def _submit_token_escrow_lock(
        self,
        payment: JobPayment,
        payment_data: JobPaymentCreate,
        buyer: str,
        provider: str,
    ) -> PaymentEscrow | None:
        """Build the buyer-signed ESCROW_LOCK and submit it; recover ambiguous failures."""
        try:
            nonce = payment_data.buyer_lock_nonce
            if nonce is None:
                # ESCROW-LOCK-NONCE-1 (#807): a signed lock fixes its nonce — guessing the
                # account nonce here would build a tx the buyer's signature never verifies.
                # The guess stays only for the coordinator-signed path (no buyer signature).
                if payment_data.buyer_lock_signature:
                    raise ValueError("buyer_lock_nonce is required when buyer_lock_signature is given")
                nonce = await self._get_account_nonce(buyer)
            fee = payment_data.buyer_lock_fee
            lock_tx, _amount_seconds = self._build_escrow_lock_tx(payment, buyer, provider, nonce, fee)
            meta = payment.meta_data or {}

            if payment_data.buyer_lock_signature:
                lock_tx["signature"] = payment_data.buyer_lock_signature
            else:
                logger.warning(
                    "No buyer lock signature supplied for job %s; the hub will not sign on behalf of the buyer",
                    payment.job_id,
                )
                self._mark_escrow_failed(payment, "unsigned", "no buyer lock signature was supplied")
                return None

            return await self._submit_escrow_create(payment, buyer, provider, lock_tx, meta)
        except _OPS_ERRORS as e:
            kind, detail = _escrow_failure_reason(e)
            if kind != "unavailable":
                self._mark_escrow_failed(payment, kind, detail)
                return None
            # A refusal or a missing signature is definitive; everything else
            # (timeout, disconnect, 5xx, an unparseable 2xx) may have committed
            # the lock anyway — look before declaring failure.
            recovered, absence_confirmed = await self._recover_ambiguous_escrow(payment, buyer, provider)
            if recovered is not None:
                return recovered
            if absence_confirmed:
                self._mark_escrow_failed(
                    payment,
                    "unavailable",
                    "the node has no escrow lock for this job; the purchase can be retried",
                )
            # else: _recover_ambiguous_escrow already marked it funding_unknown.
            return None

    async def _create_crypto_escrow(self, payment: JobPayment) -> PaymentEscrow | None:
        """Create an escrow for crypto payments (exchange only)"""
        # Resolve via the facade module: tests patch ``payments.AsyncAITBCHTTPClient``.
        from . import payments as _pm

        try:
            client = _pm.AsyncAITBCHTTPClient(timeout=30.0, api_key=self.blockchain_rpc_api_key)
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
                await run_in_threadpool(self.session.commit)
                logger.info("Created crypto escrow for payment %s", payment.id)
                return escrow
            except NetworkError as e:
                logger.error("Failed to create crypto escrow: %s", e)
                payment.status = "failed"
                payment.updated_at = datetime.now(UTC)
                await run_in_threadpool(self.session.commit)
                return None
        except _OPS_ERRORS as e:
            logger.error("Error creating crypto escrow: %s", e)
            payment.status = "failed"
            payment.updated_at = datetime.now(UTC)
            await run_in_threadpool(self.session.commit)
            return None
