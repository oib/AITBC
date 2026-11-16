"""Block import result type and proposer signature validation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from .logger import get_logger
from .metrics import metrics_registry

from .config import legacy_attestation_dual_accept_open, settings

logger = get_logger(__name__)


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

    def __init__(
        self,
        trusted_proposers: list[str] | None = None,
        *,
        parent_timestamp_resolver: Callable[[str], Any] | None = None,
    ) -> None:
        self._trusted = set(trusted_proposers or [])
        # #1242: resolves a parent_hash to its block timestamp so round-bound
        # attestations (signed over the 8-field message) can be verified even
        # when the attestation entry does not carry an explicit "round".
        self._parent_timestamp_resolver = parent_timestamp_resolver

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

        proposer, header_error = self._validate_block_header(block_data)
        if header_error:
            return (False, header_error)

        auth_error = self._verify_proposer_auth(block_data, proposer)
        if auth_error is not None:
            return (False, auth_error)

        # #1940 F3: the multi-validator attestation gate below only runs when
        # BOTH its flag and a non-empty configured set are present — with
        # either missing, nothing else would enforce the strict PBFT
        # certificate contract, so consult the shared verdict on that outer
        # path (``_trusted`` members still feed the verifier). The gated path
        # applies the same verdict inside ``_validate_attestations``, so no
        # block is ever verified twice.
        multivalidator_gate = getattr(settings, "multi_validator_consensus_enabled", False) and getattr(
            settings, "validator_set", ""
        )
        if not multivalidator_gate:
            strict_verdict = self._strict_pbft_verdict(block_data)
            if strict_verdict is not None and not strict_verdict[0]:
                metrics_registry.increment("sync_signature_rejected_total")
                return (False, strict_verdict[1])

        # v0.7.5: if multi-validator consensus is enabled, verify block attestations
        # stored in block_metadata. At least multi_validator_min_attestations must
        # be valid signatures from the configured validator set.
        if getattr(settings, "multi_validator_consensus_enabled", False) and getattr(settings, "validator_set", ""):
            validator_set = self._load_validator_set()
            from aitbc.crypto.signature_recovery import canonical_address

            proposer_canonical = canonical_address(proposer)
            if not any(canonical_address(v) == proposer_canonical for v in validator_set):
                # #842: a proposer outside the set is not "no attestation
                # needed" — multi-validator consensus is on, so the block is
                # invalid on its face.
                metrics_registry.increment("sync_signature_rejected_total")
                return (False, "Block proposer is not in the configured validator set")
            valid, reason = self._validate_attestations(block_data)
            if not valid:
                metrics_registry.increment("sync_signature_rejected_total")
                return (False, reason)

        metrics_registry.increment("sync_signature_validated_total")
        return (True, "Valid")

    def _validate_block_header(self, block_data: dict[str, Any]) -> tuple[str, str]:
        """Extract and validate the block header fields.

        Returns (proposer, error_reason); error_reason is empty on success.
        """
        proposer = block_data.get("proposer", "")
        block_hash = block_data.get("hash", "")
        if not proposer:
            return ("", "Missing proposer field")
        if not block_hash:
            return ("", f"Invalid block hash format: {block_hash}")
        if not block_hash.startswith("0x"):
            block_hash = f"0x{block_hash}"
        for field in ("height", "parent_hash", "timestamp"):
            if field not in block_data:
                return ("", f"Missing required field: {field}")
        hash_hex = block_hash[2:]
        if len(hash_hex) != 64:
            return ("", f"Invalid hash length: {len(hash_hex)}")
        try:
            int(hash_hex, 16)
        except ValueError:
            return ("", f"Invalid hex in hash: {hash_hex}")
        return (proposer, "")

    def _verify_proposer_auth(self, block_data: dict[str, Any], proposer: str) -> str | None:
        """Verify proposer authorization: trusted-set membership plus signature.

        Returns the rejection reason, or None when the proposer authenticates.
        """
        if self._trusted and proposer not in self._trusted:
            metrics_registry.increment("sync_signature_rejected_total")
            return f"Proposer '{proposer}' not in trusted set"
        signature = block_data.get("signature", "")
        if signature:
            from aitbc.crypto.consensus_signing import (
                DOMAIN_BLOCK_PROPOSAL,
                block_header_message,
                verify_block_signature,
                verify_consensus_message_domain,
            )

            # #1298: at/above the armed activation height the proposer signs
            # under the proposal domain — the legacy/raw-hash fallbacks in
            # verify_block_signature must not accept it (hard cutover).
            height = block_data.get("height", 0)
            activation = getattr(settings, "consensus_domain_separation_height", None)
            if activation is not None and isinstance(height, int) and height >= activation:
                sig_ok = verify_consensus_message_domain(
                    block_header_message(block_data), signature, proposer, DOMAIN_BLOCK_PROPOSAL
                )
            else:
                sig_ok = verify_block_signature(block_data, signature, proposer)
            if not sig_ok:
                metrics_registry.increment("sync_signature_rejected_total")
                return "Invalid proposer signature"
        elif not self._trusted:
            metrics_registry.increment("sync_signature_rejected_total")
            return "Unsigned block and no trusted proposer set configured"
        return None

    def _load_validator_set(self) -> set[str]:
        """Return the configured validator set addresses."""
        validator_set = getattr(settings, "validator_set", "")
        if not validator_set:
            return set()
        try:
            import json

            return {v.get("address", "").lower() for v in json.loads(validator_set) if v.get("address")}
        except Exception as exc:
            # #842: a VALIDATOR_SET that does not parse must not silently read
            # as "no validators" — that turns attestation enforcement off.
            logger.warning("VALIDATOR_SET failed to parse (%s) — treating as empty", exc)
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

    def _attestation_metadata(self, block_data: dict[str, Any]) -> tuple[Any, tuple[bool, str] | None]:
        """Parse ``block_metadata`` for the attestation path.

        Returns ``(metadata, None)`` on success, or ``(None, verdict)`` where
        verdict is the rejection tuple the caller returns directly.
        """
        metadata_str = block_data.get("block_metadata", "")
        if not metadata_str:
            return None, (False, "Multi-validator block missing block_metadata attestations")

        try:
            import json

            metadata = json.loads(metadata_str)
        except json.JSONDecodeError as e:
            return None, (False, f"Invalid block_metadata JSON: {e}")
        return metadata, None

    def _count_valid_attestations(self, block_data: dict[str, Any], attestations: list[Any]) -> int:
        """Count distinct validator-set attestations with valid signatures."""
        validator_set = self._load_validator_set() or self._trusted
        from aitbc.crypto.signature_recovery import canonical_address

        valid_count = 0
        seen: set[str] = set()
        validator_canonical = {canonical_address(v) for v in validator_set}
        for att in attestations:
            validator = att.get("validator", "")
            signature = att.get("signature", "")
            if not validator or not signature:
                continue
            if canonical_address(validator) not in validator_canonical:
                continue
            # Count each validator once: the PBFT path below already dedups via
            # ``seen``, and a duplicated entry must not count twice toward
            # min_attestations.
            validator_key = canonical_address(validator)
            if validator_key in seen:
                continue
            if self._attestation_sig_ok(block_data, att, validator):
                valid_count += 1
                seen.add(validator_key)
        return valid_count

    def _validate_attestations(self, block_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate attestations in block_metadata for multi-validator consensus."""
        strict_verdict = self._strict_pbft_verdict(block_data)
        if strict_verdict is not None:
            return strict_verdict
        min_attestations = self._effective_min_attestations()
        if min_attestations <= 0:
            return (True, "No attestations required")

        metadata, error = self._attestation_metadata(block_data)
        if error is not None:
            return error

        # v0.7.7: PBFT blocks store a commit certificate in block_metadata instead
        # of the older attestations list. A PBFT commit is equivalent to an
        # attestation: it is a signature over the block hash from a validator.
        pbft_certificate = metadata.get("pbft_certificate")
        if isinstance(pbft_certificate, list):
            return self._validate_pbft_certificate(block_data, pbft_certificate)

        attestations = metadata.get("attestations", [])
        if not isinstance(attestations, list) or len(attestations) < min_attestations:
            return (False, f"Insufficient attestations: {len(attestations)} < {min_attestations}")

        valid_count = self._count_valid_attestations(block_data, attestations)
        if valid_count < min_attestations:
            return (False, f"Only {valid_count} valid attestations, need {min_attestations}")
        return (True, f"{valid_count} valid attestations")

    def _attestation_sig_ok(self, block_data: dict[str, Any], att: dict[str, Any], validator: str) -> bool:
        """Verify one attestation entry against the block.

        #1242: round-bound attestations sign an 8-field message that includes
        the proposer round. Entries sealed before the "round" hint existed
        still carry round-bound signatures, so when no explicit round is
        present we derive it from the parent timestamp exactly as attesters
        do. The legacy 7-field message is always tried as a fallback for
        mixed-version fleets.
        """
        from aitbc.crypto.consensus_signing import (
            DOMAIN_BLOCK_ATTESTATION,
            verify_block_signature,
            verify_consensus_message,
            verify_consensus_message_domain,
        )

        signature = att.get("signature", "")
        # #1298: at/above the armed activation height attestations are signed
        # under the attestation domain — legacy shared-preimage signatures
        # must not verify (hard cutover per design v2.2 §7), EXCEPT inside
        # the bounded dual-accept window [H, S) where both preimages count.
        activation = getattr(settings, "consensus_domain_separation_height", None)
        height = block_data.get("height", 0)
        domain_active = activation is not None and isinstance(height, int) and height >= activation
        dual_accept = domain_active and legacy_attestation_dual_accept_open(height)
        rounds: list[int] = []
        att_round = att.get("round")
        if att_round is not None:
            try:
                rounds.append(int(att_round))
            except (TypeError, ValueError):
                pass
        else:
            derived = self._derive_attestation_round(block_data)
            if derived is not None:
                rounds.append(derived)
        if self._round_bound_attestation_ok(block_data, att, validator, domain_active, dual_accept, rounds):
            return True
        if domain_active:
            msg7 = {
                "chain_id": block_data.get("chain_id", ""),
                "height": block_data.get("height", 0),
                "hash": block_data.get("hash", ""),
                "parent_hash": block_data.get("parent_hash", ""),
                "proposer": block_data.get("proposer", ""),
                "state_root": block_data.get("state_root", ""),
                "bridge_state_root": block_data.get("bridge_state_root", ""),
            }
            if verify_consensus_message_domain(msg7, signature, validator, DOMAIN_BLOCK_ATTESTATION):
                return True
            # Window legacy accept is the shared-preimage header message only —
            # the raw-hash fallback inside verify_block_signature stays gated
            # to heights below the activation height (design v2.1 O4).
            if dual_accept and verify_consensus_message(msg7, signature, validator):
                metrics_registry.increment("consensus_legacy_attestation_accepted_total")
                return True
            return False
        return verify_block_signature(block_data, signature, validator)

    def _round_bound_attestation_ok(
        self,
        block_data: dict[str, Any],
        att: dict[str, Any],
        validator: str,
        domain_active: bool,
        dual_accept: bool,
        rounds: list[int],
    ) -> bool:
        """Verify the round-bound 8-field attestation message per candidate round."""
        from aitbc.crypto.consensus_signing import (
            DOMAIN_BLOCK_ATTESTATION,
            verify_consensus_message,
            verify_consensus_message_domain,
        )

        signature = att.get("signature", "")
        for rnd in rounds:
            msg = {
                "chain_id": block_data.get("chain_id", ""),
                "height": block_data.get("height", 0),
                "hash": block_data.get("hash", ""),
                "parent_hash": block_data.get("parent_hash", ""),
                "proposer": block_data.get("proposer", ""),
                "state_root": block_data.get("state_root", ""),
                "bridge_state_root": block_data.get("bridge_state_root", ""),
                "round": rnd,
            }
            if domain_active:
                if verify_consensus_message_domain(msg, signature, validator, DOMAIN_BLOCK_ATTESTATION):
                    return True
                if dual_accept and verify_consensus_message(msg, signature, validator):
                    metrics_registry.increment("consensus_legacy_attestation_accepted_total")
                    return True
            elif verify_consensus_message(msg, signature, validator):
                return True
        return False

    def _derive_attestation_round(self, block_data: dict[str, Any]) -> int | None:
        """Independently derive the proposer round for this block."""
        if self._parent_timestamp_resolver is None:
            return None
        try:
            from datetime import datetime

            from .consensus.multi_validator_poa import proposer_round

            block_ts_raw = block_data.get("timestamp")
            if isinstance(block_ts_raw, str):
                block_ts = datetime.fromisoformat(block_ts_raw)
            elif isinstance(block_ts_raw, datetime):
                block_ts = block_ts_raw
            else:
                return None
            parent_hash = str(block_data.get("parent_hash", "") or "")
            if not parent_hash:
                return None
            parent_ts = self._parent_timestamp_resolver(parent_hash)
            if parent_ts is None:
                return None
            if isinstance(parent_ts, str):
                parent_ts = datetime.fromisoformat(parent_ts)
            window = int(getattr(settings, "consensus_proposer_round_seconds", 120) or 120)
            if window <= 0:
                return None
            return proposer_round(parent_ts, block_ts, window)
        except Exception as e:  # noqa: BLE001 - round derivation failure reports unknown round
            logger.debug("proposer round derivation failed: %s", type(e).__name__)
            return None

    @staticmethod
    def _strict_era_metadata(block_data: dict[str, Any]) -> tuple[bool, Any]:
        """Safely parse ``block_metadata`` for the strict-era gate (#1940 F3).

        Returns ``(True, parsed)`` — ``parsed`` may be any JSON value —
        or ``(False, None)`` when metadata is absent, not a string, or
        unparseable. ``RecursionError`` from pathologically deep JSON is
        caught here so the gate itself can never raise.
        """
        import json

        metadata_str = block_data.get("block_metadata", "")
        if not isinstance(metadata_str, str) or not metadata_str:
            return False, None
        try:
            return True, json.loads(metadata_str)
        except (ValueError, RecursionError, TypeError):
            return False, None

    def _strict_pbft_verdict(self, block_data: dict[str, Any]) -> tuple[bool, str] | None:
        """#1940 F3 strict-era certificate gate, consulted at the top of
        ``_validate_attestations``.

        Returns ``None`` when the strict contract does not apply — the
        block height is pre-threshold, or (PBFT disabled) the metadata
        carries no ``pbft_certificate`` key — so the legacy body runs
        byte-equivalent. Otherwise returns the certificate verdict
        directly:

        - strict era AND ``pbft_consensus_enabled``: the block MUST carry
          parseable metadata object with a ``pbft_certificate`` list that
          passes the shared strict verifier — missing/malformed/non-object
          metadata or a missing/non-list certificate rejects even at
          ``min_attestations=0``, so a proposer cannot omit the certificate
          and fall back to a gossip attestation quorum;
        - strict era with PBFT off: only a metadata object CONTAINING
          ``pbft_certificate`` is intercepted (non-list rejects, a list is
          strictly verified); everything else returns ``None`` and keeps
          the normal attestation behaviour.
        """
        from .consensus.pbft_certificate import strict_certificate_active

        height = block_data.get("height")
        if not strict_certificate_active(height):
            return None
        pbft_on = bool(getattr(settings, "pbft_consensus_enabled", False))
        parsed, metadata = self._strict_era_metadata(block_data)
        if not parsed:
            if pbft_on:
                return False, "strict-era PBFT block missing parseable block_metadata"
            return None
        if not isinstance(metadata, dict):
            if pbft_on:
                return False, "strict-era PBFT block_metadata is not a JSON object"
            return None
        if "pbft_certificate" not in metadata:
            if pbft_on:
                return False, "strict-era PBFT block missing pbft_certificate"
            return None
        certificate = metadata["pbft_certificate"]
        if not isinstance(certificate, list):
            return False, "strict-era pbft_certificate is not a list"
        return self._strict_certificate_verdict(block_data, certificate)

    def _bound_certificate_view(self, block_data: dict[str, Any], height: Any) -> tuple[int | None, str | None]:
        """The PBFT view a strict certificate must carry, when binding is armed (#1940 F3-B).

        Returns ``(expected_view, None)`` — ``expected_view`` is ``None``
        when the view stays unpinned — or ``(None, reason)`` when the gate
        requires a view but the proposer's timestamp-derived round cannot be
        derived for this block: fail closed, because an underivable round on
        a PBFT-enabled strict block means the certificate cannot be bound to
        the round the producer signed under.

        Binding applies only when ALL of these hold: the
        ``pbft_certificate_view_binding_height`` gate is active at ``height``,
        the strict certificate contract is active, and
        ``pbft_consensus_enabled`` is set. PBFT-off blocks that merely carry
        a certificate keep the unpinned check — the gate was armed for the
        PBFT producer/importer pair, not for carried-certificate blocks.
        """
        from .consensus.pbft_certificate import certificate_view_binding_active, strict_certificate_active
        from .consensus.pbft_view_change import view_change_active

        # #2005 F3-C ruling 3A: ``pbft_view_change_height`` pins the same
        # derived-round view — the certificate's view must equal the block's
        # timestamp-derived proposer round once the view-change protocol is
        # armed, closing the residual view-substitution gap.
        if not (certificate_view_binding_active(height) or view_change_active(height)) or not strict_certificate_active(
            height
        ):
            return None, None
        if not getattr(settings, "pbft_consensus_enabled", False):
            return None, None
        expected = self._derive_attestation_round(block_data)
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
            return None, "strict-era PBFT certificate view underivable: proposer round could not be derived"
        return expected, None

    def _strict_certificate_verdict(
        self,
        block_data: dict[str, Any],
        certificate: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """The ONE strict-era certificate verdict shared by importer paths (#1940 F3 / F3-B).

        Both ``_strict_pbft_verdict`` (the mandatory-certificate gate) and
        ``_validate_pbft_certificate`` (the carried-certificate path)
        delegate here so producer-side and importer-side checks can never
        drift: same validator set, same height, same optional view pin —
        the pin supplied by ``_bound_certificate_view`` when the dormant
        ``pbft_certificate_view_binding_height`` gate is armed.
        """
        from .consensus.pbft_certificate import validate_commit_certificate

        height = block_data.get("height")
        expected_view, view_error = self._bound_certificate_view(block_data, height)
        if view_error is not None:
            return False, view_error
        return validate_commit_certificate(
            certificate,
            str(block_data.get("hash", "")),
            self._load_validator_set() or self._trusted,
            height=cast(int, height),
            view=expected_view,
            chain_id=str(block_data.get("chain_id") or ""),
        )

    def _validate_pbft_certificate(
        self,
        block_data: dict[str, Any],
        certificate: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Validate a PBFT commit certificate stored in block_metadata."""
        from .consensus.pbft_certificate import strict_certificate_active

        height = block_data.get("height")
        if strict_certificate_active(height):
            # #1940 F3 / F3-B: strict era delegates to the shared verdict —
            # one coherent (seq, view) commit quorum at the real BFT
            # threshold, never the legacy attestation-minimum union count.
            # ``view`` is unpinned unless the dormant view-binding gate is
            # armed; the gate guarantees ``height`` is a strict int here.
            return self._strict_certificate_verdict(block_data, certificate)
        return self._validate_pbft_certificate_legacy(block_data, certificate)

    def _validate_pbft_certificate_legacy(
        self,
        block_data: dict[str, Any],
        certificate: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Pre-#1940-F3 certificate check — the legacy body, byte-equivalent
        while the strict gate is inactive: unions distinct senders across ALL
        stored commit messages (mixed sequences/views included) and sizes the
        quorum by the attestation minimum, not ``pbft_required_messages``."""
        import hashlib

        from aitbc.crypto.signature_recovery import canonical_address

        from .consensus.pbft_vote_signature import verify_pbft_vote_signature

        # #2102: commit signatures verify under the block's chain_id-bound
        # preimage first, legacy preimage second.
        chain_id = block_data.get("chain_id") or None

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
            if canonical_address(sender) not in validator_canonical:
                continue
            sender_canonical = canonical_address(sender)
            if sender_canonical in seen:
                continue
            if verify_pbft_vote_signature(commit, signature, sender, chain_id):
                valid_count += 1
                seen.add(sender_canonical)

        if valid_count < min_attestations:
            return (False, f"Only {valid_count} valid PBFT commits, need {min_attestations}")
        return (True, f"{valid_count} valid PBFT commits")
