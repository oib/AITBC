"""Dormant PBFT VIEW_CHANGE / NEW_VIEW protocol (#2005 F3-C).

Design of record: #2005 design comment (16 parts) + rulings comment
(q=2f+1 uniform VC quorum, full signed block in pre-prepare, certificate
view pinned to derived round, ALL arming deferred — PBFT stays OFF).

This module is the pure, DB-free, clock-free core shared by the consensus
engine (``pbft.py``) and the on-chain unlock verifier
(``equivocation_policy`` / ``state.deactivation_evidence``):

- ``view_change_active(sequence)`` — the single settings-side gate,
  mirroring ``pbft_cross_view.cross_view_commit_lock_active``. Armed by
  ``ChainSettings.pbft_view_change_height``; ``None``/malformed/pre-
  threshold resolves False and every consumer behaves byte-identically to
  the pre-#2005 code.
- Wire schemas exactly as designed:

  - VIEW_CHANGE ``{message_type:"view_change", sender, sequence_number,
    view_number, digest, lock[, prepared]}`` with
    ``digest = sha256("vc|{chain_id}|{h}|{v'}|{lock_view}|{lock_hash}")``
    (``lock_view/hash`` = ``-1``/``""`` when the voter holds no commit
    lock). ``lock`` is ``null`` or ``{view, block_hash, commit_msgs:[own
    signed COMMIT]}`` — the voter's persisted commit-lock for the height.
  - NEW_VIEW ``{message_type:"new_view", sender, sequence_number,
    view_number, digest, vc_set, chosen_hash}`` with
    ``digest = sha256("nv|{chain_id}|{h}|{v'}|{chosen_hash or ''}|{sorted
    vc digests joined by ','}")``. The sender must be the scheduled
    proposer of ``(h, v')`` — checked by the caller, which owns the
    proposer schedule.

  Unlike the legacy PREPARE/COMMIT digests (``sha256(block_hash:seq:view)``,
  which do NOT bind chain_id and stay byte-identical for replay safety),
  every digest here binds ``chain_id`` and a domain tag, so a signed
  VIEW_CHANGE/NEW_VIEW cannot replay on another chain (#2102 stays a
  separate dormant hardening row for the legacy preimage).

- Quorum: ``pbft_required_messages(n)`` — the same q as commit
  certificates (ruling 1A). Any q-set intersects every commit quorum in
  >= f+1 members, at least one honest, so a q-sized VC set forces the
  committed value whenever one exists (§3 of the design).

- Deterministic selection, recomputed by every verifier and never trusted
  from the leader: ``analyze_vc_set`` validates each VC (signature, digest,
  chain binding, membership, lock-commit signatures) and
  ``select_forced_hash`` returns ``("locked", hash)`` for the highest-view
  reported lock, ``("free", None)`` when no VC reports a lock, or
  ``("conflict", None)`` when two different hashes claim the same highest
  lock view (fail closed — honest members cannot produce that, so the NEW_VIEW
  is unverifiable). A ``("locked", H)`` selection requires
  ``chosen_hash == H``; a ``("free", ...)`` selection requires
  ``chosen_hash`` to be null — the leader's free choice is the
  pre-prepare's own ``block_hash``, so any hash is permitted only when no
  commit quorum can exist (§6 of the design).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypeGuard

from aitbc.crypto.consensus_signing import verify_consensus_message
from aitbc.crypto.signature_recovery import SignatureMalformed, canonical_address

from ..config import settings
from .pbft_quorum import pbft_required_messages

VC_MESSAGE_TYPE = "view_change"
NV_MESSAGE_TYPE = "new_view"

# Flood bounds (#2005 §9 DoS row + design §8 test 8). All intake paths must
# enforce these BEFORE signature work where possible.
MAX_VC_PAYLOAD_BYTES = 65_536  # one VIEW_CHANGE incl. its lock commit_msgs
MAX_NV_PAYLOAD_BYTES = 1_048_576  # NEW_VIEW incl. the embedded vc_set
MAX_VC_SET_ENTRIES = 512  # vc_set records accepted inside one NEW_VIEW
MAX_LOCK_PROOF_MSGS = 64  # vote records a VC lock proof may carry
MAX_VC_BUCKETS = 256  # distinct (sequence, view) VC sets tracked per engine
MAX_NV_BUCKETS = 256  # distinct (sequence, view) NEW_VIEWs tracked per engine
MAX_PROPOSAL_PAYLOAD_BYTES = 1_000_000  # persisted pre-prepare block body
MAX_PROPOSALS_PER_SEQUENCE = 8  # proposal bodies retained per height


def _strict_int(value: Any) -> TypeGuard[int]:
    """Strictly ``int`` and not ``bool`` — JSON ``true`` must never pass as 1."""
    return isinstance(value, int) and not isinstance(value, bool)


def _non_empty_str(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and bool(value)


def view_change_active(sequence: int | None) -> bool:
    """Whether the VIEW_CHANGE/NEW_VIEW protocol applies at ``sequence``.

    Armed by ``pbft_view_change_height``: active iff a valid non-negative
    int threshold is configured AND ``sequence`` is a valid non-negative
    int at or above it — the same dormant shape as
    ``strict_certificate_active`` / ``cross_view_commit_lock_active``.
    ``None``/unset/malformed threshold or sequence resolves False — callers
    must treat False as "pre-#2005 behavior, byte-identical".
    """
    threshold = getattr(settings, "pbft_view_change_height", None)
    if not _strict_int(threshold):
        return False
    if threshold < 0:
        return False
    return _strict_int(sequence) and sequence >= threshold


# ---------------------------------------------------------------------------
# Digests — chain_id + domain tag bound into every new preimage (#2005 §2)
# ---------------------------------------------------------------------------


def vc_lock_fields(vc: dict[str, Any]) -> tuple[int, str]:
    """``(lock_view, lock_hash)`` a VIEW_CHANGE digest commits to.

    ``(-1, "")`` when the voter reports no commit lock — the design's
    explicit empty-lock encoding.
    """
    lock = vc.get("lock")
    if not isinstance(lock, dict):
        return -1, ""
    view = lock.get("view")
    block_hash = lock.get("block_hash")
    if not _strict_int(view) or view < 0 or not _non_empty_str(block_hash):
        return -1, ""
    return view, block_hash


def view_change_digest(chain_id: str, sequence: int, view: int, lock_view: int, lock_hash: str) -> str:
    """``sha256("vc|{chain_id}|{h}|{v'}|{lock_view}|{lock_hash}")``."""
    return hashlib.sha256(f"vc|{chain_id}|{sequence}|{view}|{lock_view}|{lock_hash}".encode()).hexdigest()


def new_view_digest(chain_id: str, sequence: int, view: int, chosen_hash: str | None, vc_digests: list[str]) -> str:
    """``sha256("nv|{chain_id}|{h}|{v'}|{chosen or ''}|{sorted digests joined})"``.

    The vc digests are sorted and joined with ``,`` — a canonical order
    independent of the order the leader collected them in.
    """
    joined = ",".join(sorted(vc_digests))
    return hashlib.sha256(f"nv|{chain_id}|{sequence}|{view}|{chosen_hash or ''}|{joined}".encode()).hexdigest()


def commit_digest(block_hash: str, sequence: int, view: int) -> str:
    """The legacy commit digest ``sha256(block_hash:seq:view)`` — reused to
    verify the own-COMMIT records embedded in a VC lock."""
    return hashlib.sha256(f"{block_hash}:{sequence}:{view}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# Signed subsets — the exact dicts ``sign_consensus_message`` /
# ``verify_consensus_message`` cover (same five fields as PBFT votes).
# ---------------------------------------------------------------------------


def vc_signed_message(vc: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_type": VC_MESSAGE_TYPE,
        "sender": vc.get("sender"),
        "view_number": vc.get("view_number"),
        "sequence_number": vc.get("sequence_number"),
        "digest": vc.get("digest"),
    }


def nv_signed_message(nv: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_type": NV_MESSAGE_TYPE,
        "sender": nv.get("sender"),
        "view_number": nv.get("view_number"),
        "sequence_number": nv.get("sequence_number"),
        "digest": nv.get("digest"),
    }


def commit_signed_message(commit: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_type": commit.get("message_type"),
        "sender": commit.get("sender"),
        "view_number": commit.get("view_number"),
        "sequence_number": commit.get("sequence_number"),
        "digest": commit.get("digest"),
    }


def _verify_signature(signed: dict[str, Any], signature: Any, sender: Any) -> bool:
    """``verify_consensus_message`` that never raises — malformed input is False."""
    if not _non_empty_str(signature) or not _non_empty_str(sender):
        return False
    try:
        return verify_consensus_message(signed, signature, sender)
    except (SignatureMalformed, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Structural gates + signature/digest verification
# ---------------------------------------------------------------------------


def _payload_size_ok(payload: dict[str, Any], limit: int) -> bool:
    try:
        return len(json.dumps(payload, separators=(",", ":"))) <= limit
    except (TypeError, ValueError):
        return False


def verify_view_change(vc: Any, chain_id: str, *, check_signature: bool = True) -> tuple[bool, str]:
    """Structural + digest + signature check for one VIEW_CHANGE.

    ``check_signature=False`` is for callers that already verified the
    signature over the same bytes (none today — kept for symmetry with the
    NEW_VIEW path which verifies signatures inside ``analyze_vc_set``).
    Returns ``(True, "")`` or ``(False, reason)``.
    """
    if not isinstance(vc, dict):
        return False, "view_change is not an object"
    if vc.get("message_type") != VC_MESSAGE_TYPE:
        return False, "view_change message_type mismatch"
    sender = vc.get("sender")
    seq = vc.get("sequence_number")
    view = vc.get("view_number")
    digest = vc.get("digest")
    if not _non_empty_str(sender) or not _non_empty_str(digest):
        return False, "view_change missing sender or digest"
    if not (_strict_int(seq) and seq >= 0) or not (_strict_int(view) and view >= 0):
        return False, "view_change has non-strict-int sequence or view"
    if not _payload_size_ok(vc, MAX_VC_PAYLOAD_BYTES):
        return False, "view_change payload exceeds size cap"
    lock_view, lock_hash = vc_lock_fields(vc)
    if digest != view_change_digest(chain_id, seq, view, lock_view, lock_hash):
        return False, "view_change digest does not match vc preimage"
    if check_signature and not _verify_signature(vc_signed_message(vc), vc.get("signature"), sender):
        return False, "view_change signature verification failed"
    return True, ""


def _verify_lock_proof_record(msg: Any, kind: str, seq: int, lock_view: int, block_hash: str) -> tuple[str, str]:
    """One vote record inside a VC lock proof.

    Returns ``(canonical_sender, "")`` on success or ``("", reason)``. Must
    be a ``kind`` ("prepare"/"commit") vote at the VC's sequence and the
    lock's view for ``block_hash``, carrying the legacy digest and a valid
    signature by its own sender. Membership is the caller's check.
    """
    if not isinstance(msg, dict):
        return "", "view_change lock proof record is not an object"
    if msg.get("message_type") != kind:
        return "", "view_change lock proof record has the wrong message_type"
    sender = msg.get("sender")
    m_seq = msg.get("sequence_number")
    m_view = msg.get("view_number")
    m_digest = msg.get("digest")
    if (
        not _non_empty_str(sender)
        or not (_strict_int(m_seq) and m_seq == seq)
        or not (_strict_int(m_view) and m_view == lock_view)
        or msg.get("block_hash") != block_hash
        or not _non_empty_str(m_digest)
    ):
        return "", "view_change lock proof record fields do not match the lock"
    if m_digest != commit_digest(block_hash, m_seq, m_view):
        return "", "view_change lock proof record digest mismatch"
    if not _verify_signature(commit_signed_message(msg), msg.get("signature"), sender):
        return "", "view_change lock proof record signature verification failed"
    return canonical_address(sender), ""


def verify_vc_lock_proof(vc: dict[str, Any], canonical: set[str], required: int) -> tuple[bool, str]:
    """Verify the quorum certificate inside a VIEW_CHANGE ``lock`` (#2005 Q1).

    A lock is ``{view, block_hash, kind, msgs}`` where ``msgs`` are signed
    PREPARE (or COMMIT) votes for ``block_hash`` at ``view`` from at least
    ``required`` DISTINCT members of ``canonical``. A single member's own
    signature therefore proves nothing: a lone Byzantine voter cannot
    fabricate a lock, so it cannot force the next view onto a hash no
    quorum ever prepared. ``lock.view`` must lie strictly below the VC's
    target view. ``lock: null`` verifies trivially. Cheap structural and
    duplicate checks run before any signature is verified, and the record
    count is capped, so a proof costs a bounded number of verifications.
    """
    lock = vc.get("lock")
    if lock is None:
        return True, ""
    if not isinstance(lock, dict):
        return False, "view_change lock is not an object or null"
    lock_view = lock.get("view")
    block_hash = lock.get("block_hash")
    kind = lock.get("kind")
    msgs = lock.get("msgs")
    seq = vc.get("sequence_number")
    vc_view = vc.get("view_number")
    if not (_strict_int(lock_view) and lock_view >= 0) or not _non_empty_str(block_hash):
        return False, "view_change lock has malformed view or block_hash"
    if not _strict_int(seq) or not _strict_int(vc_view):
        return False, "view_change lock sequence or view malformed"
    if lock_view >= vc_view:
        return False, "view_change lock view is not below the target view"
    if kind not in ("prepare", "commit"):
        return False, "view_change lock kind must be prepare or commit"
    if not isinstance(msgs, list) or len(msgs) < required or len(msgs) > MAX_LOCK_PROOF_MSGS:
        return False, "view_change lock proof missing, below quorum or over cap"
    seen: set[str] = set()
    for msg in msgs:
        if not isinstance(msg, dict):
            return False, "view_change lock proof record is not an object"
        who = canonical_address(str(msg.get("sender", "")))
        if who not in canonical:
            return False, "view_change lock proof voter is not a consensus member"
        seen.add(who)
    if len(seen) < required:
        return False, "view_change lock proof has too few distinct voters"
    voters: set[str] = set()
    for msg in msgs:
        who, reason = _verify_lock_proof_record(msg, str(kind), seq, lock_view, block_hash)
        if reason:
            return False, reason
        voters.add(who)
    if len(voters) < required:
        return False, "view_change lock proof has too few distinct voters"
    return True, ""


def verify_new_view_signature(nv: Any, chain_id: str, vc_digests: list[str]) -> tuple[bool, str]:
    """Digest + signature check for one NEW_VIEW given its vc_set digests.

    The caller must pass the digests of the EXACT ``vc_set`` records carried
    in the message — the digest binds them, so they cannot be swapped after
    signing.
    """
    if not isinstance(nv, dict):
        return False, "new_view is not an object"
    if nv.get("message_type") != NV_MESSAGE_TYPE:
        return False, "new_view message_type mismatch"
    sender = nv.get("sender")
    seq = nv.get("sequence_number")
    view = nv.get("view_number")
    digest = nv.get("digest")
    chosen = nv.get("chosen_hash")
    if not _non_empty_str(sender) or not _non_empty_str(digest):
        return False, "new_view missing sender or digest"
    if not (_strict_int(seq) and seq >= 0) or not (_strict_int(view) and view >= 0):
        return False, "new_view has non-strict-int sequence or view"
    if chosen is not None and not _non_empty_str(chosen):
        return False, "new_view chosen_hash malformed"
    if not _payload_size_ok(nv, MAX_NV_PAYLOAD_BYTES):
        return False, "new_view payload exceeds size cap"
    expected = new_view_digest(chain_id, seq, view, chosen, vc_digests)
    if digest != expected:
        return False, "new_view digest does not match nv preimage"
    if not _verify_signature(nv_signed_message(nv), nv.get("signature"), sender):
        return False, "new_view signature verification failed"
    return True, ""


# ---------------------------------------------------------------------------
# VC-set analysis and deterministic selection
# ---------------------------------------------------------------------------


def _vc_record_acceptable(
    vc: Any,
    canonical: set[str],
    *,
    chain_id: str,
    sequence: int,
    view: int,
    required: int,
) -> tuple[bool, str]:
    """One vc_set record: signature, digest, chain binding, target
    (sequence, view), membership and the lock's quorum proof."""
    ok, reason = verify_view_change(vc, chain_id)
    if not ok:
        return False, reason
    if vc.get("sequence_number") != sequence or vc.get("view_number") != view:
        return False, "view_change in vc_set targets a different sequence or view"
    sender_canonical = canonical_address(str(vc.get("sender", "")))
    if sender_canonical not in canonical:
        return False, "view_change sender is not a consensus member"
    return verify_vc_lock_proof(vc, canonical, required)


def analyze_vc_set(
    vc_set: Any,
    validators: Any,
    *,
    chain_id: str,
    sequence: int,
    view: int,
    required: int | None = None,
) -> tuple[bool, str, dict[str, dict[str, Any]]]:
    """Validate a NEW_VIEW ``vc_set``; return ``(ok, reason, by_sender)``.

    Every record must be a VIEW_CHANGE for exactly ``(sequence, view)`` on
    ``chain_id`` from a distinct canonical member of ``validators`` —
    signature, digest, chain binding, lock-commit signatures all verified.
    Distinct senders must reach ``required`` (default
    ``pbft_required_messages(n)`` for the canonical member count). The
    returned map is keyed by canonical sender so a duplicated sender can
    never inflate the count.
    """
    canonical = {canonical_address(m) for m in validators if isinstance(m, str) and m}
    canonical.discard("")
    if not canonical:
        return False, "empty validator set", {}
    if required is None:
        required = pbft_required_messages(len(canonical))
    if not isinstance(vc_set, list) or not vc_set:
        return False, "new_view vc_set is not a non-empty list", {}
    if len(vc_set) > MAX_VC_SET_ENTRIES or len(vc_set) > len(canonical):
        # More records than members means duplicates — reject BEFORE the
        # per-record ECDSA verifications so a padded vc_set costs nothing.
        return False, "new_view vc_set exceeds entry cap", {}
    by_sender: dict[str, dict[str, Any]] = {}
    for vc in vc_set:
        ok, reason = _vc_record_acceptable(vc, canonical, chain_id=chain_id, sequence=sequence, view=view, required=required)
        if not ok:
            return False, reason, {}
        # First record per sender wins; a second conflicting VC from the
        # same sender is simply not counted (it cannot inflate quorum).
        by_sender.setdefault(canonical_address(str(vc.get("sender", ""))), vc)
    if len(by_sender) < required:
        return False, f"only {len(by_sender)} distinct view_changes, need {required}", {}
    return True, "", by_sender


def select_forced_hash(vcs: dict[str, dict[str, Any]]) -> tuple[str, str | None]:
    """Deterministic value selection over validated VIEW_CHANGEs.

    Returns ``(kind, hash_or_none)``:

    - ``("free", None)`` — no VC reports a commit lock: no commit quorum
      can exist below this view (§6), the choice is free.
    - ``("locked", hash)`` — the hash of the highest-view reported lock.
      Two different hashes at the SAME highest lock view is
      ``("conflict", None)`` — honest members cannot produce it, so the
      NEW_VIEW fails closed.
    """
    locks: list[tuple[int, str]] = []
    for vc in vcs.values():
        lock = vc.get("lock")
        if isinstance(lock, dict):
            view = lock.get("view")
            block_hash = lock.get("block_hash")
            if _strict_int(view) and view >= 0 and _non_empty_str(block_hash):
                locks.append((view, block_hash))
    if not locks:
        return "free", None
    top_view = max(view for view, _ in locks)
    top_hashes = {block_hash for view, block_hash in locks if view == top_view}
    if len(top_hashes) > 1:
        return "conflict", None
    return "locked", next(iter(top_hashes))


def verify_new_view(
    nv: Any,
    validators: Any,
    *,
    chain_id: str,
    sequence: int,
    view: int,
    expected_sender: str | None,
    required: int | None = None,
) -> tuple[bool, str, str | None, str | None]:
    """Full NEW_VIEW verification — the one verdict engine and evidence share.

    Checks, in order: payload shape/size, ``vc_set`` analysis (each VC's
    signature, digest, chain binding, membership, lock commits, distinct
    senders reaching ``required``), the NEW_VIEW digest recomputed over the
    carried vc digests, the NEW_VIEW signature, the scheduled-proposer
    sender (``expected_sender``; ``None`` skips the schedule check for
    callers without a schedule), and the deterministic selection:

    - ``("locked", H)`` requires ``chosen_hash == H`` — returns the
      selected hash;
    - ``("free", ...)`` requires ``chosen_hash`` null — returns ``None``
      meaning "any hash permitted";
    - ``("conflict", ...)`` always fails.

    Returns ``(ok, reason, selection_kind, selected_hash)``.
    """
    if not isinstance(nv, dict):
        return False, "new_view is not an object", None, None
    if nv.get("message_type") != NV_MESSAGE_TYPE:
        return False, "new_view message_type mismatch", None, None
    if nv.get("sequence_number") != sequence or nv.get("view_number") != view:
        return False, "new_view targets a different sequence or view", None, None
    if not _payload_size_ok(nv, MAX_NV_PAYLOAD_BYTES):
        return False, "new_view payload exceeds size cap", None, None
    vc_set = nv.get("vc_set")
    ok, reason, by_sender = analyze_vc_set(
        vc_set, validators, chain_id=chain_id, sequence=sequence, view=view, required=required
    )
    if not ok:
        return False, reason, None, None
    # The digest must bind EVERY carried vc record — including duplicate-
    # sender records analyze_vc_set collapsed — so recompute over the raw
    # vc_set digests, not the deduped map. ``analyze_vc_set`` already proved
    # ``vc_set`` is a list; re-check for the type checker.
    if not isinstance(vc_set, list):
        return False, "new_view vc_set is not a list", None, None
    raw_digests = [str(vc.get("digest", "")) for vc in vc_set if isinstance(vc, dict)]
    ok, reason = verify_new_view_signature(nv, chain_id, raw_digests)
    if not ok:
        return False, reason, None, None
    if expected_sender is not None:
        if canonical_address(str(nv.get("sender", ""))) != canonical_address(expected_sender):
            return False, "new_view sender is not the scheduled proposer", None, None
    kind, selected = select_forced_hash(by_sender)
    return _new_view_selection_verdict(nv, kind, selected)


def _new_view_selection_verdict(
    nv: dict[str, Any], kind: str, selected: str | None
) -> tuple[bool, str, str | None, str | None]:
    """The deterministic-selection tail of ``verify_new_view``.

    ``("locked", H)`` requires ``chosen_hash == H``; ``("free", ...)``
    requires ``chosen_hash`` null — the leader's free choice is the
    pre-prepare's own ``block_hash``; ``("conflict", ...)`` always fails.
    """
    if kind == "conflict":
        return False, "new_view selection conflict: two hashes claim the highest lock view", None, None
    chosen = nv.get("chosen_hash")
    if kind == "locked":
        if chosen != selected:
            return False, "new_view chosen_hash does not match the forced selection", None, None
        return True, "", kind, selected
    # free: the leader carries no choice — the pre-prepare's hash is it.
    if chosen is not None:
        return False, "free new_view must carry chosen_hash=null", None, None
    return True, "", kind, None


def new_view_permits(nv: dict[str, Any], block_hash: str) -> bool:
    """Whether a verified NEW_VIEW permits voting ``block_hash`` at its view.

    ``nv`` must be a dict that already passed ``verify_new_view`` — the
    ``selection_kind``/``selected_hash`` fields are stamped by the engine
    at intake; a hand-built dict without them is treated conservatively
    (only an explicit ``"free"`` kind permits arbitrary hashes).
    """
    kind = nv.get("selection_kind")
    if kind == "free":
        return True
    if kind == "locked":
        return nv.get("chosen_hash") == block_hash
    return False
