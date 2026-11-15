"""#1940 F4: isolated full post-state attestation verification.

The v9 attestation check historically verified only the *request envelope*:
signer signatures, nonce ordering, and parent binding — it never re-executed
the block's transactions, so a proposer could attach a valid header to
transactions whose real post-state diverged from the claimed roots.

When ``attestation_post_state_height`` is configured, every attest request at
or above that height additionally runs :func:`probe_post_state`: the claimed
``state_root``/``aux_state_root`` must reproduce when the delivered
transactions are applied to a *consistent snapshot* of this node's own
parent state, using the real importer (``BlockImportMixin._append_block``)
on a scratch in-memory database. The ``bridge_state_root`` is bound to the
authenticated header/stored row only — the legacy importer trusts the
carried value because its committed-set digest depends on producer-local
service records a follower cannot reproduce; deterministic bridge-root
enforcement is F5 scope, not this tranche. The production database is
only ever read — the snapshot is taken with the SQLite online-backup API —
and every speculative side effect (cache invalidation, rejection counters,
journal persist, shadow roots, mempool, gossip) is suppressed or scratch-
local. A probe that cannot complete inside its deadline refuses the
attestation; expiry is a local availability decision, never a consensus
verdict.

This tranche is deliberately *verification-only*: it does not change what a
sealed block means, does not gate import, and does not claim cross-view
safety. ``attestation_post_state_height`` ships unset — no activation value
is chosen here; enabling requires a uniform configured height.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import time
from contextlib import nullcontext
from datetime import datetime
from typing import Any, TypeGuard, cast

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ..base_models import Block
from ..config import settings
from ..state.state_root_utils import compute_state_root_full
from ..state.state_transition import StateTransition, get_block_version, get_block_version_for_height

logger = get_logger(__name__)


def _strict_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def post_state_probe_active(height: int) -> bool:
    """Whether the post-state probe applies at ``height`` (#1940 F4).

    Armed by the configured ``attestation_post_state_height``: active iff a
    valid non-negative int threshold is set AND ``height`` is a valid
    non-negative int at or above it. ``None``/invalid/bool heights and
    pre-threshold heights resolve False — the legacy shallow check then runs
    unchanged with zero snapshot cost.
    """
    threshold = getattr(settings, "attestation_post_state_height", None)
    if not _strict_int(threshold) or threshold < 0:
        return False
    return _strict_int(height) and height >= threshold


def _valid_state_root(value: Any) -> bool:
    """Nonempty 64-hex state root (optional ``0x`` prefix)."""
    if not isinstance(value, str):
        return False
    body = value[2:] if value.startswith("0x") else value
    return len(body) == 64 and all(c in "0123456789abcdefABCDEF" for c in body)


def _sig_eq(a: Any, b: Any) -> bool:
    """Signature equality ignoring case/whitespace (hex payload compare)."""
    return str(a).strip().lower() == str(b).strip().lower()


def _root_eq(a: Any, b: Any) -> bool:
    """Semantic root equality — hex compare ignoring case and ``0x``."""
    return str(a or "").replace("0x", "").lower() == str(b or "").replace("0x", "").lower()


def _read_source_pragmas(source: sqlite3.Connection) -> tuple[int, int] | None:
    """(foreign_keys, busy_timeout) off the source connection, or None."""
    try:
        return (
            int(source.execute("PRAGMA foreign_keys").fetchone()[0]),
            int(source.execute("PRAGMA busy_timeout").fetchone()[0]),
        )
    except Exception:  # noqa: BLE001 - an unreadable pragma refuses the snapshot
        return None


def _mirror_foreign_keys(dest: sqlite3.Connection, fk_enabled: int) -> bool:
    """Apply the source connection's foreign-key policy to the scratch copy.

    Production engines register ``_set_sqlite_pragmas`` per-engine and
    ``db_foreign_keys_enabled`` can opt a source connection into
    ``PRAGMA foreign_keys=ON``, while a bare ``sqlite3.connect`` defaults
    OFF — the scratch DB would then accept rows the real importer rejects.
    The production pragma installer is deliberately NOT called here: its
    WAL/disk/tuning pragmas are wrong for an in-memory scratch copy.
    """
    try:
        dest.execute("PRAGMA foreign_keys=ON" if fk_enabled else "PRAGMA foreign_keys=OFF")
        return True
    except Exception:  # noqa: BLE001 - pragma failure must refuse, never attest
        return False


def _backup_snapshot(
    source: sqlite3.Connection,
    dest: sqlite3.Connection,
    deadline: float | None,
    original_busy: int,
) -> sqlite3.Connection | str:
    """Online-backup ``source`` into ``dest`` under the deadline.

    A contended ``backup_step`` invokes the busy handler *inside* the step,
    so the progress callback alone cannot cap a single step at the deadline
    (production ``busy_timeout`` is 60s). ``busy_timeout`` is leased to 0 on
    the source for the copy only — the sole permitted temporary
    source-connection change; it is restored to the exact original value in
    ``finally`` before the session can return the connection to the pool.
    No rows are written (``total_changes`` is unchanged); this is a
    nondurable connection-setting lease, not a persistent config change.
    """

    def _progress(_status: int, _remaining: int, _total: int) -> None:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("post-state snapshot deadline")

    try:
        source.execute("PRAGMA busy_timeout=0")
    except Exception:  # noqa: BLE001 - lease failure must refuse, never attest
        dest.close()
        return "post_state_snapshot_failed"
    restored = False
    try:
        source.backup(dest, pages=256, progress=_progress, sleep=0.01)
    except TimeoutError:
        dest.close()
        return "post_state_timeout"
    except Exception:  # noqa: BLE001 - copy failure must refuse, never attest
        dest.close()
        return "post_state_snapshot_failed"
    finally:
        try:
            source.execute(f"PRAGMA busy_timeout={original_busy}")
            restored = True
        except Exception:  # noqa: BLE001 - a failed restore must not attest
            logger.warning("ATTEST-PROBE failed to restore source busy_timeout")
    if not restored:
        dest.close()
        return "post_state_snapshot_failed"
    return dest


def _snapshot_source(session: Session, deadline: float | None) -> sqlite3.Connection | str:
    """Consistent SQLite snapshot of the source DB via online backup.

    Returns the in-memory destination connection, or a refusal reason.
    ``pages``/``sleep`` bound each backup step; the progress callback raises
    ``TimeoutError`` once the absolute monotonic deadline passes. The dest
    connection mirrors the source's ``PRAGMA foreign_keys`` and the source's
    ``busy_timeout`` is leased to 0 for the copy so a contended step cannot
    park inside the busy handler past the deadline — restored to its exact
    original value before returning.
    """
    try:
        conn = session.connection()
        if conn.dialect.name != "sqlite":
            return "post_state_unsupported_backend"
        fairy = conn.connection
        source = getattr(fairy, "dbapi_connection", fairy)
    except Exception:  # noqa: BLE001 - any bind/dialect surprise refuses
        return "post_state_unsupported_backend"
    if not isinstance(source, sqlite3.Connection):
        return "post_state_unsupported_backend"
    if deadline is not None and time.monotonic() > deadline:
        return "post_state_timeout"

    pragmas = _read_source_pragmas(source)
    if pragmas is None:
        return "post_state_snapshot_failed"
    fk_enabled, original_busy = pragmas
    dest = sqlite3.connect(":memory:", timeout=0)
    if not _mirror_foreign_keys(dest, fk_enabled):
        dest.close()
        return "post_state_snapshot_failed"
    return _backup_snapshot(source, dest, deadline, original_busy)


def _arm_sql_deadline(conn: sqlite3.Connection, deadline: float | None) -> None:
    """Abort scratch SQL once the absolute deadline passes.

    Pure-Python trie work cannot be preempted; bounded single-worker
    execution plus the caller's ``wait_for`` timeout is the documented
    contract — the worker retains its permit until it actually finishes.
    """
    if deadline is None:
        return
    effective = deadline

    def _handler() -> int:
        return 1 if time.monotonic() > effective else 0

    conn.set_progress_handler(_handler, 2048)


def _local_metadata(raw: Any, version: int) -> str:
    """block_metadata for the scratch apply with the version pinned locally.

    The version the block *should* run under is derived from its height —
    never trusted from peer-supplied metadata, which could otherwise stamp a
    downgrade and pick weaker apply rules. Other metadata keys (e.g. sealed
    rejection detail) are preserved.
    """
    parsed: dict[str, Any] = {}
    if isinstance(raw, dict):
        parsed = dict(raw)
    elif isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                parsed = loaded
        except (ValueError, RecursionError, TypeError):
            parsed = {}
    parsed["state_transition_version"] = version
    return json.dumps(parsed)


class _AttestationProbeImporter:
    """``BlockImportMixin`` stand-in bound to the probe's scratch session.

    No HTTP client, no production session factory, no Prometheus failure
    counters, no rejection/resync bookkeeping. The mixin instance is composed
    lazily so this module's import graph stays acyclic.
    """

    def __init__(self, chain_id: str, scratch_session: Session) -> None:
        from ..sync_block_import import BlockImportMixin

        # Attributes the wrapper's own overrides read.
        self._chain_id = chain_id
        self._scratch_session = scratch_session
        self._mv_loaded = False
        self._multi_validator_cache: Any = None

        impl: Any = BlockImportMixin.__new__(BlockImportMixin)  # type: ignore[type-abstract]
        impl.__dict__.update(
            {
                "_chain_id": chain_id,
                "_scratch_session": scratch_session,
                "_logger": logger,
                "_rejection_counts": {},
                "_multi_validator_cache": None,
                "_mv_loaded": False,
            }
        )
        # Per-instance overrides: no failure counters, no resync tracking.
        impl._make_import_result = self._make_import_result
        impl._track_rejection = self._track_rejection
        impl._reset_rejection_counter = self._reset_rejection_counter
        impl._get_multi_validator = self._get_multi_validator
        self._impl = impl

    # -- side-effect-free overrides -------------------------------------

    def _make_import_result(self, **kwargs: Any) -> Any:
        from ..sync_validator import ImportResult

        return ImportResult(**kwargs)

    def _track_rejection(self, chain_id: str) -> None:
        pass

    def _reset_rejection_counter(self, chain_id: str) -> None:
        pass

    def _get_multi_validator(self) -> Any:
        """Settings-only MV whose chain-state reads hit the scratch session."""
        if not getattr(settings, "multi_validator_consensus_enabled", False):
            return None
        if not getattr(settings, "validator_set", ""):
            return None
        if not self._mv_loaded:
            self._mv_loaded = True
            # Fail closed: a verifier that cannot be built must refuse the
            # attestation, never silently skip the schedule check. The public
            # probe converts the raise into a refusal verdict.
            from .multi_validator_poa import MultiValidatorPoA

            self._multi_validator_cache = MultiValidatorPoA.from_settings(
                self._chain_id,
                chain_state_session_factory=lambda: nullcontext(self._scratch_session),
            )
        return self._multi_validator_cache

    # -- pass-through -----------------------------------------------------

    def _append_block(self, *args: Any, **kwargs: Any) -> Any:
        return self._impl._append_block(*args, **kwargs)

    def _derive_bridge_state_root(self, *args: Any, **kwargs: Any) -> Any:
        return self._impl._derive_bridge_state_root(*args, **kwargs)


def _verify_imported(scratch: Session, chain_id: str, header: dict[str, Any], height: int) -> str | None:
    """Already-imported exact height/hash: bind stored fields to the request
    and recompute the account root over current state — never return early
    unverified."""
    stored = scratch.exec(select(Block).where(Block.chain_id == chain_id, Block.height == height)).first()
    if stored is None or not _root_eq(stored.hash, header.get("hash")):
        return "not_at_parent"
    req_root = str(header.get("state_root") or "")
    if not _root_eq(stored.state_root, req_root):
        return "post_state_root_mismatch"
    req_aux = str(header.get("aux_state_root") or "")
    if not _root_eq(stored.aux_state_root, req_aux):
        return "post_state_aux_mismatch"
    req_bridge = str(header.get("bridge_state_root") or "")
    if not _root_eq(stored.bridge_state_root, req_bridge):
        return "post_state_bridge_mismatch"
    actual_root = compute_state_root_full(scratch, chain_id)
    if actual_root is None or not _root_eq(actual_root, req_root):
        return "post_state_root_mismatch"
    # Aux is recomputed only for eras whose committed set is verifiable —
    # matching the importer's historical compare-only semantics. The stored
    # row's recorded version governs, never the request's claim.
    stored_version = get_block_version(stored, height)
    if stored_version >= 14:
        from ..state import side_root_shadow

        computed_aux = side_root_shadow.committed_fingerprint(scratch.connection().connection, stored_version)["fingerprint"]
        if side_root_shadow.aux_check_verifiable(stored_version) and not _root_eq(computed_aux, req_aux):
            return "post_state_aux_mismatch"
    return None


def _apply_and_verify(
    scratch: Session,
    chain_id: str,
    header: dict[str, Any],
    transactions: list[dict[str, Any]],
    version: int,
    proposer_signature: str | None,
) -> str | None:
    """Fresh apply on the scratch session through the real importer."""
    probe_block_data = dict(header)
    # The proposer signature comes from the *verified request envelope* —
    # never an unverified field embedded in the block header itself.
    probe_block_data["signature"] = proposer_signature or ""
    probe_block_data["block_metadata"] = _local_metadata(header.get("block_metadata"), version)
    importer = _AttestationProbeImporter(chain_id, scratch)
    # Deep copies: the probe must never mutate the caller's request objects,
    # and _append_block normalizes tx dicts in place.
    try:
        result = importer._append_block(
            scratch,
            probe_block_data,
            copy.deepcopy(transactions),
            _probe=True,
            _state_transition=StateTransition(cache_side_effects=False),
        )
    except ValueError as e:
        # Proposer-schedule rejection surfaces as ValueError — an
        # actionable refusal, not an internal error.
        logger.warning(
            "ATTEST-PROBE post-state apply refused at height %s: %s",
            header.get("height"),
            e,
        )
        return "post_state_apply_refused"
    if not result.accepted:
        logger.warning(
            "ATTEST-PROBE post-state apply refused at height %s: %s",
            header.get("height"),
            result.reason,
        )
        return "post_state_apply_refused"
    # The bridge root is carried, not recomputed: the legacy importer trusts
    # the authenticated header value because the committed-set digest depends
    # on producer-local service records a follower cannot reproduce. F4 binds
    # account/aux rules only; deterministic bridge enforcement is F5 scope.
    return None


def _header_timestamp(header: dict[str, Any]) -> datetime | None:
    """Parseable header timestamp, or None — blocks without one refuse."""
    raw = header.get("timestamp")
    try:
        return datetime.fromisoformat(str(raw)) if raw else None
    except (TypeError, ValueError):
        return None


def _signature_contract_refusal(header: dict[str, Any], proposer_signature: str | None) -> str | None:
    """Signature contract (#1940 F4): the verified request-envelope
    ``proposer_signature`` is authoritative — the honest collector sends it
    separately and its header projection omits ``signature``. An embedded
    header signature that is truthy AND differs refuses; missing/empty is
    normal. When block signatures are required (the default), an absent
    request signature refuses even if the legacy attest-request gate is
    still off; the explicit global bypass
    (``bridge_block_signature_required=False``) keeps legacy semantics.
    """
    embedded_sig = header.get("signature")
    if embedded_sig and not _sig_eq(embedded_sig, proposer_signature or ""):
        return "post_state_signature_mismatch"
    if getattr(settings, "bridge_block_signature_required", True) and not proposer_signature:
        return "post_state_missing_proposer_signature"
    return None


def _probe_post_state(
    session: Session,
    chain_id: str,
    header: dict[str, Any],
    transactions: list[dict[str, Any]],
    *,
    deadline: float | None,
    proposer_signature: str | None,
) -> str | None:
    height = header.get("height")
    if not _strict_int(height) or height < 0:
        return "post_state_bad_height"
    if _header_timestamp(header) is None:
        return "post_state_bad_timestamp"
    if not _valid_state_root(header.get("state_root")):
        return "post_state_bad_state_root"
    # Local version metadata — a peer-stamped downgrade must not pick the
    # apply rules; the height-derived version governs.
    version = get_block_version_for_height(height)
    if version >= 14 and not header.get("aux_state_root"):
        return "post_state_missing_aux_root"

    sig_refusal = _signature_contract_refusal(header, proposer_signature)
    if sig_refusal is not None:
        return sig_refusal

    snapshot = _snapshot_source(session, deadline)
    if isinstance(snapshot, str):
        return snapshot
    dest = snapshot
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        creator=lambda: dest,
    )
    scratch = Session(engine)
    try:
        _arm_sql_deadline(dest, deadline)
        try:
            return _verify_on_snapshot(scratch, chain_id, header, transactions, version, deadline, proposer_signature)
        except sqlite3.OperationalError:
            if deadline is not None and time.monotonic() > deadline:
                return "post_state_timeout"
            raise
    finally:
        try:
            scratch.close()
        finally:
            engine.dispose()
            try:
                dest.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                logger.debug("ATTEST-PROBE scratch connection close failed")


def _verify_on_snapshot(
    scratch: Session,
    chain_id: str,
    header: dict[str, Any],
    transactions: list[dict[str, Any]],
    version: int,
    deadline: float | None,
    proposer_signature: str | None,
) -> str | None:
    """Tip check inside the snapshot, then verify or apply."""
    tip = scratch.exec(
        select(Block.height, Block.hash).where(Block.chain_id == chain_id).order_by(text("height DESC")).limit(1)
    ).first()
    if tip is None:
        return "not_at_parent"
    tip_height, tip_hash = tip
    height = cast(int, header["height"])
    req_hash = str(header.get("hash") or "")
    if tip_height == height and _root_eq(tip_hash, req_hash):
        return _verify_imported(scratch, chain_id, header, height)
    if tip_height != height - 1 or not _root_eq(tip_hash, header.get("parent_hash")):
        return "not_at_parent"
    return _apply_and_verify(scratch, chain_id, header, transactions, version, proposer_signature)


def probe_post_state(
    session: Session,
    chain_id: str,
    header: dict[str, Any],
    transactions: list[dict[str, Any]],
    *,
    deadline: float | None = None,
    proposer_signature: str | None = None,
) -> str | None:
    """Verify an attest request's claimed post-state on an isolated snapshot.

    Returns None when the claimed roots reproduce under the real importer
    rules on a consistent snapshot of local parent state; otherwise a short
    refusal reason. Never raises for malformed input — every failure is a
    refusal — and the source session/connection is only ever read.
    """
    if deadline is None:
        # Direct callers get the same bounded budget the worker enforces —
        # an unset deadline must never mean an unbounded backup.
        timeout = float(getattr(settings, "attestation_post_state_timeout_seconds", 10.0))
        deadline = time.monotonic() + timeout
    try:
        verdict = _probe_post_state(
            session, chain_id, header, transactions, deadline=deadline, proposer_signature=proposer_signature
        )
    except Exception as e:  # noqa: BLE001 - a probe failure must refuse, never attest unverified
        # A deadline that expired mid-apply (e.g. SQLAlchemy-wrapped
        # SQLITE_INTERRUPT) reports timeout, not internal error.
        if time.monotonic() > deadline:
            return "post_state_timeout"
        logger.warning("ATTEST-PROBE post-state check errored: %s", type(e).__name__)
        return "post_state_error"
    # Pure-Python trie work and short SQL may never trip the progress
    # handlers — re-check before attesting on a spent budget.
    if verdict is None and time.monotonic() > deadline:
        return "post_state_timeout"
    return verdict
