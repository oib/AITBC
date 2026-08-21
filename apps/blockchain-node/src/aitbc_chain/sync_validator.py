"""Block import result type and proposer signature validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import metrics_registry

from ..config import settings


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

            if not verify_block_signature(block_hash, signature, proposer):
                metrics_registry.increment("sync_signature_rejected_total")
                return (False, "Invalid proposer signature")
        elif not self._trusted:
            metrics_registry.increment("sync_signature_rejected_total")
            return (False, "Unsigned block and no trusted proposer set configured")

        # v0.7.5: if multi-validator consensus is enabled, verify block attestations
        # stored in block_metadata. At least multi_validator_min_attestations must
        # be valid signatures from the configured validator set.
        if getattr(settings, "multi_validator_consensus_enabled", False):
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

    def _validate_attestations(self, block_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate attestations in block_metadata for multi-validator consensus."""
        min_attestations = getattr(settings, "multi_validator_min_attestations", 0)
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

        attestations = metadata.get("attestations", [])
        if not isinstance(attestations, list) or len(attestations) < min_attestations:
            return (False, f"Insufficient attestations: {len(attestations)} < {min_attestations}")

        block_hash = block_data.get("hash", "")
        if not block_hash.startswith("0x"):
            block_hash = f"0x{block_hash}"

        validator_set = self._load_validator_set() or self._trusted
        from aitbc.crypto.consensus_signing import verify_block_signature

        valid_count = 0
        for att in attestations:
            validator = att.get("validator", "")
            signature = att.get("signature", "")
            if not validator or not signature:
                continue
            if validator_set and validator.lower() not in {v.lower() for v in validator_set}:
                continue
            if verify_block_signature(block_hash, signature, validator):
                valid_count += 1

        if valid_count < min_attestations:
            return (False, f"Only {valid_count} valid attestations, need {min_attestations}")
        return (True, f"{valid_count} valid attestations")
