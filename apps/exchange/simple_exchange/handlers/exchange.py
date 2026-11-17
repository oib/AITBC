"""Exchange API facade — mixin assembly, health/ready/metrics, DB checks.

The handler bodies live in sibling modules (``exchange_queries``,
``exchange_orders``, ``exchange_settlement``, ``exchange_nodes``,
``exchange_matching``); ``ExchangeMixin`` below inherits them so every
method stays reachable (and patchable) as ``ExchangeMixin.<name>`` and
every module-level name stays importable from this module. Monetary
arithmetic uses ``Decimal`` throughout (B2 backport from v0.10.3).
Order placement and matching occur within a single ``BEGIN IMMEDIATE``
transaction to prevent race conditions (B1 backport). All database
connections are closed via ``try/finally`` (B3 backport).
"""

import os
import sqlite3
import time as time
import http.client
import urllib.error
import urllib.parse
import urllib.request  # noqa: F401 - import parity with the pre-split module
from datetime import UTC, datetime
from decimal import Decimal as Decimal, InvalidOperation
from pathlib import Path

# File-relative repo root — kept for import parity; consumers moved to
# exchange_queries.py which defines its own copy.
_REPO_ROOT = str(Path(__file__).resolve().parents[4])

from aitbc.aitbc_logging import get_logger
from aitbc.operations import BeginStatus as BeginStatus, request_hash as request_hash
from aitbc.utils.decimal import to_decimal as _to_decimal  # noqa: F401 - tests import it from this module
from aitbc_errors import AITBCError

from ..db import (
    _SETTLEMENT_STATES as _SETTLEMENT_STATES,
    connect_db,
    get_db_path,
    ticks_to_decimal as ticks_to_decimal,
    to_ticks as to_ticks,
)
from .base import (
    RPC_BASE_URL as RPC_BASE_URL,
    RPC_TIMEOUT as RPC_TIMEOUT,
    _RATE_BUCKETS as _RATE_BUCKETS,
    _RATE_LOCK as _RATE_LOCK,
    _env_int as _env_int,
    _idempotency_key as _idempotency_key,
    _rate_limit_hit as _rate_limit_hit,
    get_operation_ledger as get_operation_ledger,
    mutating_rate_limit_reached as mutating_rate_limit_reached,
)
from .exchange_helpers import (
    BAND_CACHE_TTL_S as BAND_CACHE_TTL_S,
    EXCHANGE_ORDER_PAIR as EXCHANGE_ORDER_PAIR,
    _BLOCKED_PAYOUT_CONSTANTS as _BLOCKED_PAYOUT_CONSTANTS,
    _BLOCKED_PAYOUT_ENVS as _BLOCKED_PAYOUT_ENVS,
    _CANCEL_ACTION as _CANCEL_ACTION,
    _CANCEL_ENVELOPE_FIELDS as _CANCEL_ENVELOPE_FIELDS,
    _ENV_DECIMAL_MAX as _ENV_DECIMAL_MAX,
    _MAX_PAGE_ROWS as _MAX_PAGE_ROWS,
    _MAX_REGISTRY_ROWS as _MAX_REGISTRY_ROWS,
    _ORDER_ENVELOPE_FIELDS as _ORDER_ENVELOPE_FIELDS,
    _PAYOUT_ACTION as _PAYOUT_ACTION,
    _PAYOUT_ENVELOPE_FIELDS as _PAYOUT_ENVELOPE_FIELDS,
    _REGISTER_ACTION as _REGISTER_ACTION,
    _REGISTER_ENVELOPE_FIELDS as _REGISTER_ENVELOPE_FIELDS,
    _SIGNED_INT64_MAX as _SIGNED_INT64_MAX,
    _SIDE_DESTINATION_ENV,
    _TRADE_STATE_FORWARD as _TRADE_STATE_FORWARD,
    _WATCHLIST_LOGGED as _WATCHLIST_LOGGED,
    _apply_exchange_fee as _apply_exchange_fee,
    _band_cache as _band_cache,
    _canonical_envelope_json as _canonical_envelope_json,
    _cancel_settlement_effects as _cancel_settlement_effects,
    _close_buy_debit as _close_buy_debit,
    _commit_trade_cost as _commit_trade_cost,
    _envelope_hash as _envelope_hash,
    _env_decimal as _env_decimal,
    _exchange_chain_id as _exchange_chain_id,
    _funding_destination,
    _is_int64 as _is_int64,
    _payout_address_blocked as _payout_address_blocked,
    _prepaid_spendable as _prepaid_spendable,
    _row_to_order as _row_to_order,
    _settlement_enabled,
    _short_addr as _short_addr,
    _signed_orders_required as _signed_orders_required,
    _verify_envelope_signature as _verify_envelope_signature,
)
from .exchange_matching import (
    ExchangeMatchingMixin,
    _fill_from_match as _fill_from_match,
    _insert_matched_trade as _insert_matched_trade,
    _match_candidates as _match_candidates,
    _match_fee_ait as _match_fee_ait,
    _persist_new_order as _persist_new_order,
    _sell_lock_covers as _sell_lock_covers,
)
from .exchange_nodes import ExchangeNodesMixin
from .exchange_orders import ExchangeOrdersMixin
from .exchange_queries import ExchangeQueriesMixin
from .exchange_settlement import ExchangeSettlementMixin

logger = get_logger(__name__)

# Expected failure surface for the handler-level fallbacks below: lazy
# imports (ImportError), RPC/filesystem I/O (OSError covers urllib errors,
# socket and timeout failures), request/JSON decode and Decimal conversion
# (ValueError/InvalidOperation), and data-shape errors. RuntimeError covers
# abort-style raises a handler re-aborts with; genuine BaseExceptions still
# propagate (#1862).
_OPS_ERRORS = (
    ImportError,
    OSError,
    ValueError,
    InvalidOperation,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    http.client.HTTPException,
    AITBCError,
)


class ExchangeMixin(
    ExchangeQueriesMixin,
    ExchangeOrdersMixin,
    ExchangeSettlementMixin,
    ExchangeNodesMixin,
    ExchangeMatchingMixin,
):
    """Trading, metrics, treasury, health, and wallet-balance methods.

    The domain bodies live in the exchange_* sibling mixins; this class
    keeps the service/health surface and assembles the full handler.
    """

    def health_check(self):
        """Health check"""
        self.send_json_response({"status": "ok", "timestamp": datetime.now(UTC).isoformat()})  # type: ignore[attr-defined]

    def ready_check(self):
        """Readiness probe — 503 while an enabled required feature is unavailable.

        The order book needs only its own database. The bridge deposit/withdraw
        surface is enabled by default and additionally needs the deposits store
        the bridge-monitor service initializes; deployments that do not run the
        bridge should set BRIDGE_DEPOSIT_ENABLED=false rather than be reported
        ready with dead endpoints.
        """
        from aitbc.health_checks import run_readiness_checks

        from ..config import bridge_config

        checks = {"database": _check_exchange_db}
        if bridge_config.deposit_enabled or bridge_config.withdraw_enabled:
            checks["bridge_storage"] = _check_bridge_storage
        if _settlement_enabled():
            checks["settlement_envs"] = _check_settlement_envs
        failed = run_readiness_checks(checks)
        if failed:
            self.send_json_response(  # type: ignore[attr-defined]
                {"status": "not_ready", "error": "readiness check failed", "failed": failed}, status=503
            )
            return
        self.send_json_response(  # type: ignore[attr-defined]
            {"status": "ready", "checks": sorted(checks), "timestamp": datetime.now(UTC).isoformat()}
        )

    def handle_metrics(self):
        """Prometheus metrics endpoint"""
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            output = generate_latest()
            self.send_response(200)  # type: ignore[attr-defined]
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)  # type: ignore[attr-defined]
            self.end_headers()  # type: ignore[attr-defined]
            self.wfile.write(output)  # type: ignore[attr-defined]
        except _OPS_ERRORS:
            self.send_error(500, "Internal server error")  # type: ignore[attr-defined]


def _check_exchange_db() -> None:
    """The exchange database answers a trivial query."""
    conn = connect_db(get_db_path())
    try:
        conn.execute("SELECT 1")
    finally:
        conn.close()


def _check_settlement_envs() -> None:
    """Under EXCHANGE_SETTLEMENT_ENABLED both funding destinations must be
    configured EIP-55 addresses. Placement enforces the same rule per
    side — failing readiness surfaces the misconfig once instead of
    refusing every order."""
    for env_name in _SIDE_DESTINATION_ENV.values():
        if _funding_destination(env_name) is None:
            raise RuntimeError(f"{env_name} unset or not an EIP-55 address")


def _check_bridge_storage() -> None:
    """The bridge monitor's deposits store exists and has its schema.

    Created by the bridge-monitor service, not this one — a missing file or
    missing table means deposits cannot be served, so readiness fails.
    """
    from aitbc.constants import DATA_DIR

    path = Path((os.getenv("BRIDGE_DEPOSITS_DB") or "").strip() or Path(DATA_DIR) / "data" / "bridge_deposits.db")
    if not path.exists():
        raise RuntimeError("bridge deposits database not initialized")
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='eth_deposits'").fetchone()
        if row is None:
            raise RuntimeError("bridge deposits table missing")
    finally:
        conn.close()
