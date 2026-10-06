"""
Escrow RPC endpoints for the blockchain node.
Provides create/release/refund/get endpoints backed by EscrowManager and Escrow DB model.
"""

from __future__ import annotations
from aitbc.constants import BLOCKCHAIN_RPC_URL

import hmac
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
from aitbc.market.energy_pricing import (
    DEFAULT_MAX_RATE_AGE_SECONDS,
    EnergyPricingError,
    EnergyQuote,
    SettlementRoute,
    evaluate_quote,
)
from aitbc.utils import ait_to_units, units_to_ait, UNITS_PER_AIT
from eth_utils import keccak

from ..config import settings
from ..contracts.escrow import EscrowState, backfill_settlement_legs, get_escrow_manager
from ..database import session_scope
from ..logger import get_logger
from ..metrics import escrow_fee_sweep_total
from ..models import Account, Escrow, Stake
from ..protocol_escrow import queue_protocol_transfer, stake_escrow_address

from .utils import _unsigned_tx_fields

_raw_rpc_url = os.getenv("HUB_RPC_URL", BLOCKCHAIN_RPC_URL).rstrip("/")
_HUB_RPC_URL = _raw_rpc_url if _raw_rpc_url.endswith("/rpc") else f"{_raw_rpc_url}/rpc"
_CHAIN_ID = os.getenv("CHAIN_ID", os.getenv("SUPPORTED_CHAINS", "ait-localnet"))
_NODE_WALLET = os.getenv("NODE_WALLET_ADDRESS", os.getenv("GENESIS_WALLET_ADDRESS", ""))
_logger = get_logger(__name__)


def _energy_operator_address() -> str:
    """Return the operator address that must have signed protected energy quotes.

    Read per call rather than pinned at import so the gate follows a config
    change on restart-free reloads and so tests can set it. Empty means the
    check is skipped. The same variable configures the coordinator's
    ``settings.energy_operator_address``, so setting it turns both gates on
    together. Deployment state today: hub's coordinator env and hub1's rpc
    env carry it; hub's rpc env does not, so this gate stays off on the
    node that actually serves protected creates.
    """
    return os.getenv("ENERGY_OPERATOR_ADDRESS", "").strip()


_FALLBACK_MAX_RATE_AGE_SECONDS = DEFAULT_MAX_RATE_AGE_SECONDS


def _energy_max_rate_age_seconds() -> int:
    """Return the freshness window applied to a protected quote's rate.

    Read per call rather than pinned at import, same pattern as
    ``_energy_operator_address``. The variable name matches the
    coordinator's ``settings.energy_max_rate_age_seconds`` so one operator
    setting aligns the issuance, funding, and node gates. Unset,
    non-integer, or non-positive values fall back to the shared
    ``DEFAULT_MAX_RATE_AGE_SECONDS`` (86400s) — the operator policy the
    coordinator already runs on hub.
    """
    try:
        value = int(os.getenv("ENERGY_MAX_RATE_AGE_SECONDS", ""))
    except ValueError:
        return _FALLBACK_MAX_RATE_AGE_SECONDS
    return value if value > 0 else _FALLBACK_MAX_RATE_AGE_SECONDS


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
    if api_key is None or not hmac.compare_digest(api_key.encode(), _RPC_API_KEY.encode()):
        _logger.warning("Rejected escrow RPC request: missing or invalid X-API-Key")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: missing or invalid API key",
        )
    return api_key


# Peer-node keys accepted on the node-internal subscription routes only. Each
# fleet node holds its own BLOCKCHAIN_RPC_API_KEY, so a follower calling the
# hub's /rpc/subscribe cannot satisfy the hub's local key — the hub lists the
# follower keys it trusts here. Deliberately NOT merged into verify_rpc_api_key:
# a peer key must not unlock governance, chain control or settlement.
_RPC_API_PEER_KEYS = frozenset(k.strip() for k in os.getenv("BLOCKCHAIN_RPC_API_KEY_PEERS", "").split(",") if k.strip())


def verify_rpc_peer_key(api_key: str | None = Security(_api_key_header)) -> str:
    """Accept this node's own RPC key, a configured peer-node key, or an
    issued join key.

    Node-to-hub internal routes (subscription register/heartbeat/lease
    revocation). Distinct from ``verify_rpc_api_key`` so a leaked peer key
    only ever reaches lease state, never the control plane.

    Issued keys come from ``POST /rpc/join`` (see ``peer_keys.py``) and are
    bound to a single node_id — the subscription routes enforce that binding,
    so an issued key can only ever manage its own lease.
    """
    if api_key and (
        hmac.compare_digest(api_key.encode(), _RPC_API_KEY.encode())
        or any(hmac.compare_digest(api_key.encode(), k.encode()) for k in _RPC_API_PEER_KEYS)
    ):
        return api_key
    if api_key:
        from .peer_keys import is_issued_key

        if is_issued_key(api_key):
            return api_key
    _logger.warning("Rejected peer RPC request: missing or invalid X-API-Key")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: missing or invalid API key",
    )


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
                # Do not create the row. The provider account is created by the
                # ESCROW_RELEASE credit during block processing; writing it here
                # would add an account no block header accounts for, and the
                # state root is a full scan of that table.
                _logger.warning("AUTO_STAKE: no account yet for %s; skipping reinvestment", address)
                return None
            if account.balance < amount:
                _logger.warning("AUTO_STAKE: insufficient balance for %s: %s < %s", address, account.balance, amount)
                return None
            locked_until = datetime.now(UTC) + timedelta(days=30)
            # The stake row is not part of the state root; the balance is. The
            # debit therefore rides on a STAKE_LOCK transfer applied at block
            # time rather than being committed here. See ``protocol_escrow``.
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
            queue_protocol_transfer(
                sender=address,
                recipient=stake_escrow_address(),
                amount=amount,
                chain_id=chain_id,
                tx_type="STAKE_LOCK",
                # v4: the same 30-day window locked_until gives the local row —
                # lock_days makes it consensus-visible instead of route-only.
                payload={"stake_id": str(stake.id), "source": "auto_stake", "lock_days": 30},
            )
            _logger.info("AUTO_STAKE: %s staking %s queued, stake_id=%s", address, amount, stake.id)
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
    *,
    energy_quote_id: str | None = None,
    energy_quote_digest: str | None = None,
    settlement_route: str | None = None,
    settlement_asset: str | None = None,
    settlement_unit_scale: int | None = None,
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
    payload: dict[str, Any] = {
        "action": "escrow_lock",
        "job_id": job_id,
        "provider": _to_canonical(provider),
    }
    if energy_quote_id:
        payload["energy_quote_id"] = energy_quote_id
    if energy_quote_digest:
        payload["energy_quote_digest"] = energy_quote_digest
    if settlement_route:
        payload["settlement_route"] = settlement_route
    if settlement_asset:
        payload["settlement_asset"] = settlement_asset
    if settlement_unit_scale is not None:
        payload["settlement_unit_scale"] = settlement_unit_scale
    tx: dict[str, Any] = {
        "from": _to_canonical(buyer),
        "to": _to_canonical(_NODE_WALLET),
        "amount": amount_units,
        "fee": fee,
        "nonce": nonce,
        "type": "ESCROW_LOCK",
        "chain_id": _CHAIN_ID,
        "payload": payload,
    }
    return tx, amount_units


async def _submit_lock_tx(signed_lock_tx: dict[str, Any]) -> str:
    """Submit a signed ESCROW_LOCK transaction and return its hash."""
    tx = dict(signed_lock_tx)
    if "signature" not in tx and "sig" in tx:
        tx["signature"] = tx.pop("sig")
    resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/market", json=tx, timeout=10.0)
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


async def _find_existing_lock_tx(job_id: str) -> dict[str, Any] | None:
    """Return the sealed ESCROW_LOCK transaction row for ``job_id``, if any."""
    try:
        r = await SharedHttpClient.get(
            f"{_HUB_RPC_URL}/transactions?transaction_type=ESCROW_LOCK&job_id={job_id}&limit={_RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            if isinstance(tx, dict) and (tx.get("payload") or {}).get("job_id") == job_id:
                return tx
    except Exception as e:
        _logger.warning("ESCROW_LOCK: settled-lock lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _find_existing_lock(job_id: str) -> str | None:
    """Return the hash of an ESCROW_LOCK already on-chain for ``job_id``, if any.

    The create endpoint must be idempotent like the release/refund paths: a retry
    whose first attempt already mined must see the settled lock instead of
    submitting a second ESCROW_LOCK for the same job.
    """
    lock_tx = await _find_existing_lock_tx(job_id)
    settled_hash = (lock_tx or {}).get("tx_hash")
    return str(settled_hash) if settled_hash else None


async def _refuse_v2_lock(job_id: str) -> None:
    """Refuse route settlement for a lock sealed before the v3 custody height.

    A v2-era lock has no per-escrow custody account at apply time, so a route
    re-drive pays value+fee out of the settlement authority with no apply-time
    dedup — the late-seal double-pay. The demote-only sweeper clears the dead
    marks, and the coordinator retry paths re-drive whatever looks unsettled;
    without this guard the first retry after deploy would replay every v2 row
    on its own. Repair of these rows goes through the operator path only.

    Probe semantics: the sealed-lock gate runs immediately before this, so a
    ``None`` here means the era re-read flaked between the two calls — while
    the hub is unreachable the settlement submit fails anyway, so failing open
    cannot mint a dead record. A lock that *is* returned must carry its
    ``block_height``; anything else is a malformed response and refuses. With
    ``state_transition_v3_height == 0`` (v3 never activated on this chain) no
    block height is below it and the guard is inert.
    """
    lock_tx = await _find_existing_lock_tx(job_id)
    if lock_tx is None:
        _logger.warning(
            "v2-era check could not re-read the lock for job_id=%s after the sealed-lock gate passed; allowing",
            job_id,
        )
        return
    block_height = lock_tx.get("block_height")
    if not isinstance(block_height, int):
        raise HTTPException(
            status_code=409,
            detail=(
                f"escrow lock for job_id={job_id} returned without a readable block_height; "
                "routes do not settle locks of unverifiable era — retry or repair manually"
            ),
        )
    if block_height < settings.state_transition_v3_height:
        raise HTTPException(
            status_code=409,
            detail=(
                f"escrow lock for job_id={job_id} sealed at block {block_height}, below "
                f"state_transition_v3_height={settings.state_transition_v3_height} (v2-era); "
                "routes do not settle these rows — operator repair only"
            ),
        )


async def _ensure_lock_sealed(job_id: str) -> None:
    """Refuse the settlement while the job's ESCROW_LOCK is not sealed in a block.

    Admission does not check escrow state: a release/refund evaluated before its
    lock's block is dropped at production ("No ESCROW_LOCK found", or the v3
    escrow-balance check), while this route would still have marked the row
    settled at RPC acceptance and served the dead hash forever (S-8). The sealed
    ``transaction`` table is the same view production consults, so whatever the
    gate defers would have been dropped anyway. HTTP 425 tells every existing
    caller "not yet, retry": the coordinator leaves the payment escrowed and
    re-attempts on its next sweep; the row stays unmarked either way.
    """
    if not await _find_existing_lock(job_id):
        raise HTTPException(
            status_code=425,
            detail=(
                f"escrow lock for job_id={job_id} is not yet sealed in a block "
                "(absent or still in mempool); retry after the ESCROW_LOCK lands"
            ),
            headers={"Retry-After": "5"},
        )


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

        resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/market", json=tx, timeout=5.0)
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

        resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/market", json=tx, timeout=5.0)
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


# --- v11: ESCROW_FEE_SWEEP — drain a settled job's custody residue -----------
#
# A v3 settlement leaves the withheld platform fee plus rounding dust in the
# per-job custody account. From state_transition_v11_height a distinct
# authority-signed ESCROW_FEE_SWEEP pays that residue to the governed
# escrow_fee_recipient. Cadence (a): one sweep leg right after a job's FINAL
# settlement leg — release plus its change refund — never during a metered
# multi-leg settle. Off unless ESCROW_FEE_SWEEP_ENABLED is set.
#
# The release is authoritative: a sweep failure must never fail or roll back
# the release, so _submit_fee_sweep_tx swallows every error (unlike
# _submit_refund_tx, which re-raises), logs it, and counts it in
# blockchain_escrow_fee_sweep_total{result=...}. A missed attempt retries on
# the next release-route call for the job — the already-released path below
# re-offers it, deduped by _find_existing_fee_sweep.


def _fee_sweep_enabled() -> bool:
    return os.getenv("ESCROW_FEE_SWEEP_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _fee_sweep_recipient() -> str | None:
    """Env-side fee recipient for sweep signing. Consensus re-checks the ``to``
    against the on-chain ``escrow_fee_recipient`` parameter at apply height;
    when they disagree the sweep is refused and stays visible in the metric."""
    raw = os.getenv("ESCROW_FEE_RECIPIENT", "").strip()
    return _to_canonical(raw) if raw else None


async def _find_existing_fee_sweep(job_id: str) -> str | None:
    """Return the hash of an ESCROW_FEE_SWEEP already on-chain for ``job_id``, if any.

    Same dedupe contract as _find_existing_release/_find_existing_refund: a
    sealed sweep makes every later attempt a no-op, which is what lets the
    retry path offer the leg again safely.
    """
    try:
        r = await SharedHttpClient.get(
            f"{_HUB_RPC_URL}/transactions?transaction_type=ESCROW_FEE_SWEEP&job_id={job_id}&limit={_RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            if (tx.get("payload") or {}).get("job_id") == job_id:
                settled_hash = tx.get("tx_hash")
                return str(settled_hash) if settled_hash else None
    except Exception as e:
        _logger.warning("ESCROW_FEE_SWEEP: settled-sweep lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _escrow_custody_balance(job_id: str) -> int | None:
    """On-chain balance of the job's derived custody account, or None when it
    cannot be proven (RPC failure / unknown account) — callers must skip rather
    than guess."""
    from ..state.pure_state_transition import _escrow_address

    try:
        r = await SharedHttpClient.get(f"{_HUB_RPC_URL}/accounts/{_escrow_address(job_id)}")
        if r.status_code == 200:
            return int(r.json().get("balance", 0))
    except Exception as e:
        _logger.warning("ESCROW_FEE_SWEEP: custody balance lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _submit_fee_sweep_tx(job_id: str, contract_id: str, residue_units: int) -> str | None:
    """Submit an ESCROW_FEE_SWEEP draining ``residue_units`` from the job's
    custody account to the fee recipient. Returns the tx hash, an existing
    hash when the job was already swept, or None — never raises, the release
    it follows is authoritative and must not see a sweep error."""
    if residue_units <= 0:
        return None
    try:
        existing = await _find_existing_fee_sweep(job_id)
        if existing:
            _logger.info(
                "ESCROW_FEE_SWEEP already settled for job_id=%s (%s); not resubmitting",
                job_id,
                existing,
            )
            return existing
        recipient = _fee_sweep_recipient()
        if not recipient:
            _logger.warning(
                "ESCROW_FEE_SWEEP skipped for job_id=%s: ESCROW_FEE_RECIPIENT is not configured "
                "(consensus requires the escrow_fee_recipient chain parameter)",
                job_id,
            )
            escrow_fee_sweep_total.labels(result="skipped").inc()
            return None
        settlement_key = _get_settlement_key()
        settlement_address = _get_settlement_address()
        if not settlement_key or not settlement_address:
            _logger.warning("ESCROW_FEE_SWEEP skipped for job_id=%s: settlement key/address not configured", job_id)
            escrow_fee_sweep_total.labels(result="skipped").inc()
            return None

        nonce = await _get_account_nonce(settlement_address)
        tx = {
            "from": settlement_address,
            "to": recipient,
            "amount": residue_units,
            "fee": _fee_for(residue_units),
            "nonce": nonce,
            "type": "ESCROW_FEE_SWEEP",
            "chain_id": _CHAIN_ID,
            "payload": {
                "action": "escrow_fee_sweep",
                "job_id": job_id,
                "contract_id": contract_id,
            },
        }
        # Same rule as release/refund: no wall-clock in the payload, an
        # identical retry at the same nonce must hash identically.
        signing_hash = _compute_tx_signing_hash(tx)
        tx["signature"] = sign_transaction_hash(signing_hash, settlement_key)

        resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/market", json=tx, timeout=5.0)
        if resp.status_code in (200, 201):
            result = resp.json()
            raw_tx_hash = result.get("transaction_hash")
            actual_tx_hash: str | None = str(raw_tx_hash) if raw_tx_hash else None
            _logger.info(
                "ESCROW_FEE_SWEEP TX submitted: hash=%s residue=%s from=%s to=%s job_id=%s",
                actual_tx_hash,
                residue_units,
                settlement_address,
                recipient,
                job_id,
            )
            escrow_fee_sweep_total.labels(result="submitted").inc()
            return actual_tx_hash
        _logger.error(
            "ESCROW_FEE_SWEEP TX rejected %s for job_id=%s residue=%s — release stands, sweep retries "
            "on the next settlement call: %s",
            resp.status_code,
            job_id,
            residue_units,
            resp.text[:200],
        )
        escrow_fee_sweep_total.labels(result="rejected").inc()
    except Exception as e:
        _logger.error(
            "ESCROW_FEE_SWEEP TX submission failed for job_id=%s residue=%s — release stands, sweep "
            "retries on the next settlement call: %s",
            job_id,
            residue_units,
            e,
        )
        escrow_fee_sweep_total.labels(result="error").inc()
    return None


async def _retry_sweep_released_escrow(job_id: str, record: Escrow, session) -> str | None:
    """Re-offer the sweep for an already-released job — the retry surface.

    The residue is derived from *sealed chain legs*, never the row's amount
    columns: a refund the row claims but that never sealed cannot poison the
    sum, and a NULL ``refunded_amount`` column simply means "no sealed
    refund" rather than "ambiguous, skip" (F2). The same fee-only proof the
    periodic pass applies gates the submit (D11): residue beyond the provable
    withheld platform fee is owed buyer change — a released-marked row whose
    release leg is dead while the change refund sealed produces exactly that
    shape, and custody equality alone cannot tell fee from change. Custody
    equality still gates too: a balance above the derived residue means an
    owed leg is still pending, below it means the account was touched; either
    way the job is skipped, never guessed."""
    if not _fee_sweep_enabled():
        return None
    from ..contracts.escrow import DEFAULT_FEE_BPS, recompute_release_proofs, settlement_legs_from_chain

    try:
        legs = settlement_legs_from_chain(session, job_id)
    except Exception as e:
        _logger.warning("ESCROW_FEE_SWEEP retry: sealed-leg lookup failed for job_id=%s: %s", job_id, e)
        legs = None
    if not legs:
        escrow_fee_sweep_total.labels(result="skipped").inc()
        return None
    # Same floor the pass applies (A4d): a settlement leg below the fork
    # height makes the residue a pre-fork census matter — an operator
    # decision, not the retry's. NULL height fails closed: unproven is
    # unreadable, never assumed post-floor.
    min_height = legs.get("min_settlement_height")
    if legs.get("null_settlement_height") or min_height is None or min_height < settings.escrow_fee_sweep_pass_min_height:
        _logger.info(
            "ESCROW_FEE_SWEEP deferred for job_id=%s: settlement leg below floor (min height %s < %s) — "
            "pre-fork residue is an operator decision",
            job_id,
            min_height,
            settings.escrow_fee_sweep_pass_min_height,
        )
        escrow_fee_sweep_total.labels(result="skipped").inc()
        return None
    lock_units = int(legs.get("locked_amount") or 0)
    expected = lock_units - int(legs.get("released_amount") or 0) - int(legs.get("refunded_amount") or 0)
    if expected <= 0:
        return None
    bps = record.energy_fee_basis_points if record.energy_fee_basis_points is not None else DEFAULT_FEE_BPS
    proof = recompute_release_proofs(
        legs.get("release_legs") or [],
        record.billed_legs,
        fee_bps=bps,
        protected=bool(record.protected),
        credit_units=record.energy_provider_credit_units,
        net_floor_units=record.energy_net_floor_units,
        lock_units=lock_units,
    )
    fee_bound = proof[1] if proof else None
    if fee_bound is None or expected > fee_bound:
        _logger.info(
            "ESCROW_FEE_SWEEP deferred for job_id=%s: residue %s exceeds provable fee bound %s — "
            "owed change is not treasury money",
            job_id,
            expected,
            fee_bound,
        )
        escrow_fee_sweep_total.labels(result="skipped").inc()
        return None
    custody = await _escrow_custody_balance(job_id)
    if custody is None or custody != expected:
        if custody is not None:
            _logger.info(
                "ESCROW_FEE_SWEEP deferred for job_id=%s: custody %s != residue %s — an owed leg may still be pending",
                job_id,
                custody,
                expected,
            )
        escrow_fee_sweep_total.labels(result="skipped").inc()
        return None
    return await _submit_fee_sweep_tx(job_id, job_id, expected)


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

    # Idempotency: a retry whose first create already landed an ESCROW_LOCK
    # on-chain must not submit a second lock. Mirrors the
    # _find_existing_release/_find_existing_refund guards on the settlement
    # paths — this was the one submission path without it.
    existing_lock_hash = await _find_existing_lock(job_id)
    if existing_lock_hash:
        with session_scope() as session:
            existing_row = session.get(Escrow, job_id)
        if existing_row and (
            _to_canonical(existing_row.buyer) != _to_canonical(buyer)
            or _to_canonical(existing_row.provider) != _to_canonical(provider)
            or int(existing_row.amount) != ait_to_units(amount_dec)
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"escrow for job {job_id} is already locked on-chain with different parameters (tx {existing_lock_hash})"
                ),
            ) from None
        # ``_find_contract_id`` falls back to loading the contract from the DB
        # row and finally to reconstructing row + contract from the on-chain
        # lock, so a create whose response was lost after the lock landed still
        # heals the local state here instead of returning contract_id=None.
        existing_contract_id = await _find_contract_id(mgr, job_id)
        _logger.info(
            "ESCROW_LOCK already settled for job_id=%s (%s); returning existing escrow",
            job_id,
            existing_lock_hash,
        )
        return {
            "success": True,
            "duplicate": True,
            "contract_id": existing_contract_id,
            "job_id": job_id,
            "buyer": buyer,
            "provider": provider,
            "amount": str(amount_dec),
            "lock_tx_hash": (existing_row.lock_tx_hash if existing_row and existing_row.lock_tx_hash else existing_lock_hash),
            "message": "escrow already locked",
        }

    # No ESCROW_LOCK for this job_id reached the chain, so any contract or
    # Escrow row still carrying the id is residue of a create whose lock
    # submission failed -- or of a restart, since ``load_from_db`` revives every
    # unsettled row. Drop it so the retry below is not rejected as a duplicate
    # ("Invalid contract inputs") with no funds locked to show for it.
    stale_contract_id = next((cid for cid, c in mgr.escrow_contracts.items() if c.job_id == job_id), None)
    if stale_contract_id is not None:
        mgr.escrow_contracts.pop(stale_contract_id, None)
        mgr.active_contracts.discard(stale_contract_id)
        mgr.disputed_contracts.discard(stale_contract_id)
        _logger.info(
            "Dropped stale escrow contract %s for job_id=%s: no ESCROW_LOCK on-chain",
            stale_contract_id,
            job_id,
        )
    try:
        with session_scope() as session:
            stale_row = session.get(Escrow, job_id)
            if stale_row is not None and stale_row.released_at is None and stale_row.refunded_at is None:
                session.delete(stale_row)
                session.commit()
    except Exception as e:
        _logger.warning("Failed to drop stale escrow record for job_id=%s: %s", job_id, e)

    # E1: parse the energy quote up front so the lock_signature reconstruction
    # below can bind the quote id and digest into the payload. The signature
    # check downstream rejects any tx that differs from what the buyer signed,
    # so a field the buyer did not sign can never be smuggled in this way.
    energy_quote_data = body.get("energy_quote") or body.get("energy_quote_snapshot")
    quote: EnergyQuote | None = None
    if energy_quote_data:
        try:
            quote = EnergyQuote.from_dict(energy_quote_data)
        except EnergyPricingError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid energy quote: {exc}") from exc

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
            tx_to_submit, _ = _build_lock_tx(
                job_id,
                buyer,
                provider,
                amount_dec,
                nonce,
                fee,
                energy_quote_id=quote.quote_id if quote else None,
                energy_quote_digest=quote.digest_sha256().hex() if quote else None,
                settlement_route=quote.settlement_route.value if quote else None,
                settlement_asset=quote.settlement_asset if quote else None,
                settlement_unit_scale=quote.settlement_unit_scale if quote else None,
            )
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

    # E1: validate the energy quote for fixed-duration GPU rentals.
    energy_kwargs: dict[str, Any] = {}
    if payload.get("energy_quote_id") or energy_quote_data:
        if quote is None:
            raise HTTPException(
                status_code=400,
                detail="Protected ESCROW_LOCK payload references an energy quote but no quote was supplied",
            ) from None
        if quote.job_id != job_id:
            raise HTTPException(status_code=400, detail="energy quote job_id mismatch") from None
        if quote.provider != provider:
            raise HTTPException(status_code=400, detail="energy quote provider mismatch") from None
        if quote.buyer != buyer:
            raise HTTPException(status_code=400, detail="energy quote buyer mismatch") from None
        if quote.settlement_route != SettlementRoute.NATIVE:
            raise HTTPException(status_code=400, detail="energy quote settlement route is not native") from None
        lock_amount_units = int(tx_to_submit.get("amount", 0))
        if quote.principal_units != lock_amount_units:
            raise HTTPException(
                status_code=400,
                detail=f"energy quote principal {quote.principal_units} does not match lock amount {lock_amount_units}",
            ) from None
        # Bind the quote digest and settlement metadata so a replay or
        # substitution cannot fund a different route/asset/amount against the
        # same quote id. The digest covers the canonical signed payload, so a
        # mismatch here means the quote was altered after signing.
        payload_energy_quote_digest = payload.get("energy_quote_digest")
        if payload_energy_quote_digest and payload_energy_quote_digest != quote.digest_sha256().hex():
            raise HTTPException(
                status_code=400,
                detail="energy quote digest in lock payload does not match supplied quote",
            ) from None
        if payload.get("settlement_route") and payload.get("settlement_route") != quote.settlement_route.value:
            raise HTTPException(
                status_code=400,
                detail="energy quote settlement route in lock payload does not match quote",
            ) from None
        payload_unit_scale = payload.get("settlement_unit_scale")
        if payload_unit_scale is not None and int(payload_unit_scale) != quote.settlement_unit_scale:
            raise HTTPException(
                status_code=400,
                detail="energy quote settlement unit scale in lock payload does not match quote",
            ) from None

        # Verify the operator signature against the configured operator address
        # so a self-attested quote cannot fund an escrow. ``evaluate_quote``
        # below still compares the quote against ``quote.to_profile()`` /
        # ``quote.to_rate()``, which is self-referential and therefore proves
        # nothing on its own; this signature is what makes those embedded terms
        # attributable to the operator. Replacing them with an authoritative
        # oracle read is tracked separately.
        _operator = _energy_operator_address()
        if _operator and not quote.verify_operator_signature(_operator):
            raise HTTPException(
                status_code=422,
                detail="Energy quote operator signature is missing or invalid",
            ) from None

        result = evaluate_quote(
            quote=quote,
            profile=quote.to_profile(),
            rate=quote.to_rate(),
            now=int(datetime.now(UTC).timestamp()),
            max_rate_age_seconds=_energy_max_rate_age_seconds(),
        )
        if not result.approved:
            raise HTTPException(
                status_code=422,
                detail=f"Energy quote refused: {result.refusal_reason} ({result.refusal_code})",
            ) from None
        if result.breakdown is None:
            raise HTTPException(status_code=422, detail="Energy quote did not produce a funding breakdown") from None

        # Use the exact locked units as the authoritative gross amount.
        amount_dec = units_to_ait(quote.principal_units)
        energy_kwargs = {
            "protected": True,
            "energy_quote_snapshot": quote.to_dict(include_signature=False),
            "energy_quote_id": quote.quote_id,
            "energy_quote_digest": quote.digest_sha256().hex(),
            "energy_settlement_route": quote.settlement_route.value,
            "energy_settlement_asset": quote.settlement_asset,
            "energy_settlement_unit_scale": quote.settlement_unit_scale,
            "energy_net_floor_units": quote.net_energy_floor_units,
            "energy_provider_credit_units": result.breakdown.provider_credit_units,
            "energy_fee_basis_points": quote.fee_basis_points,
        }

    # v0.25.5: do not call POST /register-account to bootstrap the buyer.  The
    # buyer must already have an on-chain account (genesis allocation or previous transfer)
    # before the lock transaction can be admitted.

    # The contract is created only after the submit below, so run its input
    # validation up front: rejecting a bad address or a job_id that raced in
    # after the cleanup once the lock is on-chain would leave money moved with
    # no escrow behind it.
    if not mgr._validate_contract_inputs(job_id, buyer, provider, amount_dec):
        raise HTTPException(status_code=400, detail="Invalid contract inputs") from None

    # Broadcast the lock *before* creating any local state. Doing it the other
    # way left an orphan behind whenever the submit failed: the row sat at
    # status="created" and the in-memory contract kept the job_id, so a
    # same-job_id retry died on "Invalid contract inputs" with nothing on-chain.
    # A submit whose response is lost after the tx landed stays safe -- the next
    # create sees the settled lock via ``_find_existing_lock`` above.
    lock_tx_hash = await _submit_lock_tx(tx_to_submit)

    success, message, contract_id = await mgr.create_contract(
        job_id=job_id,
        client_address=buyer,
        agent_address=provider,
        amount=amount_dec,
        **energy_kwargs,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message) from None
    if contract_id is None:
        raise HTTPException(status_code=500, detail="escrow contract_id missing after create")

    amount_units = int(tx_to_submit.get("amount", 0)) if energy_kwargs else ait_to_units(amount_dec)

    # Fund the in-memory contract now that the lock has been submitted.
    await mgr.fund_contract(contract_id, lock_tx_hash)

    # Persist the Escrow DB record only once the lock was accepted. If the
    # process dies between submit and this write the row is missing, but the
    # next create (or release/refund) rebuilds it from the on-chain lock via
    # ``_reconstruct_escrow_from_chain`` — the funds are never orphaned.
    try:
        with session_scope() as session:
            for addr in (buyer, provider):
                ait_addr = _to_canonical(addr)
                account = session.get(Account, (_CHAIN_ID, ait_addr))
                if account is None:
                    session.add(Account(chain_id=_CHAIN_ID, address=ait_addr, balance=0, nonce=0))
            existing = session.get(Escrow, job_id)
            if existing:
                existing.status = "locked"
                existing.lock_tx_hash = lock_tx_hash
                existing.buyer = _to_canonical(buyer)
                existing.provider = _to_canonical(provider)
                existing.amount = amount_units
                if energy_kwargs:
                    existing.protected = True
                    existing.energy_quote_snapshot = energy_kwargs.get("energy_quote_snapshot")
                    existing.energy_quote_id = energy_kwargs.get("energy_quote_id")
                    existing.energy_quote_digest = energy_kwargs.get("energy_quote_digest")
                    existing.energy_settlement_route = energy_kwargs.get("energy_settlement_route")
                    existing.energy_settlement_asset = energy_kwargs.get("energy_settlement_asset")
                    existing.energy_settlement_unit_scale = energy_kwargs.get("energy_settlement_unit_scale")
                    existing.energy_net_floor_units = energy_kwargs.get("energy_net_floor_units")
                    existing.energy_provider_credit_units = energy_kwargs.get("energy_provider_credit_units")
                    existing.energy_fee_basis_points = energy_kwargs.get("energy_fee_basis_points")
            else:
                escrow_record = Escrow(
                    job_id=job_id,
                    chain_id=_CHAIN_ID,
                    buyer=_to_canonical(buyer),
                    provider=_to_canonical(provider),
                    amount=amount_units,
                    status="locked",
                    lock_tx_hash=lock_tx_hash,
                    **(
                        {
                            "protected": True,
                            "energy_quote_snapshot": energy_kwargs.get("energy_quote_snapshot"),
                            "energy_quote_id": energy_kwargs.get("energy_quote_id"),
                            "energy_quote_digest": energy_kwargs.get("energy_quote_digest"),
                            "energy_settlement_route": energy_kwargs.get("energy_settlement_route"),
                            "energy_settlement_asset": energy_kwargs.get("energy_settlement_asset"),
                            "energy_settlement_unit_scale": energy_kwargs.get("energy_settlement_unit_scale"),
                            "energy_net_floor_units": energy_kwargs.get("energy_net_floor_units"),
                            "energy_provider_credit_units": energy_kwargs.get("energy_provider_credit_units"),
                            "energy_fee_basis_points": energy_kwargs.get("energy_fee_basis_points"),
                        }
                        if energy_kwargs
                        else {}
                    ),
                )
                session.add(escrow_record)
            session.commit()
    except Exception as e:
        _logger.error("Failed to persist escrow to DB after lock: %s", e)
        raise HTTPException(status_code=500, detail="Failed to persist escrow") from e

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
    # unbilled remainder is reported as owed change and paid by the settlement
    # sweeper's change pass once the release seals; without that it would sit in
    # the job's custody account with nothing left to claim it. Omitting the
    # amount bills the whole escrow, which is what a fixed-price job wants.
    requested_amount: Decimal | None = None
    raw_amount = request.get("amount")
    if raw_amount is not None:
        try:
            requested_amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=400, detail="amount must be a decimal number") from None
        if requested_amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be positive") from None
        # A7d: quantize to whole compute-units — sub-unit precision cannot be
        # billed on-chain and would wedge billed_legs vs the sealed leg (the
        # real CLI sends e.g. str(Decimal(tokens)/1000*price): 1234 tokens at
        # 0.0073 AIT/1k = 324295.2 units). ROUND_HALF_UP via ait_to_units; the
        # sub-unit dust stays in custody as unbilled change. An amount that
        # quantizes to zero units cannot be billed at all — refuse it rather
        # than sign a 1-unit leg against a recorded billed of 0.
        requested_amount = units_to_ait(ait_to_units(requested_amount))
        if ait_to_units(requested_amount) == 0:
            raise HTTPException(status_code=400, detail="amount is below one billable compute-unit")

    # Reconciliation/duplicate release handling: if the row is already released,
    # return the stored result without resubmitting.
    escrow_record: Escrow | None = None
    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            escrow_record = record
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
                # v11: re-offer the custody-residue sweep for an already-released
                # job — the retry surface for residue a pass or earlier attempt
                # left behind. Deduped on-chain; residue derived from sealed
                # chain legs, provable only.
                await _retry_sweep_released_escrow(job_id, record, session)
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
            # ``settlement_failed`` is a demoted dead mark, not a settled row:
            # it reaches the gate below and re-drives like a locked row (the
            # v2-era guard still applies to its lock).
            if record is not None and record.status not in (None, "locked", "settlement_failed"):
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
    # The lock must be sealed before the release can apply — checked before any
    # contract state is touched, like the settlement-key preamble above.
    await _ensure_lock_sealed(job_id)
    # And it must not be a v2-era lock: re-driving one pays out of the authority
    # with no apply-time dedup. Demoted settlement_failed rows reach this too,
    # so the guard is what keeps a sweeper demote + coordinator retry from
    # replaying the v2 dead-set without an operator go.
    await _refuse_v2_lock(job_id)
    contract = mgr.escrow_contracts.get(contract_id)
    if contract:
        for ms in contract.milestones:
            ms["completed"] = True
            ms["verified"] = True
        from ..contracts.escrow import EscrowState

        contract.state = EscrowState.JOB_COMPLETED
    # Hold the per-contract lock across release and settlement so the rollback
    # snapshot cannot interleave with a concurrent release of this contract.
    # E1: fixed-duration protected rentals do not accept arbitrary metered overrides
    # and must release the full frozen gross amount.
    if escrow_record and escrow_record.protected:
        requested_amount = None
        # §4.3: enforce that the settlement asset and unit scale match the
        # frozen quote. A protected rental was priced in a specific asset at a
        # specific scale; releasing in a different asset or scale would
        # silently change the economic terms.
        if escrow_record.energy_settlement_asset and escrow_record.energy_settlement_asset != "AITBC":
            raise HTTPException(
                status_code=422,
                detail=f"Protected escrow settlement asset {escrow_record.energy_settlement_asset} is not supported for native release",
            )
        if escrow_record.energy_settlement_unit_scale is not None:
            if escrow_record.energy_settlement_unit_scale != UNITS_PER_AIT:
                raise HTTPException(
                    status_code=422,
                    detail=f"Protected escrow settlement unit scale {escrow_record.energy_settlement_unit_scale} does not match native scale {UNITS_PER_AIT}",
                )
        if contract and escrow_record.energy_fee_basis_points is not None:
            contract.fee_rate = Decimal(escrow_record.energy_fee_basis_points) / Decimal(10000)
        if contract and escrow_record.energy_provider_credit_units is not None:
            contract.energy_provider_credit_units = escrow_record.energy_provider_credit_units
            contract.energy_net_floor_units = escrow_record.energy_net_floor_units

    async with mgr.release_lock(contract_id):
        release_snapshot = mgr.snapshot_release_state(contract_id)
        ok, message = await mgr.release_payment(contract_id, requested_amount)
        if not ok:
            raise HTTPException(status_code=400, detail=message)
        released_amount = contract.released_amount if contract else Decimal(0)

        # E1: ensure the provider receives at least the frozen credit, never below
        # the energy floor. Bump the settled amount up to the exact signed target.
        if escrow_record and escrow_record.protected and escrow_record.energy_provider_credit_units is not None:
            target_ait = units_to_ait(escrow_record.energy_provider_credit_units)
            if released_amount < target_ait:
                released_amount = target_ait
                if contract:
                    contract.released_amount = target_ait
            if escrow_record.energy_net_floor_units is not None:
                floor_ait = units_to_ait(escrow_record.energy_net_floor_units)
                if released_amount < floor_ait:
                    mgr.restore_after_failed_settlement(contract_id, release_snapshot)
                    raise HTTPException(
                        status_code=422,
                        detail="Protected escrow release would underpay the energy floor",
                    )
        buyer_addr = contract.client_address if contract else ""
        provider_addr = contract.agent_address if contract else ""
        # What the buyer locked but the job did not consume. release_payment clamps an
        # over-estimate to the lock, so this is never negative.
        # sum()'s no-start-value overload types as "T | Literal[0]" (its empty-iterable
        # fallback is int 0), which mypy then propagates as "Decimal | int" through
        # billed_gross/unbilled_amount into the refund call below. Passing an explicit
        # Decimal start pins the type and makes an empty milestones list (which
        # create_contract never actually produces) return Decimal(0) instead of int 0.
        locked_total = sum((Decimal(str(ms["amount"])) for ms in contract.milestones), Decimal(0)) if contract else Decimal(0)
        billed_gross = locked_total if requested_amount is None else min(requested_amount, locked_total)
        unbilled_amount = locked_total - billed_gross
        # A7d: the sealed leg value is derived on whole compute-units by the
        # same integer formula the settlement passes recompute with — the
        # Decimal AIT path can cross an exact .5 rounding boundary and would
        # leave the row permanently unproven.
        from ..contracts.escrow import DEFAULT_FEE_BPS, expected_release_units

        billed_units = ait_to_units(billed_gross)
        fee_bps = (
            escrow_record.energy_fee_basis_points
            if escrow_record is not None and escrow_record.energy_fee_basis_points is not None
            else DEFAULT_FEE_BPS
        )
        release_units = expected_release_units(
            billed_units,
            fee_bps=fee_bps,
            protected=bool(escrow_record.protected) if escrow_record else False,
            credit_units=escrow_record.energy_provider_credit_units if escrow_record else None,
        )
        if ait_to_units(released_amount) != release_units:
            # Pathological divergence (e.g. an earlier milestone payout left
            # contract.released_amount above billable−fee): sign the
            # provable billed-derived value, not the contract's residue.
            _logger.warning(
                "Escrow release leg for job_id=%s: contract released_amount %s units != recomputed %s — signing the recomputed value",
                job_id,
                ait_to_units(released_amount),
                release_units,
            )
        released_amount = units_to_ait(release_units)
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

        # Owed change (F1b/A6): the change leg is never submitted in-request.
        # Signed now it would carry the release's own sealed nonce and collide
        # on the (sender, N) mempool slot; waited-for it would out-live the
        # caller's timeout on this block interval and invite a second
        # submission on retry. The settlement sweeper's change pass pays owed
        # change from sealed legs on a later tick — custody holds it, provably,
        # until then. The response reports it explicitly; nothing is marked.
        if unbilled_amount > 0:
            _logger.info(
                "Escrow change deferred to the change pass: job_id=%s buyer=%s owed=%s",
                job_id,
                buyer_addr,
                unbilled_amount,
            )

        # No settle-time sweep attempt: every settlement leg is signed at the
        # sealed authority nonce, so an in-request sweep can only lose the
        # mempool (sender, nonce) slot to the release/refund that precedes it
        # (F1). The residue is swept by the periodic pass in the settlement
        # sweeper and by the retry surface on the next release call — both
        # derive it from sealed chain legs, never from this request's legs.
        released_at = datetime.now(UTC)
        try:
            with session_scope() as session:
                record = session.get(Escrow, job_id)
                if record:
                    # A settlement_failed row carries the dead hash from the mark
                    # the sweeper demoted; this re-drive's hash must replace it or
                    # the row would keep pointing at the corpse. Other statuses
                    # keep fill-if-empty: a settled row's original hash is fact.
                    was_failed = record.status == "settlement_failed"
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
                    # refunded_amount/refund_tx_hash stay untouched: the change
                    # pass marks them only from a sealed ESCROW_REFUND leg.
                    if tx_hash:
                        # A7: record the billed gross this submission consumed,
                        # keyed by the leg's own hash — the passes prove the
                        # sealed release by recomputing the route's fee rule
                        # from it. A dropped leg's entry orphans (its hash never
                        # seals); a same-hash dedup retry does not re-append.
                        # getattr: the row-update block must never fail on a
                        # missing attr — released_at is the load-bearing write.
                        entries = list(getattr(record, "billed_legs", None) or [])
                        if not any(e.get("tx_hash") == tx_hash for e in entries if isinstance(e, dict)):
                            entries.append({"tx_hash": tx_hash, "billed": billed_units})
                            record.billed_legs = entries
                    if tx_hash and (not record.release_tx_hash or was_failed):
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
            "refunded_amount": "0",
            "refund_tx_hash": None,
            "change_owed_amount": str(unbilled_amount) if unbilled_amount > 0 else "0",
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
    locked_units: int | None = None
    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            if record:
                locked_units = record.amount
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
    # The lock must be sealed before the refund can apply — same race as release.
    await _ensure_lock_sealed(job_id)
    # Same v2-era refusal as the release path: no route re-drive on a lock that
    # predates per-escrow custody — operator repair only.
    await _refuse_v2_lock(job_id)
    # B: a refund is only final once the on-chain ESCROW_REFUND transaction lands.
    # Apply the in-memory state, then settle on-chain, then roll back if settlement fails.
    async with mgr.release_lock(contract_id):
        refund_snapshot = mgr.snapshot_refund_state(contract_id)
        success, message = await mgr.refund_contract(contract_id, reason)
        if not success:
            raise HTTPException(status_code=400, detail=message)
        contract = mgr.escrow_contracts.get(contract_id)
        refund_amount = contract.refunded_amount if contract else Decimal(0)
        if locked_units is not None:
            # The lock is the ceiling: this pays out of the node wallet, and the
            # in-memory contract is a reconstruction of an on-chain fact rather
            # than the fact itself. It has been wrong before -- by exactly the
            # platform fee -- and a refund that overpays is money the operator
            # cannot get back, so cap it at what the chain says was locked.
            locked_ait = units_to_ait(locked_units)
            if refund_amount > locked_ait:
                _logger.error(
                    "Refund for job_id=%s clamped from %s to the locked %s AIT (contract_id=%s)",
                    job_id,
                    refund_amount,
                    locked_ait,
                    contract_id,
                )
                refund_amount = locked_ait
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
                    # Record what moved, not just that something did; a NULL here
                    # makes every reader fall back to reporting the whole lock.
                    record.refunded_amount = ait_to_units(refund_amount)
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
