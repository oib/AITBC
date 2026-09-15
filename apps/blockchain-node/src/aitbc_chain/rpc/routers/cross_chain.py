"""Cross-chain swap and bridge endpoints backed by the real bridge (GAP-47).

These endpoints replace the earlier in-memory simulation that returned
fabricated ``0xfrom…`` / ``0xsrc…`` hashes. Every swap and bridge created
here runs ``CrossChainBridge.initiate_transfer``: the sender's signature is
verified, funds are locked on the source chain through a real ``BRIDGE_LOCK``
transaction, and the returned ``source_tx_hash`` is the actual transaction
hash under which the lock is recorded and sealed into a block.

Settlement then follows the genuine bridge lifecycle — ``pending`` until the
lock is sealed and reaches finality, ``confirmed`` after proof verification
releases funds on the target chain, ``completed`` once the release
transaction is sealed, ``failed``/``refunded`` on real failure paths. Nothing
here claims a terminal state the bridge did not reach; when release
infrastructure (validators, finality headers, the relayer, or the release
fence) is not operational, records simply stay in their honest intermediate
state.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from sqlmodel import select

from aitbc.rate_limiting import rate_limit

from ...config import settings
from ...logger import get_logger
from ...models import CrossChainSwap, CrossChainTransfer, Transaction
from ..utils import get_supported_chains, validate_chain_id, verify_request_signature

_logger = get_logger(__name__)

router = APIRouter(tags=["cross-chain"])

# Terminal transfer states — a swap/bridge in one of these will not change again.
_TERMINAL_STATES = {"completed", "failed", "refunded"}


def _get_bridge() -> Any:
    from ...cross_chain.bridge import get_cross_chain_bridge

    bridge = get_cross_chain_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="Cross-chain bridge not initialized")
    return bridge


def _swap_rates() -> dict[str, float]:
    """Operator-configured swap rates ("from::to=rate,..." in settings)."""
    rates: dict[str, float] = {}
    raw = getattr(settings, "cross_chain_swap_rates", "") or ""
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        pair, _, value = entry.partition("=")
        try:
            rates[pair.strip()] = float(value)
        except ValueError:
            _logger.warning("Ignoring unparseable cross_chain_swap_rates entry: %s", entry)
    return rates


def _quote_swap_rate(from_chain: str, to_chain: str, from_token: str, to_token: str) -> float:
    """Return the configured swap rate for a pair.

    Same-asset pairs settle at parity (rate 1.0) — locking AIT on one chain
    and releasing AIT on another is a genuine 1:1 claim. Different assets
    need an operator-configured rate; there is no AMM to derive one from, so
    the endpoint refuses the swap instead of inventing a price.
    """
    rates = _swap_rates()
    pair = f"{from_chain}::{to_chain}"
    if pair in rates:
        return rates[pair]
    token_pair = f"{from_chain}:{from_token}::{to_chain}:{to_token}"
    if token_pair in rates:
        return rates[token_pair]
    if from_token == to_token:
        return 1.0
    raise HTTPException(
        status_code=400,
        detail=(
            f"No swap rate configured for {from_token}@{from_chain} -> {to_token}@{to_chain}; "
            "set CROSS_CHAIN_SWAP_RATES (e.g. 'ait-mainnet::ait-side=1.05')"
        ),
    )


def _require_amount_units(value: Any, field: str = "amount", allow_zero: bool = False) -> int:
    """Coerce the request amount to positive integer compute-units.

    Bridge endpoints take compute-units (1 AIT = 36_000_000 units), the same
    unit ``/rpc/transaction`` and ``/rpc/bridge/lock`` use. Decimal-looking
    input is rejected so "100" (units) is never confused with "100.0" AIT.
    ``allow_zero`` accepts 0 for optional bounds such as ``min_amount``.
    """
    if isinstance(value, bool) or value is None:
        raise HTTPException(status_code=400, detail=f"{field} is required (integer compute-units)")
    if isinstance(value, int):
        units = value
    elif isinstance(value, str) and value.strip().isdigit():
        units = int(value.strip())
    else:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be integer compute-units (1 AIT = 36,000,000 units)",
        )
    if units < 0 or (units == 0 and not allow_zero):
        raise HTTPException(status_code=400, detail=f"{field} must be positive")
    return units


def _bridge_supported_targets() -> list[str]:
    return [c.strip() for c in (getattr(settings, "bridge_supported_chains", "") or "").split(",") if c.strip()]


def _lock_transfer(
    *,
    sign_data: dict[str, Any],
    source_chain: str,
    target_chain: str,
    sender: str,
    recipient: str,
    amount_units: int,
    asset: str,
    signature: str,
    release_amount_units: int | None = None,
) -> Any:
    """Verify the sender signature over ``sign_data`` and run a real bridge lock.

    The bridge endpoint signs the same six-field payload as ``/rpc/bridge/lock``;
    the swap endpoint signs its nine-field request (which includes the chain
    pair, tokens, amount, min_amount and slippage). Either way the signature
    authorizes exactly the operation the wallet approved.
    """
    bridge = _get_bridge()
    if not validate_chain_id(source_chain):
        raise HTTPException(
            status_code=400,
            detail=f"Source chain '{source_chain}' not in supported_chains (allowed: {get_supported_chains()})",
        )
    supported_targets = _bridge_supported_targets()
    if supported_targets and target_chain not in supported_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Target chain '{target_chain}' not in bridge_supported_chains (allowed: {supported_targets})",
        )
    if not signature:
        raise HTTPException(status_code=403, detail="Signature required for cross-chain lock")
    if not verify_request_signature(sender, signature, sign_data):
        raise HTTPException(status_code=403, detail="Invalid sender signature")
    try:
        return bridge.initiate_transfer(
            source_chain=source_chain,
            target_chain=target_chain,
            sender=sender.lower(),
            recipient=recipient.lower(),
            amount=amount_units,
            asset=asset,
            release_amount=release_amount_units,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _lock_block_height(bridge: Any, source_chain: str, source_tx_hash: str | None) -> int | None:
    """Return the block height the lock tx was sealed at, or None if unsealed."""
    if not source_tx_hash:
        return None
    try:
        with bridge._session_for(source_chain) as session:
            tx = session.exec(
                select(Transaction.block_height).where(
                    Transaction.chain_id == source_chain,
                    Transaction.tx_hash == source_tx_hash,
                )
            ).first()
        return int(tx) if tx is not None else None
    except Exception:
        return None


def _find_transfer(bridge: Any, transfer_id: str) -> Any | None:
    """Find a transfer record across all chains this node knows about."""
    transfer = bridge.get_transfer(transfer_id)
    if transfer is not None:
        return transfer
    for chain_id in bridge._known_chains():
        if not bridge._chain_db_ready(chain_id):
            continue
        transfer = bridge.get_transfer(transfer_id, chain_id=chain_id)
        if transfer is not None:
            return transfer
    return None


def _transfer_status_payload(transfer: Any, bridge: Any) -> dict[str, Any]:
    lock_height = _lock_block_height(bridge, transfer.source_chain, transfer.source_tx_hash)
    return {
        "success": True,
        "transfer_id": transfer.transfer_id,
        "status": transfer.status.value,
        "source_chain": transfer.source_chain,
        "target_chain": transfer.target_chain,
        "sender": transfer.sender,
        "recipient": transfer.recipient,
        "amount": transfer.amount,
        "asset": transfer.asset,
        "source_tx_hash": transfer.source_tx_hash,
        "target_tx_hash": transfer.target_tx_hash,
        "lock_time": transfer.lock_time.isoformat() if transfer.lock_time else None,
        "confirm_time": transfer.confirm_time.isoformat() if transfer.confirm_time else None,
        "lock_block_height": lock_height,
        "lock_sealed": lock_height is not None,
    }


def _swap_status_payload(swap: CrossChainSwap, bridge: Any) -> dict[str, Any]:
    """Merge the swap quote row with the live bridge transfer state."""
    transfer = bridge.get_transfer(swap.transfer_id, chain_id=swap.chain_id)
    status = swap.status
    to_tx_hash = None
    from_tx_hash = swap.transfer_id
    completed_at = swap.completed_at.isoformat() if swap.completed_at else None
    lock_height = None
    if transfer is not None:
        status = transfer.status.value
        from_tx_hash = transfer.source_tx_hash or swap.transfer_id
        to_tx_hash = transfer.target_tx_hash
        lock_height = _lock_block_height(bridge, transfer.source_chain, transfer.source_tx_hash)
        if status in _TERMINAL_STATES and swap.status != status:
            # Opportunistically persist the terminal state so list views stay correct.
            try:
                with bridge._session_for(swap.chain_id) as session:
                    record = session.get(CrossChainSwap, swap.swap_id)
                    if record is not None:
                        record.status = status
                        if status == "completed" and record.completed_at is None:
                            record.completed_at = transfer.confirm_time or datetime.now(UTC)
                            completed_at = record.completed_at.isoformat()
                        session.add(record)
                        session.commit()
            except Exception:
                _logger.debug("Failed to persist swap status for %s", swap.swap_id)
    return {
        "success": True,
        "swap_id": swap.swap_id,
        "transfer_id": swap.transfer_id,
        "from_chain": swap.from_chain,
        "to_chain": swap.to_chain,
        "from_token": swap.from_token,
        "to_token": swap.to_token,
        "amount": swap.amount,
        "amount_units": swap.amount_units,
        "expected_amount": swap.expected_amount,
        "actual_amount": swap.expected_amount if status == "completed" else None,
        "min_amount": swap.min_amount,
        "rate": swap.rate,
        "total_fees": swap.total_fees,
        "slippage_tolerance": swap.slippage_tolerance,
        "user_address": swap.user_address,
        "recipient": swap.recipient,
        "status": status,
        "error": swap.error,
        "from_tx_hash": from_tx_hash,
        "to_tx_hash": to_tx_hash,
        "lock_block_height": lock_height,
        "lock_sealed": lock_height is not None,
        "created_at": swap.created_at.isoformat() if swap.created_at else None,
        "completed_at": completed_at,
    }


@router.get("/cross-chain/rates", summary="Get cross-chain exchange rates")
@rate_limit(rate=50, per=60)
async def get_cross_chain_rates(
    request: Request, from_chain: str | None = None, to_chain: str | None = None
) -> dict[str, Any]:
    """Return operator-configured cross-chain swap rates.

    Same-asset pairs always settle at parity (1.0). Rates for other pairs
    come from ``cross_chain_swap_rates`` configuration — there is no
    fabricated demo table.
    """
    rates = _swap_rates()
    if from_chain and to_chain:
        key = f"{from_chain}::{to_chain}"
        if key in rates:
            return {"rates": {key: rates[key]}}
        return {
            "rates": {},
            "detail": f"No configured rate for {from_chain} -> {to_chain}; same-asset pairs settle at parity (1.0)",
        }
    return {
        "rates": rates,
        "parity": "same-asset pairs settle at rate 1.0",
        "configured": bool(rates),
    }


@router.post("/swap", summary="Create cross-chain swap")
@rate_limit(rate=20, per=60)
async def create_cross_chain_swap(request: Request, swap_data: dict[str, Any]) -> dict[str, Any]:
    """Create a cross-chain swap: a signed, rate-quoted bridge lock.

    ``amount`` is integer compute-units locked on the source chain. The
    release amount is ``amount * rate`` — the rate is configured server-side
    (same-asset pairs settle at parity), never supplied by the caller, so a
    client cannot mint arbitrary target-chain value. ``min_amount`` is a real
    slippage guard: the swap is rejected when the quote falls below it.
    """
    from_chain = swap_data.get("from_chain")
    to_chain = swap_data.get("to_chain")
    from_token = swap_data.get("from_token")
    to_token = swap_data.get("to_token")
    sender = swap_data.get("sender") or swap_data.get("user_address")
    recipient = swap_data.get("recipient") or sender
    signature = swap_data.get("signature")
    slippage = float(swap_data.get("slippage_tolerance", 0.01))

    if not all([from_chain, to_chain, from_token, to_token, sender, recipient]):
        raise HTTPException(
            status_code=400,
            detail="from_chain, to_chain, from_token, to_token and sender are required",
        )
    if from_chain == to_chain:
        raise HTTPException(status_code=400, detail="Source and target chains must be different")
    amount_units = _require_amount_units(swap_data.get("amount"))
    min_amount_units = 0
    if swap_data.get("min_amount") is not None:
        min_amount_units = _require_amount_units(swap_data.get("min_amount"), field="min_amount", allow_zero=True)

    rate = _quote_swap_rate(str(from_chain), str(to_chain), str(from_token), str(to_token))
    expected_units = int(Decimal(amount_units) * Decimal(str(rate)))
    if expected_units < min_amount_units:
        raise HTTPException(
            status_code=400,
            detail=f"Quoted amount {expected_units} is below min_amount {min_amount_units} (slippage protection)",
        )

    # The signature covers the request the wallet actually approved.
    sign_data = {
        "from_chain": from_chain,
        "to_chain": to_chain,
        "from_token": from_token,
        "to_token": to_token,
        "sender": sender,
        "recipient": recipient,
        "amount": amount_units,
        "min_amount": min_amount_units,
        "slippage_tolerance": slippage,
    }
    transfer = _lock_transfer(
        sign_data=sign_data,
        source_chain=cast(str, from_chain),
        target_chain=cast(str, to_chain),
        sender=cast(str, sender),
        recipient=cast(str, recipient),
        amount_units=amount_units,
        asset=str(from_token),
        signature=str(signature) if signature else "",
        release_amount_units=expected_units,
    )

    bridge = _get_bridge()
    fee_units = amount_units * getattr(bridge, "BRIDGE_FEE_BASIS_POINTS", 10) // 10000
    swap_id = f"swap_{uuid.uuid4().hex[:12]}"
    try:
        with bridge._session_for(str(from_chain)) as session:
            session.add(
                CrossChainSwap(
                    swap_id=swap_id,
                    transfer_id=transfer.transfer_id,
                    chain_id=str(from_chain),
                    from_chain=str(from_chain),
                    to_chain=str(to_chain),
                    from_token=str(from_token),
                    to_token=str(to_token),
                    amount=str(Decimal(amount_units) / Decimal(36_000_000)),
                    amount_units=amount_units,
                    expected_amount=str(Decimal(expected_units) / Decimal(36_000_000)),
                    min_amount=str(Decimal(min_amount_units) / Decimal(36_000_000)),
                    rate=rate,
                    total_fees=str(Decimal(fee_units) / Decimal(36_000_000)),
                    slippage_tolerance=slippage,
                    user_address=cast(str, sender),
                    recipient=cast(str, recipient),
                    status="pending",
                )
            )
            session.commit()
    except Exception as e:
        # The lock already happened — never pretend it did not. Report the
        # real transfer id so the operation remains trackable.
        _logger.error("Swap record persist failed for transfer %s: %s", transfer.transfer_id, e)
        raise HTTPException(
            status_code=500,
            detail=(f"Swap locked on-chain (transfer {transfer.transfer_id}) but the swap record could not be stored: {e}"),
        ) from e

    release_available, release_reason = bridge.release_availability(str(from_chain))

    return {
        "success": True,
        "swap_id": swap_id,
        "transfer_id": transfer.transfer_id,
        "from_chain": from_chain,
        "to_chain": to_chain,
        "from_token": from_token,
        "to_token": to_token,
        "amount": str(Decimal(amount_units) / Decimal(36_000_000)),
        "amount_units": amount_units,
        "expected_amount": str(Decimal(expected_units) / Decimal(36_000_000)),
        "expected_amount_units": expected_units,
        "actual_amount": None,
        "min_amount": str(Decimal(min_amount_units) / Decimal(36_000_000)),
        "rate": rate,
        "total_fees": str(Decimal(fee_units) / Decimal(36_000_000)),
        "slippage_tolerance": slippage,
        "user_address": sender,
        "recipient": recipient,
        "status": transfer.status.value,
        "from_tx_hash": transfer.source_tx_hash,
        "to_tx_hash": None,
        "release_available": release_available,
        "release_note": release_reason,
        "created_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "settlement": "bridge",
    }


@router.get("/cross-chain/swap/{swap_id}", summary="Get cross-chain swap status")
@rate_limit(rate=100, per=60)
async def get_cross_chain_swap(request: Request, swap_id: str) -> dict[str, Any]:
    """Return the real status of a cross-chain swap."""
    bridge = _get_bridge()
    swap = None
    for chain_id in bridge._known_chains():
        if not bridge._chain_db_ready(chain_id):
            continue
        try:
            with bridge._session_for(chain_id) as session:
                record = session.exec(
                    select(CrossChainSwap).where((CrossChainSwap.swap_id == swap_id) | (CrossChainSwap.transfer_id == swap_id))
                ).first()
        except Exception:
            continue
        if record is not None:
            swap = record
            break
    if swap is None:
        raise HTTPException(status_code=404, detail=f"Swap not found: {swap_id}")
    return _swap_status_payload(swap, bridge)


@router.get("/cross-chain/swaps", summary="List cross-chain swaps")
@rate_limit(rate=50, per=60)
async def list_cross_chain_swaps(
    request: Request, user_address: str | None = None, status: str | None = None, limit: int = 100
) -> dict[str, Any]:
    """List persisted cross-chain swaps with optional filters."""
    bridge = _get_bridge()
    results: list[dict[str, Any]] = []
    seen: set[str] = set()  # a swap row is only stored on its source chain, but
    # dedupe anyway so multi-chain scans over a shared store can't repeat it
    for chain_id in bridge._known_chains():
        if not bridge._chain_db_ready(chain_id):
            continue
        try:
            with bridge._session_for(chain_id) as session:
                query = select(CrossChainSwap)
                if user_address:
                    query = query.where(CrossChainSwap.user_address == user_address)
                for record in session.exec(query).all():
                    if record.swap_id in seen:
                        continue
                    seen.add(record.swap_id)
                    results.append(_swap_status_payload(record, bridge))
        except Exception:
            continue
    results.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    if status:
        results = [s for s in results if s.get("status") == status]
    return {"swaps": results[:limit], "count": len(results[:limit])}


@router.post("/cross-chain/bridge", summary="Create cross-chain bridge transaction")
@rate_limit(rate=20, per=60)
async def create_cross_chain_bridge(request: Request, bridge_data: dict[str, Any]) -> dict[str, Any]:
    """Create a cross-chain bridge transfer: a signed real bridge lock.

    ``amount`` is integer compute-units. The returned ``bridge_id`` is the
    transfer id, which is also the real source-chain transaction hash of the
    ``BRIDGE_LOCK`` transaction.
    """
    source_chain = bridge_data.get("source_chain")
    target_chain = bridge_data.get("target_chain")
    token = bridge_data.get("token") or bridge_data.get("asset") or "native"
    sender = bridge_data.get("sender") or bridge_data.get("user_address")
    recipient = bridge_data.get("recipient") or bridge_data.get("recipient_address")
    signature = bridge_data.get("signature")

    if not all([source_chain, target_chain, token, sender, recipient]):
        raise HTTPException(
            status_code=400,
            detail="source_chain, target_chain, token, sender and recipient are required",
        )
    if source_chain == target_chain:
        raise HTTPException(status_code=400, detail="Source and target chains must be different")
    amount_units = _require_amount_units(bridge_data.get("amount"))

    sign_data = {
        "source_chain": source_chain,
        "target_chain": target_chain,
        "sender": sender,
        "recipient": recipient,
        "amount": amount_units,
        "asset": token,
    }
    transfer = _lock_transfer(
        sign_data=sign_data,
        source_chain=cast(str, source_chain),
        target_chain=cast(str, target_chain),
        sender=cast(str, sender),
        recipient=cast(str, recipient),
        amount_units=amount_units,
        asset=str(token),
        signature=str(signature) if signature else "",
    )
    bridge = _get_bridge()
    fee_units = amount_units * getattr(bridge, "BRIDGE_FEE_BASIS_POINTS", 10) // 10000
    release_available, release_reason = bridge.release_availability(str(source_chain))
    return {
        "success": True,
        "bridge_id": transfer.transfer_id,
        "transfer_id": transfer.transfer_id,
        "source_chain": source_chain,
        "target_chain": target_chain,
        "token": token,
        "amount": str(Decimal(amount_units) / Decimal(36_000_000)),
        "amount_units": amount_units,
        "bridge_fee": str(Decimal(fee_units) / Decimal(36_000_000)),
        "fee_units": fee_units,
        "sender": sender,
        "recipient_address": recipient,
        "status": transfer.status.value,
        "source_tx_hash": transfer.source_tx_hash,
        "target_tx_hash": None,
        "release_available": release_available,
        "release_note": release_reason,
        "created_at": (transfer.lock_time or datetime.now(UTC)).isoformat(),
        "completed_at": None,
    }


@router.get("/cross-chain/bridge/{bridge_id}", summary="Get cross-chain bridge status")
@rate_limit(rate=100, per=60)
async def get_cross_chain_bridge(request: Request, bridge_id: str) -> dict[str, Any]:
    """Return the real status of a cross-chain bridge transfer.

    ``bridge_id`` is the transfer id (identical to the source lock tx hash).
    """
    bridge = _get_bridge()
    transfer = _find_transfer(bridge, bridge_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail=f"Bridge transfer not found: {bridge_id}")
    payload = _transfer_status_payload(transfer, bridge)
    payload["bridge_id"] = transfer.transfer_id
    payload["recipient_address"] = transfer.recipient
    payload["created_at"] = payload.pop("lock_time")
    payload["completed_at"] = payload.pop("confirm_time")
    return payload


@router.get("/cross-chain/pools", summary="Show cross-chain liquidity pools")
@rate_limit(rate=50, per=60)
async def get_cross_chain_pools(request: Request) -> dict[str, Any]:
    """Return cross-chain liquidity pools.

    There is no cross-chain AMM — swaps settle through fixed-rate bridge
    transfers, so this honestly reports an empty pool set.
    """
    return {
        "pools": [],
        "detail": "No cross-chain liquidity pools exist; swaps settle through fixed-rate bridge locks",
    }


@router.get("/cross-chain/stats", summary="Show cross-chain trading statistics")
@rate_limit(rate=50, per=60)
async def get_cross_chain_stats(request: Request) -> dict[str, Any]:
    """Return aggregate statistics computed from real persisted records."""
    bridge = _get_bridge()
    swap_stats: dict[str, dict[str, Any]] = {}
    bridge_stats: dict[str, dict[str, Any]] = {}
    seen_swaps: set[str] = set()
    seen_transfers: set[str] = set()
    total_volume_units = 0
    for chain_id in bridge._known_chains():
        if not bridge._chain_db_ready(chain_id):
            continue
        try:
            with bridge._session_for(chain_id) as session:
                for swap in session.exec(select(CrossChainSwap)).all():
                    if swap.swap_id in seen_swaps:
                        continue
                    seen_swaps.add(swap.swap_id)
                    entry = swap_stats.setdefault(swap.status, {"status": swap.status, "count": 0, "volume": 0})
                    entry["count"] += 1
                    entry["volume"] += swap.amount_units
                    total_volume_units += swap.amount_units
                for transfer in session.exec(select(CrossChainTransfer)).all():
                    if transfer.transfer_id in seen_transfers:
                        continue
                    seen_transfers.add(transfer.transfer_id)
                    entry = bridge_stats.setdefault(transfer.status, {"status": transfer.status, "count": 0, "volume": 0})
                    entry["count"] += 1
                    entry["volume"] += transfer.amount
        except Exception:
            continue
    return {
        "total_volume": str(Decimal(total_volume_units) / Decimal(36_000_000)),
        "total_volume_units": total_volume_units,
        "supported_chains": get_supported_chains(),
        "bridge_supported_chains": _bridge_supported_targets(),
        "release_enabled": getattr(settings, "bridge_release_enabled", False),
        "relayer_enabled": getattr(settings, "bridge_relayer_enabled", True),
        "timestamp": datetime.now(UTC).isoformat(),
        "swap_stats": list(swap_stats.values()),
        "bridge_stats": list(bridge_stats.values()),
    }
