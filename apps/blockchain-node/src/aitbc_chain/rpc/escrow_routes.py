"""
Escrow RPC endpoints for the blockchain node.
Provides create/release/refund/get endpoints backed by EscrowManager and Escrow DB model.
"""

from __future__ import annotations
from aitbc.constants import BLOCKCHAIN_RPC_URL

import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from aitbc.network import SharedHttpClient
from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils import ait_to_units, units_to_ait
from eth_utils import keccak

from ..contracts.escrow import EscrowState, backfill_settlement_legs, get_escrow_manager
from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Escrow, Stake

from .utils import _unsigned_tx_fields

_raw_rpc_url = os.getenv("HUB_RPC_URL", BLOCKCHAIN_RPC_URL).rstrip("/")
_HUB_RPC_URL = _raw_rpc_url if _raw_rpc_url.endswith("/rpc") else f"{_raw_rpc_url}/rpc"
_CHAIN_ID = os.getenv("CHAIN_ID", os.getenv("SUPPORTED_CHAINS", "ait-hub.aitbc.bubuit.net"))
_NODE_WALLET = os.getenv("NODE_WALLET_ADDRESS", os.getenv("GENESIS_WALLET_ADDRESS", ""))
_logger = get_logger(__name__)


def _settled_leg_ait(stored_units: int | None, settled_at: Any, locked_units: int) -> str:
    """Return one settled leg of an escrow as AIT.

    ``released_amount``/``refunded_amount`` are NULL on rows written before metered
    settlement and on rows rebuilt by a node that did not serve the release. Both
    are healed from the chain by ``backfill_settlement_legs`` on the way in, so
    this is the last resort for an escrow whose settlement txns this node has not
    synced. It reports the whole lock, which is the right order of magnitude but
    overstates a release by the platform fee the provider never received.
    """
    if stored_units is not None:
        return str(units_to_ait(stored_units))
    return str(units_to_ait(locked_units)) if settled_at else "0"


def get_node_wallet_address() -> str:
    """Return the node wallet that custodies escrow locks.

    This is the address ``_build_lock_tx`` requires as the ESCROW_LOCK ``to``.
    It is deliberately not the consensus ``proposer_id``: the proposer signs
    blocks and is per-node, while the node wallet holds escrow and is shared
    across the nodes that settle for a chain. ``/health`` advertises it so
    clients do not have to guess which of the two to lock against.
    """
    return _NODE_WALLET


_RPC_API_KEY = os.getenv("BLOCKCHAIN_RPC_API_KEY", "")
if not _RPC_API_KEY:
    _logger.warning(
        "BLOCKCHAIN_RPC_API_KEY is not set; escrow RPC endpoints will reject all requests until both services are configured with the same key"
    )

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_rpc_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """Require a valid X-API-Key header for all escrow RPC routes."""
    if not _RPC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Escrow RPC is not configured for authentication",
        )
    if api_key != _RPC_API_KEY:
        _logger.warning("Rejected escrow RPC request: missing or invalid X-API-Key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: missing or invalid API key",
        )
    return api_key


router = APIRouter(tags=["escrow"], dependencies=[Depends(verify_rpc_api_key)])


async def _resolve_chain_account(address: str) -> str | None:
    """Return the canonical 0x form of ``address`` if it is valid.

    v0.25.5: do not require the account to exist.  The block state transition
    creates recipient accounts on first credit, so a provider can be paid even
    if it has never transacted before.
    """
    try:
        return _to_canonical(address)
    except Exception:  # nosec B110 - intentional silent failure
        pass
    return None


async def _get_account_nonce(address: str) -> int:
    """Fetch current nonce for an account from the chain."""
    try:
        r = await SharedHttpClient.get(f"{_HUB_RPC_URL}/accounts/{address}")
        if r.status_code == 200:
            return int(r.json().get("nonce", 0))
    except Exception:
        pass
    return 0


_GENESIS_WALLET_PRIVATE_KEY = os.getenv("GENESIS_WALLET_PRIVATE_KEY", "")

# v0.7.3: ESCROW_RELEASE may be signed by a dedicated non-genesis key.
_ESCROW_RELEASE_PRIVATE_KEY = os.getenv("ESCROW_RELEASE_PRIVATE_KEY", "")
_ESCROW_RELEASE_ADDRESS = os.getenv("ESCROW_RELEASE_ADDRESS", "")


def _compute_tx_signing_hash(tx: dict[str, Any]) -> str:
    """Return the keccak hash the RPC verifies for a transaction signature."""
    canonical = json.dumps(_unsigned_tx_fields(tx), sort_keys=True, separators=(",", ":")).encode()
    return "0x" + keccak(canonical).hex()


def _to_canonical(address: str) -> str:
    """Return the canonical EIP-55 0x form of an address, falling back to input."""
    evm = canonical_address(address)
    if evm.startswith("0x"):
        return evm
    return str(address)


def _get_settlement_key() -> str:
    """Return the configured non-genesis escrow release key, falling back to genesis."""
    if _ESCROW_RELEASE_PRIVATE_KEY:
        return _ESCROW_RELEASE_PRIVATE_KEY
    if _GENESIS_WALLET_PRIVATE_KEY:
        _logger.warning(
            "ESCROW_RELEASE: ESCROW_RELEASE_PRIVATE_KEY is not set; signing payouts with the "
            "genesis key. Configure a dedicated settlement key to decouple settlement from genesis."
        )
    return _GENESIS_WALLET_PRIVATE_KEY


def _get_settlement_address() -> str | None:
    """Return the canonical settlement address for ESCROW_RELEASE signing.

    The address must be the one the signing key actually controls: the RPC
    verifies the signature against the transaction ``from`` field, so a
    key/address mismatch produces a 403 and the provider is never paid. When
    ``ESCROW_RELEASE_ADDRESS`` is set it is checked against the address derived
    from the signing key and a mismatch is refused rather than submitted.
    """
    key = _get_settlement_key()
    if not key:
        return None
    try:
        derived = canonical_address(derive_ethereum_address(key))
    except Exception as e:
        _logger.error("ESCROW_RELEASE: failed to derive settlement address: %s", e)
        return None
    if not _ESCROW_RELEASE_ADDRESS:
        return derived
    configured = canonical_address(_ESCROW_RELEASE_ADDRESS)
    if configured != derived:
        _logger.error(
            "ESCROW_RELEASE: settlement key/address mismatch - ESCROW_RELEASE_ADDRESS is %s but the "
            "configured signing key controls %s. Refusing to submit a transaction the RPC would "
            "reject; fix ESCROW_RELEASE_PRIVATE_KEY / ESCROW_RELEASE_ADDRESS in the node environment.",
            configured,
            derived,
        )
        return None
    return configured


async def _auto_stake(provider: str, amount: int, chain_id: str, job_id: str | None = None) -> str | None:
    """Stake a portion of released escrow for the provider without requiring a signature.

    This is a protocol-level reinvestment triggered from the escrow release path.
    The provider's on-chain account is expected to have just been credited by the
    ESCROW_RELEASE transaction. If job_id is supplied the address is also checked
    against the escrow's recorded provider so a caller cannot route reinvestment to
    an unrelated stake.
    """
    if not provider or amount <= 0:
        return None
    try:
        with session_scope() as session:
            canonical = canonical_address(provider)
            address = canonical if canonical else provider.lower().strip()
            if job_id:
                escrow = session.get(Escrow, job_id)
                if escrow:
                    expected = canonical_address(escrow.provider) or escrow.provider.lower().strip()
                    if address != expected:
                        _logger.warning(
                            "AUTO_STAKE: refusing to stake for %s; it is not the recorded provider %s for job %s",
                            address,
                            expected,
                            job_id,
                        )
                        return None
            account = session.get(Account, (chain_id, address))
            if not account:
                _logger.warning("AUTO_STAKE: no account for %s, creating with zero balance", address)
                account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
                session.add(account)
            if account.balance < amount:
                _logger.warning("AUTO_STAKE: insufficient balance for %s: %s < %s", address, account.balance, amount)
                return None
            account.balance -= amount
            session.add(account)
            locked_until = datetime.now(UTC) + timedelta(days=30)
            stake = Stake(
                chain_id=chain_id,
                address=address,
                amount=amount,
                locked_until=locked_until,
                status="active",
            )
            session.add(stake)
            session.commit()
            session.refresh(stake)
            _logger.info("AUTO_STAKE: %s staked %s, stake_id=%s", address, amount, stake.id)
            # Stake.id is an int; every consumer (the release response, the
            # coordinator's ReceiptView.reinvest_stake_id) declares it a string.
            return str(stake.id)
    except Exception as e:
        _logger.error("AUTO_STAKE failed: %s", e)
    return None


# Safety bound on an already job_id-filtered result set; a job should match at most one
# release. This is no longer a history scan: the RPC filters by payload job_id in SQL.
_RELEASE_LOOKUP_LIMIT = int(os.getenv("ESCROW_RELEASE_LOOKUP_LIMIT", "10"))


def _fee_for(amount: int) -> int:
    """Default network fee for an escrow transaction.

    v0.25.6: use a 1% fee with a dust floor rather than the flat
    DEFAULT_TX_FEE_UNITS. For small escrow amounts (e.g. 0.01 AIT)
    the flat fee was equal to the value, which burned the entire
    payment if the lock was applied.
    """
    return max(36, amount // 100)


def _build_lock_tx(
    job_id: str,
    buyer: str,
    provider: str,
    amount_dec: Decimal,
    nonce: int,
    fee: int | None = None,
) -> tuple[dict[str, Any], int]:
    """Build the canonical ESCROW_LOCK transaction dict and return it with the compute-unit amount."""
    amount_units = ait_to_units(amount_dec)
    if amount_units <= 0:
        raise ValueError("escrow amount must be positive")
    if not _NODE_WALLET:
        raise ValueError("NODE_WALLET_ADDRESS / GENESIS_WALLET_ADDRESS not configured")
    if _to_canonical(buyer) == _to_canonical(_NODE_WALLET):
        raise ValueError("escrow buyer cannot be the node wallet")
    if _to_canonical(provider) == _to_canonical(_NODE_WALLET):
        raise ValueError("escrow provider cannot be the node wallet")
    if fee is None:
        fee = _fee_for(amount_units)
    tx: dict[str, Any] = {
        "from": _to_canonical(buyer),
        "to": _to_canonical(_NODE_WALLET),
        "amount": amount_units,
        "fee": fee,
        "nonce": nonce,
        "type": "ESCROW_LOCK",
        "chain_id": _CHAIN_ID,
        "payload": {
            "action": "escrow_lock",
            "job_id": job_id,
            "provider": _to_canonical(provider),
        },
    }
    return tx, amount_units


async def _submit_lock_tx(signed_lock_tx: dict[str, Any]) -> str:
    """Submit a signed ESCROW_LOCK transaction and return its hash."""
    tx = dict(signed_lock_tx)
    if "signature" not in tx and "sig" in tx:
        tx["signature"] = tx.pop("sig")
    resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/marketplace", json=tx, timeout=10.0)
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=400, detail=f"ESCROW_LOCK transaction submission failed: {resp.status_code} {resp.text[:200]}"
        )
    result = resp.json()
    tx_hash = result.get("transaction_hash")
    if not tx_hash:
        raise HTTPException(status_code=400, detail="ESCROW_LOCK transaction accepted but no transaction_hash returned")
    _logger.info(
        "ESCROW_LOCK TX submitted: hash=%s from=%s to=%s amount=%s", tx_hash, tx.get("from"), tx.get("to"), tx.get("amount")
    )
    return str(tx_hash)


async def _find_existing_release(job_id: str) -> str | None:
    """Return the hash of an ESCROW_RELEASE already on-chain for ``job_id``, if any.

    A retry must never pay twice. Once a first attempt is mined the nonce check rejects
    a replay, which looks like a failure even though the provider was paid -- so a
    reconciler that trusted the failure alone would retry forever. This lookup tells the
    two apart, and lets a retry return the transaction that already settled.

    The query filters on payload job_id server-side. An unfiltered scan was not merely
    slow: /transactions returns rows oldest-first and truncates to ``limit``, so a bounded
    scan silently missed recent settlements -- exactly the ones a retry asks about.
    """
    try:
        r = await SharedHttpClient.get(
            f"{_HUB_RPC_URL}/transactions?transaction_type=ESCROW_RELEASE&job_id={job_id}&limit={_RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            # Re-check the payload: an older node without the job_id filter would
            # otherwise return unrelated releases and settle the wrong job.
            if (tx.get("payload") or {}).get("job_id") == job_id:
                settled_hash = tx.get("tx_hash")
                return str(settled_hash) if settled_hash else None
    except Exception as e:
        _logger.warning("ESCROW_RELEASE: settled-release lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _find_existing_refund(job_id: str) -> str | None:
    """Return the hash of an ESCROW_REFUND already on-chain for ``job_id``, if any.

    Refund retries must be idempotent in the same way as releases: once a refund lands,
    a later attempt must return the settled transaction rather than build a new one.
    """
    try:
        r = await SharedHttpClient.get(
            f"{_HUB_RPC_URL}/transactions?transaction_type=ESCROW_REFUND&job_id={job_id}&limit={_RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                settled_hash = tx.get("tx_hash")
                return str(settled_hash) if settled_hash else None
    except Exception as e:
        _logger.warning("ESCROW_REFUND: settled-refund lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _submit_payment_tx(buyer: str, provider: str, amount: Decimal, job_id: str, contract_id: str) -> str | None:
    """Submit an ESCROW_RELEASE transaction to the blockchain so payment is on-chain."""
    if amount <= 0:
        return None
    # The chain denominates value in whole compute-units.  Any positive
    # release that rounds down to zero units would otherwise leave the provider
    # unpaid, so round up to the smallest transferable unit (1 compute-unit).
    amount_int = max(ait_to_units(amount), 1)
    try:
        # Never pay a job twice: if it already settled, hand back that transaction.
        existing_release = await _find_existing_release(job_id)
        if existing_release:
            _logger.info(
                "ESCROW_RELEASE already settled for job_id=%s (%s); not resubmitting",
                job_id,
                existing_release,
            )
            return existing_release

        settlement_key = _get_settlement_key()
        if not settlement_key:
            _logger.warning("ESCROW_RELEASE TX skipped: no settlement private key configured")
            return None

        settlement_address = _get_settlement_address()
        if not settlement_address:
            _logger.warning("ESCROW_RELEASE TX skipped: could not resolve settlement address")
            return None

        sender = settlement_address

        # v0.25.5: do not call POST /register-account.  The block proposer and
        # state transition now auto-create the recipient account on first credit,
        # so provider releases are deterministic and do not require direct RPC
        # writes outside consensus.

        # Re-resolve after creation; use canonical 0x form for the state layer.
        # Never fall back to the node wallet: a missing or unresolvable provider
        # means the release has no valid payee, and paying the node wallet would
        # be a custody bug.
        recipient = await _resolve_chain_account(provider)
        if not recipient:
            _logger.error("ESCROW_RELEASE TX skipped: could not resolve recipient (provider=%s)", provider)
            return None

        nonce = await _get_account_nonce(sender)
        tx = {
            "from": sender,
            "to": recipient,
            "amount": amount_int,
            "fee": max(36, amount_int // 100),
            "nonce": nonce,
            "type": "ESCROW_RELEASE",
            "chain_id": _CHAIN_ID,
            "payload": {
                "action": "escrow_release",
                "job_id": job_id,
                "contract_id": contract_id,
                "buyer_escrow_addr": buyer,
                "provider_escrow_addr": provider,
            },
        }
        # The payload carries no wall-clock timestamp on purpose: an identical retry
        # must hash identically so the mempool deduplicates it (mempool.add returns the
        # existing hash for a duplicate). Two concurrent release attempts would otherwise
        # build two different transactions sharing one nonce, and admission validates the
        # nonce against the account -- which has not advanced while the first is pending --
        # so both would be admitted and the provider paid twice. Settlement time is
        # recoverable from the including block; the local escrow row keeps released_at.
        # Sign with the configured non-genesis settlement key (or genesis as fallback).
        signing_hash = _compute_tx_signing_hash(tx)
        tx["signature"] = sign_transaction_hash(signing_hash, settlement_key)

        resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/marketplace", json=tx, timeout=5.0)
        if resp.status_code in (200, 201):
            result = resp.json()
            raw_tx_hash = result.get("transaction_hash")
            actual_tx_hash: str | None = str(raw_tx_hash) if raw_tx_hash else None
            _logger.info(
                "ESCROW_RELEASE TX submitted: hash=%s amount=%s from=%s to=%s", actual_tx_hash, amount_int, sender, recipient
            )
            return actual_tx_hash
        else:
            _logger.error(
                "ESCROW_RELEASE TX rejected %s for job_id=%s (provider %s was NOT paid on-chain): %s",
                resp.status_code,
                job_id,
                provider,
                resp.text[:200],
            )
    except Exception as e:
        _logger.error(
            "ESCROW_RELEASE TX submission failed for job_id=%s (provider %s was NOT paid on-chain): %s",
            job_id,
            provider,
            e,
        )
    return None


async def _submit_refund_tx(buyer: str, provider: str, amount: Decimal, job_id: str, contract_id: str) -> str | None:
    """Submit an ESCROW_REFUND transaction to the blockchain so a refund is on-chain."""
    if amount <= 0:
        return None
    # The chain denominates value in whole compute-units. Round up to the
    # smallest transferable unit so a small refund is not lost.
    amount_int = max(ait_to_units(amount), 1)
    try:
        existing_refund = await _find_existing_refund(job_id)
        if existing_refund:
            _logger.info(
                "ESCROW_REFUND already settled for job_id=%s (%s); not resubmitting",
                job_id,
                existing_refund,
            )
            return existing_refund

        settlement_key = _get_settlement_key()
        if not settlement_key:
            _logger.warning("ESCROW_REFUND TX skipped: no settlement private key configured")
            return None

        settlement_address = _get_settlement_address()
        if not settlement_address:
            _logger.warning("ESCROW_REFUND TX skipped: could not resolve settlement address")
            return None

        sender = settlement_address

        # v0.25.5: do not call POST /register-account.  Buyer and provider
        # accounts are created deterministically when the refund transaction is
        # mined.

        # Refunding the node wallet is a custody bug: it would pay the operator
        # instead of the buyer. Refuse and let the caller handle it.
        if _to_canonical(buyer) == _to_canonical(_NODE_WALLET):
            _logger.error("ESCROW_REFUND TX skipped: refund buyer is the node wallet (buyer=%s)", buyer)
            return None

        # Re-resolve after creation; use canonical 0x form for the state layer.
        # Never fall back to the node wallet; a missing buyer account is a bug.
        recipient = await _resolve_chain_account(buyer)
        if not recipient:
            _logger.error("ESCROW_REFUND TX skipped: buyer account does not exist (buyer=%s)", buyer)
            return None

        nonce = await _get_account_nonce(sender)
        tx = {
            "from": sender,
            "to": recipient,
            "amount": amount_int,
            "fee": max(36, amount_int // 100),
            "nonce": nonce,
            "type": "ESCROW_REFUND",
            "chain_id": _CHAIN_ID,
            "payload": {
                "action": "escrow_refund",
                "job_id": job_id,
                "contract_id": contract_id,
                "buyer_escrow_addr": buyer,
                "provider_escrow_addr": provider,
            },
        }
        # Identical retry must hash identically; no wall-clock timestamp in the payload.
        signing_hash = _compute_tx_signing_hash(tx)
        tx["signature"] = sign_transaction_hash(signing_hash, settlement_key)

        resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/marketplace", json=tx, timeout=5.0)
        if resp.status_code in (200, 201):
            result = resp.json()
            raw_tx_hash = result.get("transaction_hash")
            actual_tx_hash: str | None = str(raw_tx_hash) if raw_tx_hash else None
            _logger.info(
                "ESCROW_REFUND TX submitted: hash=%s amount=%s from=%s to=%s",
                actual_tx_hash,
                amount_int,
                sender,
                recipient,
            )
            return actual_tx_hash
        _logger.error(
            "ESCROW_REFUND TX rejected %s for job_id=%s (buyer %s was NOT refunded on-chain): %s",
            resp.status_code,
            job_id,
            buyer,
            resp.text[:200],
        )
    except Exception as e:
        _logger.error(
            "ESCROW_REFUND TX submission failed for job_id=%s (buyer %s was NOT refunded on-chain): %s",
            job_id,
            buyer,
            e,
        )
        raise
    return None


@router.post("/escrow/create", summary="Create escrow for a job")
async def create_escrow(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new escrow contract after the buyer has signed an ESCROW_LOCK transaction.

    The request must include either a fully signed `lock_tx` dict or the
    `lock_signature` plus the lock transaction fields (nonce/fee).  The lock
    transaction must transfer the escrow amount from the buyer to the node
    wallet and include the job_id and provider in the payload.
    """
    job_id = body.get("job_id")
    buyer = body.get("buyer")
    provider = body.get("provider")
    amount = body.get("amount")
    if not all([job_id, buyer, provider, amount is not None]):
        raise HTTPException(status_code=400, detail="job_id, buyer, provider, and amount are required")
    try:
        amount_dec = Decimal(str(amount))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid amount: {amount}") from None
    if not isinstance(job_id, str) or not isinstance(buyer, str) or not isinstance(provider, str):
        raise HTTPException(status_code=400, detail="Invalid types for job_id, buyer, or provider") from None
    if amount_dec <= 0:
        raise HTTPException(status_code=400, detail="escrow amount must be positive") from None
    if _to_canonical(buyer) == _to_canonical(_NODE_WALLET):
        raise HTTPException(status_code=400, detail="escrow buyer cannot be the node wallet") from None

    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    # Accept a pre-built signed lock tx or build one from the provided signature.
    signed_lock_tx = body.get("lock_tx")
    lock_signature = body.get("lock_signature")

    if signed_lock_tx:
        if not isinstance(signed_lock_tx, dict):
            raise HTTPException(status_code=400, detail="lock_tx must be an object") from None
        if signed_lock_tx.get("type") != "ESCROW_LOCK":
            raise HTTPException(status_code=400, detail="lock_tx type must be ESCROW_LOCK") from None
        tx_to_submit = signed_lock_tx
    elif lock_signature:
        nonce = body.get("lock_nonce")
        if nonce is None:
            nonce = await _get_account_nonce(_to_canonical(buyer))
        try:
            nonce = int(nonce)
        except Exception:
            raise HTTPException(status_code=400, detail="lock_nonce must be an integer") from None
        fee = body.get("lock_fee")
        if fee is not None:
            try:
                fee = int(fee)
            except Exception:
                raise HTTPException(status_code=400, detail="lock_fee must be an integer") from None
        try:
            tx_to_submit, _ = _build_lock_tx(job_id, buyer, provider, amount_dec, nonce, fee)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        tx_to_submit["signature"] = lock_signature
    else:
        raise HTTPException(status_code=400, detail="escrow lock is required: provide lock_tx or lock_signature") from None

    # Verify the lock tx moves the expected amount to the node wallet.
    try:
        expected_tx, _ = _build_lock_tx(job_id, buyer, provider, amount_dec, tx_to_submit.get("nonce", 0))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    if tx_to_submit.get("from") != expected_tx["from"]:
        raise HTTPException(status_code=400, detail="lock_tx from must be the buyer") from None
    if _to_canonical(tx_to_submit.get("to", "")) != _to_canonical(expected_tx["to"]):
        raise HTTPException(status_code=400, detail="lock_tx to must be the node wallet") from None
    amount_units = ait_to_units(amount_dec)
    if int(tx_to_submit.get("amount", 0)) != amount_units:
        raise HTTPException(status_code=400, detail=f"lock_tx amount must be {amount_units} compute-units") from None
    payload = tx_to_submit.get("payload") or {}
    if payload.get("job_id") != job_id:
        raise HTTPException(status_code=400, detail="lock_tx payload job_id mismatch") from None
    if _to_canonical(payload.get("provider", "")) != _to_canonical(provider):
        raise HTTPException(status_code=400, detail="lock_tx payload provider mismatch") from None

    # v0.25.5: do not call POST /register-account to bootstrap the buyer.  The
    # buyer must already have an on-chain account (faucet or previous transfer)
    # before the lock transaction can be admitted.

    success, message, contract_id = await mgr.create_contract(
        job_id=job_id, client_address=buyer, agent_address=provider, amount=amount_dec
    )
    if not success:
        raise HTTPException(status_code=400, detail=message) from None

    lock_tx_hash = await _submit_lock_tx(tx_to_submit)

    # Fund the in-memory contract now that the lock has been submitted.
    if contract_id is None:
        raise HTTPException(status_code=500, detail="escrow contract_id missing after create")
    await mgr.fund_contract(contract_id, lock_tx_hash)

    try:
        amount_units = ait_to_units(amount_dec)
        with session_scope() as session:
            existing = session.get(Escrow, job_id)
            if existing:
                existing.status = "locked"
                existing.lock_tx_hash = lock_tx_hash
                existing.buyer = _to_canonical(buyer)
                existing.provider = _to_canonical(provider)
                existing.amount = amount_units
            else:
                escrow_record = Escrow(
                    job_id=job_id,
                    chain_id=_CHAIN_ID,
                    buyer=_to_canonical(buyer),
                    provider=_to_canonical(provider),
                    amount=amount_units,
                    status="locked",
                    lock_tx_hash=lock_tx_hash,
                )
                session.add(escrow_record)
            session.commit()
    except Exception as e:
        _logger.warning("Failed to persist escrow to DB after lock: %s", e)

    _logger.info(
        "Escrow created and locked: contract_id=%s job_id=%s amount=%s tx=%s", contract_id, job_id, amount, lock_tx_hash
    )
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "buyer": buyer,
        "provider": provider,
        "amount": str(amount_dec),
        "lock_tx_hash": lock_tx_hash,
        "message": message,
    }


@router.post("/escrow/{job_id}/release", summary="Release escrow to provider")
async def release_escrow(job_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Release locked funds to the provider after job completion.
    Accepts optional job_tx_hash as proof of work reference."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    # Settlement must be possible before any escrow state is mutated. A node whose
    # settlement key and address disagree cannot pay the provider, and releasing
    # first would leave the escrow marked paid with nothing on-chain.
    if not _get_settlement_key() or not _get_settlement_address():
        _logger.error(
            "ESCROW_RELEASE: refusing to release job_id=%s - settlement key/address is missing or mismatched",
            job_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Settlement key/address is not configured correctly; escrow was not released",
        )

    job_tx_hash = request.get("job_tx_hash")

    # Metered services lock an upper bound and bill what the job actually used, so
    # honour the requested amount instead of always paying out the whole lock. The
    # unbilled remainder is returned to the buyer below; without that it would sit in
    # the node wallet with nothing left to claim it. Omitting the amount bills the
    # whole escrow, which is what a fixed-price job wants.
    requested_amount: Decimal | None = None
    raw_amount = request.get("amount")
    if raw_amount is not None:
        try:
            requested_amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=400, detail="amount must be a decimal number") from None
        if requested_amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be positive") from None

    # Reconciliation/duplicate release handling: if the row is already released,
    # return the stored result without resubmitting.
    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            if record is not None:
                # Heal before the guards read the row: a release whose change leg
                # was mined last reads back as a refund until it is reconciled,
                # and would be rejected here as already refunded.
                backfill_settlement_legs(session, record)
            if record and record.refunded_at is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Escrow for job_id={job_id} has already been refunded",
                )
            if record and record.released_at is not None:
                # The DB may not have stored the release tx hash (legacy rows), so
                # look it up on-chain before returning a stale/empty job_tx_hash.
                existing_release = await _find_existing_release(job_id)
                if existing_release and not record.release_tx_hash:
                    record.release_tx_hash = existing_release
                    session.add(record)
                    session.commit()
                release_tx_hash = record.release_tx_hash or existing_release or record.job_tx_hash or ""
                return {
                    "success": True,
                    "contract_id": getattr(record, "contract_id", None) or "",
                    "job_id": job_id,
                    "message": "Escrow already released",
                    "released_amount": _settled_leg_ait(record.released_amount, record.released_at, record.amount),
                    "refunded_amount": _settled_leg_ait(record.refunded_amount, None, record.amount),
                    "refund_tx_hash": record.refund_tx_hash,
                    "tx_hash": release_tx_hash,
                    "released_at": record.released_at.isoformat(),
                }
            if record is not None and record.status not in (None, "locked"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Escrow for job_id={job_id} is not locked (status={record.status})",
                )
    except HTTPException:
        raise
    except Exception as e:
        _logger.warning("Failed to check escrow release state: %s", e)

    contract_id = await _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")
    contract = mgr.escrow_contracts.get(contract_id)
    if contract:
        for ms in contract.milestones:
            ms["completed"] = True
            ms["verified"] = True
        from ..contracts.escrow import EscrowState

        contract.state = EscrowState.JOB_COMPLETED
    # Hold the per-contract lock across release and settlement so the rollback
    # snapshot cannot interleave with a concurrent release of this contract.
    async with mgr.release_lock(contract_id):
        release_snapshot = mgr.snapshot_release_state(contract_id)
        ok, message = await mgr.release_payment(contract_id, requested_amount)
        if not ok:
            raise HTTPException(status_code=400, detail=message)
        released_amount = contract.released_amount if contract else Decimal(0)
        buyer_addr = contract.client_address if contract else ""
        provider_addr = contract.agent_address if contract else ""
        # What the buyer locked but the job did not consume. release_payment clamps an
        # over-estimate to the lock, so this is never negative.
        locked_total = sum(Decimal(str(ms["amount"])) for ms in contract.milestones) if contract else Decimal(0)
        billed_gross = locked_total if requested_amount is None else min(requested_amount, locked_total)
        unbilled_amount = locked_total - billed_gross
        # Reinvestment must be paid to the escrow's recorded provider; the caller must
        # not be able to name an arbitrary stake address (CHOKE-POINT).
        reinvest_address = provider_addr
        auto_reinvest_pct = request.get("auto_reinvest_pct")

        # Settle on-chain first; only a confirmed transaction counts as a release.
        tx_hash = await _submit_payment_tx(buyer_addr, provider_addr, released_amount, job_id, contract_id)
        if not tx_hash:
            mgr.restore_after_failed_settlement(contract_id, release_snapshot)
            _logger.error(
                "Escrow release NOT settled on-chain: contract_id=%s job_id=%s provider=%s amount=%s. "
                "The release was rolled back so it can be retried.",
                contract_id,
                job_id,
                provider_addr,
                released_amount,
            )
            return {
                "success": False,
                "contract_id": contract_id,
                "job_id": job_id,
                "message": "Escrow release could not be settled on-chain; the provider was not paid",
                "released_amount": str(released_amount),
                "refunded_amount": "0",
                "refund_tx_hash": None,
                "tx_hash": None,
                "settlement_status": "unsettled",
                "released_at": None,
                "reinvest_amount": "0",
                "reinvest_stake_id": None,
            }

        # Return the buyer's change. The provider is already paid, so a failure here
        # leaves the remainder with the node wallet rather than unwinding the payout;
        # it is logged loudly so it can be swept, and the release itself still stands.
        refund_tx_hash: str | None = None
        refunded_amount = Decimal(0)
        if unbilled_amount > 0:
            refund_tx_hash = await _submit_refund_tx(buyer_addr, provider_addr, unbilled_amount, job_id, contract_id)
            if refund_tx_hash:
                refunded_amount = unbilled_amount
            else:
                _logger.error(
                    "Escrow change NOT returned on-chain: job_id=%s buyer=%s unbilled=%s. "
                    "The provider was paid; the remainder is still held by the node wallet.",
                    job_id,
                    buyer_addr,
                    unbilled_amount,
                )

        released_at = datetime.now(UTC)
        try:
            with session_scope() as session:
                record = session.get(Escrow, job_id)
                if record:
                    # A reconciliation retry re-releases an escrow that already settled,
                    # and _submit_payment_tx hands back the transaction that settled it.
                    # Keep the original timestamp: it is when the provider was actually
                    # paid. Overwriting it would date the payment to the retry instead.
                    if record.released_at is not None:
                        released_at = record.released_at
                    else:
                        record.released_at = released_at
                    record.status = "released"
                    record.released_amount = ait_to_units(released_amount)
                    if refunded_amount > 0:
                        # refunded_at stays unset: it marks an escrow that was refunded
                        # instead of released, and the release checks above key off it.
                        record.refunded_amount = ait_to_units(refunded_amount)
                        if refund_tx_hash and not record.refund_tx_hash:
                            record.refund_tx_hash = refund_tx_hash
                    if tx_hash and not record.release_tx_hash:
                        record.release_tx_hash = tx_hash
                    if job_tx_hash:
                        record.job_tx_hash = job_tx_hash
                    session.commit()
        except Exception as e:
            _logger.warning("Failed to update released_at/job_tx_hash in DB: %s", e)
        reinvest_stake_id = None
        reinvest_amount = Decimal(0)
        if auto_reinvest_pct and reinvest_address and released_amount > 0:
            try:
                pct = Decimal(str(auto_reinvest_pct))
                if 0 < pct <= 100:
                    reinvest_amount_ait = (released_amount * pct / 100).quantize(Decimal("0.00000001"))
                    if reinvest_amount_ait > 0:
                        reinvest_amount_units = ait_to_units(reinvest_amount_ait)
                        if reinvest_amount_units > 0:
                            reinvest_stake_id = await _auto_stake(reinvest_address, reinvest_amount_units, _CHAIN_ID, job_id)
                            reinvest_amount = reinvest_amount_ait
                        _logger.info(
                            "Escrow reinvestment: job_id=%s stake_id=%s amount=%s pct=%s",
                            job_id,
                            reinvest_stake_id,
                            reinvest_amount,
                            pct,
                        )
            except Exception as e:
                _logger.warning("Failed to auto-reinvest for job %s: %s", job_id, e)
        _logger.info("Escrow released: contract_id=%s job_id=%s tx=%s", contract_id, job_id, tx_hash)
        return {
            "success": True,
            "contract_id": contract_id,
            "job_id": job_id,
            "message": message,
            "released_amount": str(released_amount),
            "refunded_amount": str(refunded_amount),
            "refund_tx_hash": refund_tx_hash,
            "tx_hash": tx_hash,
            "settlement_status": "settled" if tx_hash else "unsettled",
            "released_at": released_at.isoformat(),
            "reinvest_amount": str(reinvest_amount),
            "reinvest_stake_id": reinvest_stake_id,
        }


@router.post("/escrow/{job_id}/refund", summary="Refund escrow to buyer")
async def refund_escrow(job_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refund locked funds back to the buyer."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")
    # Reconciliation/duplicate refund handling: a refund is only final when the
    # same job_id has an ESCROW_REFUND transaction on-chain.
    record_refunded = False
    record_released = False
    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            if record:
                if record.refunded_at is not None:
                    record_refunded = True
                if record.released_at is not None:
                    record_released = True
    except Exception as e:
        _logger.warning("Failed to check escrow refund state: %s", e)
    if record_refunded:
        existing_refund = await _find_existing_refund(job_id)
        refund_tx_hash = existing_refund or (record.refund_tx_hash if record else None)
        if refund_tx_hash:
            return {
                "success": True,
                "contract_id": "",
                "job_id": job_id,
                "message": "Escrow already refunded",
                "refund_tx_hash": refund_tx_hash,
            }
    if record_released:
        raise HTTPException(
            status_code=400,
            detail=f"Escrow for job_id={job_id} has already been released",
        )

    contract_id = await _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")
    contract = mgr.escrow_contracts.get(contract_id)
    if contract and contract.state in {
        EscrowState.JOB_COMPLETED,
        EscrowState.RELEASED,
        EscrowState.REFUNDED,
        EscrowState.EXPIRED,
    }:
        if contract.state == EscrowState.REFUNDED:
            existing_refund = await _find_existing_refund(job_id)
            if existing_refund:
                return {
                    "success": True,
                    "contract_id": contract_id,
                    "job_id": job_id,
                    "message": "Escrow already refunded",
                    "refund_tx_hash": existing_refund,
                }
            # B-residue: the contract was marked refunded but no ESCROW_REFUND landed.
            _logger.warning(
                "Escrow %s for job %s is REFUNDED in memory but not on-chain; resetting for a real refund",
                contract_id,
                job_id,
            )
            contract.refunded_amount = Decimal("0")
            contract.state = EscrowState.FUNDED
            mgr.active_contracts.add(contract_id)
        else:
            raise HTTPException(status_code=400, detail=f"Escrow already in final state: {contract.state.value}")
    reason = (body or {}).get("reason", "buyer_requested")
    # B: a refund is only final once the on-chain ESCROW_REFUND transaction lands.
    # Apply the in-memory state, then settle on-chain, then roll back if settlement fails.
    async with mgr.release_lock(contract_id):
        refund_snapshot = mgr.snapshot_refund_state(contract_id)
        success, message = await mgr.refund_contract(contract_id, reason)
        if not success:
            raise HTTPException(status_code=400, detail=message)
        contract = mgr.escrow_contracts.get(contract_id)
        refund_amount = contract.refunded_amount if contract else Decimal(0)
        tx_hash = await _submit_refund_tx(
            _to_canonical(contract.client_address) if contract else "",
            _to_canonical(contract.agent_address) if contract else "",
            refund_amount,
            job_id,
            contract_id,
        )
        if not tx_hash:
            mgr.restore_after_failed_refund(contract_id, refund_snapshot)
            _logger.error(
                "Escrow refund NOT settled on-chain: contract_id=%s job_id=%s buyer=%s amount=%s. "
                "The refund was rolled back so it can be retried.",
                contract_id,
                job_id,
                contract.client_address if contract else None,
                refund_amount,
            )
            return {
                "success": False,
                "contract_id": contract_id,
                "job_id": job_id,
                "message": "Escrow refund could not be settled on-chain; the buyer was not refunded",
                "refund_tx_hash": None,
            }
        refunded_at = datetime.now(UTC)
        try:
            with session_scope() as session:
                record = session.get(Escrow, job_id)
                if record:
                    record.status = "refunded"
                    record.refunded_at = refunded_at
                    record.refund_tx_hash = tx_hash
                    session.commit()
        except Exception as e:
            _logger.warning("Failed to update refunded_at for job %s: %s", job_id, e)
    _logger.info("Escrow refunded: contract_id=%s job_id=%s tx=%s", contract_id, job_id, tx_hash)
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "message": message,
        "refund_tx_hash": tx_hash,
    }


@router.get("/escrow/{job_id}", summary="Get escrow state")
async def get_escrow(job_id: str) -> dict[str, Any]:
    """Get current escrow state for a job."""
    mgr = get_escrow_manager()
    db_record: Escrow | None = None
    try:
        with session_scope() as session:
            db_record = session.get(Escrow, job_id)
            if db_record is not None:
                # A row rebuilt on a node that did not serve the release knows the
                # escrow settled but not what it moved; take that from the chain.
                backfill_settlement_legs(session, db_record)
    except Exception as e:
        _logger.warning("Failed to query Escrow DB: %s", e)
    derived_state = ""
    if db_record:
        derived_state = "refunded" if db_record.refunded_at else ("released" if db_record.released_at else "")
    if mgr is not None:
        contract_id = await _find_contract_id(mgr, job_id)
        if contract_id:
            contract = mgr.escrow_contracts.get(contract_id)
            if contract:
                # Prefer the DB timestamps over the in-memory contract state; the
                # in-memory state can lag behind a settled on-chain transaction.
                state = derived_state or contract.state.value
                return {
                    "job_id": job_id,
                    "contract_id": contract_id,
                    "state": state,
                    "buyer": contract.client_address,
                    "provider": contract.agent_address,
                    # The row is authoritative for the money: it holds what was locked
                    # on-chain, while ``contract.amount`` is the lock plus the platform
                    # fee that create_contract adds on top and no one ever locked. The
                    # contract also never learns what a partial release returned, since
                    # the change is settled by the route rather than by the manager.
                    "amount": str(units_to_ait(db_record.amount)) if db_record else str(contract.amount),
                    "released_amount": (
                        _settled_leg_ait(db_record.released_amount, db_record.released_at, db_record.amount)
                        if db_record
                        else str(contract.released_amount)
                    ),
                    "refunded_amount": (
                        _settled_leg_ait(db_record.refunded_amount, db_record.refunded_at, db_record.amount)
                        if db_record
                        else str(contract.refunded_amount)
                    ),
                    "created_at": db_record.created_at.isoformat() if db_record else None,
                    "released_at": db_record.released_at.isoformat() if db_record and db_record.released_at else None,
                    "refunded_at": db_record.refunded_at.isoformat() if db_record and db_record.refunded_at else None,
                    "release_tx_hash": db_record.release_tx_hash if db_record else None,
                    "refund_tx_hash": db_record.refund_tx_hash if db_record else None,
                    "status": db_record.status if db_record else None,
                    "lock_tx_hash": db_record.lock_tx_hash if db_record else None,
                }
    if db_record:
        record_amount_ait = str(units_to_ait(db_record.amount))
        state = derived_state or (db_record.status or "funded")
        return {
            "job_id": job_id,
            "contract_id": None,
            "state": state,
            "buyer": db_record.buyer,
            "provider": db_record.provider,
            "amount": record_amount_ait,
            "released_amount": _settled_leg_ait(db_record.released_amount, db_record.released_at, db_record.amount),
            "refunded_amount": _settled_leg_ait(db_record.refunded_amount, db_record.refunded_at, db_record.amount),
            "created_at": db_record.created_at.isoformat(),
            "released_at": db_record.released_at.isoformat() if db_record.released_at else None,
            "refunded_at": db_record.refunded_at.isoformat() if db_record.refunded_at else None,
            "release_tx_hash": db_record.release_tx_hash,
            "refund_tx_hash": db_record.refund_tx_hash,
            "status": db_record.status,
            "lock_tx_hash": db_record.lock_tx_hash,
        }
    raise HTTPException(status_code=404, detail=f"No escrow found for job_id={job_id}") from None


async def _find_contract_id(mgr: Any, job_id: str) -> str | None:
    """Find contract_id by job_id, loading from DB if missing."""
    for cid, contract in mgr.escrow_contracts.items():
        if contract.job_id == job_id:
            return str(cid)
    # Load from DB on demand before giving up.
    try:
        contract = await mgr.get_or_load_contract(job_id)
        if contract:
            return str(contract.contract_id)
    except Exception as e:
        _logger.warning("Failed to load contract for job %s: %s", job_id, e)
    return None
