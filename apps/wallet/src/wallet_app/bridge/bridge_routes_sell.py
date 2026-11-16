"""Sell-quote/lock route helpers, extracted from ``bridge_routes.py`` (#1860).

``_normalize_sell_quote`` / ``_normalize_sell_lock`` shape sell rows for the
sell status/list routes, which stay in ``bridge_routes`` and resolve these
names through its namespace (re-exported below). ``_sell_gate`` and
``_check_sell_quote_rate_limit`` are likewise called by ``bridge_sell_quote``
through ``bridge_routes`` globals, so test monkeypatches on
``wallet_app.bridge.bridge_routes`` keep intercepting them exactly as before.
"""

import logging
import os
from typing import Any

from fastapi import HTTPException

from wallet_app.utc_time import parse_stored, utc_now

from .bridge_db import (
    _money_str,
    count_open_sell_quotes,
    get_latest_sell_quote_by_shop,
)
from .url_redact import redact_text

# Same logger name as ``wallet_app.bridge.bridge_routes`` so log records —
# and caplog filters on that logger — are unchanged after the move.
logger = logging.getLogger("wallet_app.bridge.bridge_routes")


def _normalize_sell_quote(quote: dict[str, Any]) -> dict[str, Any]:
    return {
        "quote_id": quote.get("id"),
        "shop_ait_address": quote.get("shop_ait_address"),
        "shop_eth_address": quote.get("shop_eth_address"),
        "ait_amount": _money_str(quote.get("ait_amount")),
        "rate": _money_str(quote.get("rate_eth_usd")),
        "fee_ait": _money_str(quote.get("fee_ait")),
        "eth_amount": _money_str(quote.get("eth_amount")),
        "status": quote.get("status"),
        "expires_at": quote.get("expires_at"),
        "created_at": quote.get("created_at"),
    }


def _normalize_sell_lock(lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": lock.get("id"),
        "quote_id": lock.get("quote_id"),
        "ait_tx_hash": lock.get("ait_tx_hash"),
        "shop_ait_address": lock.get("shop_ait_address"),
        "shop_eth_address": lock.get("shop_eth_address"),
        "ait_amount": _money_str(lock.get("amount_ait")),
        "eth_amount": _money_str(lock.get("eth_amount")),
        "requoted": bool(lock.get("requoted")),
        "status": lock.get("status"),
        "eth_tx_hash": lock.get("eth_tx_hash"),
        "settle_tx_hash": lock.get("settle_tx_hash"),
        "refund_tx_hash": lock.get("refund_tx_hash"),
        "locked_height": lock.get("locked_height"),
        "error": lock.get("error"),
        "created_at": lock.get("created_at"),
        "released_at": lock.get("released_at"),
        "settled_at": lock.get("settled_at"),
        "refunded_at": lock.get("refunded_at"),
    }


def _sell_gate() -> None:
    """Fail closed: no sell feature when the escrow is unconfigured."""
    from .sell_escrow_monitor import sell_config_status

    enabled, reason = sell_config_status()
    if not enabled:
        logger.warning("Sell escrow disabled: %s", redact_text(reason))
        raise HTTPException(status_code=503, detail="Sell escrow disabled")


def _check_sell_quote_rate_limit(ait_address: str) -> None:
    """Per-shop limits: open-quote cap and a minimum interval between quotes."""
    try:
        max_open = int(os.getenv("SELL_MAX_OPEN_QUOTES_PER_SHOP", "5"))
    except (TypeError, ValueError):
        max_open = 5
    if count_open_sell_quotes(ait_address) >= max_open:
        raise HTTPException(
            status_code=429,
            detail=f"Too many open sell quotes for this shop (max {max_open}) — let one expire or lock first",
        )
    try:
        min_interval = int(os.getenv("SELL_QUOTE_MIN_INTERVAL_SECONDS", "30"))
    except (TypeError, ValueError):
        min_interval = 30
    latest = get_latest_sell_quote_by_shop(ait_address)
    if latest and latest.get("created_at"):
        try:
            waited = (utc_now() - parse_stored(latest["created_at"])).total_seconds()
        except (TypeError, ValueError):
            waited = min_interval
        if waited < min_interval:
            raise HTTPException(
                status_code=429,
                detail=f"Quote rate limit: wait {int(min_interval - waited) + 1}s between quotes",
            )
