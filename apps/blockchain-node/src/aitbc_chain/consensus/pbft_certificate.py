"""Strict PBFT commit-certificate contract (#1940 F3 certificate subtranche).

A PBFT commit certificate is the quorum proof a proposer attaches to
``block_metadata.pbft_certificate`` and every importer re-verifies. The
legacy verifier counted distinct senders across *all* stored commit
messages — unioning different ``(sequence_number, view_number)`` buckets —
and sized the quorum by the attestation minimum, so commits for different
heights/views could be combined into an apparent quorum.

This module is the shared strict contract used by BOTH sides once the
configured ``pbft_certificate_strict_height`` activation height is reached:

- producer: ``PBFTConsensus.get_certificate`` returns exactly one complete
  coherent ``(sequence, view)`` group — never a union across buckets;
- consumer: ``ProposerSignatureValidator._validate_pbft_certificate``
  delegates here instead of the legacy counter;
- proposer gate: ``PoAProposer._collect_and_gate_attestations`` refuses to
  seal a block whose certificate does not validate, before gossip
  attestations are even collected.

``validate_commit_certificate`` is pure: no DB reads, no wall clock — replay
and reorg agree on every node. ``strict_certificate_active`` resolves the
activation threshold from ``ChainSettings`` only; nothing here reads the
environment per call beyond that settings object.

This tranche pins the certificate *contract* only. Cross-view safety (a
safe view-change protocol) remains separate active design work — fleet PBFT
must stay OFF until that lands.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any, TypeGuard

from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from .pbft_quorum import pbft_required_messages


def _strict_int(value: Any) -> TypeGuard[int]:
    """Strictly ``int`` and not ``bool`` — JSON ``true`` must never pass as 1."""
    return isinstance(value, int) and not isinstance(value, bool)


def strict_certificate_active(height: int | None) -> bool:
    """Whether the strict certificate contract applies at ``height`` (#1940 F3).

    Armed by the configured activation height ``pbft_certificate_strict_height``:
    active iff a valid non-negative int threshold is configured AND ``height``
    is a valid non-negative int at or above it. ``None``, bools, malformed
    values and pre-threshold heights all resolve False — the legacy verifier
    then runs byte-for-byte as before.
    """
    threshold = getattr(settings, "pbft_certificate_strict_height", None)
    if not _strict_int(threshold):
        return False
    if threshold < 0:
        return False
    return _strict_int(height) and height >= threshold


def certificate_view_binding_active(height: int | None) -> bool:
    """Whether the certificate view-binding gate applies at ``height`` (#1940 F3-B).

    Armed by ``pbft_certificate_view_binding_height``: active iff a valid
    non-negative int threshold is configured AND ``height`` is a valid
    non-negative int at or above it — the same dormant shape as
    ``strict_certificate_active``. Consumers additionally require the strict
    contract AND ``pbft_consensus_enabled`` before pinning the view, so an
    armed-but-PBFT-off deployment keeps the unpinned check byte-for-byte.
    """
    threshold = getattr(settings, "pbft_certificate_view_binding_height", None)
    if not _strict_int(threshold):
        return False
    if threshold < 0:
        return False
    return _strict_int(height) and height >= threshold


def _commit_digest(block_hash: str, sequence_number: int, view_number: int) -> str:
    """The digest every commit signs: ``sha256(block_hash:seq:view)`` — the
    same preimage ``PBFTConsensus.get_message_digest`` and the legacy
    importer verifier use."""
    return hashlib.sha256(f"{block_hash}:{sequence_number}:{view_number}".encode()).hexdigest()


def _canonical_members(validators: Iterable[str]) -> set[str]:
    """Canonical, non-empty member addresses of the validator set."""
    members: set[str] = set()
    for member in validators:
        if isinstance(member, str) and member:
            members.add(canonical_address(member))
    members.discard("")
    return members


def _commit_fields(record: Any, block_hash: str) -> tuple[str, str, int, int, str] | None:
    """Structural gate for one certificate record (#1940 F3).

    Returns ``(sender, signature, sequence_number, view_number, digest)``
    when the record is a ``commit`` message carrying an explicit
    ``block_hash`` equal to the block's, strictly-int non-negative
    ``view_number`` / ``sequence_number``, and the matching
    ``sha256(block_hash:seq:view)`` digest; ``None`` otherwise. Malformed
    records never raise — they simply do not count.
    """
    if not isinstance(record, dict) or record.get("message_type") != "commit":
        return None
    sender = record.get("sender")
    signature = record.get("signature")
    seq = record.get("sequence_number")
    view_number = record.get("view_number")
    digest = record.get("digest")
    if (
        not isinstance(sender, str)
        or not sender
        or not isinstance(signature, str)
        or not signature
        or not isinstance(digest, str)
        or record.get("block_hash") != block_hash
        or not (_strict_int(seq) and seq >= 0)
        or not (_strict_int(view_number) and view_number >= 0)
    ):
        return None
    if digest.lower() != _commit_digest(block_hash, seq, view_number):
        return None
    return sender, signature, seq, view_number, digest


def _signature_valid(sender: str, signature: str, seq: int, view_number: int, digest: str, chain_id: str | None) -> bool:
    """``verify_pbft_vote_signature`` over the PBFT preimage — never raises.

    #2102: chain-bound preimage first, legacy fallback — a commit signed on
    another chain sharing the validator key no longer counts here.
    """
    from .pbft_vote_signature import verify_pbft_vote_signature

    try:
        return verify_pbft_vote_signature(
            {
                "message_type": "commit",
                "sender": sender,
                "view_number": view_number,
                "sequence_number": seq,
                "digest": digest,
            },
            signature,
            sender,
            chain_id,
        )
    except Exception:  # noqa: BLE001 - a malformed signature must never raise here
        return False


def _counted_commits(
    certificate: list[dict[str, Any]],
    block_hash: str,
    canonical: set[str],
    chain_id: str | None,
) -> tuple[set[tuple[int, int]], set[str]]:
    """Signature-valid counted records → (signed ``(seq, view)`` tuples, senders).

    Only records passing every ``_commit_fields`` gate, membership in the
    canonical validator set and ``_signature_valid`` count. Each counted
    record joins the coherence tuple set and — once per distinct canonical
    sender — the quorum set, so a duplicated sender cannot inflate it.
    """
    tuples: set[tuple[int, int]] = set()
    senders: set[str] = set()
    for record in certificate:
        fields = _commit_fields(record, block_hash)
        if fields is None:
            continue
        sender, signature, seq, view_number, digest = fields
        sender_canonical = canonical_address(sender)
        if sender_canonical not in canonical:
            continue
        if not _signature_valid(sender, signature, seq, view_number, digest, chain_id):
            continue
        tuples.add((seq, view_number))
        senders.add(sender_canonical)
    return tuples, senders


def _certificate_verdict(
    tuples: set[tuple[int, int]],
    senders: set[str],
    *,
    height: int,
    view: int | None,
    required: int,
) -> tuple[bool, str]:
    """Coherence + quorum verdict over the counted commits (#1940 F3)."""
    if not tuples:
        return False, "no valid commit signatures"
    if len(tuples) > 1:
        return False, "mixed sequence/view commits in certificate"
    seq, view_number = next(iter(tuples))
    if seq != height:
        return False, f"certificate sequence {seq} != block height {height}"
    if view is not None and view_number != view:
        return False, f"certificate view {view_number} != expected view {view}"
    if len(senders) < required:
        return False, f"only {len(senders)} distinct commits, need {required}"
    return True, f"{len(senders)} valid commits at sequence {seq} view {view_number}"


def validate_commit_certificate(
    certificate: list[dict[str, Any]],
    block_hash: str,
    validators: Iterable[str],
    *,
    height: int,
    view: int | None = None,
    chain_id: str,
) -> tuple[bool, str]:
    """Verify a PBFT commit certificate under the strict contract (#1940 F3).

    ``certificate`` is the ``block_metadata.pbft_certificate`` list (or the
    producer's candidate group); ``validators`` is the active consensus
    participant set; ``height`` is the block height the certificate must
    commit to; ``view`` optionally pins the expected PBFT view; ``chain_id``
    (#2102) is the chain the certificate must belong to — commit signatures
    verify under the chain-bound preimage first, legacy preimage second.

    Rules, all deterministic:

    - every counted record must be a ``commit`` message from a canonical
      member of ``validators`` carrying an explicit ``block_hash`` equal to
      the block's, strictly-int non-negative ``view_number`` /
      ``sequence_number``, the matching ``sha256(block_hash:seq:view)``
      digest, and a ``verify_pbft_vote_signature``-valid signature over the
      PBFT preimage (chain-bound first, legacy fallback) — malformed records
      and bad signatures never raise and simply do not count;
    - ALL signature-valid counted records must share ONE ``(seq, view)`` —
      mixed views (or sequences) are rejected rather than combined, so votes
      for different rounds can never be unioned into a quorum;
    - the shared ``sequence_number`` must equal ``height`` and, when ``view``
      is given, the shared ``view_number`` must equal it;
    - distinct canonical senders must reach ``pbft_required_messages(n)``
      for ``n = len(canonical validator set)`` — the real BFT quorum,
      independent of any attestation minimum; a duplicated sender cannot
      inflate the count;
    - an empty validator set is rejected outright.

    Returns ``(True, reason)`` or ``(False, reason)``.
    """
    if not isinstance(block_hash, str) or not block_hash:
        return False, "missing block hash"
    if not _strict_int(height) or height < 0:
        return False, "invalid certificate height"
    if view is not None and (not _strict_int(view) or view < 0):
        return False, "invalid expected view"

    canonical = _canonical_members(validators)
    if not canonical:
        return False, "empty validator set"

    required = pbft_required_messages(len(canonical))
    tuples, senders = _counted_commits(certificate, block_hash, canonical, chain_id)
    return _certificate_verdict(tuples, senders, height=height, view=view, required=required)
