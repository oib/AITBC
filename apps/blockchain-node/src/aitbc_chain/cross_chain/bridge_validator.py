"""Cross-chain bridge validator set management and signature verification."""

from __future__ import annotations

import json as _json
from datetime import UTC, datetime, timedelta
from typing import Any

from eth_utils import keccak
from sqlmodel import select

from aitbc.bridge import ValidatorInfo, ValidatorSet

from ..config import settings
from ..logger import get_logger
from ..models import BridgeValidator
from .bridge_base import BridgeBase

logger = get_logger(__name__)


class BridgeValidatorMixin(BridgeBase):
    """Validator set registration, loading, and signature verification."""

    # ponytail: Protocol base declares the attributes the concrete CrossChainBridge sets.

    # v0.7.1: Validator set management + multi-sig threshold verification
    # ------------------------------------------------------------------

    def register_validator(self, chain_id: str, address: str, public_key: str, epoch: int = 0) -> None:
        """Register a bridge validator in the DB and in-memory registry.

        Called by the RPC endpoint ``POST /bridge/validators/register``.
        Replaces any existing registration for the same (chain_id, address, epoch).
        """
        with self._session_factory() as session:
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

    def load_validator_set(self, chain_id: str, epoch: int | None = None) -> Any:
        """Load the validator set for a chain from the DB into the registry.

        If epoch is None, loads the latest epoch for the chain.
        Returns the ValidatorSet, or None if no validators are registered.
        """
        with self._session_factory() as session:
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
            vset = ValidatorSet(
                chain_id=chain_id,
                epoch=epoch,
                validators=validators,
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

    def _verify_proposer_signature(self, proof: dict[str, Any]) -> bool:
        """Verify the proposer signature on a bridge proof.

        The signed message is the keccak256 hash of the canonical JSON of
        the proof fields excluding the proposer_signature itself.
        The signer's address must match the source chain's proposer at the
        claimed block height.

        If a validator set is registered for the proof's source chain, the
        recovered signer address **must** be a member of that set. If no
        validator set is registered (e.g. dev/isolated networks), any valid
        signature is accepted for backward compatibility.
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

            # v0.10.16: Validator-set membership is required for production
            # release paths. When bridge_release_enabled is True, a missing set
            # or a non-member signature is a hard failure (fail-closed). Dev/test
            # networks with the release fence disabled still accept any valid
            # signature for backward compatibility.
            source_chain = proof.get("source_chain") or proof.get("chain_id")
            release_enabled = getattr(settings, "bridge_release_enabled", False)
            if source_chain:
                try:
                    vset = self.get_validator_set(source_chain)
                except Exception as e:
                    if release_enabled:
                        logger.warning(
                            "Validator set lookup failed for chain=%s (%s) with release enabled; rejecting proof",
                            source_chain,
                            e,
                        )
                        return False
                    # Validator set lookup may fail with mocked sessions or
                    # transient DB issues. Treat as unregistered for dev mode.
                    logger.debug(
                        "Validator set lookup failed for chain=%s (%s); treating as unregistered",
                        source_chain,
                        e,
                    )
                    vset = None
                if vset is not None:
                    validator_addresses = {
                        v.address.lower() if hasattr(v, "address") else str(v).lower() for v in vset.validators
                    }
                    if recovered.lower() not in validator_addresses:
                        logger.warning(
                            "Proposer signature recovered to %s which is NOT in the validator set for chain=%s",
                            recovered,
                            source_chain,
                        )
                        return False
                elif release_enabled:
                    logger.warning(
                        "No validator set registered for chain=%s and bridge_release_enabled=True; rejecting proof",
                        source_chain,
                    )
                    return False
                else:
                    logger.debug(
                        "No validator set registered for chain=%s — accepting any valid signature (dev mode)",
                        source_chain,
                    )

            return True
        except Exception as e:
            logger.warning("Proposer signature verification error: %s", e)
            return False

    def _verify_threshold_signatures(self, proof: dict[str, Any]) -> bool:
        """Verify proof signatures using M-of-N threshold (v0.7.1).

        When ``bridge_multisig_enabled`` is True, requires M-of-N validator
        signatures. When False, falls back to single-signer verification
        (backward-compatible with v0.7.0 proofs).
        """
        multisig_enabled = getattr(settings, "bridge_multisig_enabled", False)
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
        meets, count, valid = check_threshold(signers, vset, threshold)

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

    def _check_validator_set_freshness(self, chain_id: str) -> bool:
        """Check that the validator set for a chain is not stale (B6).

        Validates that the validator set's epoch is within the grace period.
        If the latest validator registration is older than the grace period
        and no newer epoch exists, the set is considered stale.
        """
        grace_period = getattr(settings, "bridge_validator_set_grace_period", 7200)
        now = datetime.now(UTC)

        with self._session_factory() as session:
            # Get the latest validator registration for this chain
            latest = session.exec(
                select(BridgeValidator)
                .where(BridgeValidator.chain_id == chain_id)
                .order_by(BridgeValidator.registered_at.desc())  # type: ignore[attr-defined]
                .limit(1)
            ).first()
            if latest is None:
                # No validators registered — fresh enough (will fail elsewhere)
                return True

            # Check if the registration is within the grace period
            # SQLite may return timezone-naive datetimes — normalize to UTC
            registered = latest.registered_at
            if registered.tzinfo is None:
                registered = registered.replace(tzinfo=UTC)
            age = now - registered
            if age > timedelta(seconds=grace_period):
                logger.warning(
                    "Validator set for chain=%s is stale (last registration %s ago, grace=%ss)",
                    chain_id,
                    age,
                    grace_period,
                )
                return False
            return True
