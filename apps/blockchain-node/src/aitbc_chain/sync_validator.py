"""Block import result type and proposer signature validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import metrics_registry

from .config import settings


@dataclass
class ImportResult:
    accepted: bool
    height: int
    block_hash: str
    reason: str
    reorged: bool = False
    reorg_depth: int = 0
    # Set when the block was refused because we hold a *different* block at its height, as
    # opposed to a transient gap or a stale duplicate. Callers need the distinction: divergence
    # is permanent without operator action, while a gap heals on the next block (V23-90).
    diverged: bool = False


class ProposerSignatureValidator:
    """Validates proposer signatures on imported blocks."""

    def __init__(self, trusted_proposers: list[str] | None = None) -> None:
        self._trusted = set(trusted_proposers or [])

    @property
    def trusted_proposers(self) -> set[str]:
        return self._trusted

    def add_trusted(self, proposer_id: str) -> None:
        self._trusted.add(proposer_id)

    def remove_trusted(self, proposer_id: str) -> None:
        self._trusted.discard(proposer_id)

    def validate_block_signature(self, block_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate that a block was produced by an authorized proposer.

        Verifies the proposer's secp256k1 signature over the block hash
        when the block carries one. Fails closed when the block is
        unsigned and no trusted proposer set is configured — without
        either, there is no way to authenticate the proposer. Unsigned
        legacy blocks are only accepted from configured trusted proposers.

        Returns (is_valid, reason).
        """
        if not getattr(settings, "bridge_block_signature_required", True):
            return (True, "Block signature verification disabled")

        proposer = block_data.get("proposer", "")
        block_hash = block_data.get("hash", "")
        if not proposer:
            return (False, "Missing proposer field")
        if not block_hash:
            return (False, f"Invalid block hash format: {block_hash}")
        if not block_hash.startswith("0x"):
            block_hash = f"0x{block_hash}"
        expected_fields = ["height", "parent_hash", "timestamp"]
        for field in expected_fields:
            if field not in block_data:
                return (False, f"Missing required field: {field}")
        hash_hex = block_hash[2:]
        if len(hash_hex) != 64:
            return (False, f"Invalid hash length: {len(hash_hex)}")
        try:
            int(hash_hex, 16)
        except ValueError:
            return (False, f"Invalid hex in hash: {hash_hex}")

        if self._trusted and proposer not in self._trusted:
            metrics_registry.increment("sync_signature_rejected_total")
            return (False, f"Proposer '{proposer}' not in trusted set")
        signature = block_data.get("signature", "")
        if signature:
            from aitbc.crypto.consensus_signing import verify_block_signature

            if not verify_block_signature(block_data, signature, proposer):
                metrics_registry.increment("sync_signature_rejected_total")
                return (False, "Invalid proposer signature")
        elif not self._trusted:
            metrics_registry.increment("sync_signature_rejected_total")
            return (False, "Unsigned block and no trusted proposer set configured")

        # v0.7.5: if multi-validator consensus is enabled, verify block attestations
        # stored in block_metadata. At least multi_validator_min_attestations must
        # be valid signatures from the configured validator set.
        if getattr(settings, "multi_validator_consensus_enabled", False) and getattr(settings, "validator_set", ""):
            validator_set = self._load_validator_set()
            from aitbc.crypto.signature_recovery import canonical_address

            proposer_canonical = canonical_address(proposer)
            if any(canonical_address(v) == proposer_canonical for v in validator_set):
                valid, reason = self._validate_attestations(block_data)
                if not valid:
                    metrics_registry.increment("sync_signature_rejected_total")
                    return (False, reason)

        metrics_registry.increment("sync_signature_validated_total")
        return (True, "Valid")

    def _load_validator_set(self) -> set[str]:
        """Return the configured validator set addresses."""
        validator_set = getattr(settings, "validator_set", "")
        if not validator_set:
            return set()
        try:
            import json

            return {v.get("address", "").lower() for v in json.loads(validator_set) if v.get("address")}
        except Exception:
            return set()

    def _effective_min_attestations(self) -> int:
        """Return the configured minimum clamped by the available validator set.

        A block can never carry more non-proposer attestations than the set
        contains, so requiring more would create an impossible quorum.
        """
        configured = getattr(settings, "multi_validator_min_attestations", 0)
        if configured <= 0:
            return 0
        validator_set = self._load_validator_set() or self._trusted
        if not validator_set:
            return 0
        from aitbc.crypto.signature_recovery import canonical_address

        active_non_proposer = max(0, len({canonical_address(v) for v in validator_set}) - 1)
        return max(0, min(configured, active_non_proposer))

    def _validate_attestations(self, block_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate attestations in block_metadata for multi-validator consensus."""
        min_attestations = self._effective_min_attestations()
        if min_attestations <= 0:
            return (True, "No attestations required")

        metadata_str = block_data.get("block_metadata", "")
        if not metadata_str:
            return (False, "Multi-validator block missing block_metadata attestations")

        try:
            import json

            metadata = json.loads(metadata_str)
        except json.JSONDecodeError as e:
            return (False, f"Invalid block_metadata JSON: {e}")

        # v0.7.7: PBFT blocks store a commit certificate in block_metadata instead
        # of the older attestations list. A PBFT commit is equivalent to an
        # attestation: it is a signature over the block hash from a validator.
        pbft_certificate = metadata.get("pbft_certificate")
        if isinstance(pbft_certificate, list):
            return self._validate_pbft_certificate(block_data, pbft_certificate)

        attestations = metadata.get("attestations", [])
        if not isinstance(attestations, list) or len(attestations) < min_attestations:
            return (False, f"Insufficient attestations: {len(attestations)} < {min_attestations}")

        validator_set = self._load_validator_set() or self._trusted
        from aitbc.crypto.consensus_signing import verify_block_signature
        from aitbc.crypto.signature_recovery import canonical_address

        valid_count = 0
        validator_canonical = {canonical_address(v) for v in validator_set}
        for att in attestations:
            validator = att.get("validator", "")
            signature = att.get("signature", "")
            if not validator or not signature:
                continue
            if validator_canonical and canonical_address(validator) not in validator_canonical:
                continue
            if verify_block_signature(block_data, signature, validator):
                valid_count += 1

        if valid_count < min_attestations:
            return (False, f"Only {valid_count} valid attestations, need {min_attestations}")
        return (True, f"{valid_count} valid attestations")

    def _validate_pbft_certificate(
        self,
        block_data: dict[str, Any],
        certificate: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Validate a PBFT commit certificate stored in block_metadata."""
        import hashlib

        from aitbc.crypto.consensus_signing import verify_consensus_message
        from aitbc.crypto.signature_recovery import canonical_address

        min_attestations = self._effective_min_attestations()
        validator_set = self._load_validator_set() or self._trusted
        validator_canonical = {canonical_address(v) for v in validator_set}

        block_hash = block_data.get("hash", "")

        valid_count = 0
        seen = set()
        for commit in certificate:
            if not isinstance(commit, dict) or commit.get("message_type") != "commit":
                continue
            sender = commit.get("sender", "")
            signature = commit.get("signature", "")
            view_number = commit.get("view_number")
            sequence_number = commit.get("sequence_number")
            digest = commit.get("digest", "")
            commit_block_hash = commit.get("block_hash", "")
            if not sender or not signature or view_number is None or sequence_number is None or not digest:
                continue
            if commit_block_hash and commit_block_hash != block_hash:
                continue
            # The PBFT sequence_number is the PBFT view sequence, not the chain
            # height, so the only height binding we enforce is the block_hash.
            expected_block_hash = commit_block_hash or block_hash
            expected_digest = hashlib.sha256(f"{expected_block_hash}:{sequence_number}:{view_number}".encode()).hexdigest()
            if digest.lower() != expected_digest.lower():
                continue
            if validator_canonical and canonical_address(sender) not in validator_canonical:
                continue
            sender_canonical = canonical_address(sender)
            if sender_canonical in seen:
                continue
            msg_data = {
                "message_type": commit.get("message_type"),
                "sender": sender,
                "view_number": view_number,
                "sequence_number": sequence_number,
                "digest": digest,
            }
            if verify_consensus_message(msg_data, signature, sender):
                valid_count += 1
                seen.add(sender_canonical)

        if valid_count < min_attestations:
            return (False, f"Only {valid_count} valid PBFT commits, need {min_attestations}")
        return (True, f"{valid_count} valid PBFT commits")
