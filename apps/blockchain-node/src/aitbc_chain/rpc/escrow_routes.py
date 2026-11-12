"""
Escrow RPC endpoints for the blockchain node.
Provides create/release/refund/get endpoints backed by EscrowManager and Escrow DB model.
"""

from __future__ import annotations
from aitbc.constants import BLOCKCHAIN_RPC_URL

import hmac as hmac
import json as json
import os
from dataclasses import dataclass as dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security as Security, status as status
from fastapi.security import APIKeyHeader
from starlette.concurrency import run_in_threadpool
from sqlmodel import Session as Session

from aitbc.network import SharedHttpClient as SharedHttpClient
from aitbc.crypto.crypto import (
    derive_ethereum_address as derive_ethereum_address,
    sign_transaction_hash as sign_transaction_hash,
)
from aitbc.crypto.signature_recovery import canonical_address as canonical_address
from aitbc.market.energy_pricing import (
    DEFAULT_MAX_RATE_AGE_SECONDS,
    EnergyPricingError,
    EnergyQuote,
    SettlementRoute,
    evaluate_quote,
)
from aitbc.utils import UNITS_PER_AIT as UNITS_PER_AIT, ait_to_units, units_to_ait
from eth_utils import keccak as keccak

from ..chain_id import resolve_chain_id as resolve_chain_id
from ..config import settings as settings
from ..contracts.escrow import EscrowState, backfill_settlement_legs, get_escrow_manager, serialise_milestones
from ..contracts.escrow_txn import EscrowBusy, EscrowMutation as EscrowMutation, escrow_mutation
from ..database import session_scope
from ..logger import get_logger
from ..metrics import escrow_fee_sweep_total as escrow_fee_sweep_total, escrow_settlement_refused_total
from ..models import Escrow

from .utils import _unsigned_tx_fields as _unsigned_tx_fields

_raw_rpc_url = os.getenv("HUB_RPC_URL", BLOCKCHAIN_RPC_URL).rstrip("/")
_HUB_RPC_URL = _raw_rpc_url if _raw_rpc_url.endswith("/rpc") else f"{_raw_rpc_url}/rpc"
_NODE_WALLET = os.getenv("NODE_WALLET_ADDRESS", os.getenv("GENESIS_WALLET_ADDRESS", ""))
_logger = get_logger(__name__)
_AUTO_STAKE_RETIRED_LOGGED = False
_FALLBACK_MAX_RATE_AGE_SECONDS = DEFAULT_MAX_RATE_AGE_SECONDS
_RPC_API_KEY = os.getenv("BLOCKCHAIN_RPC_API_KEY", "")
_api_key_header: APIKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)
# Settlement-node credential (#1917): release/refund move money, so they
# require a dedicated key in addition to the router-wide X-API-Key. Until
# now any holder of the shared BLOCKCHAIN_RPC_API_KEY — including every
# issued join key's parent credential — could settle any escrow. The
# settlement key is a second header (X-Settlement-Key) so the base RPC key
# check is untouched; unset means the routes refuse (fail-closed, same
# contract as verify_rpc_api_key).
_RPC_SETTLEMENT_API_KEY = os.getenv("BLOCKCHAIN_RPC_SETTLEMENT_API_KEY", "")
if not _RPC_SETTLEMENT_API_KEY:
    _logger.warning(
        "BLOCKCHAIN_RPC_SETTLEMENT_API_KEY is not set; escrow release/refund endpoints will "
        "refuse all requests until it is configured"
    )
_settlement_key_header: APIKeyHeader = APIKeyHeader(name="X-Settlement-Key", auto_error=False)
_RPC_API_PEER_KEYS = frozenset(k.strip() for k in os.getenv("BLOCKCHAIN_RPC_API_KEY_PEERS", "").split(",") if k.strip())
_GENESIS_WALLET_PRIVATE_KEY = os.getenv("GENESIS_WALLET_PRIVATE_KEY", "")
_ESCROW_RELEASE_PRIVATE_KEY = os.getenv("ESCROW_RELEASE_PRIVATE_KEY", "")
_ESCROW_RELEASE_ADDRESS = os.getenv("ESCROW_RELEASE_ADDRESS", "")
_RELEASE_LOOKUP_LIMIT = int(os.getenv("ESCROW_RELEASE_LOOKUP_LIMIT", "10"))
_FUNDING_LOCK_MEMPOOL_LIMIT = 1000

from .escrow_routes_helpers import (
    _chain_id as _chain_id,
    _check_stored_agent_binding as _check_stored_agent_binding,
    _compute_tx_signing_hash as _compute_tx_signing_hash,
    _energy_max_rate_age_seconds as _energy_max_rate_age_seconds,
    _energy_operator_address as _energy_operator_address,
    _escrow_agent_fields as _escrow_agent_fields,
    _escrow_busy as _escrow_busy,
    _fee_for as _fee_for,
    _fee_sweep_enabled as _fee_sweep_enabled,
    _fee_sweep_recipient as _fee_sweep_recipient,
    _find_contract_id as _find_contract_id,
    _find_existing_fee_sweep as _find_existing_fee_sweep,
    _find_existing_lock as _find_existing_lock,
    _find_existing_lock_tx as _find_existing_lock_tx,
    _find_existing_receipt_claim as _find_existing_receipt_claim,
    _find_existing_refund as _find_existing_refund,
    _find_existing_release as _find_existing_release,
    _get_account_nonce as _get_account_nonce,
    _get_account_nonce_strict as _get_account_nonce_strict,
    _get_settlement_address as _get_settlement_address,
    _get_settlement_key as _get_settlement_key,
    _is_nonce_refusal as _is_nonce_refusal,
    _mempool_nonce_floor as _mempool_nonce_floor,
    _optional_agent_binding as _optional_agent_binding,
    _require_settlement_signing as _require_settlement_signing,
    _resolve_chain_account as _resolve_chain_account,
    _settled_leg_ait as _settled_leg_ait,
    _settlement_next_nonce as _settlement_next_nonce,
    _settlement_signing_nonce as _settlement_signing_nonce,
    _settlement_signing_ready as _settlement_signing_ready,
    _to_canonical as _to_canonical,
    _verify_job_tx_proof as _verify_job_tx_proof,
    get_node_wallet_address as get_node_wallet_address,
    rpc_fleet_key_accepted as rpc_fleet_key_accepted,
    rpc_peer_key_accepted as rpc_peer_key_accepted,
    verify_rpc_api_key as verify_rpc_api_key,
    verify_rpc_export_key as verify_rpc_export_key,
    verify_rpc_peer_key as verify_rpc_peer_key,
    verify_rpc_settlement_key as verify_rpc_settlement_key,
)
from .escrow_routes_lock import (
    _assert_lock_matches_contract as _assert_lock_matches_contract,
    _build_lock_tx as _build_lock_tx,
    _canonical_lock_fields as _canonical_lock_fields,
    _ensure_lock_sealed as _ensure_lock_sealed,
    _refuse_v2_lock as _refuse_v2_lock,
    _submit_lock_tx as _submit_lock_tx,
    _verify_funding_lock as _verify_funding_lock,
)
from .escrow_routes_submit import (
    _escrow_custody_balance as _escrow_custody_balance,
    _retry_sweep_released_escrow as _retry_sweep_released_escrow,
    _submit_fee_sweep_tx as _submit_fee_sweep_tx,
    _submit_market_signed as _submit_market_signed,
    _submit_payment_tx as _submit_payment_tx,
    _submit_receipt_claim_tx as _submit_receipt_claim_tx,
    _submit_refund_tx as _submit_refund_tx,
)
from .escrow_routes_release import (
    _ReleasePlan as _ReleasePlan,
    _already_released_result as _already_released_result,
    _read_release_row as _read_release_row,
    _release_read_locked as _release_read_locked,
    _release_settle_locked as _release_settle_locked,
    _release_settle_locked_impl as _release_settle_locked_impl,
)
from .escrow_routes_refund import (
    _RefundPlan as _RefundPlan,
    _RefundRow as _RefundRow,
    _read_refund_row as _read_refund_row,
    _refund_read_locked as _refund_read_locked,
    _refund_settle_locked as _refund_settle_locked,
    _refund_settle_locked_impl as _refund_settle_locked_impl,
)

router = APIRouter(tags=["escrow"], dependencies=[Depends(verify_rpc_api_key)])


def _auto_stake(provider: str, amount: int, chain_id: str, job_id: str | None = None) -> str | None:
    """Stake a portion of released escrow for the provider without requiring a signature.

    This is a protocol-level reinvestment triggered from the escrow release path.
    The provider's on-chain account is expected to have just been credited by the
    ESCROW_RELEASE transaction. If job_id is supplied the address is also checked
    against the escrow's recorded provider so a caller cannot route reinvestment to
    an unrelated stake.
    """
    if not provider or amount <= 0:
        return None
    # Retired unconditionally at v9 — protocol-escrow transfers cannot seal;
    # the escrow release is unaffected.
    global _AUTO_STAKE_RETIRED_LOGGED
    if not _AUTO_STAKE_RETIRED_LOGGED:
        _AUTO_STAKE_RETIRED_LOGGED = True
        _logger.warning(
            "AUTO_STAKE skipped permanently: retired at v9 (protocol-escrow transfers cannot seal); "
            "the escrow release is unaffected"
        )
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

    buyer_agent_id, provider_agent_id = _optional_agent_binding(body)

    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    # Settlement capability gates create: a node that cannot sign the release
    # or refund would still accept and submit the buyer's ESCROW_LOCK, leaving
    # the funds locked with no settlement path on this node. The release gate's
    # own predicate runs here — before the idempotent lock probe, before any
    # submission, before any row or contract is written.
    _require_settlement_signing(job_id, "ESCROW_CREATE")

    # Idempotency: a retry whose first create already landed an ESCROW_LOCK
    # on-chain must not submit a second lock. Mirrors the
    # _find_existing_release/_find_existing_refund guards on the settlement
    # paths — this was the one submission path without it.
    existing_lock_hash = await _find_existing_lock(job_id)
    if existing_lock_hash:

        def _read_lock_row() -> Escrow | None:
            with session_scope() as session:
                return session.get(Escrow, job_id)

        existing_row = await run_in_threadpool(_read_lock_row)
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
        if existing_row:
            _check_stored_agent_binding(existing_row, buyer_agent_id, provider_agent_id)
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
            **_escrow_agent_fields(existing_row),
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

        def _drop_stale_row() -> None:
            with session_scope() as session:
                stale_row = session.get(Escrow, job_id)
                if stale_row is not None and stale_row.released_at is None and stale_row.refunded_at is None:
                    session.delete(stale_row)
                    session.commit()

        await run_in_threadpool(_drop_stale_row)
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
            raise HTTPException(
                status_code=400,
                detail="lock_nonce is required with lock_signature: the nonce is inside the signed envelope and cannot be reconstructed",
            )
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

    # Verify the lock still exists and carries this contract's facts before
    # marking FUNDED. Admission's hash is not proof: a mempool-evicted lock
    # would leave the job funded with nothing locked, and the settlement gates
    # would 425 forever on a hash that never seals. On any failure the
    # just-created contract is dropped, mirroring the stale-cleanup above, so
    # the retry starts clean.
    try:
        verified_lock = await _verify_funding_lock(lock_tx_hash, job_id=job_id, buyer=buyer, amount_units=amount_units)
        funded, fund_message = await mgr.fund_contract(contract_id, lock_tx_hash, verified_lock)
    except HTTPException:
        mgr.escrow_contracts.pop(contract_id, None)
        mgr.active_contracts.discard(contract_id)
        mgr.disputed_contracts.discard(contract_id)
        raise
    if not funded:
        mgr.escrow_contracts.pop(contract_id, None)
        mgr.active_contracts.discard(contract_id)
        mgr.disputed_contracts.discard(contract_id)
        raise HTTPException(status_code=425, detail=fund_message, headers={"Retry-After": "5"}) from None

    # #780 (b): the contract's lifecycle columns, taken from the contract just funded so
    # the row carries what the in-memory object does. The id is the one create_contract
    # derived (contract_id_for), identical on every worker.
    funded_contract = mgr.escrow_contracts.get(contract_id)
    state_columns: dict[str, Any] = {}
    if funded_contract is not None:
        state_columns = {
            "contract_id": contract_id,
            "state": EscrowState.FUNDED.value,
            "expires_at": datetime.fromtimestamp(funded_contract.expires_at, UTC),
            "fee_bps": int((funded_contract.fee_rate * 10000).to_integral_value()),
            "milestones": serialise_milestones(funded_contract.milestones),
            "current_milestone": funded_contract.current_milestone,
        }

    # Persist the Escrow DB record only once the lock was accepted. If the
    # process dies between submit and this write the row is missing, but the
    # next create (or release/refund) rebuilds it from the on-chain lock via
    # ``_reconstruct_escrow_from_chain`` — the funds are never orphaned.
    try:

        def _persist_escrow_row() -> None:
            with session_scope() as session:
                existing = session.get(Escrow, job_id)
                if existing:
                    existing.status = "locked"
                    existing.lock_tx_hash = lock_tx_hash
                    existing.buyer = _to_canonical(buyer)
                    existing.provider = _to_canonical(provider)
                    existing.amount = amount_units
                    if buyer_agent_id:
                        existing.buyer_agent_id = buyer_agent_id
                    if provider_agent_id:
                        existing.provider_agent_id = provider_agent_id
                    for column, value in state_columns.items():
                        setattr(existing, column, value)
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
                        chain_id=_chain_id(),
                        buyer=_to_canonical(buyer),
                        provider=_to_canonical(provider),
                        amount=amount_units,
                        status="locked",
                        lock_tx_hash=lock_tx_hash,
                        buyer_agent_id=buyer_agent_id,
                        provider_agent_id=provider_agent_id,
                        **state_columns,
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

        await run_in_threadpool(_persist_escrow_row)
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
        **({"buyer_agent_id": buyer_agent_id} if buyer_agent_id else {}),
        **({"provider_agent_id": provider_agent_id} if provider_agent_id else {}),
    }


@router.post(
    "/escrow/{job_id}/release",
    summary="Release escrow to provider",
    dependencies=[Depends(verify_rpc_settlement_key)],
)
async def release_escrow(job_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Release locked funds to the provider after job completion.
    Accepts optional job_tx_hash as proof of work reference."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    # Settlement must be possible before any escrow state is mutated. A node whose
    # settlement key and address disagree cannot pay the provider, and releasing
    # first would leave the escrow marked paid with nothing on-chain.
    if not _settlement_signing_ready():
        _logger.error(
            "ESCROW_RELEASE: refusing to release job_id=%s - settlement key/address is missing or mismatched",
            job_id,
        )
        escrow_settlement_refused_total.labels(op="release").inc()
        raise HTTPException(
            status_code=503,
            detail="Settlement key/address is not configured correctly; escrow was not released",
        )

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
        # A7e: NaN/sNaN/±Infinity parse fine but must never reach a
        # comparison or the unit conversion (NaN <= 0 raises, Infinity
        # raises in ait_to_units).
        if not requested_amount.is_finite():
            raise HTTPException(status_code=400, detail="amount must be a finite decimal number") from None
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

    try:
        async with escrow_mutation(job_id, session_scope) as txn:
            plan = await _release_read_locked(mgr, job_id, request)
            if isinstance(plan, dict):
                return plan
            # The lock must be sealed before the release can apply — checked before any
            # contract state is touched, like the settlement-key preamble above.
            await _ensure_lock_sealed(job_id)
            # And it must not be a v2-era lock: re-driving one pays out of the authority
            # with no apply-time dedup. Demoted settlement_failed rows reach this too,
            # so the guard is what keeps a sweeper demote + coordinator retry from
            # replaying the v2 dead-set without an operator go.
            await _refuse_v2_lock(job_id)
            return await _release_settle_locked(mgr, job_id, request, requested_amount, plan, txn)
    except EscrowBusy:
        raise _escrow_busy(job_id) from None


@router.post(
    "/escrow/{job_id}/refund",
    summary="Refund escrow to buyer",
    dependencies=[Depends(verify_rpc_settlement_key)],
)
async def refund_escrow(job_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refund locked funds back to the buyer."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")
    # The refund leg is settlement-signed like the release: a keyless node
    # cannot serve it, so it refuses before touching any state — the same gate
    # create and release already carry.
    _require_settlement_signing(job_id, "ESCROW_REFUND")
    try:
        async with escrow_mutation(job_id, session_scope) as txn:
            plan = await _refund_read_locked(mgr, job_id, body)
            if isinstance(plan, dict):
                return plan
            # The lock must be sealed before the refund can apply — same race as release.
            await _ensure_lock_sealed(job_id)
            # Same v2-era refusal as the release path: no route re-drive on a lock that
            # predates per-escrow custody — operator repair only.
            await _refuse_v2_lock(job_id)
            return await _refund_settle_locked(mgr, job_id, plan, txn)
    except EscrowBusy:
        raise _escrow_busy(job_id) from None


@router.get("/escrow/{job_id}", summary="Get escrow state")
async def get_escrow(job_id: str) -> dict[str, Any]:
    """Get current escrow state for a job."""
    mgr = get_escrow_manager()
    db_record: Escrow | None = None
    try:

        def _read_escrow_row() -> None:
            nonlocal db_record
            with session_scope() as session:
                db_record = session.get(Escrow, job_id)
                if db_record is not None:
                    # A row rebuilt on a node that did not serve the release knows the
                    # escrow settled but not what it moved; take that from the chain.
                    backfill_settlement_legs(session, db_record)

        await run_in_threadpool(_read_escrow_row)
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
                    **_escrow_agent_fields(db_record),
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
            **_escrow_agent_fields(db_record),
        }
    raise HTTPException(status_code=404, detail=f"No escrow found for job_id={job_id}") from None
