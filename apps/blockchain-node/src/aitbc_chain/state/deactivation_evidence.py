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
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from sqlmodel import Session

from aitbc.crypto.consensus_signing import verify_consensus_message, verify_consensus_message_domain
from aitbc.crypto.signature_recovery import SignatureMalformed, canonical_address

from ..config import legacy_attestation_dual_accept_open, settings
from ..consensus.equivocation_policy import pair_stands_as_evidence
from ..consensus.slashing import SlashingCondition, SlashingEvent, SlashingManager

EVIDENCE_VERSION = 2
MAX_EVIDENCE_EVENTS = 32


def _evidence_required(session: Session, chain_id: str, block_height: int | None) -> bool:
    """Whether the armed gate applies at ``block_height`` (chain parameter)."""
    from .state_transition import _chain_parameter_value

    value = _chain_parameter_value(session, chain_id, "validator_deactivation_evidence_required", block_height)
    return bool(value and value.strip().lower() in ("true", "1", "yes"))


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
        # was inside the signed message only under the round lock.
        if att.get("round_in_payload"):
            message["round"] = att.get("request_round")
        if not _verify_stored_signature(att, message, validator, event.block_height):
            return False
        seen.add(block_hash.lower())
    return seen == expected


def _verify_vote_equivocation(payload: dict[str, Any], validator: str) -> bool:
    """Verify a ``vote_equivocation`` event's two signed PBFT messages."""
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
        signed = {
            "message_type": message_type,
            "sender": msg.get("sender", ""),
            "view_number": view,
            "sequence_number": sequence,
            "digest": digest,
        }
        try:
            if not verify_consensus_message(signed, str(msg.get("signature", "")), validator):
                return False
        except SignatureMalformed:
            return False
        views.add(view)
        sequences.add(sequence)
        phases.add(message_type)
        hashes.add(block_hash.lower())
    # Same phase/view/sequence, two different digests — the slashable offense.
    return len(hashes) == 2 and len(views) == 1 and len(sequences) == 1 and len(phases) == 1


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


def _verify_equivocations(events: list[SlashingEvent], validator_addr: str) -> str | None:
    """Verify every equivocation claim; ≥1 verified equivocation required."""
    verified = 0
    for event in events:
        ep = _evidence_json(event)
        kind = ep.get("kind") if ep is not None else None
        if ep is not None and kind == "attestation_equivocation":
            if not _verify_attestation_equivocation(ep, event, validator_addr):
                return "attestation equivocation evidence failed signature verification"
            if not pair_stands_as_evidence(ep):
                # signatures verified, but the cross-round unlock carries an independently
                # verifiable protocol proof (#1274): excused, not counted, bundle not failed
                continue
            verified += 1
        elif ep is not None and kind == "vote_equivocation":
            if not _verify_vote_equivocation(ep, validator_addr):
                return "vote equivocation evidence failed signature verification"
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
) -> str | None:
    """Verify ``payload``'s evidence bundle and equivocation proofs.

    Returns None when the evidence verifies, or a skip reason. ``chain_id``
    is accepted for symmetry with the capture preimage but the attestation
    records carry their own ``chain_id`` field — verification trusts the
    signed bytes, not the caller's claim.
    """
    del chain_id  # signed preimages carry chain_id per attestation record
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

    return _verify_equivocations(events, validator_addr)
