"""Admin bridge read routes, extracted from ``bridge_routes.py`` (#1860).

Exchange-settlement listing, the admin-keyed ETH float view, and the
sell-lane config-status document. ``bridge_routes`` imports this module at
the position the section used to occupy so ``bridge_router`` registration
order is unchanged.
"""

import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, HTTPException

from wallet_app.deps import require_admin_api_key
from wallet_app.utc_time import utc_now

from .bridge_db import _money_str, list_exchange_settlements
from .bridge_routes_common import bridge_router
from .url_redact import redact_text


def _normalize_settlement(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("amount_ait", "eth_amount", "fee_ait"):
        out[key] = _money_str(row.get(key))
    return out


@bridge_router.get("/settlements")
def bridge_settlements(
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: Annotated[None, Depends(require_admin_api_key)] = None,
) -> dict[str, Any]:
    """List exchange-settlement ledger rows (CLI-1).

    Admin-keyed like sell/quote: the /v1/bridge mount is publicly exposed on
    hub and settlement rows carry diagnostic error text plus release
    nonces/hashes — not a participants board. Flag-off the table is empty and
    the route returns []."""
    if kind is not None and kind not in ("trade", "order_refund"):
        raise HTTPException(status_code=400, detail="kind must be 'trade' or 'order_refund'")
    limit = max(0, min(limit, 500))
    offset = max(0, offset)
    rows = list_exchange_settlements(status=status, kind=kind, limit=limit, offset=offset)
    return {
        "settlements": [_normalize_settlement(r) for r in rows],
        "count": len(rows),
        "limit": limit,
        "offset": offset,
    }


def _release_window(since: datetime) -> dict[str, Any]:
    """Per-lane ETH released (or possibly released) since ``since`` —
    the committed-status semantics of get_*_eth_committed_since.

    Ledger rows are stamped with aware UTC ``datetime.now(UTC)`` (#1575),
    so the comparison runs on the UTC isoformat. Pre-#1575 naive
    host-local rows still order by wall time but can skew a lexical
    window boundary by the host's UTC offset — bounded and documented.
    The reported ``since`` attaches the host's zone for display, and
    ``timezone`` names it."""
    from .bridge_db import (
        get_exchange_eth_committed_since,
        get_sell_eth_committed_since,
        get_withdrawal_eth_committed_since,
    )

    since_iso = since.isoformat()
    withdrawals = get_withdrawal_eth_committed_since(since_iso)
    sell = get_sell_eth_committed_since(since_iso)
    exchange = get_exchange_eth_committed_since(since_iso)
    aware = since.astimezone()
    return {
        "since": aware.isoformat(),
        "timezone": aware.tzname(),
        "withdrawals_eth": _money_str(withdrawals),
        "sell_eth": _money_str(sell),
        "exchange_eth": _money_str(exchange),
        "total_eth": _money_str(withdrawals + sell + exchange),
    }


@bridge_router.get("/float")
async def bridge_float(
    _admin: Annotated[None, Depends(require_admin_api_key)] = None,
) -> dict[str, Any]:
    """Bridge ETH float: wallet balance, pending reserve, and release
    windows (CLI-5). Read-only — the balance is an eth_getBalance call on
    the configured RPC; ledger figures come from the same reserve/committed
    helpers the monitors use.

    Admin-keyed like /settlements: reserve and committed totals reveal the
    bridge's in-flight payment book. ``windows.today`` starts at UTC
    midnight; each window reports ``since`` with the host's zone name in
    ``timezone``. ``windows.last_24h`` is the rolling 24h window the sell
    day-cap itself uses. Ledger stamps are aware UTC (#1575); pre-#1575
    naive host-local rows can skew a window boundary by the host's UTC
    offset — bounded and documented."""
    from .bridge_withdraw_monitor import _eth_balance, _pending_eth_reserve

    address = os.getenv("ETH_WALLET_ADDRESS", "")
    balance: Decimal | None = None
    balance_error: str | None = None
    if address:
        try:
            balance = await _eth_balance(address)
        except Exception as e:  # noqa: BLE001 - provider hiccup must not blank the float view — ledger stays authoritative
            # A provider hiccup must not blank the whole float view — the
            # ledger-side numbers below stay authoritative either way.
            balance_error = redact_text(str(e))
    reserve = _pending_eth_reserve()
    available = balance - reserve if balance is not None else None

    now = utc_now()
    windows = {
        "today": _release_window(now.replace(hour=0, minute=0, second=0, microsecond=0)),
        "last_24h": _release_window(now - timedelta(hours=24)),
    }
    cap = Decimal(os.getenv("SELL_MAX_ETH_PER_DAY", "0.03"))
    sell_committed = Decimal(windows["last_24h"]["sell_eth"])
    return {
        "eth_address": address,
        "balance_eth": _money_str(balance) if balance is not None else None,
        "balance_error": balance_error,
        "pending_reserve_eth": _money_str(reserve),
        "available_eth": _money_str(available) if available is not None else None,
        "windows": windows,
        "sell_daily_cap": {
            "max_eth_per_day": _money_str(cap),
            "committed_24h": _money_str(sell_committed),
            "remaining": _money_str(max(cap - sell_committed, Decimal(0))),
            "window": "rolling 24h",
        },
    }


@bridge_router.get("/sell/config-status")
def bridge_sell_config_status(
    _admin: Annotated[None, Depends(require_admin_api_key)] = None,
) -> dict[str, Any]:
    """Sell-lane enablement + non-secret config (CLI-5).

    The sell lane's enabled/disabled state readable without journald —
    sell_status_document() carries the fail-closed (enabled, reason) pair
    and redacts key slots to configured booleans. Admin-keyed: config
    internals are operator information, not a participants board."""
    from .sell_escrow_monitor import sell_status_document

    return sell_status_document()
