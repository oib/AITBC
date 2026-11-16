"""Bridge deposit read routes, extracted from ``bridge_routes.py`` (#1860).

GET /v1/bridge/deposits, /v1/bridge/deposit/{tx_hash} and
/v1/bridge/deposit/by-recipient/{address}, plus the deposit normalizers they
share. Paths, methods, dependencies and response shapes are unchanged;
``bridge_routes`` imports this module at the position the section used to
occupy so ``bridge_router`` registration order — and the OpenAPI path order
built from it — is preserved.
"""

from typing import Any

from fastapi import HTTPException, Request

from aitbc.rate_limiting import rate_limit

from .bridge_db import (
    _money_str,
    get_all_deposits,
    get_deposit_by_tx_hash,
    get_deposits_by_recipient,
    get_pending_deposits,
)
from .bridge_routes_common import bridge_router


@bridge_router.get("/deposits")
def bridge_list_deposits(status: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List bridge deposits."""
    limit = max(0, min(limit, 500))
    if status == "pending":
        deposits = get_pending_deposits(limit=limit, offset=offset)
    else:
        deposits = get_all_deposits(limit=limit, offset=offset)
    return {
        "deposits": _normalize_deposits(deposits),
        "count": len(deposits),
        "total": len(deposits),
        "limit": limit,
        "offset": offset,
    }


@bridge_router.get("/deposit/{tx_hash}")
def bridge_get_deposit(tx_hash: str) -> dict[str, Any]:
    """Get a single bridge deposit by ETH transaction hash."""
    deposit = get_deposit_by_tx_hash(tx_hash)
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit not found")
    return _normalize_deposit(deposit)


@bridge_router.get("/deposit/by-recipient/{address}")
@rate_limit(rate=50, per=60)
def bridge_deposits_by_recipient(request: Request, address: str, limit: int = 10) -> dict[str, Any]:
    """Get recent bridge deposits for a single AIT recipient address.

    Non-enumerable: the caller must already know the recipient, matching the
    privacy profile of the public per-tx-hash lookup. The enumerable
    /v1/bridge/deposits index stays loopback-only in nginx.
    """
    # Format check only — a lookup field must accept the address however the
    # user copied it (lowercase or checksummed); matching is case-insensitive.
    if not (address.startswith("0x") and len(address) == 42 and all(c in "0123456789abcdefABCDEF" for c in address[2:])):
        raise HTTPException(status_code=422, detail="Invalid AIT address: expected 0x + 40 hex chars")
    limit = max(1, min(limit, 50))
    deposits = get_deposits_by_recipient(address, limit=limit)
    # The caller is the recipient — their own ETH sender isn't theirs to see;
    # the enumerable deposit index stays loopback-only for the same reason.
    return {
        "deposits": [{k: v for k, v in d.items() if k != "eth_from_address"} for d in _normalize_deposits(deposits)],
        "count": len(deposits),
    }


def _normalize_deposit(deposit: dict[str, Any]) -> dict[str, Any]:
    """Normalize wallet-bridge deposit to the shape the website expects."""
    return {
        "id": deposit.get("id"),
        "eth_tx_hash": deposit.get("tx_hash"),
        "eth_from_address": deposit.get("from_address"),
        "eth_amount": _money_str(deposit.get("amount_eth")),
        "ait_amount": _money_str(deposit.get("amount_ait")),
        "ait_recipient": deposit.get("recipient") or "",
        "status": deposit.get("status"),
        "ait_tx_hash": deposit.get("ait_tx_hash"),
        "created_at": deposit.get("created_at"),
        "processed_at": deposit.get("completed_at") or deposit.get("created_at"),
    }


def _normalize_deposits(deposits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalize_deposit(d) for d in deposits]
