"""Escrow lock/obligation/context helpers for ``StateTransition``.

Pure-move split out of ``state_transition.py``: the state-transition facade
re-exports every name defined here, so ``from aitbc_chain.state.state_transition
import X`` keeps working unchanged for all of them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from eth_utils import keccak
from sqlmodel import Session, select

from ..base_models import Block, _to_ait_address
from ..models import Transaction
from aitbc.crypto.signature_recovery import canonical_address
from .bridge_credit import bridge_refund_lock_hash
from .state_transition_authority import (
    _escrow_fee_cap_bps,
    _escrow_fee_recipient,
    _escrow_settlement_authority,
)
from .state_transition_txmeta import _tx_type, get_block_version, get_block_version_for_height


def _escrow_address(job_id: str) -> str:
    """Derive a deterministic escrow address for a job (S-4).

    Funds locked for a job go to escrow:<job_id> — an address with no
    known private key, so the locked value is unspendable by the node
    wallet until a release or refund transaction moves it.
    """
    return canonical_address("0x" + keccak(f"aitbc.escrow.{job_id}".encode()).hex()[:40])


def _is_escrow_address(address: str, job_id: str | None = None) -> bool:
    """Check whether an address is (or matches) a per-escrow lock address."""
    if job_id is None:
        # Without a job_id, check if it matches the escrow prefix pattern.
        # This is a heuristic — we can't reverse the hash.
        return False
    return canonical_address(address) == _escrow_address(job_id)


def _is_valid_0x_address(address: str) -> bool:
    """Return True if ``address`` is a canonical 42-character 0x address."""
    try:
        normalized = canonical_address(address)
    except (TypeError, ValueError):
        return False
    return normalized.startswith("0x") and len(normalized) == 42


def _get_escrow_lock(session: Session, chain_id: str, job_id: str) -> Transaction | None:
    """Find the on-chain ESCROW_LOCK transaction for ``job_id``."""
    return session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == "ESCROW_LOCK",
            Transaction.payload.op("->>")("job_id") == job_id,  # type: ignore
        )
    ).first()


def _get_escrow_lock_block_version(session: Session, chain_id: str, job_id: str) -> int | None:
    """Return the state-transition version of the block that mined the lock for ``job_id``."""
    lock_tx = _get_escrow_lock(session, chain_id, job_id)
    if not lock_tx or lock_tx.block_height is None:
        return None
    row = session.exec(
        # Column-only: the entity select would eager-load the block's selectin
        # transactions/receipts; only the recorded version stamp is needed.
        select(Block.height, Block.block_metadata).where(Block.chain_id == chain_id, Block.height == lock_tx.block_height)
    ).first()
    if row is None:
        return None
    return get_block_version({"block_metadata": row[1]}, row[0])


def _escrow_beneficiary(lock_tx: Transaction, tx_type: str) -> str | None:
    """Return the canonical address that ``tx_type`` must pay for this lock."""
    payload = lock_tx.payload or {}
    if tx_type == "ESCROW_RELEASE":
        provider = payload.get("provider") or ""
        return _to_ait_address(provider) if provider else None
    if tx_type == "ESCROW_REFUND":
        return _to_ait_address(lock_tx.sender or "")
    return None


_ESCROW_SETTLEMENT_TYPES = ("ESCROW_RELEASE", "ESCROW_REFUND")


def _escrow_lock_rows(session: Session, chain_id: str, job_id: str) -> list[Transaction]:
    """All applied ESCROW_LOCK rows for ``job_id``.

    Only ``status='confirmed'`` transactions moved funds — rejected
    write-backs and failed applies never did and must not count toward
    the obligation.
    """
    return list(
        session.exec(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                Transaction.type == "ESCROW_LOCK",
                Transaction.payload.op("->>")("job_id") == job_id,  # type: ignore
                Transaction.status == "confirmed",
            )
        )
    )


def _sum_confirmed_escrow_values(
    session: Session, chain_id: str, job_id: str, tx_types: tuple[str, ...], exclude_tx_hash: str = ""
) -> int | None:
    """Σ ``value`` of confirmed ``tx_types`` rows for ``job_id``; None when a row's
    value is missing/unparseable (the caller treats the state as unbounded)."""
    total = 0
    for tx in session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type.in_(tx_types),  # type: ignore
            Transaction.payload.op("->>")("job_id") == job_id,  # type: ignore
            Transaction.status == "confirmed",
        )
    ):
        if exclude_tx_hash and tx.tx_hash == exclude_tx_hash:
            continue
        try:
            total += int(tx.value)
        except (TypeError, ValueError):
            return None
    return total


def _escrow_obligation_state(
    session: Session, chain_id: str, job_id: str, exclude_tx_hash: str = "", fee_cap_bps: int | None = None
) -> dict[str, Any]:
    """v23 obligation accounting for one job's escrow custody.

    ``obligation`` = Σ sealed ``ESCROW_LOCK.value``;
    ``settled`` = Σ sealed ``ESCROW_RELEASE``/``ESCROW_REFUND``.value
    (``exclude_tx_hash`` lets a tx be revalidated without counting
    itself); ``remaining`` = obligation − settled is the most any single
    release/refund may still pay, and custody beyond it is sweep residue.

    A lock or settlement row whose ``value`` is missing/unparseable marks
    the state unbounded: ``remaining`` is ``None`` and callers must fail
    closed rather than under-count what is owed.

    With ``fee_cap_bps`` (sweep validation), the state also carries ``swept``
    (Σ sealed ``ESCROW_FEE_SWEEP``.value) and ``fee_allowance`` =
    ``obligation × fee_cap_bps / 10000 − swept`` (floored at 0), which is 0
    until some release/refund has settled (``settled > 0``): the authority
    cannot pull the fee out of a lock nothing has settled yet.
    """
    obligation = 0
    unbounded = False
    for lock in _escrow_lock_rows(session, chain_id, job_id):
        try:
            obligation += int(lock.value)
        except (TypeError, ValueError):
            unbounded = True
            break
    settled = 0
    swept = 0
    fee_allowance = 0
    if not unbounded:
        settled_sum = _sum_confirmed_escrow_values(session, chain_id, job_id, _ESCROW_SETTLEMENT_TYPES, exclude_tx_hash)
        unbounded = settled_sum is None
        settled = settled_sum or 0
    if fee_cap_bps is not None and not unbounded:
        swept_sum = _sum_confirmed_escrow_values(session, chain_id, job_id, ("ESCROW_FEE_SWEEP",), exclude_tx_hash)
        unbounded = swept_sum is None
        swept = swept_sum or 0
        if not unbounded and settled > 0:
            fee_allowance = max(0, obligation * fee_cap_bps // 10_000 - swept)
    return {
        "obligation": obligation,
        "settled": settled,
        "swept": swept,
        "fee_allowance": fee_allowance,
        "remaining": None if unbounded else obligation - settled,
        "unbounded": unbounded,
    }


def _escrow_lock_beneficiaries(session: Session, chain_id: str, job_id: str, tx_type: str) -> tuple[str | None, bool]:
    """v23 beneficiary resolution across ALL sealed locks for ``job_id``.

    ``ESCROW_RELEASE`` pays each lock's recorded ``provider``;
    ``ESCROW_REFUND`` pays each lock's ``sender``. Returns
    ``(beneficiary, ambiguous)`` — more than one distinct beneficiary, or
    a lock whose beneficiary field is missing, is ambiguous and the caller
    must refuse rather than guess.
    """
    seen: set[str] = set()
    for lock in _escrow_lock_rows(session, chain_id, job_id):
        if tx_type == "ESCROW_RELEASE":
            provider = (lock.payload or {}).get("provider") or ""
            addr = _to_ait_address(provider) if provider else None
        elif tx_type == "ESCROW_REFUND":
            addr = _to_ait_address(lock.sender or "") if lock.sender else None
        else:
            return None, True
        if not addr:
            return None, True
        seen.add(addr)
    if len(seen) == 1:
        return next(iter(seen)), False
    return (None, True) if seen else (None, False)


_ESCROW_CONTEXT_TYPES = ("ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")


def _escrow_tx_job_id(tx_data: dict[str, Any]) -> str:
    payload = tx_data.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (RecursionError, TypeError, ValueError):  # malformed payload JSON decodes to the empty/default branch
            payload = {}
    return payload.get("job_id") or tx_data.get("job_id") or ""


def _escrow_v23_context_params(session: Session, chain_id: str, block_height: int | None) -> tuple[bool, int | None]:
    """v23 gate + fee cap for ``build_escrow_context`` — below v23 the
    context is bit-for-bit what it always was (no obligation fields)."""
    if block_height is None or get_block_version_for_height(block_height) < 23:
        return False, None
    return True, _escrow_fee_cap_bps(session, chain_id, block_height)


def _escrow_duplicate_settlement(tx_datas: list[dict[str, Any]]) -> bool:
    """v23 (R12-05-F1/#1232, R14-06-F1/#1230): two settlement txs for one job
    cannot share a single static ``remaining`` — the second must see the
    first's settlement — so such a batch falls back to sequential, which
    applies the checks in order."""
    settlement_counts: dict[str, int] = {}
    for tx_data in tx_datas:
        if _tx_type(tx_data) not in _ESCROW_CONTEXT_TYPES:
            continue
        job_id = _escrow_tx_job_id(tx_data)
        settlement_counts[job_id] = settlement_counts.get(job_id, 0) + 1
    return any(count > 1 for count in settlement_counts.values())


def _escrow_merge_existing_entry(
    session: Session,
    chain_id: str,
    tx_type: str,
    job_id: str,
    entry: dict[str, Any],
    resolved_fee_recipient: Callable[[], str | None],
) -> dict[str, Any] | None:
    """Fold a settlement tx into an existing context entry.

    Returns the (possibly mutated) entry to store, or ``None`` when the
    batch must go sequential so its own checks apply. An entry that already
    covers this tx is returned unchanged.
    """
    if entry.get("tx_type") == tx_type:
        return entry
    if tx_type == "ESCROW_FEE_SWEEP":
        # Release/refund + sweep for one job is the designed settlement
        # cadence: the sweep adds no beneficiary constraint, it only
        # needs the chain-level fee recipient on the entry.
        entry["fee_recipient"] = resolved_fee_recipient()
        return entry
    if entry.get("tx_type") == "ESCROW_FEE_SWEEP":
        # The sweep arrived first; this release/refund still needs its
        # lock fields resolved against the same entry.
        lock_tx = _get_escrow_lock(session, chain_id, job_id) if job_id else None
        if lock_tx is None:
            return None
        entry["tx_type"] = tx_type
        entry["lock_version"] = _get_escrow_lock_block_version(session, chain_id, job_id)
        entry["expected_beneficiary"] = _escrow_beneficiary(lock_tx, tx_type)
        return entry
    # A second release/refund for the same job with a different tx_type
    # would need a different beneficiary — an invalid batch anyway; let
    # the sequential path apply its own checks.
    return None


def _escrow_new_context_entry(
    session: Session,
    chain_id: str,
    tx_type: str,
    job_id: str,
    *,
    v23: bool,
    obligation_fields: Callable[[str], dict[str, Any]],
    resolved_authority: Callable[[], str | None],
    resolved_fee_recipient: Callable[[], str | None],
) -> dict[str, Any] | None:
    if tx_type == "ESCROW_FEE_SWEEP":
        entry: dict[str, Any] = {
            "tx_type": tx_type,
            "escrow_addr": _escrow_address(job_id) if job_id else "",
            "settlement_authority": resolved_authority(),
            "fee_recipient": resolved_fee_recipient(),
        }
        if v23:
            entry.update(obligation_fields(job_id))
        return entry
    lock_tx = _get_escrow_lock(session, chain_id, job_id) if job_id else None
    if lock_tx is None:
        return None
    if v23:
        # v23: beneficiary resolves across ALL sealed locks; ambiguity
        # sends the batch sequential where validate_transaction refuses
        # it identically.
        expected_beneficiary, beneficiary_ambiguous = _escrow_lock_beneficiaries(session, chain_id, job_id, tx_type)
        if beneficiary_ambiguous:
            return None
    else:
        expected_beneficiary = _escrow_beneficiary(lock_tx, tx_type)
    entry = {
        "tx_type": tx_type,
        "lock_version": _get_escrow_lock_block_version(session, chain_id, job_id),
        "expected_beneficiary": expected_beneficiary,
        "escrow_addr": _escrow_address(job_id),
        # The pure path has no DB access — every entry carries the
        # resolved chain-level values.
        "settlement_authority": resolved_authority(),
    }
    if v23:
        entry.update(obligation_fields(job_id))
    return entry


class _EscrowContextParams:
    """Per-batch lazy resolvers for ``build_escrow_context``.

    The chain-level parameters are not per-job — resolve them lazily on the
    first escrow tx so batches without one never pay for the queries.
    """

    def __init__(self, session: Session, chain_id: str, block_height: int | None, fee_cap_bps: int | None) -> None:
        self._session = session
        self._chain_id = chain_id
        self._block_height = block_height
        self._fee_cap_bps = fee_cap_bps
        self._authority: str | None = None
        self._authority_resolved = False
        self._fee_recipient: str | None = None
        self._fee_recipient_resolved = False
        self._obligation_cache: dict[str, dict[str, Any]] = {}

    def authority(self) -> str | None:
        if not self._authority_resolved:
            self._authority = _escrow_settlement_authority(self._session, self._chain_id, self._block_height)
            self._authority_resolved = True
        return self._authority

    def fee_recipient(self) -> str | None:
        if not self._fee_recipient_resolved:
            self._fee_recipient = _escrow_fee_recipient(self._session, self._chain_id, self._block_height)
            self._fee_recipient_resolved = True
        return self._fee_recipient

    def obligation_fields(self, job_id: str) -> dict[str, Any]:
        if job_id not in self._obligation_cache:
            self._obligation_cache[job_id] = _escrow_obligation_state(
                self._session, self._chain_id, job_id, fee_cap_bps=self._fee_cap_bps
            )
        state = self._obligation_cache[job_id]
        return {
            "remaining_obligation": state["remaining"],
            "obligation_unbounded": state["unbounded"],
            "fee_allowance": state["fee_allowance"],
        }


def build_escrow_context(
    session: Session, chain_id: str, tx_datas: list[dict[str, Any]], block_height: int | None = None
) -> dict[str, dict[str, Any]] | None:
    """Prefetch per-job metadata for ESCROW_RELEASE/ESCROW_REFUND/ESCROW_FEE_SWEEP txs (S-4, v11).

    The pure/parallel ``compute_state_delta`` cannot touch the DB, so callers
    that want parallel validation of v3+ blocks must supply this map:
    ``{job_id: {"lock_version": int|None, "expected_beneficiary": str|None,
    "escrow_addr": str, "settlement_authority": str|None,
    "fee_recipient": str|None}}``.
    ``settlement_authority``/``fee_recipient`` are chain-level (on-chain
    parameters, env fallback) rather than per-job, but every entry carries the
    resolved values so the pure path never needs a session.

    A sweep needs no lock: the custody account is derived from the job_id and a
    v2-era job simply holds no balance there. A release/refund plus a sweep for
    the same job in one batch is the designed settlement cadence, so a sweep
    merges into an existing entry instead of forcing the sequential path.

    Returns ``None`` when any release/refund references a job_id with no
    on-chain lock — the sequential path applies its own missing-lock rules, so
    the caller must keep sequential processing to stay consensus-identical.
    Batches with no escrow settlement txs return ``{}`` (cheap no-op).
    """
    context: dict[str, dict[str, Any]] = {}
    # v23 (R12-05-F1/#1232, R14-06-F1/#1230): each context entry carries the
    # job's obligation state so the pure path can enforce the bound without
    # a session. Two settlement txs for one job cannot share a single
    # static ``remaining`` — the second must see the first's settlement —
    # so such a batch falls back to sequential, which applies the checks
    # in order. Below v23 the context is bit-for-bit what it always was.
    v23, fee_cap_bps = _escrow_v23_context_params(session, chain_id, block_height)
    params = _EscrowContextParams(session, chain_id, block_height, fee_cap_bps)

    if v23 and _escrow_duplicate_settlement(tx_datas):
        return None

    for tx_data in tx_datas:
        tx_type = _tx_type(tx_data)
        if tx_type not in _ESCROW_CONTEXT_TYPES:
            continue
        job_id = _escrow_tx_job_id(tx_data)
        existing = context.get(job_id)
        if existing is not None:
            entry = _escrow_merge_existing_entry(session, chain_id, tx_type, job_id, existing, params.fee_recipient)
        else:
            entry = _escrow_new_context_entry(
                session,
                chain_id,
                tx_type,
                job_id,
                v23=v23,
                obligation_fields=params.obligation_fields,
                resolved_authority=params.authority,
                resolved_fee_recipient=params.fee_recipient,
            )
        if entry is None:
            return None
        context[job_id] = entry
    return context


def _refund_lock_record(session: Session, chain_id: str, lock_hash: str, exclude_tx_hash: str = "") -> dict[str, Any]:
    """Resolve the ``{exists, sender, amount, refunded}`` record for a refund's
    named lock — the shape ``validate_bridge_refund_lock`` consumes.

    ``refunded`` means another *sealed* ``BRIDGE_REFUND`` (``block_height`` set,
    hash different from ``exclude_tx_hash``) already names the same lock — so a
    legitimately sealed refund re-validates cleanly while a second refund for
    the same lock fails. ``exists`` requires the lock row to be sealed too.
    """
    lock = session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.tx_hash == lock_hash,
            Transaction.type == "BRIDGE_LOCK",
        )
    ).first()
    refunded = False
    for prior in session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == "BRIDGE_REFUND",
            Transaction.block_height.is_not(None),  # type: ignore[union-attr]
        )
    ):
        if exclude_tx_hash and prior.tx_hash == exclude_tx_hash:
            continue
        prior_payload = prior.payload if isinstance(prior.payload, dict) else {}
        if prior_payload.get("lock_tx_hash") == lock_hash:
            refunded = True
            break
    return {
        "exists": lock is not None and lock.block_height is not None,
        "sender": lock.sender if lock else None,
        "amount": lock.value if lock else None,
        "refunded": refunded,
    }


def build_bridge_lock_context(
    session: Session, chain_id: str, tx_datas: list[dict[str, Any]]
) -> dict[str, dict[str, Any]] | None:
    """Prefetch lock records for BRIDGE_REFUND txs (v6), like ``build_escrow_context``.

    Returns ``{lock_tx_hash: {"exists","sender","amount","refunded"}}`` for the
    pure path. Returns ``None`` when the batch is unsafe for parallel
    resolution — two refunds naming the same lock — so the caller falls back to
    the sequential path, which applies the double-refund rule in order.
    Batches with no refunds return ``{}`` (cheap no-op).
    """
    context: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for tx_data in tx_datas:
        if _tx_type(tx_data) != "BRIDGE_REFUND":
            continue
        lock_hash = bridge_refund_lock_hash(tx_data)
        if lock_hash in seen:
            return None
        seen.add(lock_hash)
        if lock_hash and lock_hash not in context:
            context[lock_hash] = _refund_lock_record(session, chain_id, lock_hash)
    return context
