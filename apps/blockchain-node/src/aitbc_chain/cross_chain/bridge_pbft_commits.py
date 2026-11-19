"""PBFT commit certificate as bridge-proof signer evidence (#2249).

Blocks sealed from the PBFT commit certificate (VIEW_CHANGE gate) carry no
attestations, so a proof built from header signatures alone cannot reach
``bridge_multisig_threshold``. The certificate's commit votes are validator
signatures over a PBFT vote preimage (not the header message), so they ride in
the proof as their own channel (``pbft_commits``) and are verified here under
the same rules the importing node applies to a stored certificate:
``digest == sha256(block_hash:seq:view)``, sender in the validator set, valid
vote signature (chain-bound preimage first, legacy second).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings

_COMMIT_FIELDS = ("message_type", "sender", "signature", "view_number", "sequence_number", "digest", "block_hash")
# Upper bound on commits a proof may carry/we will verify (n validators, one commit each).
_MAX_COMMITS = 64


def commit_proof_active(height: int | None) -> bool:
    """True when ``height`` is at/above the armed #2249 activation height."""
    activation = getattr(settings, "bridge_pbft_commit_proof_height", None)
    return activation is not None and height is not None and int(height) >= int(activation)


def commits_from_metadata(block_metadata: Any) -> list[dict[str, Any]]:
    """Commit votes out of a block's ``pbft_certificate``; malformed -> empty."""
    if not block_metadata:
        return []
    try:
        meta = json.loads(block_metadata) if isinstance(block_metadata, str) else block_metadata
    except (RecursionError, TypeError, ValueError):
        return []
    certificate = meta.get("pbft_certificate") if isinstance(meta, dict) else None
    if not isinstance(certificate, list):
        return []
    commits = [
        {k: c[k] for k in _COMMIT_FIELDS if k in c}
        for c in certificate
        if isinstance(c, dict) and c.get("message_type") == "commit" and c.get("sender") and c.get("signature")
    ]
    return commits[:_MAX_COMMITS]


def _commit_fields(commit: Any) -> tuple[Any, Any, Any, Any, Any] | None:
    """``(sender, signature, seq, view, digest)`` for a structurally complete commit."""
    if not isinstance(commit, dict) or commit.get("message_type") != "commit":
        return None
    sender, signature = commit.get("sender"), commit.get("signature")
    seq, view, digest = commit.get("sequence_number"), commit.get("view_number"), commit.get("digest")
    if not sender or not signature or seq is None or view is None or not digest:
        return None
    return sender, signature, seq, view, digest


def _commit_binding_ok(commit: dict[str, Any], block_hash: str, seq: Any, view: Any, digest: Any) -> bool:
    """The vote must bind to this block: optional ``block_hash`` match plus the
    ``sha256(block_hash:seq:view)`` digest — the same rule the importer applies."""
    if commit.get("block_hash") and commit["block_hash"] != block_hash:
        return False
    expected = hashlib.sha256(f"{block_hash}:{seq}:{view}".encode()).hexdigest()
    return str(digest).lower() == expected


def _commit_signer(
    commit: Any,
    block_hash: str,
    members: set[str],
    chain_id: str | None,
) -> tuple[tuple[Any, Any], str] | None:
    """``((seq, view), canonical_sender)`` for a fully valid commit, else None."""
    from ..consensus.pbft_vote_signature import verify_pbft_vote_signature

    fields = _commit_fields(commit)
    if fields is None:
        return None
    sender, signature, seq, view, digest = fields
    if not _commit_binding_ok(commit, block_hash, seq, view, digest):
        return None
    try:
        sender_c = canonical_address(str(sender))
    except (TypeError, ValueError):
        return None
    if sender_c.lower() not in members:
        return None
    if not verify_pbft_vote_signature(commit, str(signature), str(sender), chain_id):
        return None
    return (seq, view), sender_c


def verified_commit_signers(
    commits: Iterable[Any],
    block_hash: str,
    chain_id: str | None,
    member_addrs: Iterable[str],
) -> list[str]:
    """Distinct validator-set addresses with a valid commit for ``block_hash``.

    Only the (sequence, view) group with the most valid distinct committers
    counts, so mixed rounds or an equivocating committer cannot be unioned
    into a quorum.
    """
    members = {canonical_address(a).lower() for a in member_addrs}
    groups: dict[tuple[Any, Any], dict[str, str]] = {}
    for i, commit in enumerate(commits):
        if i >= _MAX_COMMITS:
            break
        signer = _commit_signer(commit, block_hash, members, chain_id)
        if signer is None:
            continue
        (seq, view), sender_c = signer
        groups.setdefault((seq, view), {})[sender_c.lower()] = sender_c
    if not groups:
        return []
    best = max(groups.values(), key=len)
    return sorted(best.values())
