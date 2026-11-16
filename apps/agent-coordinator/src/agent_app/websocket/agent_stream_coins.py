"""Coin-request grant flow for the agent WebSocket stream (#1860 Phase 6 split).

Pure-move split of the REQUEST_COINS section of ``agent_stream.py``: the
coin-request ledger helpers (``_agent_db_conn`` and friends), the
budget-gated claim path, the approval-strategy repeat path, and
``request_coins_handler`` itself now live here. ``agent_stream.py``
re-exports every name moved here, so ``agent_stream.<name>`` — including
the private helpers the coin-grant tests drive — is unchanged.

Patch-sensitive reads are routed through the ``agent_stream`` module
object (``_agent_stream.``) exactly like the state-transition mixins do,
so ``monkeypatch.setattr(agent_stream, ...)`` on ``TransactionService``,
``_submit_transaction``, ``_record_pending_coin_request``,
``_has_received_initial_coins`` and ``_get_approval_strategy`` keeps
working. ``logger`` and ``_OPS_ERRORS`` are imported from ``agent_stream``
so log records and the expected-failure tuple stay identical.

Import ``agent_app.websocket.agent_stream`` first (it wires these names
into its namespace); this module is not meant to be imported directly.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from fastapi import WebSocket

from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS, ait_to_units, units_to_ait

from . import agent_stream as _agent_stream
from .agent_stream import _OPS_ERRORS, ConnectionManager, logger

# ── Coin transfer constants ──────────────────────────────────
INITIAL_COIN_AMOUNT = ait_to_units(3)  # AIT granted automatically on first request per node (3 AIT)
TRANSACTION_FEE = DEFAULT_TX_FEE_UNITS  # blockchain transaction fee (matches RPC default, 0.01 AIT)


def _has_received_initial_coins(sender: str, wallet_address: str) -> bool | None:
    """Check whether this destination — or this agent — has already received initial coins.

    Keyed on the destination as well as the sender (V23-67). `sender` is a self-declared
    string on an inbound message and nothing ties it to an identity, so keying on it alone
    meant a caller could take a second automatic grant to the same wallet by renaming itself.
    This path matters more than the registration one: it signs and submits on the spot, so a
    bypass here is a payout rather than a row waiting for an operator.

    Returns ``None`` when the ledger cannot be read at all (#1082) — an
    unanswerable lookup must park the request, not wave it through.

    Approved rows count whether or not they carry a transaction hash. The old query required
    one, which was defensible while this handler was the only way to create a request — it
    pays microseconds after approving, so there was no window. `/register` is now a second
    way in and it writes approved rows that stay unexecuted until an operator runs `execute`,
    and those rows have to count here too or the same wallet collects from both paths.
    """
    conn = _agent_db_conn()
    if conn is None:
        return None
    try:
        from ..services.coin_request_policy import address_spellings

        spellings = address_spellings(wallet_address)
        # The f-string interpolates a run of `?` placeholders, one per spelling -- never a
        # value. Every address still arrives through the parameter tuple below. sqlite3 has
        # no way to bind a variable-length IN list, so building the placeholders is the
        # supported idiom; bandit cannot tell it from string-concatenated SQL.
        placeholders = ",".join("?" * len(spellings))
        cursor = conn.execute(
            "SELECT COUNT(*) FROM coin_requests WHERE status IN ('APPROVED') "  # nosec
            f"AND (sender = ? OR lower(wallet_address) IN ({placeholders}))",
            (sender, *spellings),
        )
        count = cursor.fetchone()[0]
        conn.close()
        return bool(count > 0)
    except _OPS_ERRORS as e:
        logger.warning("Could not query coin_requests DB: %s", e)
        return None


def _submit_transaction(transaction: dict[str, Any]) -> dict[str, Any] | None:
    """Submit a signed transaction to the blockchain RPC."""
    try:
        rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", BLOCKCHAIN_RPC_URL)
        import httpx  # noqa: F811 — lazy rebind keeps sys.modules stubs working in tests

        # Ensure chain_id is present in the transaction body
        if "chain_id" not in transaction or not transaction.get("chain_id"):
            transaction["chain_id"] = os.getenv("CHAIN_ID", "")

        resp = httpx.post(f"{rpc_url}/rpc/transaction", json=transaction, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        logger.info("Transaction submitted: %s", result)
        return cast(dict[str, Any], result)
    except _OPS_ERRORS as e:
        logger.error("Failed to submit transaction: %s", e)
        return None


# The agent DB and the SQLAlchemy ``CoinRequest`` table are the SAME sqlite file and the
# SAME ``coin_requests`` table (``aitbc.db.agent_db.get_db_path`` resolves the identical
# AGENT_DB_PATH/HERMES_DB_PATH env vars). This raw writer therefore has to produce rows the
# ORM can read and a table the ORM can write: the schema below carries every column
# ``aitbc.models.coin_request.CoinRequest`` declares, and ``_ensure_agent_db_columns``
# upgrades databases where this narrower schema was created first (#1604 — a raw-created
# table missing ``rejection_reason``/``signed_transaction`` made every ORM INSERT fail with
# "no such column"). Status strings match the ORM's stored enum names ('APPROVED',
# 'PENDING', 'FAILED'), which is what lets ``has_prior_grant`` and the rolling budgets in
# ``coin_request_policy`` see WS-granted rows without a second store (#1542).
_AGENT_DB_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS coin_requests (id TEXT, sender TEXT, recipient TEXT, amount INTEGER, "
    "wallet_address TEXT, status TEXT, approval_mode TEXT, approved_by TEXT, approved_at TEXT, "
    "created_at TEXT, expires_at TEXT, transaction_hash TEXT, audit_log TEXT, "
    "rejection_reason TEXT, signed_transaction TEXT)"
)

# Columns the ORM model declares that the historical raw schema lacked. Only nullable
# columns may be ALTER-added; anything else missing means the file is not a coin-request
# ledger at all and the caller's park-on-unreadable path takes over.
_AGENT_DB_COMPAT_COLUMNS = {"rejection_reason": "TEXT", "signed_transaction": "TEXT"}

# #1658: bounded retries for the fresh-file first-open lock race — 10 attempts
# with 50–500 ms linear backoff covers the schema-create window without
# stalling a genuinely broken store for long.
_AGENT_DB_OPEN_ATTEMPTS = 10


def _ensure_agent_db_columns(conn: sqlite3.Connection) -> None:
    """Bring a pre-existing ``coin_requests`` table up to the ORM column set.

    Idempotent: PRAGMA table_info + ALTER TABLE ADD COLUMN only for columns still
    missing, so every process start and every grant is a no-op once converged.
    """
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(coin_requests)")}
    except sqlite3.Error as e:
        logger.warning("Could not inspect coin_requests schema: %s", e)
        return
    for name, decl in _AGENT_DB_COMPAT_COLUMNS.items():
        if name not in existing:
            # nosec B608 - identifiers come from the static _AGENT_DB_COMPAT_COLUMNS map
            try:
                conn.execute(f"ALTER TABLE coin_requests ADD COLUMN {name} {decl}")
            except sqlite3.OperationalError as e:
                # Concurrent openers race the same ALTER: the loser sees
                # 'duplicate column name' even though the column now exists —
                # that is convergence, not failure (#v11 item 9). Any other
                # operational error still propagates to the open retry loop.
                if "duplicate column" not in str(e).lower():
                    raise
            else:
                logger.info("Added missing column %s to agent coin_requests ledger", name)


def _agent_db_conn() -> sqlite3.Connection | None:
    """Open the agent coin-request DB, creating the table on a fresh node.

    Returns ``None`` when the store exists but cannot be opened or written —
    the callers then park instead of paying blind (#1082). The connection is in
    autocommit mode (``isolation_level=None``) so the first-grant claim path can
    take an explicit ``BEGIN IMMEDIATE`` write lock around its check-and-insert.
    """
    db_path = os.getenv("AGENT_DB_PATH", os.getenv("HERMES_DB_PATH", "/var/lib/aitbc/data/agent_coin_requests.db"))
    last_error: Exception | None = None
    # #1658: N workers opening a FRESH file race the journal_mode/CREATE TABLE
    # first writes; busy_timeout does not cover that schema-lock window, so a
    # legitimate first grant used to fail closed with 'database is locked'.
    # Retry the whole open briefly before declaring the ledger unwritable.
    for attempt in range(_AGENT_DB_OPEN_ATTEMPTS):
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
            # #1560: WAL + busy_timeout on the coin-request ledger.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(_AGENT_DB_SCHEMA)
            _ensure_agent_db_columns(conn)
            return conn
        except _OPS_ERRORS as e:
            last_error = e
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            locked = isinstance(e, sqlite3.OperationalError) and "locked" in str(e).lower()
            if not locked or attempt + 1 >= _AGENT_DB_OPEN_ATTEMPTS:
                break
            time.sleep(0.05 * (attempt + 1))
    logger.warning("Could not open coin-request ledger %s: %s", db_path, last_error)
    return None


def _record_coin_request(sender: str, amount: int, wallet_address: str, tx_hash: str) -> None:
    """Record the auto-approved coin request in the agent SQLite database."""
    conn = _agent_db_conn()
    if conn is None:
        return
    try:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC).replace(tzinfo=None)
        conn.execute(
            "INSERT INTO coin_requests (id, sender, recipient, amount, wallet_address, status, "
            "approval_mode, approved_by, approved_at, created_at, expires_at, transaction_hash, audit_log) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"auto-{sender}-{int(now.timestamp())}",
                sender,
                os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
                amount,
                wallet_address,
                "APPROVED",
                "automatic",
                "request_coins_handler",
                now.isoformat(),
                now.isoformat(),
                (now + timedelta(hours=24)).isoformat(),
                tx_hash,
                json.dumps({"action": "initial_coin_grant", "auto_approved": True}),
            ),
        )
        conn.commit()
        conn.close()
        logger.info("Recorded coin request in agent DB for %s", sender)
    except _OPS_ERRORS as e:
        logger.warning("Could not record coin request in DB: %s", e)


def _record_claiming_coin_request(
    sender: str, amount: int, wallet_address: str, *, first_grant: bool = False
) -> tuple[str | None, bool]:
    """Insert the request row BEFORE paying it, claim marker in transaction_hash.

    The ``claiming:<ts>`` marker is the same convention /register's execute
    path uses (EXECUTION_CLAIM_PREFIX): the row proves the hub committed to
    this payout *before* signing, so a crash mid-send leaves a findable claim
    instead of an unrecorded payout.

    Returns ``(request_id, already_granted)``:

    - ``(id, False)`` — the claim row is committed; the caller may pay.
    - ``(None, False)`` — the ledger could not be written; the caller must
      NOT pay (same contract as the old ``None`` return).
    - ``(None, True)`` — only possible with ``first_grant=True``: the
      prior-grant check and the INSERT ran inside one ``BEGIN IMMEDIATE``
      transaction, and an APPROVED row for this sender or wallet was already
      there. SQLite serializes writers, so exactly one of N concurrent
      first-grant claims across workers can win; the losers must park for
      review instead of paying (#1542 dual-ledger, #1604).

    ``first_grant`` stays False on the strategy-approved path: a repeat grant
    there is legitimate (the strategy already ruled on it and the rolling
    budget bounds the aggregate), so only the unguarded first-grant path
    needs the atomic "no prior APPROVED" gate.
    """
    conn = _agent_db_conn()
    if conn is None:
        return None, False
    try:
        from datetime import UTC, datetime, timedelta

        from ..services.coin_request_policy import address_spellings

        now = datetime.now(UTC).replace(tzinfo=None)
        request_id = f"auto-{sender}-{uuid4().hex[:12]}"
        insert_sql = (
            "INSERT INTO coin_requests (id, sender, recipient, amount, wallet_address, status, "
            "approval_mode, approved_by, approved_at, created_at, expires_at, transaction_hash, audit_log) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        insert_params = (
            request_id,
            sender,
            os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
            amount,
            wallet_address,
            "APPROVED",
            "automatic",
            "request_coins_handler",
            now.isoformat(),
            now.isoformat(),
            (now + timedelta(hours=24)).isoformat(),
            f"claiming:{now.isoformat()}",
            json.dumps({"action": "initial_coin_grant", "auto_approved": True}),
        )
        if first_grant:
            # BEGIN IMMEDIATE takes the sqlite write lock up front, so the
            # EXISTS probe and the INSERT are one atomic step against every
            # other connection — including other uvicorn workers on the same
            # host sharing this file. Without it two workers can both pass the
            # earlier SELECT-then-INSERT check and both pay (#1542).
            conn.execute("BEGIN IMMEDIATE")
            try:
                spellings = address_spellings(wallet_address)
                # `?` placeholders, one per spelling — values still bind through
                # the parameter tuple; same idiom as _has_received_initial_coins.
                placeholders = ",".join("?" * len(spellings))
                exists = conn.execute(
                    "SELECT 1 FROM coin_requests WHERE status = 'APPROVED' "  # nosec
                    f"AND (sender = ? OR lower(wallet_address) IN ({placeholders})) LIMIT 1",
                    (sender, *spellings),
                ).fetchone()
                if exists is not None:
                    conn.execute("ROLLBACK")
                    conn.close()
                    return None, True
                conn.execute(insert_sql, insert_params)
                conn.execute("COMMIT")
            except Exception:  # noqa: BLE001 — rollback must be attempted for any failure inside the write tx
                try:
                    conn.execute("ROLLBACK")
                except _OPS_ERRORS as rb_err:
                    logger.debug("coin-request rollback failed: %s", rb_err)
                raise
        else:
            conn.execute(insert_sql, insert_params)
        conn.close()
        return request_id, False
    except _OPS_ERRORS as e:
        logger.warning("Could not write claiming coin request in DB: %s", e)
        return None, False


def _claim_budget_gate(conn, amount: int, hour_since: str, day_since: str) -> str | None:
    """Rolling hourly/daily auto-grant budget check inside the claim's
    BEGIN IMMEDIATE transaction.

    Emits the same gauges/trip counters ``ws_budget_allows`` produced so
    the alerting that watches them sees identical series. Returns a
    human-readable deny reason, or ``None`` when the grant fits.
    """
    from ..monitoring.prometheus_metrics import metrics_registry
    from ..services import coin_request_policy as policy

    def _spent(since_iso: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM coin_requests WHERE status = 'APPROVED' "
            "AND approval_mode = 'automatic' AND created_at >= ?",  # nosec B608 - static SQL, param tuple
            (since_iso,),
        ).fetchone()
        return int(row[0] or 0)

    hour_spent = _spent(hour_since)
    day_spent = _spent(day_since)
    gauge = metrics_registry.gauge(
        "coin_request_auto_granted_window", "Automatic coin grants in the rolling window", ["window"]
    )
    gauge.set(float(hour_spent), window="hourly")
    gauge.set(float(day_spent), window="daily")

    for window, spent, budget, label in (
        ("hourly", hour_spent, policy.auto_budget_per_hour(), "hourly"),
        ("daily", day_spent, policy.auto_budget_per_day(), "daily"),
    ):
        if spent + amount > budget:
            metrics_registry.counter(
                "coin_request_auto_budget_trips_total",
                "Requests parked by an exhausted automatic budget",
                ["window"],
            ).inc(window=window)
            logger.warning(
                "WS coin-request %s budget exceeded: %s + %s > %s — parked for review",
                label,
                spent,
                amount,
                budget,
            )
            return f"the automatic {label} budget is exhausted"
    return None


def _budgeted_claim_coin_request(
    sender: str, amount: int, wallet_address: str, *, first_grant: bool = False
) -> tuple[str | None, str, str | None]:
    """Atomically check the rolling auto-grant budgets AND insert the claim row.

    ``ws_budget_allows`` + ``_record_claiming_coin_request`` ran as two
    separate transactions on separate connections: two concurrent grants
    could both read the same ``spent`` total, both pass the budget check,
    and both pay — the hourly/daily budget overshot by the loser (#1658
    sibling residual). ``BEGIN IMMEDIATE`` here covers the SUM reads and
    the INSERT in one write-locked step, so SQLite serializes the
    check-and-claim across every connection and worker, exactly like the
    first-grant prior-grant probe already did.

    Returns ``(request_id, outcome, reason)``:

    - ``("auto-...", "claimed", None)`` — claim committed; caller may pay.
    - ``(None, "budget", "<reason>")`` — a rolling budget would be exceeded;
      nothing was written.
    - ``(None, "prior_grant", None)`` — ``first_grant`` only: an APPROVED row
      for this sender/wallet already exists.
    - ``(None, "unavailable", None)`` — the ledger could not be opened or
      written; the caller must NOT pay.
    """
    conn = _agent_db_conn()
    if conn is None:
        return None, "unavailable", None
    try:
        from datetime import UTC, datetime, timedelta

        from ..services import coin_request_policy as policy

        now = datetime.now(UTC).replace(tzinfo=None)
        hour_since = (now - timedelta(hours=1)).isoformat()
        day_since = (now - timedelta(hours=24)).isoformat()
        request_id = f"auto-{sender}-{uuid4().hex[:12]}"
        insert_sql = (
            "INSERT INTO coin_requests (id, sender, recipient, amount, wallet_address, status, "
            "approval_mode, approved_by, approved_at, created_at, expires_at, transaction_hash, audit_log) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        insert_params = (
            request_id,
            sender,
            os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
            amount,
            wallet_address,
            "APPROVED",
            "automatic",
            "request_coins_handler",
            now.isoformat(),
            now.isoformat(),
            (now + timedelta(hours=24)).isoformat(),
            f"claiming:{now.isoformat()}",
            json.dumps({"action": "initial_coin_grant", "auto_approved": True}),
        )

        # BEGIN IMMEDIATE takes the sqlite write lock up front, so the budget
        # SUMs, the optional prior-grant probe and the INSERT are one atomic
        # step against every other connection — including other uvicorn
        # workers on the same host sharing this file.
        conn.execute("BEGIN IMMEDIATE")
        try:
            budget_reason = _claim_budget_gate(conn, amount, hour_since, day_since)
            if budget_reason is not None:
                conn.execute("ROLLBACK")
                conn.close()
                return None, "budget", budget_reason

            if first_grant:
                # Same EXISTS probe _record_claiming_coin_request ran — now
                # inside the same write lock as the budget reads, so a loser
                # of the race cannot slip a grant between check and insert.
                spellings = policy.address_spellings(wallet_address)
                placeholders = ",".join("?" * len(spellings))
                exists = conn.execute(
                    "SELECT 1 FROM coin_requests WHERE status = 'APPROVED' "  # nosec
                    f"AND (sender = ? OR lower(wallet_address) IN ({placeholders})) LIMIT 1",
                    (sender, *spellings),
                ).fetchone()
                if exists is not None:
                    conn.execute("ROLLBACK")
                    conn.close()
                    return None, "prior_grant", None

            conn.execute(insert_sql, insert_params)
            conn.execute("COMMIT")
            conn.close()
            return request_id, "claimed", None
        except Exception:  # noqa: BLE001 — rollback must be attempted for any failure inside the write tx
            try:
                conn.execute("ROLLBACK")
            except _OPS_ERRORS as rb_err:
                logger.debug("coin-request rollback failed: %s", rb_err)
            raise
    except _OPS_ERRORS as e:
        try:
            conn.close()
        except _OPS_ERRORS as close_err:
            logger.debug("coin-request conn close failed: %s", close_err)
        logger.warning("Could not write budgeted coin-request claim in DB: %s", e)
        return None, "unavailable", None


def _finish_claimed_coin_request(request_id: str, tx_hash: str, *, failed: bool = False) -> None:
    """Replace the claim marker with the real tx hash, or mark the claim FAILED.

    Both paths compare-and-swap on the in-flight claim (#1812 / #1424): only an
    APPROVED row still carrying a ``claiming:`` marker may be finished — a stale
    failure marker cannot clobber a completed payout.
    """
    _claim_cas = "status = 'APPROVED' AND transaction_hash LIKE 'claiming:%'"
    conn = _agent_db_conn()
    if conn is None:
        return
    try:
        if failed:
            conn.execute(
                f"UPDATE coin_requests SET status = 'FAILED' WHERE id = ? AND {_claim_cas}",  # nosec
                (request_id,),
            )
        else:
            conn.execute(
                f"UPDATE coin_requests SET transaction_hash = ? WHERE id = ? AND {_claim_cas}",  # nosec
                (tx_hash, request_id),
            )
        conn.commit()
        conn.close()
    except _OPS_ERRORS as e:
        logger.warning("Could not finish claiming coin request %s: %s", request_id, e)


def _record_pending_coin_request(sender: str, amount: int, wallet_address: str) -> str:
    """Record a pending coin request in the agent SQLite database for manual approval.

    Returns the request_id so the handler can include it in the response.
    """
    conn = _agent_db_conn()
    if conn is None:
        return f"req-{sender}-unknown"
    try:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC).replace(tzinfo=None)
        request_id = f"req-{sender}-{uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO coin_requests (id, sender, recipient, amount, wallet_address, status, "
            "approval_mode, created_at, expires_at, audit_log) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                sender,
                os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
                amount,
                wallet_address,
                "PENDING",
                "manual",
                now.isoformat(),
                (now + timedelta(hours=24)).isoformat(),
                json.dumps({"action": "subsequent_coin_request", "auto_approved": False}),
            ),
        )
        conn.commit()
        conn.close()
        logger.info("Recorded pending coin request %s for %s", request_id, sender)
        return request_id
    except _OPS_ERRORS as e:
        logger.warning("Could not record pending coin request in DB: %s", e)
        return f"req-{sender}-unknown"


def _wallet_match(authenticated: str | None, requested: str) -> bool:
    """True iff the requested payout address equals the authenticated wallet.

    Comparison goes through ``canonical_address`` so EIP-55 case differences
    cannot fail a legitimate match; a missing authenticated wallet or a
    malformed requested address never matches.
    """
    if not authenticated or not requested:
        return False
    from aitbc.crypto.signature_recovery import canonical_address

    return canonical_address(authenticated) == canonical_address(requested)


def _parse_coin_request(content: str, sender: str) -> tuple[Any, str]:
    """Extract ``(amount, wallet_address)`` from a REQUEST_COINS payload."""
    if "{" in content:
        json_part = content[content.index("{") :]
        data = json.loads(json_part)
        return data.get("amount", 0), data.get("wallet_address", "")
    return INITIAL_COIN_AMOUNT, sender


def _pending_coin_response(
    sender: str, amount: int, wallet_address: str, reason: str | None, extra_message: str = ""
) -> dict[str, Any]:
    """Parked-for-review response; also writes the PENDING ledger row."""
    return {
        "action": "coin_request_received",
        "request_id": _agent_stream._record_pending_coin_request(sender, amount, wallet_address),
        "amount": amount,
        "wallet_address": wallet_address,
        "status": "pending_approval",
        "reason": reason,
        "message": f"Coin request requires approval. Reason: {reason}.{extra_message}",
    }


def _wallet_mismatch_response(
    sender: str, wallet_address: str, connection_manager: ConnectionManager
) -> dict[str, Any] | None:
    """Phase C payout-address gate. ``None`` means the request may proceed.

    In enforce mode the requested payout address must equal the connection's
    authenticated wallet — the registry-bound identity the ``?token=``
    principal proved it controls. An unauthenticated connection (or an
    operator principal, which carries no wallet) cannot name an address;
    advisory logs ``coin_wallet_mismatch`` and allows; disabled keeps the
    pre-auth behaviour.
    """
    from ..config import settings

    mode = settings.agent_msg_signature_mode
    if mode == "disabled":
        return None
    auth_wallet = connection_manager.connection_wallets.get(sender)
    if _wallet_match(auth_wallet, wallet_address):
        return None
    logger.warning(
        "coin_wallet_mismatch sender=%s auth_wallet=%s requested=%s mode=%s",
        sender,
        auth_wallet,
        wallet_address,
        mode,
    )
    if mode == "enforce":
        return {
            "action": "coin_request_failed",
            "error": "wallet_mismatch",
            "message": "wallet_address must equal the connection's authenticated wallet",
        }
    return None


def _sign_submit_claim(wallet_address: str, amount: int, claim_id: str) -> tuple[str, dict[str, Any] | None]:
    """Sign and submit a claimed grant. ``(tx_hash, None)`` or ``("", error)``.

    Every failure path marks the claim FAILED so the ledger never shows an
    in-flight claim for a payout that did not happen.
    """
    transaction = _agent_stream.TransactionService().generate_signed_transaction(wallet_address, amount)
    if not transaction:
        _finish_claimed_coin_request(claim_id, "", failed=True)
        return "", {"action": "coin_request_failed", "error": "Failed to generate signed transaction"}
    result = _agent_stream._submit_transaction(transaction)
    if not result or not result.get("success"):
        _finish_claimed_coin_request(claim_id, "", failed=True)
        return "", {"action": "coin_request_failed", "error": "Blockchain rejected transaction", "detail": result}
    tx_hash = result.get("transaction_hash", "")
    _finish_claimed_coin_request(claim_id, tx_hash)
    return tx_hash, None


async def _grant_confirmation(
    connection_manager: ConnectionManager,
    sender: str,
    wallet_address: str,
    amount: int,
    tx_hash: str,
    content: str,
) -> None:
    confirmation = {
        "type": "COINS_TRANSFERRED",
        "sender": os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
        "recipient": sender,
        "content": content,
        "amount": amount,
        "wallet_address": wallet_address,
        "transaction_hash": tx_hash,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await connection_manager.send_personal_message(confirmation, sender)


async def _repeat_coin_request(
    sender: str, amount: int, wallet_address: str, connection_manager: ConnectionManager
) -> dict[str, Any]:
    """Approval-strategy path for a sender that already holds a grant."""
    strategy, _approval_mode = _agent_stream._get_approval_strategy()
    approval_request = {
        "id": f"req-{sender}-{int(datetime.now(UTC).timestamp())}",
        "sender": sender,
        "recipient": os.getenv("AGENT_ID", os.getenv("HERMES_AGENT_ID", "hub-coordinator")),
        "amount": amount,
        "wallet_address": wallet_address,
        "created_at": datetime.now(UTC),
    }
    approval_decision = strategy.approve(approval_request)
    if not approval_decision["approved"]:
        # Strategy rejected or pending — record in DB for manual review
        return _pending_coin_response(
            sender,
            amount,
            wallet_address,
            approval_decision["reason"],
            " Use 'aitbc coin-requests approve <request_id>' to approve.",
        )

    # Budget check and claim insert are ONE BEGIN IMMEDIATE transaction
    # (#1658 sibling): the old ws_budget_allows + _record_claiming_coin_request
    # pair let two concurrent grants both pass the same 'spent' read and both
    # pay. Repeat grants are legitimate here (the strategy ruled on them), so
    # no first-grant dedupe gate.
    claim_id, outcome, why = _budgeted_claim_coin_request(sender, amount, wallet_address)
    if outcome == "budget":
        return _pending_coin_response(sender, amount, wallet_address, why)
    if claim_id is None:
        return {
            "action": "coin_request_failed",
            "error": "coin-request ledger unavailable — not paying without a record",
        }
    tx_hash, err = _sign_submit_claim(wallet_address, amount, claim_id)
    if err is not None:
        return err
    await _grant_confirmation(
        connection_manager,
        sender,
        wallet_address,
        amount,
        tx_hash,
        f"Coin request approved: {units_to_ait(amount)} AIT to {wallet_address}. Transaction: {tx_hash}",
    )
    return {
        "action": "coins_transferred",
        "amount": amount,
        "wallet_address": wallet_address,
        "transaction_hash": tx_hash,
        "status": "completed",
        "reason": approval_decision["reason"],
    }


async def _first_coin_request(sender: str, wallet_address: str, connection_manager: ConnectionManager) -> dict[str, Any]:
    """First-time request: auto-transfer initial coins through the rolling
    hourly/daily budget, atomically with the claim insert (#837/#1658)."""
    claim_id, outcome, why = _budgeted_claim_coin_request(sender, INITIAL_COIN_AMOUNT, wallet_address, first_grant=True)
    if outcome == "budget":
        return _pending_coin_response(sender, INITIAL_COIN_AMOUNT, wallet_address, why)

    # The row exists BEFORE the payout (#1082): a claim marker stands in for
    # the tx hash so a mid-send crash leaves a findable claim instead of an
    # unrecorded payout. The fused claim runs the prior-grant probe inside the
    # same IMMEDIATE transaction as the budget reads, so a second worker
    # racing the same wallet loses atomically instead of double-paying
    # (#1542/#1604) and cannot overspend the budget.
    if outcome == "prior_grant":
        # Lost the race: another claim for this sender/wallet committed
        # between the earlier probe and this insert. Park for review exactly
        # like a detected prior grant — never pay twice.
        return _pending_coin_response(
            sender,
            INITIAL_COIN_AMOUNT,
            wallet_address,
            "a coin grant for this wallet is already recorded",
        )
    if claim_id is None:
        return {
            "action": "coin_request_failed",
            "error": "coin-request ledger unavailable — not paying without a record",
        }

    grant_amount = INITIAL_COIN_AMOUNT
    logger.info(
        "First-time coin request from %s — auto-transferring %s AIT to %s",
        sender,
        grant_amount,
        wallet_address,
    )
    tx_hash, err = _sign_submit_claim(wallet_address, grant_amount, claim_id)
    if err is not None:
        return err
    await _grant_confirmation(
        connection_manager,
        sender,
        wallet_address,
        grant_amount,
        tx_hash,
        f"Transferred {units_to_ait(grant_amount)} AIT to {wallet_address}",
    )
    return {
        "action": "coins_transferred",
        "amount": grant_amount,
        "wallet_address": wallet_address,
        "transaction_hash": tx_hash,
        "status": "completed",
    }


async def request_coins_handler(
    message: dict[str, Any], connection_manager: ConnectionManager, websocket: WebSocket
) -> dict[str, Any]:
    """Handle REQUEST_COINS messages.

    First request from a node: auto-transfer 3 AIT without approval.
    Subsequent requests: return pending_approval for manual review.
    """
    sender = message.get("sender_id", "unknown")
    content = message.get("content", "")
    logger.info("REQUEST_COINS received from %s: %s", sender, content)
    try:
        amount, wallet_address = _parse_coin_request(content, sender)

        # #837: the amount is caller-supplied JSON — it must be a positive int
        # inside the automatic ceiling before anything signs with it.
        from ..services.coin_request_policy import auto_approve_ceiling

        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            return {"action": "coin_request_failed", "error": "amount must be a positive integer of compute-units"}
        if amount > auto_approve_ceiling():
            return {"action": "coin_request_failed", "error": "amount is above the automatic ceiling"}

        if not wallet_address or wallet_address == "unknown":
            return {"action": "coin_request_failed", "error": "No wallet address provided"}

        gate = _wallet_mismatch_response(sender, wallet_address, connection_manager)
        if gate is not None:
            return gate

        # Check if this sender has already received initial coins. An
        # unreadable ledger is not "no prior grant" — park for review (#1082).
        prior = _agent_stream._has_received_initial_coins(sender, wallet_address)
        if prior is None:
            return _pending_coin_response(sender, amount, wallet_address, "the coin-request ledger is unreadable")
        if prior:
            logger.info("Coin request from %s: already received initial coins — running approval strategy", sender)
            return await _repeat_coin_request(sender, amount, wallet_address, connection_manager)
        return await _first_coin_request(sender, wallet_address, connection_manager)
    except _OPS_ERRORS as e:
        logger.error("Failed to process coin request: %s", e)
        return {"action": "coin_request_failed", "error": str(e)}
