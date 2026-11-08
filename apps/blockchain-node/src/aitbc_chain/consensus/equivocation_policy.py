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


def justified_unlock(payload: dict[str, Any]) -> bool:
    """True only when the payload carries a *registered, verifying* unlock proof.

    Fails closed: no justification, an unknown kind (including ``time``,
    ``journal_valve`` and ``operator``), a malformed justification or a
    verifier that raises all mean "not justified" — the pair stands.
    """
    justification = payload.get(JUSTIFICATION_FIELD)
    if not isinstance(justification, dict):
        return False
    kind = justification.get("kind")
    verifier = UNLOCK_PROOF_VERIFIERS.get(kind) if isinstance(kind, str) else None
    if verifier is None:
        return False
    try:
        return verifier(justification) is True
    except Exception:  # noqa: BLE001 - a broken proof must never excuse an equivocation
        return False


def pair_stands_as_evidence(payload: dict[str, Any]) -> bool:
    """A signature-bearing pair is slashable evidence unless its unlock is justified."""
    return not justified_unlock(payload)
