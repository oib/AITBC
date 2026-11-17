"""Mempool database admission-lock helpers (mempool split, #1860).

PostgreSQL advisory-lock and timeout plumbing shared by the
``DatabaseMempool`` admission paths. Facade module: ``aitbc_chain.mempool``
re-exports every name defined here; not meant to be imported directly."""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, text


class MempoolAdmissionTimeout(Exception):
    """A mempool admission lock/statement wait exceeded its bound (#1300).

    Raised instead of a raw ``OperationalError`` so callers can answer with a
    clean admission refusal. Covers ``lock_timeout`` (55P03) and
    ``statement_timeout`` (57014) inside the admission transaction.
    """


_PG_LOCK_NOT_AVAILABLE = "55P03"
_PG_QUERY_CANCELED = "57014"


def _is_admission_timeout(exc: BaseException) -> bool:
    orig = getattr(exc, "orig", exc)
    code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    return code in {_PG_LOCK_NOT_AVAILABLE, _PG_QUERY_CANCELED}


def _normalize_lock_key(key: str) -> str:
    """Sanitize a lock-key string: alnum kept, everything else -> '-'.

    Applied BEFORE sorting and BEFORE hashing so every process derives the
    same acquisition order and the same ``hashtext`` input from raw slot
    data. The sort key is this sanitized string, never the 32-bit hash —
    hashtext collisions cannot invert acquisition order (they only merge
    two keys into one lock, a bounded liveness corner covered by
    ``lock_timeout``).
    """
    return "".join(c if c.isalnum() else "-" for c in key)


def _slot_lock_key_str(chain_id: str, slot: tuple[str, int]) -> str:
    return _normalize_lock_key(f"{chain_id}|{slot[0]}|{slot[1]}")


def _apply_admission_timeouts(session: Session) -> None:
    """Bound lock and statement waits for this transaction (PostgreSQL).

    ``SET LOCAL`` scopes both GUCs to the current transaction, so pooled
    connections return to the server defaults on commit/rollback.
    """
    from .config import settings

    ms = int(settings.mempool_admission_lock_timeout_ms)
    session.exec(text(f"SET LOCAL lock_timeout = {ms}"))  # type: ignore[call-overload]
    session.exec(text(f"SET LOCAL statement_timeout = {ms}"))  # type: ignore[call-overload]


def _slot_advisory_lock(session: Session, chain_id: str, slot: tuple[str, int]) -> None:
    """Serialize same-slot admissions across processes (Refs #743, #1300).

    The occupancy rule is check-then-insert inside one transaction; under
    READ COMMITTED two uvicorn workers can both observe an empty slot and
    both insert, producing duplicate (sender, nonce) pending rows. A
    transaction-scoped advisory lock keyed on the slot makes the second
    caller wait until the first commits, after which its SELECT sees the
    occupant and applies the fee rule normally. PostgreSQL only — sqlite
    serializes writers at the file level and the in-process ``self._lock``
    already covers threads.

    #1300 P2-v2.4: the key is a bound parameter (never string-interpolated),
    lock/statement waits are bounded by ``mempool_admission_lock_timeout_ms``
    and surface as :class:`MempoolAdmissionTimeout`.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    _slot_advisory_lock_by_key(session, _slot_lock_key_str(chain_id, slot))


def _slot_advisory_lock_by_key(session: Session, lock_key: str) -> None:
    """Acquire one normalized advisory-lock key (PostgreSQL only).

    Separated from :func:`_slot_advisory_lock` so batch callers can sort the
    normalized strings first and then acquire in that exact order.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    _apply_admission_timeouts(session)
    try:
        session.exec(text("SELECT pg_advisory_xact_lock(hashtext(:key))").bindparams(key=lock_key))  # type: ignore[call-overload]
    except SQLAlchemyError as exc:
        if _is_admission_timeout(exc):
            raise MempoolAdmissionTimeout(f"mempool advisory lock timed out for key {lock_key!r}") from exc
        raise
