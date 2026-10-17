"""Cross-chain bridge validator set management and signature verification."""

from __future__ import annotations

import json as _json
from datetime import UTC, datetime, timedelta
from typing import Any

from eth_utils import keccak
from sqlmodel import func, select

from aitbc.bridge import ValidatorInfo, ValidatorSet

from ..config import settings
from ..database import init_db
from ..logger import get_logger
from ..models import BridgeValidator
from .bridge_base import BridgeBase

logger = get_logger(__name__)


class BridgeValidatorMixin(BridgeBase):
    """Validator set registration, loading, and signature verification."""

    # Protocol base declares the attributes the concrete CrossChainBridge sets.

    # v0.7.1: Validator set management + multi-sig threshold verification
    # ------------------------------------------------------------------

    def register_validator(self, chain_id: str, address: str, public_key: str, epoch: int = 0) -> None:
        """Register a bridge validator in the DB and in-memory registry.

        Called by the RPC endpoint ``POST /bridge/validators/register``.
        Replaces any existing registration for the same (chain_id, address, epoch).
        """
        with self._session_for(chain_id) as session:
            # Check if validator already exists for this chain+address+epoch
            existing = session.exec(
                select(BridgeValidator).where(
                    BridgeValidator.chain_id == chain_id,
                    BridgeValidator.address == address,
                    BridgeValidator.epoch == epoch,
                )
            ).first()
            if existing:
                existing.public_key = public_key
                existing.is_active = True
                existing.registered_at = datetime.now(UTC)
                session.add(existing)
            else:
                record = BridgeValidator(
                    chain_id=chain_id,
                    address=address,
                    public_key=public_key,
                    epoch=epoch,
                    is_active=True,
                )
                session.add(record)
            session.commit()

        # Update in-memory registry
        info = ValidatorInfo(
            address=address,
            public_key=public_key,
            chain_id=chain_id,
            epoch=epoch,
            is_active=True,
        )
        self._validator_registry.register_validator(info)
        # Mark this epoch as needing reload (registry already updated, but
        # clear the cache flag so future loads re-read from DB if needed)
        self._validator_cache_loaded.discard((chain_id, epoch))
        logger.info("Registered bridge validator: %s for chain=%s epoch=%s", address[:12], chain_id, epoch)

    def ensure_supported_chain_validators(self) -> None:
        """Backfill bridge validator sets for BRIDGE_SUPPORTED_CHAINS from the default chain.

        If a supported bridge chain has no bridge validators registered, copy the
        active validator set from ``settings.chain_id``. This keeps island/shop
        chains from starting with an empty validator set.
        """
        source_chain = str(getattr(settings, "chain_id", ""))
        if not source_chain:
            return
        with self._session_for(source_chain) as session:
            source_validators = list(
                session.exec(
                    select(BridgeValidator).where(
                        BridgeValidator.chain_id == source_chain,
                        BridgeValidator.is_active.is_(True),  # type: ignore[attr-defined]
                    )
                ).all()
            )
        if not source_validators:
            logger.warning("No active bridge validators on source chain %s", source_chain)
            return
        supported = str(getattr(settings, "bridge_supported_chains", ""))
        if not supported:
            return
        for target_chain in [c.strip() for c in supported.split(",") if c.strip()]:
            if target_chain == source_chain:
                continue
            try:
                # Ensure target chain tables exist before probing or writing.
                init_db(target_chain)
                with self._session_for(target_chain) as session:
                    existing = session.exec(select(BridgeValidator).where(BridgeValidator.chain_id == target_chain)).first()
                    if existing:
                        continue
                for v in source_validators:
                    self.register_validator(target_chain, v.address, v.public_key, v.epoch)
                logger.info(
                    "Backfilled %s bridge validators for %s from %s",
                    len(source_validators),
                    target_chain,
                    source_chain,
                )
            except Exception:
                logger.exception("Failed to backfill bridge validators for %s", target_chain)

    def load_validator_set(self, chain_id: str, epoch: int | None = None) -> Any:
        """Load the validator set for a chain from the DB into the registry.

        If epoch is None, loads the latest epoch for the chain.
        Returns the ValidatorSet, or None if no validators are registered.
        """
        with self._session_for(chain_id) as session:
            query = select(BridgeValidator).where(BridgeValidator.chain_id == chain_id)
            if epoch is not None:
                query = query.where(BridgeValidator.epoch == epoch)
            else:
                # Get the latest epoch
                latest = session.exec(
                    select(BridgeValidator.epoch)
                    .where(BridgeValidator.chain_id == chain_id)
                    .order_by(BridgeValidator.epoch.desc())  # type: ignore[attr-defined]
                    .limit(1)
                ).first()
                if latest is None:
                    return None
                epoch = latest
                query = query.where(BridgeValidator.epoch == epoch)

            records = session.exec(query).all()
            if not records:
                return None

            validators = [
                ValidatorInfo(
                    address=r.address,
                    public_key=r.public_key,
                    chain_id=r.chain_id,
                    epoch=r.epoch,
                    is_active=r.is_active,
                    registered_at=r.registered_at,
                )
                for r in records
            ]
            # v0.7.2: derive the M-of-N threshold from live settings so the
            # validator set metadata matches the policy actually enforced by
            # _verify_threshold_signatures. ``total`` is the real N.
            threshold = getattr(settings, "bridge_multisig_threshold", 3)
            vset = ValidatorSet(
                chain_id=chain_id,
                epoch=epoch,
                validators=validators,
                threshold=threshold,
                total=len(validators),
            )
            # Update the in-memory registry
            self._validator_registry._sets.setdefault(chain_id, {})[epoch] = vset
            self._validator_registry._current_epoch[chain_id] = max(
                epoch, self._validator_registry._current_epoch.get(chain_id, 0)
            )
            self._validator_cache_loaded.add((chain_id, epoch))
            return vset

    def get_validator_set(self, chain_id: str, epoch: int | None = None) -> Any:
        """Get the validator set for a chain.

        Checks the in-memory registry first; loads from DB on cache miss.
        Returns the ValidatorSet, or None if no validators are registered.
        """
        # Check if we have it in memory
        vset = self._validator_registry.get_validator_set(chain_id, epoch)
        if vset is not None:
            return vset
        # Cache miss — load from DB
        return self.load_validator_set(chain_id, epoch)

    def release_availability(self, source_chain: str) -> tuple[bool, str | None]:
        """Report whether the release path can currently succeed for a chain.

        Mirrors the gates ``confirm_transfer`` → ``_validate_proof`` applies,
        so create endpoints can tell callers up front that a lock will
        confirm but never release. Returns ``(available, reason)`` —
        ``reason`` is None when available.

        Fails closed identically to the verification path: a missing or
        unreachable validator set means release is impossible; when multisig
        is enabled, a validator set smaller than the threshold can never
        satisfy it.
        """
        if not (getattr(settings, "escrow_enabled", False) or getattr(settings, "bridge_release_enabled", False)):
            return False, "release path disabled (escrow_enabled=false, bridge_release_enabled=false)"

        multisig_enabled = getattr(settings, "bridge_multisig_enabled", False)
        threshold = int(getattr(settings, "bridge_multisig_threshold", 3))

        try:
            vset = self.get_validator_set(source_chain)
        except Exception as e:
            return False, f"validator set lookup failed for {source_chain}: {e}"

        if vset is None:
            return False, f"no validator set registered for source chain {source_chain}"

        if multisig_enabled and vset.total < threshold:
            return False, f"validator set size {vset.total} below required threshold {threshold} for {source_chain}"

        return True, None

    def _verify_proposer_signature(self, proof: dict[str, Any]) -> bool:
        """Verify the proposer signature on a bridge proof.

        The signed message is the keccak256 hash of the canonical JSON of
        the proof fields excluding the proposer_signature itself.
        The signer's address must match the source chain's proposer at the
        claimed block height.

        The recovered signer address **must** be a member of the proof's
        source-chain validator set; with no set registered the proof is
        refused (F2).
        """
        proposer_signature = proof.get("proposer_signature", "")
        if not proposer_signature:
            return False

        # Build the message that was signed (proof without proposer_signature)
        proof_for_signing = {k: v for k, v in proof.items() if k != "proposer_signature"}
        message = _json.dumps(proof_for_signing, sort_keys=True, separators=(",", ":")).encode()

        try:
            from aitbc.crypto.signature_recovery import SignatureMalformed, recover_address

            try:
                recovered = recover_address(keccak(message), proposer_signature)
            except SignatureMalformed as e:
                logger.warning("Malformed proposer signature (encoding fault): %s", e)
                return False
            logger.debug("Proof signed by: %s", recovered)

            # F2: the signer must be a member of the source chain's validator
            # set on every path; a missing or unreadable set fails closed.
            source_chain = proof.get("source_chain") or proof.get("chain_id")
            if not source_chain:
                logger.warning("Proof missing source_chain for validator set lookup")
                return False
            try:
                vset = self.get_validator_set(source_chain)
            except Exception as e:
                logger.warning("Validator set lookup failed for chain=%s (%s); rejecting proof", source_chain, e)
                return False
            if vset is None:
                logger.warning("No validator set registered for chain=%s; rejecting proof", source_chain)
                return False
            validator_addresses = {v.address.lower() if hasattr(v, "address") else str(v).lower() for v in vset.validators}
            if recovered.lower() not in validator_addresses:
                logger.warning(
                    "Proposer signature recovered to %s which is NOT in the validator set for chain=%s",
                    recovered,
                    source_chain,
                )
                return False

            return True
        except Exception as e:
            logger.warning("Proposer signature verification error: %s", e)
            return False

    def _verify_threshold_signatures(self, proof: dict[str, Any], header: Any | None = None) -> bool:
        """Verify proof signatures using M-of-N threshold (v0.7.1/v0.7.3).

        When a ``header`` is provided, signatures are verified against the
        canonical block header message (v0.7.3). Otherwise the proof fields
        are used directly.

        When ``bridge_multisig_enabled`` is True, requires M-of-N validator
        signatures. When False, falls back to single-signer verification.
        """
        multisig_enabled = getattr(settings, "bridge_multisig_enabled", False)
        sig_required = getattr(settings, "bridge_block_signature_required", True)
        if header is not None and sig_required:
            return self._verify_header_threshold_signatures(proof, header, multisig_enabled)
        if not multisig_enabled:
            # Backward-compatible: use single-signer verification
            return self._verify_proposer_signature(proof)

        # Multi-sig path: collect validator signatures from the proof
        validator_signatures = proof.get("validator_signatures", [])
        proposer_signature = proof.get("proposer_signature", "")

        # Build the message that was signed (proof without signature fields)
        proof_for_signing = {k: v for k, v in proof.items() if k not in ("proposer_signature", "validator_signatures")}

        # Get the validator set for the source chain
        source_chain = proof.get("source_chain") or proof.get("chain_id")
        if not source_chain:
            logger.warning("Proof missing source_chain for validator set lookup")
            return False

        vset = self.get_validator_set(source_chain)
        if vset is None:
            logger.warning("No validator set registered for chain: %s", source_chain)
            return False

        # Collect all signatures (validator sigs + backward-compat proposer sig)
        all_sigs = list(validator_signatures)
        if proposer_signature and proposer_signature not in all_sigs:
            all_sigs.append(proposer_signature)

        # Recover all signers
        from aitbc.bridge import check_threshold, recover_all_signers

        signers = recover_all_signers(proof_for_signing, all_sigs)
        # Normalize signers to lowercase for case-insensitive comparison with
        # validator addresses (recover_signer returns checksum addresses,
        # validators are registered with lowercase addresses)
        signers = [s.lower() for s in signers]
        threshold = getattr(settings, "bridge_multisig_threshold", 3)
        meets, count, _ = check_threshold(signers, vset, threshold)

        if not meets:
            logger.warning(
                "Threshold not met: %d/%d valid signers (need %d) for chain %s",
                count,
                vset.total,
                threshold,
                source_chain,
            )
            return False

        logger.debug("Threshold met: %d/%d valid signers for chain %s", count, vset.total, source_chain)
        return True

    def _verify_header_threshold_signatures(self, proof: dict[str, Any], header: Any, multisig_enabled: bool) -> bool:
        """Verify block header signatures against the canonical header message.

        Builds the canonical block header message from ``header``, recovers
        signers from the proof's ``proposer_signature`` and
        ``validator_signatures`` using ``aitbc.bridge.recover_all_signers``,
        and checks the multi-sig threshold against the validator set.
        """
        from aitbc.bridge import build_verification_message, check_threshold, recover_all_signers

        message = build_verification_message(header)
        validator_signatures = proof.get("validator_signatures", [])
        proposer_signature = proof.get("proposer_signature", "")

        all_sigs = list(validator_signatures)
        if proposer_signature and proposer_signature not in all_sigs:
            all_sigs.append(proposer_signature)

        signers = recover_all_signers(message, all_sigs)
        source_chain = header.chain_id or proof.get("source_chain") or proof.get("chain_id")
        if not source_chain:
            logger.warning("Block header missing chain_id")
            return False

        if not multisig_enabled:
            # Single-sig: at least one recovered signer must match the proposer.
            if not signers:
                logger.warning("No signers recovered from block header for chain=%s", source_chain)
                return False
            if header.proposer and header.proposer.lower() not in {s.lower() for s in signers}:
                logger.warning(
                    "Block header signer does not match proposer: expected %s",
                    header.proposer,
                )
                return False

            # F2: the signer must be a registered validator; a missing or
            # unreadable set fails closed rather than accepting any key.
            try:
                vset = self.get_validator_set(source_chain)
            except Exception as e:
                logger.warning("Validator set lookup failed for chain=%s (%s); rejecting proof", source_chain, e)
                return False

            if vset is None:
                logger.warning("No validator set registered for chain=%s; rejecting proof", source_chain)
                return False
            valid_addresses = {a.lower() for a in vset.addresses}
            if not any(s.lower() in valid_addresses for s in signers):
                logger.warning("Proposer not in validator set for chain=%s", source_chain)
                return False

            return True

        vset = self.get_validator_set(source_chain)
        if vset is None:
            logger.warning("No validator set registered for chain: %s", source_chain)
            return False

        threshold = getattr(settings, "bridge_multisig_threshold", 3)
        meets, count, _ = check_threshold(signers, vset, threshold)

        if not meets:
            logger.warning(
                "Threshold not met: %d/%d valid signers (need %d) for chain %s",
                count,
                vset.total,
                threshold,
                source_chain,
            )
            return False

        logger.debug("Threshold met: %d/%d valid signers for chain %s", count, vset.total, source_chain)
        return True

    def _check_validator_set_freshness(self, chain_id: str, epoch: int | None = None) -> bool:
        """Check that the validator set for a chain is not stale (B6).

        Epoch-aware semantics matching the config comment ("old epoch
        valid during rotation"): the chain's LATEST epoch is the
        authoritative set and does not decay — supersession, not wall
        time, is the rotation mechanism. A SUPERSEDED epoch stays
        verifiable only for ``bridge_validator_set_grace_period`` seconds
        after the superseding registration (the newest ``registered_at``
        of any newer-epoch row).

        ``epoch=None`` means "the current set" and is fresh whenever any
        set exists. ``epoch`` newer than the latest registered epoch is
        unknown → False (the set lookup fails on its own anyway).
        """
        grace_period = getattr(settings, "bridge_validator_set_grace_period", 7200)
        now = datetime.now(UTC)

        with self._session_for(chain_id) as session:
            latest_epoch_row = session.exec(
                select(func.max(BridgeValidator.epoch)).where(BridgeValidator.chain_id == chain_id)
            ).first()
            if latest_epoch_row is None:
                # F2: no validators registered — nothing can be fresh.
                logger.warning("Validator set for chain=%s is empty", chain_id)
                return False
            latest_epoch = int(latest_epoch_row)

            if epoch is None or epoch == latest_epoch:
                return True
            if epoch > latest_epoch:
                logger.warning(
                    "Validator set epoch %d for chain=%s unknown (latest=%d)",
                    epoch,
                    chain_id,
                    latest_epoch,
                )
                return False

            # Superseded epoch: grace runs from the superseding
            # registration — the newest registered_at among newer epochs.
            superseded_by = session.exec(
                select(BridgeValidator)
                .where(
                    BridgeValidator.chain_id == chain_id,
                    BridgeValidator.epoch > epoch,
                )
                .order_by(BridgeValidator.registered_at.desc())  # type: ignore[attr-defined]
                .limit(1)
            ).first()
            if superseded_by is None:
                # Latest epoch advanced without a visible newer row — treat
                # as fresh; the set lookup governs.
                return True
            registered = superseded_by.registered_at
            # SQLite may return timezone-naive datetimes — normalize to UTC
            if registered.tzinfo is None:
                registered = registered.replace(tzinfo=UTC)
            age = now - registered
            if age > timedelta(seconds=grace_period):
                logger.warning(
                    "Validator set epoch %d for chain=%s is stale (superseded %s ago, grace=%ss)",
                    epoch,
                    chain_id,
                    age,
                    grace_period,
                )
                return False
            return True
