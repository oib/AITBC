"""Equivocation policy (#1274, EQUIV-XROUND-1) — what counts as slashable evidence.

Audit-Director ruling (#1274 comment 20233), encoded here as one pure,
DB-free, clock-free module so the recorder and the on-chain gate cannot drift:

1. Two signatures by the same validator over *different* hashes at the *same*
   height are equivocation evidence **across rounds** — in the legacy format
   (``round_in_payload`` false, no round filter) and in the round-bound format
   alike. Differing rounds never downgrade a pair to advisory. There is no
   blanket "same-round only" rule.
2. A cross-round transition is excused ("justified") **only** when the
   evidence carries an independently verifiable protocol proof that the first
   vote was legitimately released (for example a quorum-certificate barrier
   — the Phase-2 design). A timer, an age threshold, the vote-journal valve or
   an operator assertion is *not* proof: it is a local claim a validator could
   make about itself, and the gate must not accept it.
3. Evidence that is not justified retains its consensus-visible consequence
   (the DOUBLE_SIGN slashing record and the deactivation gate's acceptance).

Today the registry of verifiable unlock proofs is **empty**, so every pair
stands as evidence and the gate verdicts are byte-identical to pre-#1274.
A future proof kind registers a verifier in :data:`UNLOCK_PROOF_VERIFIERS`;
because that changes the replayed verdict of a transaction, the registering
change must ship behind a version-height gate (see ``AGENTS/dev-workflow.md``,
consensus apply-time rule).

Nothing here touches signature verification: signatures are still verified
by ``state.deactivation_evidence`` first; this module only decides whether a
*verified* pair is excused.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# ``evidence["unlock_justification"] = {"kind": <registered proof kind>, ...}``
JUSTIFICATION_FIELD = "unlock_justification"


class PairClass(StrEnum):
    """Shape of a two-signature attestation equivocation pair."""

    LEGACY = "legacy"  # neither signature binds a round
    ROUND_BOUND_SAME_ROUND = "round_bound_same_round"
    ROUND_BOUND_CROSS_ROUND = "round_bound_cross_round"
    MIXED_FORMAT = "mixed_format"  # one round-bound, one legacy (e.g. proposer signature vs attestation)


def _round_in_payload(attestation: dict[str, Any]) -> bool:
    return bool(attestation.get("round_in_payload"))


def classify_attestation_pair(payload: dict[str, Any]) -> PairClass | None:
    """Classify the first two attestation records of an equivocation payload.

    Returns ``None`` when the payload carries fewer than two attestation dicts
    (a hash-only advisory record has nothing to classify).
    """
    attestations = payload.get("attestations")
    if not isinstance(attestations, list):
        return None
    records = [a for a in attestations if isinstance(a, dict)]
    if len(records) < 2:
        return None
    first, second = records[0], records[1]
    bound = (_round_in_payload(first), _round_in_payload(second))
    if bound == (False, False):
        return PairClass.LEGACY
    if bound[0] != bound[1]:
        return PairClass.MIXED_FORMAT
    if first.get("request_round") == second.get("request_round"):
        return PairClass.ROUND_BOUND_SAME_ROUND
    return PairClass.ROUND_BOUND_CROSS_ROUND


# kind -> verifier(justification) -> bool. Empty by design (see module doc).
UNLOCK_PROOF_VERIFIERS: dict[str, Callable[[dict[str, Any]], bool]] = {}


@dataclass(frozen=True)
class UcApplyContext:
    """Chain-state-only inputs for the apply-time ``uc`` proof (#1281).

    Built by the state transition from on-chain parameters and the sealed
    block time, never from this node's clock or env, so replay is deterministic.
    Absent (``None``) means the ``uc`` kind is not registered: legacy verdicts.
    """

    chain_id: str
    now: float
    validator_set: frozenset[str]
    max_age: float
    min_responses: int


def _uc_justified(payload: dict[str, Any], justification: dict[str, Any], ctx: UcApplyContext) -> bool:
    """A ``uc`` proof excuses only a cross-round pair, bound to the EARLIER vote's block."""
    if classify_attestation_pair(payload) is not PairClass.ROUND_BOUND_CROSS_ROUND:
        return False
    records = [a for a in payload.get("attestations", []) if isinstance(a, dict)][:2]
    first_round, second_round = records[0].get("request_round"), records[1].get("request_round")
    if not (isinstance(first_round, int) and isinstance(second_round, int)):
        return False
    if isinstance(first_round, bool) or isinstance(second_round, bool):
        return False
    locked = records[0] if first_round < second_round else records[1]
    if str(locked.get("chain_id", "")) != ctx.chain_id:
        return False
    from .unavail import verify_unavailability_cert

    ok, _reason = verify_unavailability_cert(
        justification.get("cert") or {},
        chain_id=ctx.chain_id,
        height=int(locked["height"]),
        block_hash=str(locked.get("hash", "")),
        validator_set=set(ctx.validator_set),
        now=ctx.now,
        max_age=ctx.max_age,
        min_resp=ctx.min_responses,
    )
    return ok


def justified_unlock(payload: dict[str, Any], uc_ctx: UcApplyContext | None = None) -> bool:
    """True only when the payload carries a *registered, verifying* unlock proof.

    Fails closed: no justification, an unknown kind (including ``time``,
    ``journal_valve`` and ``operator``), a malformed justification or a
    verifier that raises all mean "not justified" — the pair stands.
    """
    justification = payload.get(JUSTIFICATION_FIELD)
    if not isinstance(justification, dict):
        return False
    kind = justification.get("kind")
    if uc_ctx is not None and kind == "uc":
        try:
            return _uc_justified(payload, justification, uc_ctx)
        except Exception:  # noqa: BLE001 - fail closed: a broken proof never excuses
            return False
    verifier = UNLOCK_PROOF_VERIFIERS.get(kind) if isinstance(kind, str) else None
    if verifier is None:
        return False
    try:
        return verifier(justification) is True
    except Exception:  # noqa: BLE001 - a broken proof must never excuse an equivocation
        return False


def pair_stands_as_evidence(payload: dict[str, Any], uc_ctx: UcApplyContext | None = None) -> bool:
    """A signature-bearing pair is slashable evidence unless its unlock is justified."""
    return not justified_unlock(payload, uc_ctx)
