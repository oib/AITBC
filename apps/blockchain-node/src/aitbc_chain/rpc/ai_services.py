"""AI Services RPC endpoints for AITBC blockchain.

AI jobs are persisted in the on-chain database instead of in-memory storage.
No demo/seed jobs are created — the job list starts empty and is populated
by real submissions.
"""

import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, and_, literal_column, or_
from sqlmodel import col, func as sql_func
from sqlmodel import select

from aitbc.rate_limiting import rate_limit
from aitbc.utils import ait_to_units
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS

from ..base_models import AIJobCancellation, Transaction, address_spellings
from ..database import session_scope
from ..keyset import cursor_dt, parse_or_400
from ..logger import get_logger
from ..metrics import metrics_registry
from .escrow_routes import verify_rpc_peer_key
from .router import router

_logger = get_logger(__name__)

# An AI job is a payment to the AI service account, so it is submitted as an
# ordinary chain transaction and the PoA proposer includes it in a block.
AI_SERVICE_RECIPIENT = "ai_service"

# The proposer upper-cases tx["type"] when it writes the confirmed Transaction
# row (see consensus/poa.py), so mined jobs are stored as "AI_JOB". Rows written
# before AI jobs reached the mempool carry the lowercase spelling; both are
# matched so pre-existing jobs stay visible.
AI_JOB_TX_TYPE = "AI_JOB"
AI_JOB_TX_TYPES = (AI_JOB_TX_TYPE, "ai_job")

# Payload keys are inlined into the SQL text below (a bound JSON path cannot
# use the expression index — see _JOB_ID_INDEX_EXPRESSIONS in
# rpc/transactions.py), so only plain identifiers may reach the f-string.
_PAYLOAD_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _payload_extract_sql(dialect: str, key: str) -> str | None:
    """SQL text extracting ``payload[key]`` for ``dialect`` (None if unsafe)."""
    if not _PAYLOAD_KEY_RE.fullmatch(key):
        return None
    if dialect == "sqlite":
        return f"""json_extract(payload, '$."{key}"')"""
    if dialect == "postgresql":
        return f"""(payload ->> '{key}')"""
    return None


# Effective job identity in SQL, mirroring ``payload.get("job_id", tx.tx_hash)``
# exactly: the payload value wins whenever the key exists — a JSON ``null``
# yields SQL NULL (never equal to a string id), matching Python's ``None`` —
# and a missing key falls back to the tx hash. The Python recheck on the
# (now tiny) candidate set keeps semantics identical even for exotic value
# types the dialect text renders differently.
_JOB_IDENTITY_SQL = {
    "sqlite": """CASE WHEN json_type(payload, '$."job_id"') IS NOT NULL THEN json_extract(payload, '$."job_id"') ELSE tx_hash END""",
    "postgresql": """CASE WHEN payload->'job_id' IS NOT NULL THEN payload->>'job_id' ELSE tx_hash END""",
}


def _job_identity_column(session: Any) -> Any | None:
    """``literal_column`` for the effective job id, or None on odd dialects."""
    expression = _JOB_IDENTITY_SQL.get(session.get_bind().dialect.name)
    return literal_column(expression) if expression is not None else None


class AIJobRequest(BaseModel):
    """AI job submission request"""

    wallet_address: str = Field(..., description="Client wallet address")
    job_type: str = Field(..., description="Type of AI job (text, image, training, etc.)")
    prompt: str = Field(..., description="AI prompt or task description")
    # not-money: wire format. This value goes into tx_data["payload"], which is
    # json.dumps'd and keccak-hashed for signature verification and for the tx hash.
    # Decimal is not JSON-serializable, and even with an encoder "0.5" != 0.5 would
    # invalidate every signature already issued. Changing it is a hard fork -- see
    # docs/architecture/money-types-and-the-signature-boundary.md.
    payment: float = Field(..., ge=0, description="Payment in AIT")
    parameters: dict[str, Any] | None = Field(default=None, description="Additional job parameters")
    nonce: int = Field(default=0, ge=0, description="Sender account nonce")
    fee: int = Field(default=DEFAULT_TX_FEE_UNITS, ge=0, description="Transaction fee in compute-units (1 AIT = 36_000_000)")
    signature: str = Field(..., description="secp256k1 signature over the job transaction, signed by wallet_address")


class AIJobCancelRequest(BaseModel):
    """Owner-signed cancel (#1055): the route took a bare job id, so anyone
    could cancel any job. The signature covers the cancel transaction shape."""

    wallet_address: str = Field(..., description="address that submitted the job")
    signature: str = Field(..., description="secp256k1 signature over the cancel transaction")


class AIJobResponse(BaseModel):
    """AI job response"""

    job_id: str
    status: str
    wallet_address: str
    job_type: str
    # not-money: echoes the request field above, whose wire type is fixed by the
    # transaction signature. Changing one without the other would be worse than either.
    payment: float
    created_at: datetime
    estimated_completion: datetime | None = None
    result: dict[str, Any] | None = None


def _cancelled_job_ids(session) -> set[str]:
    """Job ids cancelled on this host via the ai_job_cancellation service table.

    The sealed ``transaction`` row is never rewritten for a cancel
    (AI-CANCEL-SEALED-TX-1); the mark lives in this per-node service table and
    read paths overlay ``status="cancelled"`` from it.
    """
    return {r.job_id for r in session.exec(select(AIJobCancellation)).all()}


def _job_from_tx(tx: Transaction, cancelled_ids: set[str] | None = None) -> dict[str, Any]:
    """Convert a Transaction row with type='ai_job' to a job dict."""
    payload = tx.payload or {}
    job_id = payload.get("job_id", tx.tx_hash)
    status = "cancelled" if cancelled_ids and job_id in cancelled_ids else tx.status
    return {  # not-money: ratio, threshold or configuration default — not an amount of money
        "job_id": job_id,
        "wallet_address": tx.sender,
        "job_type": payload.get("job_type", "unknown"),
        "prompt": payload.get("prompt", ""),
        "payment": payload.get("payment", 0.0),
        "parameters": payload.get("parameters", {}),
        "status": status,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "estimated_completion": payload.get("estimated_completion"),
        "result": payload.get("result"),
        "tx_hash": tx.tx_hash,
        "block_height": tx.block_height,
    }


@router.post("/ai/submit", summary="Submit AI job", tags=["ai"])
def ai_submit_job(request: AIJobRequest) -> dict[str, Any]:
    """Submit a new AI job to the mempool.

    The job is an ordinary chain transaction paying ``AI_SERVICE_RECIPIENT``, so
    the PoA proposer includes it in a block like any other. It appears in the job
    endpoints once mined; until then it is pending in the mempool and visible via
    ``/mempool``. Its ``job_id`` is the transaction hash.
    """
    from ..mempool import get_mempool
    from .transactions import _validate_transaction_admission
    from .utils import get_chain_id, normalize_transaction_data, verify_transaction_signature

    try:
        metrics_registry.increment("rpc_ai_submit_total")

        chain_id = get_chain_id()
        mempool = get_mempool()

        # Every field here is client-supplied: the signature covers the whole
        # transaction, so nothing the server invents can be part of it. chain_id
        # is included so a job signed for one chain cannot be replayed on
        # another (same rule as submit_transaction).
        tx_data: dict[str, Any] = {
            "from": request.wallet_address,
            "to": AI_SERVICE_RECIPIENT,
            "amount": ait_to_units(request.payment),
            "fee": request.fee,
            "nonce": request.nonce,
            "type": AI_JOB_TX_TYPE,
            "payload": {
                "job_type": request.job_type,
                "prompt": request.prompt,
                "payment": request.payment,
                "parameters": request.parameters or {},
            },
            "chain_id": chain_id,
            "signature": request.signature,
        }

        # The job debits the sender's balance, so it has to be signed by them.
        if not verify_transaction_signature(tx_data, request.signature, request.wallet_address):
            raise HTTPException(status_code=403, detail="Invalid transaction signature")

        tx_data = normalize_transaction_data(tx_data, chain_id)
        _validate_transaction_admission(tx_data, mempool)

        tx_hash = mempool.add(tx_data, chain_id=chain_id)

        from .transactions import _queue_peer_fanout

        _queue_peer_fanout(chain_id, tx_data)

        _logger.info("AI job submitted to mempool: tx %s by %s", tx_hash, request.wallet_address)

        return {
            "job_id": tx_hash,
            "status": "pending",
            "message": "AI job submitted to mempool, pending inclusion in a block",
            "wallet_address": request.wallet_address,
            "payment": request.payment,
            "job_type": request.job_type,
            "tx_hash": tx_hash,
        }

    except HTTPException:
        raise
    except ValueError as e:
        # Rejected before admission: malformed amount/fee/nonce, unknown sender,
        # insufficient balance, wrong nonce, or unsupported chain. These are
        # client errors, and failing here is the point — the previous version
        # accepted everything and dropped it silently.
        metrics_registry.increment("rpc_ai_submit_errors_total")
        _logger.warning("AI job rejected: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to submit AI job: {e}") from e
    except Exception as e:
        metrics_registry.increment("rpc_ai_submit_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


# Keyset pagination for /ai/jobs (#1717). The status filter runs on the
# effective status (the 'cancelled' overlay), so a page may need to scan
# well past ``limit`` SQL candidates; the scan is chunked and bounded so a
# sparse filter can never turn one request into a table scan. Hitting the
# bound still advances next_cursor — the caller resumes, nothing wedges.
_AI_JOBS_SCAN_BOUND = 8192
_AI_JOBS_BATCH = 512


def _jobs_after(created_at: datetime, tx_id: int) -> ColumnElement[bool]:
    """Keyset predicate for ``ORDER BY created_at DESC, id DESC``."""
    return or_(
        col(Transaction.created_at) < created_at,
        and_(col(Transaction.created_at) == created_at, col(Transaction.id) < tx_id),
    )


def _parse_jobs_cursor(cursor: str | None) -> tuple[datetime, int] | None:
    """``<created_at iso>|<transaction id>`` — see ``next_cursor`` below."""
    parts = parse_or_400(
        cursor,
        2,
        what="'<created_at>|<id>'",
        detail="invalid cursor (want '<created_at>|<id>' from a previous next_cursor)",
    )
    if parts is None:
        return None
    try:
        return cursor_dt(parts[0]), int(parts[1])
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail="invalid cursor (want '<created_at>|<id>' from a previous next_cursor)"
        ) from e


def _job_cursor(tx: Transaction) -> str | None:
    if tx.created_at is None or tx.id is None:
        return None
    return f"{tx.created_at.isoformat()}|{tx.id}"


def _scan_job_candidates(session, stmt, cancelled_ids: set[str], status: str | None, want: int):
    """Collect up to ``want`` status-matching ``(tx, job)`` pairs.

    Returns ``(collected, last_key, exhausted)`` where ``last_key`` is the
    ``(created_at, id)`` of the last candidate scanned — the resume point
    when the scan bound cut the walk short.
    """
    collected: list[tuple[Transaction, dict[str, Any]]] = []
    last_key: tuple[datetime, int] | None = None
    scanned = 0
    exhausted = False
    while len(collected) < want and scanned < _AI_JOBS_SCAN_BOUND:
        take = min(_AI_JOBS_BATCH, _AI_JOBS_SCAN_BOUND - scanned)
        batch = stmt
        if last_key is not None:
            batch = batch.where(_jobs_after(*last_key))
        rows = session.exec(batch.limit(take)).all()
        if not rows:
            exhausted = True
            break
        for tx in rows:
            scanned += 1
            last_key = (tx.created_at, tx.id)
            job = _job_from_tx(tx, cancelled_ids)
            if status is None or job["status"] == status:
                collected.append((tx, job))
                if len(collected) >= want:
                    break
        if len(rows) < take:
            exhausted = True
            break
    return collected, last_key, exhausted


@router.get("/ai/jobs", summary="List AI jobs", tags=["ai"], dependencies=[Depends(verify_rpc_peer_key)])
def ai_list_jobs(
    wallet_address: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Get list of AI jobs, optionally filtered by wallet address or status.

    ``cursor`` takes a previous ``next_cursor`` and pages by keyset over
    ``(created_at, id)`` — immune to rows inserted between calls. ``offset``
    counts *matching* jobs (post status-trim), which also fixes the fuzzy
    pre-filter offset semantics this endpoint used to have.
    """
    keyset = _parse_jobs_cursor(cursor)
    try:
        metrics_registry.increment("rpc_ai_list_total")
        # Unbounded .all() used to scan every AI job row on every call (#1057).
        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        with session_scope("") as session:
            stmt = select(Transaction).where(Transaction.type.in_(AI_JOB_TX_TYPES))  # type: ignore[attr-defined]
            if wallet_address:
                # Verbatim column, so match every spelling of the account (V23-65).
                stmt = stmt.where(sql_func.lower(Transaction.sender).in_(address_spellings(wallet_address)))
            # id is the tiebreaker: created_at can tie (same-millisecond
            # inserts), and without a unique second key offset pages could
            # skip or repeat rows.
            stmt = stmt.order_by(col(Transaction.created_at).desc(), col(Transaction.id).desc())
            if keyset is not None:
                stmt = stmt.where(_jobs_after(*keyset))

            cancelled_ids = _cancelled_job_ids(session)
            collected, last_key, exhausted = _scan_job_candidates(session, stmt, cancelled_ids, status, limit + offset)
            page = collected[offset : offset + limit]
            jobs = [job for _, job in page]

            if len(collected) >= limit + offset:
                # Full page: resume after the last *returned* candidate.
                next_cursor = _job_cursor(page[-1][0])
                scan_bounded = False
            elif not exhausted and last_key is not None:
                # Scan bound cut the walk: resume after the last candidate
                # examined so the next call continues where this one stopped.
                last_tx_created, last_tx_id = last_key
                next_cursor = f"{last_tx_created.isoformat()}|{last_tx_id}"
                scan_bounded = True
            else:
                next_cursor = None
                scan_bounded = False

        return {
            "jobs": jobs,
            "total": len(jobs),
            "filters": {"wallet_address": wallet_address, "status": status},
            "limit": limit,
            "offset": offset,
            "next_cursor": next_cursor,
            "scan_bounded": scan_bounded,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_ai_list_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/ai/job/{job_id}", summary="Get AI job by ID", tags=["ai"], dependencies=[Depends(verify_rpc_peer_key)])
def ai_get_job(job_id: str) -> dict[str, Any]:
    """Get a specific AI job by ID"""
    try:
        metrics_registry.increment("rpc_ai_get_total")

        with session_scope("") as session:
            # Resolve the job id in SQL: job_id is the tx hash for mempool
            # submissions, or an explicit payload job_id on legacy rows —
            # _JOB_IDENTITY_SQL covers both without materializing the table
            # (#1509, residual of the #1057 ai_list_jobs bound). The Python
            # check below still verifies the effective id on the candidates.
            stmt = select(Transaction).where(Transaction.type.in_(AI_JOB_TX_TYPES))  # type: ignore[attr-defined]
            identity = _job_identity_column(session)
            if identity is not None:
                stmt = stmt.where(identity == job_id)
            txs = session.exec(stmt).all()
            cancelled_ids = _cancelled_job_ids(session)

            for tx in txs:
                payload = tx.payload or {}
                # Jobs submitted through the mempool are identified by their tx
                # hash; older rows carry an explicit job_id in the payload. Match
                # the same identity _job_from_tx reports.
                if payload.get("job_id", tx.tx_hash) == job_id:
                    return {"job": _job_from_tx(tx, cancelled_ids), "found": True}

        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_ai_get_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ai/job/{job_id}/cancel", summary="Cancel AI job", tags=["ai"])
@rate_limit(rate=20, per=60)
def ai_cancel_job(job_id: str, cancel: AIJobCancelRequest, request: Request) -> dict[str, Any]:
    """Cancel an AI job — owner signature required (#1055).

    A bare job id is public (it is the tx hash), so the cancel must prove the
    caller controls the wallet that submitted the job: a secp256k1 signature
    over {from, type:AI_JOB_CANCEL, payload.job_id, chain_id}, verified like
    ai_submit_job, with the signer matching the job's sender.
    """
    from .utils import get_chain_id, verify_transaction_signature

    try:
        metrics_registry.increment("rpc_ai_cancel_total")
        chain_id = get_chain_id()

        cancel_data: dict[str, Any] = {
            "from": cancel.wallet_address,
            "type": "AI_JOB_CANCEL",
            "payload": {"job_id": job_id},
            "chain_id": chain_id,
            "signature": cancel.signature,
        }
        if not verify_transaction_signature(cancel_data, cancel.signature, cancel.wallet_address):
            raise HTTPException(status_code=403, detail="Invalid transaction signature")

        with session_scope("") as session:
            # job_id is a tx hash / payload job_id, never the int pk — the old
            # session.get(Transaction, job_id) probe could never hit. Resolve
            # by the same SQL identity as ai_get_job (#1509) directly.
            stmt = select(Transaction).where(Transaction.type.in_(AI_JOB_TX_TYPES))  # type: ignore[attr-defined]
            identity = _job_identity_column(session)
            if identity is not None:
                stmt = stmt.where(identity == job_id)
            txs = list(session.exec(stmt).all())
            cancelled_ids = _cancelled_job_ids(session)

            for tx in txs:
                payload = tx.payload or {}
                # Jobs submitted through the mempool are identified by their tx
                # hash; older rows carry an explicit job_id in the payload. Match
                # the same identity _job_from_tx reports.
                if payload.get("job_id", tx.tx_hash) == job_id:
                    # Only the job's own sender may cancel it (#1055).
                    if not set(address_spellings(cancel.wallet_address)) & set(address_spellings(tx.sender)):
                        raise HTTPException(status_code=403, detail="Signer is not the job owner")
                    current_status = "cancelled" if job_id in cancelled_ids else tx.status
                    if current_status in ["completed", "cancelled"]:
                        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status: {current_status}")

                    # The sealed transaction row is never rewritten
                    # (AI-CANCEL-SEALED-TX-1): the cancel is service-table
                    # bookkeeping on this host.
                    session.add(
                        AIJobCancellation(
                            job_id=job_id,
                            chain_id=tx.chain_id,
                            tx_hash=tx.tx_hash,
                        )
                    )
                    session.commit()

                    return {"job_id": job_id, "status": "cancelled", "message": "AI job cancelled successfully"}

        raise HTTPException(status_code=404, detail="Job not found")

    except HTTPException:
        raise
    except Exception as e:
        metrics_registry.increment("rpc_ai_cancel_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/ai/stats", summary="AI service statistics", tags=["ai"], dependencies=[Depends(verify_rpc_peer_key)])
def ai_stats() -> dict[str, Any]:
    """Get AI service statistics"""
    try:
        metrics_registry.increment("rpc_ai_stats_total")

        with session_scope("") as session:
            base = Transaction.type.in_(AI_JOB_TX_TYPES)  # type: ignore[attr-defined]
            dialect = session.get_bind().dialect.name
            identity = _job_identity_column(session)
            job_type_sql = _payload_extract_sql(dialect, "job_type")
            payment_sql = _payload_extract_sql(dialect, "payment")

            if identity is None or job_type_sql is None or payment_sql is None:
                # Unknown dialect: keep the Python aggregation (correct but
                # unbounded — same as before this fix; only sqlite/postgres
                # are deployed).
                stmt = select(Transaction).where(base)
                txs = session.exec(stmt).all()
                cancelled_ids = _cancelled_job_ids(session)

                total_jobs = len(txs)
                status_counts: dict[str, int] = {}
                type_counts: dict[str, int] = {}
                total_revenue = Decimal("0")

                for tx in txs:
                    payload = tx.payload or {}
                    job_id = payload.get("job_id", tx.tx_hash)
                    status = ("cancelled" if job_id in cancelled_ids else tx.status) or "unknown"
                    status_counts[status] = status_counts.get(status, 0) + 1
                    job_type = payload.get("job_type", "unknown")
                    type_counts[job_type] = type_counts.get(job_type, 0) + 1
                    if status == "completed":
                        total_revenue += Decimal(str(payload.get("payment", "0")))
            else:
                # Aggregate in SQL (#1509): counts by stored status/type, the
                # cancelled overlay joined on the effective job id, and the
                # revenue sum — no row hydration at all.
                total_jobs = int(session.exec(select(sql_func.count()).select_from(Transaction).where(base)).one())
                status_counts = {}
                for status, count in session.exec(
                    select(Transaction.status, sql_func.count()).where(base).group_by(Transaction.status)
                ).all():
                    status_counts[status or "unknown"] = int(count)

                type_counts = {}
                job_type_col: ColumnElement[Any] = literal_column(f"coalesce({job_type_sql}, 'unknown')")
                for job_type, count in session.exec(
                    select(job_type_col, sql_func.count()).where(base).group_by(job_type_col)
                ).all():
                    type_counts[job_type] = int(count)

                # Cancelled overlay: effective status is 'cancelled' for every
                # AI job whose effective id has a cancellation row, whatever
                # the sealed tx status says (AI-CANCEL-SEALED-TX-1).
                cancelled_subq = select(AIJobCancellation.job_id)
                cancelled_by_status: dict[str, int] = {}
                for status, count in session.exec(
                    select(Transaction.status, sql_func.count())
                    .where(base, identity.in_(cancelled_subq))
                    .group_by(Transaction.status)
                ).all():
                    cancelled_by_status[status or "unknown"] = int(count)
                for status, count in cancelled_by_status.items():
                    status_counts[status] = status_counts.get(status, 0) - count
                    status_counts["cancelled"] = status_counts.get("cancelled", 0) + count
                status_counts = {s: c for s, c in status_counts.items() if c > 0}

                # Revenue only for effectively-completed jobs: stored
                # 'completed' minus the cancelled overlay. payment is the
                # float wire value (not-money boundary), summed as REAL.
                payment_col: ColumnElement[Any] = literal_column(payment_sql)
                if dialect == "postgresql":
                    payment_col = literal_column(f"({payment_sql})::float8")
                total_revenue_float = session.exec(
                    select(sql_func.coalesce(sql_func.sum(payment_col), 0))
                    .select_from(Transaction)
                    .where(
                        base,
                        Transaction.status == "completed",
                        # NOT IN yields NULL (excluded) when the identity expr
                        # is NULL — a JSON-null job_id. Python treats that id
                        # as "not cancelled", so keep those rows countable.
                        or_(identity.is_(None), ~identity.in_(cancelled_subq)),
                    )
                ).one()
                total_revenue = Decimal(str(total_revenue_float or 0))

        return {
            "total_jobs": total_jobs,
            "status_breakdown": status_counts,
            "type_breakdown": type_counts,
            "total_revenue": total_revenue,
            "average_payment": total_revenue / max(1, status_counts.get("completed", 0)),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        metrics_registry.increment("rpc_ai_stats_errors_total")
        logging.getLogger(__name__).exception("Unhandled exception")

        raise HTTPException(status_code=500, detail="Internal server error") from e
