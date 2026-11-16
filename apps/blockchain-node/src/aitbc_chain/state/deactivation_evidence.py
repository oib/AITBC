"""On-chain verification of ``VALIDATOR_DEACTIVATE`` evidence (#1263).

Runs inside ``StateTransition._handle_validator_deactivation`` when the
``validator_deactivation_evidence_required`` chain parameter is armed at the
block height. Everything here is a pure function of the transaction payload
and ``chain_id`` — no DB reads, no wall clock — so replay and reorg produce
identical verdicts on every node.

Gate semantics (spec v1, approved):

- ``payload.evidence_version`` must be ``2``;
- ``payload.evidence`` is the validator's canonical event list (same record
  shape as ``ConsensusState.slashing_events_json``); rebuilding the
  ``SlashingManager.evidence_bundle`` over it must reproduce
  ``payload.evidence_hash`` exactly — the hash binds every cited event;
- at least one event must be a *verified* equivocation, and every
  equivocation claim (``attestation_equivocation`` /
  ``vote_equivocation`` / legacy free-text double-sign) must verify —
  unverifiable claims fail the whole marker;
- non-equivocation conditions are hash-bound informational records only.

#1940 ruling A — per-event UC freshness: when the on-chain boolean
``unlock_proof_uc_evidence_time_enabled`` is armed at the apply height, the
``uc`` unlock proof's freshness clock is each DOUBLE_SIGN attestation event's
own evidence block time — the canonical ``Block.timestamp`` at
``(chain_id, event.block_height)`` — never the apply block's time and never
this node's wall clock. ``evidence_height == apply_height`` reuses the sealed
caller ``block_time`` because the block being applied may not be inserted
yet; negative, future (> apply height), missing or timeless evidence stays
unexcused. Parameter unset or false keeps the single apply-time context
exactly as before #1940, and the flag-off path performs no block queries.
Events already expired under ``validator_deactivation_evidence_ttl_blocks``
(#1959) are skipped before any evidence-block lookup, and the canonical
read selects only ``Block.timestamp`` — never the full ORM row.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from decimal import Decimal
from datetime import UTC, datetime
from typing import Any, TypeGuard

from sqlmodel import Session, select

from aitbc.crypto.consensus_signing import verify_consensus_message, verify_consensus_message_domain
from aitbc.crypto.signature_recovery import SignatureMalformed, canonical_address

from ..base_models import Block
from ..config import legacy_attestation_dual_accept_open, settings
from ..consensus.equivocation_policy import UcApplyContext, pair_stands_as_evidence
from ..consensus.slashing import PBFT_CROSS_VIEW_VOTE_EQUIVOCATION, SlashingCondition, SlashingEvent, SlashingManager

EVIDENCE_VERSION = 2
MAX_EVIDENCE_EVENTS = 32


def _strict_int(value: Any) -> TypeGuard[int]:
    """Strictly ``int`` and not ``bool`` — JSON ``true`` must never pass as 1."""
    return isinstance(value, int) and not isinstance(value, bool)


def _cross_view_evidence_height(session: Session, chain_id: str, block_height: int | None) -> int | None:
    """Activation height for cross-view commit equivocation evidence (#1940 F3-A).

    Reads the chain parameter
    ``validator_deactivation_pbft_cross_view_evidence_height`` through
    ``_chain_parameter_value`` at the apply ``block_height`` — the same
    height-scoped rule every gate parameter uses, so replay and reorg agree
    and a value armed later never rewrites earlier applies. Only a strict
    non-negative int activates; unset, malformed, negative or bool-ish values
    resolve to ``None``, which the verifier treats as "every cross-view claim
    is unverifiable" (fail closed).
    """
    from .state_transition import _chain_parameter_value

    value = _chain_parameter_value(session, chain_id, "validator_deactivation_pbft_cross_view_evidence_height", block_height)
    if value is None:
        return None
    try:
        height = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return height if height >= 0 else None


def _evidence_required(session: Session, chain_id: str, block_height: int | None) -> bool:
    """Whether the armed gate applies at ``block_height`` (chain parameter)."""
    from .state_transition import _chain_parameter_value

    value = _chain_parameter_value(session, chain_id, "validator_deactivation_evidence_required", block_height)
    return bool(value and value.strip().lower() in ("true", "1", "yes"))


def _uc_context(
    session: Session, chain_id: str, block_height: int | None, block_time: datetime | None
) -> UcApplyContext | None:
    """Apply-time inputs for the ``uc`` unlock proof, or None (= not registered).

    Dormant: needs the on-chain parameter ``unlock_proof_uc_enabled`` in force at
    ``block_height`` plus ``unlock_proof_uc_min_responses``, ``unlock_proof_uc_max_age_seconds``
    and ``unlock_proof_uc_validator_set_digest`` (sha256 of the sorted canonical
    validator addresses joined by newlines). Fail closed on anything missing,
    malformed or mismatched, including a local validator set whose digest differs
    from the on-chain one (so after a rotation the proof stops excusing until the
    digest parameter is updated: #1281 option-3 slice; replaying pre-rotation
    excusals is NOT supported, see the issue).
    """
    from ..consensus.unavail import validator_addresses
    from .state_transition import _chain_parameter_value

    if block_height is None or block_time is None:
        return None

    def param(name: str) -> str | None:
        return _chain_parameter_value(session, chain_id, f"unlock_proof_uc_{name}", block_height)

    enabled = param("enabled")
    if not (enabled and enabled.strip().lower() in ("true", "1", "yes")):
        return None
    try:
        min_responses = int(str(param("min_responses")))
        max_age = float(str(param("max_age_seconds")))
    except (TypeError, ValueError):
        return None
    digest = (param("validator_set_digest") or "").strip().lower()
    vset = validator_addresses()
    local_digest = hashlib.sha256("\n".join(sorted(vset)).encode()).hexdigest()
    if min_responses < 1 or not (max_age > 0) or not vset or digest != local_digest:
        return None
    when = block_time if block_time.tzinfo is not None else block_time.replace(tzinfo=UTC)
    return UcApplyContext(
        chain_id=chain_id,
        now=when.timestamp(),
        validator_set=frozenset(vset),
        max_age=max_age,
        min_responses=min_responses,
    )


def _uc_evidence_time_enabled(session: Session, chain_id: str, block_height: int | None) -> bool:
    """Whether per-event UC evidence time is armed at ``block_height`` (#1940 ruling A).

    On-chain boolean ``unlock_proof_uc_evidence_time_enabled`` resolved through
    ``_chain_parameter_value`` at the APPLY height — the same height-scoped
    rule every gate parameter uses, so replay and reorg agree and a value
    armed later never rewrites earlier applies. Missing or false keeps the
    pre-#1940 single apply-time context exactly.
    """
    from .state_transition import _chain_parameter_value

    value = _chain_parameter_value(session, chain_id, "unlock_proof_uc_evidence_time_enabled", block_height)
    return bool(value and value.strip().lower() in ("true", "1", "yes"))


def _canonical_block_time(session: Session, chain_id: str, height: int) -> datetime | None:
    """Timestamp of the canonical ``Block`` at ``(chain_id, height)``, or None.

    Both keys are constrained — a block on another chain at the same height
    can never supply the time — and ``(chain_id, height)`` is unique, so the
    row IS the canonical block: no rival-hash lookup, no fallback clock.
    Only the ``timestamp`` column is selected — a full ``Block`` ORM load
    would drag its transaction/receipt relationships through selectin
    loading inside block apply.
    """
    ts = session.exec(select(Block.timestamp).where(Block.chain_id == chain_id, Block.height == height)).first()
    return ts if isinstance(ts, datetime) else None


def _epoch_seconds(value: datetime | None) -> float | None:
    """Finite epoch seconds for a block timestamp; naive reads as UTC.

    Same naive-as-UTC rule as ``_uc_context``. ``None`` on missing,
    non-datetime or non-finite input — the event then stays unexcused.
    """
    if not isinstance(value, datetime):
        return None
    when = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    try:
        epoch = when.timestamp()
    except (OverflowError, OSError, ValueError):
        return None
    return epoch if math.isfinite(epoch) else None


def _uc_event_context(
    session: Session,
    chain_id: str,
    apply_height: int,
    apply_time: datetime,
    base: UcApplyContext,
    evidence_height: int,
) -> UcApplyContext | None:
    """UC context for ONE evidence height (#1940 ruling A).

    ``now`` is the canonical timestamp of the block at ``evidence_height``
    on this chain — never the apply block's time and never the wall clock.
    ``evidence_height == apply_height`` reuses the caller-sealed
    ``apply_time`` because the block being applied may not be inserted yet.
    Negative, future (> apply height), missing-row or timeless evidence
    resolves to ``None``: that event simply cannot be excused.
    """
    if evidence_height < 0 or evidence_height > apply_height:
        return None
    evidence_time: datetime | None
    if evidence_height == apply_height:
        evidence_time = apply_time
    else:
        evidence_time = _canonical_block_time(session, chain_id, evidence_height)
    epoch = _epoch_seconds(evidence_time)
    if epoch is None:
        return None
    return replace(base, now=epoch, evidence_height=evidence_height)


def _uc_event_contexts(
    session: Session,
    chain_id: str,
    block_height: int | None,
    block_time: datetime | None,
    events: list[SlashingEvent],
    base: UcApplyContext | None,
    ttl_blocks: int | None = None,
) -> dict[int, UcApplyContext | None] | None:
    """Per-event UC contexts keyed by evidence ``block_height`` (#1940 ruling A).

    ``None`` — the legacy single-context path — unless the on-chain
    ``unlock_proof_uc_evidence_time_enabled`` parameter is armed at the apply
    height AND the apply height/time are known AND the UC proof itself is
    armed (``base`` not None). Armed-but-unresolvable evidence heights map
    to ``None`` so those events stay unexcused; the flag-off path performs
    no block queries at all.

    ``ttl_blocks`` (#1959) mirrors the expiry predicate in
    ``_verify_equivocations``: a DOUBLE_SIGN event already expired at the
    apply height is skipped here as well — before ``_evidence_json`` and
    before any canonical block lookup — so a stale claim does no historical
    DB work. Both predicates consume the same ``ttl`` value, so the skipped
    sets agree exactly.
    """
    if block_height is None or block_time is None or base is None:
        return None
    if not _uc_evidence_time_enabled(session, chain_id, block_height):
        return None
    contexts: dict[int, UcApplyContext | None] = {}
    for event in events:
        if event.condition is not SlashingCondition.DOUBLE_SIGN or event.block_height in contexts:
            continue
        if ttl_blocks is not None and block_height - event.block_height > ttl_blocks:
            continue
        ep = _evidence_json(event)
        if ep is None or ep.get("kind") != "attestation_equivocation":
            continue
        contexts[event.block_height] = _uc_event_context(session, chain_id, block_height, block_time, base, event.block_height)
    return contexts


def _evidence_ttl(session: Session, chain_id: str, block_height: int | None) -> int | None:
    """Evidence TTL in blocks (chain parameter), or None = no expiry (#1959).

    ``validator_deactivation_evidence_ttl_blocks`` bounds how old an
    equivocation event may be and still count toward deactivation. Unset or
    malformed resolves to None — the pre-#1959 behavior exactly. Like the UC
    context, the parameter is read at the apply height so replay and reorg
    agree; a value armed later in the chain never retroactively expires
    evidence for earlier blocks.
    """
    from .state_transition import _chain_parameter_value

    value = _chain_parameter_value(session, chain_id, "validator_deactivation_evidence_ttl_blocks", block_height)
    try:
        ttl = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return ttl if ttl > 0 else None


def _record_to_event(record: dict[str, Any]) -> SlashingEvent | None:
    """Rebuild a SlashingEvent from a payload evidence record."""
    try:
        stake_before = record.get("stake_before")
        slashed_amount = record.get("slashed_amount")
        return SlashingEvent(
            validator_address=str(record["validator_address"]),
            condition=SlashingCondition(str(record["condition"])),
            evidence=str(record.get("evidence", "")),
            block_height=int(record.get("block_height", 0)),
            timestamp=float(record.get("timestamp", 0.0)),
            slash_rate=float(record.get("slash_rate", record.get("slash_amount", 0.0))),
            stake_before=Decimal(str(stake_before)) if stake_before is not None else None,
            slashed_amount=Decimal(str(slashed_amount)) if slashed_amount is not None else None,
            round_number=record.get("round_number"),
            hash_a=str(record.get("hash_a") or ""),
            hash_b=str(record.get("hash_b") or ""),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _evidence_json(event: SlashingEvent) -> dict[str, Any] | None:
    try:
        payload = json.loads(event.evidence)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _verify_stored_signature(att: dict[str, Any], message: dict[str, Any], validator: str, event_height: int) -> bool:
    """Verify one stored consensus signature under its recorded domain (#1298).

    ``signature_domain`` names the preimage the signer actually used; the
    label is self-authenticating — the signature either verifies under it or
    not — so labeled records need no height gate. Unlabeled records are
    legacy (pre-activation) signatures: they verify only for heights below
    ``consensus_domain_separation_height`` — hard cutover, no legacy fallback
    at/above the armed height — EXCEPT inside the bounded dual-accept
    window ``[H, S)`` opened by
    ``consensus_legacy_attestation_until_height`` (design v2.2 CARD5), where
    a legacy attestation signature still verifies while the fleet
    converges. This function only serves attestation-channel evidence, so
    the attestation-only scope of the window applies unchanged; proposal
    signatures never gain a window anywhere.
    """
    signature = str(att.get("signature", ""))
    domain = att.get("signature_domain")
    if domain is not None:
        if not isinstance(domain, str) or not domain:
            return False
        return verify_consensus_message_domain(message, signature, validator, domain)
    activation = getattr(settings, "consensus_domain_separation_height", None)
    height: int | None = None
    if activation is not None:
        try:
            height = int(att.get("height", event_height))
        except (TypeError, ValueError):
            height = None
        if height is None or height >= activation:
            # Dual-accept window: an unlabeled legacy signature whose height
            # sits in [H, S) still verifies under the shared preimage.
            if height is not None and legacy_attestation_dual_accept_open(height):
                try:
                    if verify_consensus_message(message, signature, validator):
                        from ..metrics import metrics_registry

                        metrics_registry.increment("consensus_legacy_attestation_accepted_total")
                        return True
                except SignatureMalformed:
                    pass
            return False
    try:
        return verify_consensus_message(message, signature, validator)
    except SignatureMalformed:
        return False


def _verify_attestation_equivocation(payload: dict[str, Any], event: SlashingEvent, validator: str) -> bool:
    """Verify an ``attestation_equivocation`` event's two signed attestations."""
    attestations = payload.get("attestations")
    if not isinstance(attestations, list) or len(attestations) < 2:
        return False
    expected = {str(payload.get("block_hash_a", "")).lower(), str(payload.get("block_hash_b", "")).lower()}
    seen: set[str] = set()
    for att in attestations[:2]:
        if not isinstance(att, dict):
            return False
        block_hash = str(att.get("hash", ""))
        if block_hash.lower() not in expected:
            return False
        message = {
            "chain_id": att.get("chain_id", ""),
            "height": att.get("height", event.block_height),
            "hash": block_hash,
            "parent_hash": att.get("parent_hash", ""),
            "proposer": att.get("proposer", ""),
            "state_root": att.get("state_root", ""),
            "bridge_state_root": att.get("bridge_state_root", ""),
        }
        # round_in_payload mirrors the capture-side flag exactly: the round
        # was inside the signed message under the round lock at any height,
        # and unconditionally at/above the domain-separation height (#1298
        # T7a — the flag now describes the signed message, not the flag state).
        if att.get("round_in_payload"):
            message["round"] = att.get("request_round")
        if not _verify_stored_signature(att, message, validator, event.block_height):
            return False
        seen.add(block_hash.lower())
    return seen == expected


def _verify_vote_equivocation(payload: dict[str, Any], validator: str, chain_id: str | None = None) -> bool:
    """Verify a ``vote_equivocation`` event's two signed PBFT messages.

    #2102: signatures verify under the apply chain's chain-bound preimage
    first, legacy preimage second — a pair signed on another chain sharing
    the validator key no longer verifies here.
    """
    messages = payload.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return False
    pair = messages[:2]
    views = set()
    sequences = set()
    phases = set()
    hashes: set[str] = set()
    for msg in pair:
        if not isinstance(msg, dict):
            return False
        block_hash = str(msg.get("block_hash", ""))
        sequence = msg.get("sequence_number")
        view = msg.get("view_number")
        message_type = msg.get("message_type")
        digest = str(msg.get("digest", ""))
        if sequence is None or view is None or not block_hash or not digest or not message_type:
            return False
        # The digest commits to block_hash:sequence:view — recompute it.
        expected_digest = hashlib.sha256(f"{block_hash}:{sequence}:{view}".encode()).hexdigest()
        if digest != expected_digest:
            return False
        if canonical_address(str(msg.get("sender", ""))) != canonical_address(validator):
            return False
        from ..consensus.pbft_vote_signature import verify_pbft_vote_signature

        try:
            if not verify_pbft_vote_signature(msg, str(msg.get("signature", "")), validator, chain_id):
                return False
        except SignatureMalformed:
            return False
        views.add(view)
        sequences.add(sequence)
        phases.add(message_type)
        hashes.add(block_hash.lower())
    # Same phase/view/sequence, two different digests — the slashable offense.
    return len(hashes) == 2 and len(views) == 1 and len(sequences) == 1 and len(phases) == 1


def _cross_view_header(
    payload: dict[str, Any],
    event: SlashingEvent,
    activation_height: int | None,
    apply_height: int | None,
) -> tuple[int | None, str | None]:
    """Phase/sequence/window header checks for cross-view evidence (#1940 F3-A).

    Returns ``(sequence, None)`` when the header is well-formed and the
    evidenced sequence sits inside the armed window, else ``(None, reason)``.
    """
    if payload.get("phase") != "commit":
        return None, "cross-view equivocation evidence is not commit-phase"
    sequence = payload.get("sequence")
    if not _strict_int(sequence):
        return None, "cross-view equivocation evidence has no strict-int sequence"
    if sequence != event.block_height:
        return None, "cross-view equivocation sequence does not match event block_height"
    if activation_height is None:
        return None, "cross-view equivocation evidence is not armed on-chain"
    if apply_height is None or sequence < activation_height or sequence > apply_height:
        return None, "cross-view equivocation sequence is outside the armed evidence window"
    return sequence, None


def _cross_view_message_fields(msg: Any, sequence: int | None) -> dict[str, Any] | str:
    """Validated counted fields of one cross-view commit record, or a reason.

    Single return keeps the caller branch-free: a ``str`` result IS the
    reject reason; a ``dict`` is the verified field carrier (the signed
    subset plus ``block_hash``/``signature`` for the crypto step).
    """
    if not isinstance(msg, dict):
        return "cross-view equivocation message record is not an object"
    block_hash = str(msg.get("block_hash", ""))
    msg_sequence = msg.get("sequence_number")
    view = msg.get("view_number")
    message_type = msg.get("message_type")
    digest = str(msg.get("digest", ""))
    if message_type != "commit":
        return "cross-view equivocation message is not a commit"
    if not _strict_int(msg_sequence) or not _strict_int(view):
        return "cross-view equivocation message has non-strict-int sequence or view"
    if msg_sequence != sequence or not block_hash or not digest:
        return "cross-view equivocation message fields do not match the evidence sequence"
    return {
        "message_type": message_type,
        "sender": msg.get("sender", ""),
        "view_number": view,
        "sequence_number": msg_sequence,
        "digest": digest,
        "block_hash": block_hash,
        "signature": msg.get("signature", ""),
    }


def _cross_view_message_crypto_ok(fields: dict[str, Any], validator_addr: str, chain_id: str | None = None) -> str | None:
    """Digest recompute + sender + signature check for one validated record.

    #2102: the signature verifies under the apply chain's chain-bound
    preimage first, legacy preimage second.
    """
    # The digest commits to block_hash:sequence:view — recompute it.
    expected_digest = hashlib.sha256(
        f"{fields['block_hash']}:{fields['sequence_number']}:{fields['view_number']}".encode()
    ).hexdigest()
    if fields["digest"] != expected_digest:
        return "cross-view equivocation digest does not match block_hash:sequence:view"
    if canonical_address(str(fields["sender"])) != validator_addr:
        return "cross-view equivocation sender does not match the deactivated validator"
    from ..consensus.pbft_vote_signature import verify_pbft_vote_signature

    try:
        if not verify_pbft_vote_signature(fields, str(fields["signature"]), validator_addr, chain_id):
            return "cross-view equivocation signature verification failed"
    except SignatureMalformed:
        return "cross-view equivocation signature is malformed"
    return None


def _verify_pbft_cross_view_vote_equivocation(
    payload: dict[str, Any],
    event: SlashingEvent,
    validator_addr: str,
    activation_height: int | None,
    apply_height: int | None,
    chain_id: str | None = None,
) -> str | None:
    """Verify a ``pbft_cross_view_vote_equivocation`` event (#1940 F3-A).

    Returns None when the evidence verifies, else a skip reason. Fail-closed
    throughout: the claim only counts when the on-chain
    ``validator_deactivation_pbft_cross_view_evidence_height`` parameter is
    armed (``activation_height`` not None) and the evidenced ``sequence`` —
    which must equal ``event.block_height`` — sits inside
    ``[activation_height, apply_height]``. Both message records must be
    COMMITs from the same canonical sender at the same sequence but
    different strict-int views signing different block hashes, each digest
    recomputed as ``sha256(block_hash:sequence:view)`` and each signature
    verified with ``verify_consensus_message`` over the signed subset.
    Prepare-phase, same-view and same-hash pairs are NOT this kind — they
    remain ``vote_equivocation`` territory or stay legal.
    """
    sequence, reason = _cross_view_header(payload, event, activation_height, apply_height)
    if reason is not None:
        return reason
    messages = payload.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return "cross-view equivocation evidence lacks two signed commit messages"
    views: set[int] = set()
    sequences: set[int] = set()
    hashes: set[str] = set()
    for msg in messages[:2]:
        fields = _cross_view_message_fields(msg, sequence)
        if isinstance(fields, str):
            return fields
        reason = _cross_view_message_crypto_ok(fields, validator_addr, chain_id)
        if reason is not None:
            return reason
        views.add(fields["view_number"])
        sequences.add(fields["sequence_number"])
        hashes.add(str(fields["block_hash"]).lower())
    # Two hashes, two views, one sequence — anything else is not the offense.
    if sorted((len(hashes), len(views), len(sequences))) != [1, 2, 2]:
        return "cross-view equivocation evidence is not a cross-view commit pair"
    if payload.get("views") != sorted(views):
        return "cross-view equivocation views do not match the message records"
    return None


def _records_to_events(records: list[Any], validator_addr: str) -> tuple[list[SlashingEvent], str | None]:
    """Parse payload evidence records into events, or return a skip reason."""
    events: list[SlashingEvent] = []
    for record in records:
        if not isinstance(record, dict):
            return [], "evidence record is not an object"
        if canonical_address(str(record.get("validator_address", ""))) != validator_addr:
            return [], "evidence record validator_address does not match payload"
        event = _record_to_event(record)
        if event is None:
            return [], "unreadable evidence record"
        events.append(event)
    return events, None


def _evidence_expired(event: SlashingEvent, ttl_blocks: int | None, apply_height: int | None) -> bool:
    """#1959 TTL predicate — the same expiry rule the loop applied inline."""
    return (
        ttl_blocks is not None
        and apply_height is not None
        and event.condition is SlashingCondition.DOUBLE_SIGN
        and apply_height - event.block_height > ttl_blocks
    )


def _verify_equivocation_claim(
    ep: dict[str, Any],
    event: SlashingEvent,
    validator_addr: str,
    uc_ctx: UcApplyContext | None,
    uc_contexts: dict[int, UcApplyContext | None] | None,
    cross_view_height: int | None,
    apply_height: int | None,
    chain_id: str | None = None,
) -> tuple[bool, str | None]:
    """Verify one equivocation claim; ``(counts_as_verified, fail_reason)``.

    A verified claim is ``(True, None)``; an unlock-excused attestation pair
    is ``(False, None)`` — signatures verified but the cross-round unlock
    carries an independently verifiable protocol proof (#1274): excused,
    not counted, bundle not failed. Any failure is ``(False, reason)``.
    ``ep["kind"]`` is one of the three equivocation kinds — the caller
    dispatches only those.
    """
    kind = ep.get("kind")
    if kind == "attestation_equivocation":
        if not _verify_attestation_equivocation(ep, event, validator_addr):
            return False, "attestation equivocation evidence failed signature verification"
        event_uc_ctx = uc_contexts.get(event.block_height) if uc_contexts is not None else uc_ctx
        if not pair_stands_as_evidence(ep, event_uc_ctx):
            return False, None
        return True, None
    if kind == "vote_equivocation":
        if not _verify_vote_equivocation(ep, validator_addr, chain_id):
            return False, "vote equivocation evidence failed signature verification"
        return True, None
    # PBFT_CROSS_VIEW_VOTE_EQUIVOCATION — fail closed unless the on-chain
    # cross-view evidence height is armed and the sequence sits in-window.
    reason = _verify_pbft_cross_view_vote_equivocation(ep, event, validator_addr, cross_view_height, apply_height, chain_id)
    if reason is not None:
        return False, reason
    return True, None


def _verify_equivocations(
    events: list[SlashingEvent],
    validator_addr: str,
    uc_ctx: UcApplyContext | None = None,
    *,
    ttl_blocks: int | None = None,
    apply_height: int | None = None,
    uc_contexts: dict[int, UcApplyContext | None] | None = None,
    cross_view_height: int | None = None,
    chain_id: str | None = None,
) -> str | None:
    """Verify every equivocation claim; ≥1 verified equivocation required.

    #1959: when ``validator_deactivation_evidence_ttl_blocks`` is armed and
    the apply height is known, DOUBLE_SIGN events older than the TTL are
    expired — skipped entirely: they neither count toward ``verified`` nor
    fail the bundle. Expiry is checked before signature verification so a
    stale claim can never wedge a marker that also cites fresh evidence;
    a bundle whose every equivocation is expired still fails closed via
    ``verified == 0``. Non-equivocation records are informational and are
    never expired.

    #1940 ruling A: ``uc_contexts`` (when not None) replaces ``uc_ctx`` per
    event — ``map.get(event.block_height)`` — so each DOUBLE_SIGN
    attestation event is judged against its own evidence block's time.
    ``None`` keeps the single shared apply-time context.
    """
    verified = 0
    for event in events:
        if _evidence_expired(event, ttl_blocks, apply_height):
            continue
        ep = _evidence_json(event)
        kind = ep.get("kind") if ep is not None else None
        if ep is not None and kind in (
            "attestation_equivocation",
            "vote_equivocation",
            PBFT_CROSS_VIEW_VOTE_EQUIVOCATION,
        ):
            counts, reason = _verify_equivocation_claim(
                ep, event, validator_addr, uc_ctx, uc_contexts, cross_view_height, apply_height, chain_id
            )
            if reason is not None:
                return reason
            if counts:
                verified += 1
        elif kind is None and event.evidence.startswith("Double sign detected"):
            # Legacy free-text double-sign: an equivocation claim with no
            # signature material — unverifiable, so it fails the gate.
            return "equivocation evidence lacks signatures (pre-#1263 capture)"
        # Non-equivocation conditions (unavailable, invalid_block,
        # slow_response) and JSON evidence of any other kind are
        # hash-bound informational records.
    if verified == 0:
        return "no verifiable equivocation evidence"
    return None


def verify_deactivation_evidence(
    payload: dict[str, Any],
    *,
    chain_id: str,
    validator_addr: str,
    evidence_hash: str,
    session: Session | None = None,
    block_height: int | None = None,
    block_time: datetime | None = None,
) -> str | None:
    """Verify ``payload``'s evidence bundle and equivocation proofs.

    Returns None when the evidence verifies, or a skip reason. ``chain_id``
    is accepted for symmetry with the capture preimage but the attestation
    records carry their own ``chain_id`` field — verification trusts the
    signed bytes, not the caller's claim.
    """
    # signed preimages carry chain_id per attestation record; it is used only for the #1281 uc context
    if payload.get("evidence_version") != EVIDENCE_VERSION:
        return f"evidence_version must be {EVIDENCE_VERSION} when verification is armed"
    records = payload.get("evidence")
    if not isinstance(records, list) or not records:
        return "evidence must be a non-empty list of canonical event records"
    if len(records) > MAX_EVIDENCE_EVENTS:
        return f"evidence exceeds {MAX_EVIDENCE_EVENTS} events"

    events, reason = _records_to_events(records, validator_addr)
    if reason is not None:
        return reason

    # Bundle binding: the recomputed canonical hash must equal the committed
    # evidence_hash — this is what stops a marker citing fabricated evidence.
    manager = SlashingManager()
    manager.slashing_events = events
    if manager.evidence_hash(validator_addr) != evidence_hash:
        return "evidence_hash does not match the submitted evidence bundle"

    ttl = _evidence_ttl(session, chain_id, block_height) if session is not None else None
    uc_ctx = _uc_context(session, chain_id, block_height, block_time) if session is not None else None
    uc_contexts = (
        _uc_event_contexts(session, chain_id, block_height, block_time, events, uc_ctx, ttl_blocks=ttl)
        if session is not None
        else None
    )
    cross_view_height = _cross_view_evidence_height(session, chain_id, block_height) if session is not None else None
    return _verify_equivocations(
        events,
        validator_addr,
        uc_ctx,
        uc_contexts=uc_contexts,
        ttl_blocks=ttl,
        apply_height=block_height,
        cross_view_height=cross_view_height,
        chain_id=chain_id,
    )
