"""Cross-chain bridge block header, Merkle proof, and finality verification."""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from aitbc.bridge import BridgeBlockHeader as SDKHeader, validate_block_header

from ..config import settings
from ..logger import get_logger
from ..models import BridgeBlockHeader
from ..state.merkle_patricia_trie import MerklePatriciaTrie
from .bridge_base import BridgeBase

logger = get_logger(__name__)


class BridgeFinalityMixin(BridgeBase):
    """Remote block header storage and cryptographic finality checks."""

    # ponytail: Protocol base declares the attributes the concrete CrossChainBridge sets.

    # v0.7.2 §B3-B6: Merkle proof, block header, finality, epoch tracking
    # ------------------------------------------------------------------

    def _get_block_header(self, chain_id: str, height: int) -> BridgeBlockHeader | None:
        """Look up a stored remote block header by chain_id + height (B2/B3)."""
        with self._session_for(chain_id) as session:
            return session.exec(
                select(BridgeBlockHeader).where(
                    BridgeBlockHeader.chain_id == chain_id,
                    BridgeBlockHeader.height == height,
                )
            ).first()

    def store_block_header(self, header_data: dict[str, Any]) -> BridgeBlockHeader:
        """Store or update a remote chain block header (B2/B4).

        Called by the RPC endpoint ``POST /bridge/block-headers`` or
        internally when a new block is learned from gossip/RPC.
        Updates confirmation counts for existing headers on the same chain.

        v0.10.16: When bridge_release_enabled is True, confirmation_count and
        finality_confirmed are derived from the verified chain (block height
        and subsequent confirmations) instead of trusting caller-supplied values.
        """
        chain_id = header_data["chain_id"]
        height = header_data["height"]
        release_enabled = getattr(settings, "bridge_release_enabled", False)
        with self._session_for(chain_id) as session:
            existing = session.exec(
                select(BridgeBlockHeader).where(
                    BridgeBlockHeader.chain_id == chain_id,
                    BridgeBlockHeader.height == height,
                )
            ).first()
            if existing:
                # Update fields
                existing.hash = header_data.get("hash", existing.hash)
                existing.parent_hash = header_data.get("parent_hash", existing.parent_hash)
                existing.proposer = header_data.get("proposer", existing.proposer)
                existing.state_root = header_data.get("state_root", existing.state_root)
                existing.signature = header_data.get("signature", existing.signature)
                # In production release paths, do not trust caller-supplied
                # confirmation/finality; derive them from stored chain data.
                if not release_enabled:
                    if "confirmation_count" in header_data:
                        existing.confirmation_count = int(header_data["confirmation_count"])
                    if "finality_confirmed" in header_data:
                        existing.finality_confirmed = bool(header_data["finality_confirmed"])
                session.add(existing)
                session.commit()
                session.refresh(existing)
                # Update finality status
                self._update_finality(chain_id, existing, session)
                return existing
            else:
                # New header starts with 0 confirmations in production; dev/test
                # networks with the release fence disabled may use caller values.
                confirmation_count = 0 if release_enabled else int(header_data.get("confirmation_count", 0))
                finality_confirmed = False if release_enabled else bool(header_data.get("finality_confirmed", False))
                header = BridgeBlockHeader(
                    chain_id=chain_id,
                    height=height,
                    hash=header_data["hash"],
                    parent_hash=header_data.get("parent_hash", "0x" + "00" * 32),
                    proposer=header_data["proposer"],
                    state_root=header_data["state_root"],
                    signature=header_data.get("signature", ""),
                    confirmation_count=confirmation_count,
                    finality_confirmed=finality_confirmed,
                )
                session.add(header)
                session.commit()
                session.refresh(header)
                # Update confirmation counts for all headers on this chain
                self._increment_confirmations(chain_id, height, session)
                self._update_finality(chain_id, header, session)
                return header

    def _increment_confirmations(self, chain_id: str, new_height: int, session: Any) -> None:
        """Increment confirmation counts for all earlier blocks on a chain (B5).

        When a new block at height H is stored, all existing blocks at
        height < H get their confirmation_count incremented by 1. Finality is
        derived from the updated confirmation count rather than caller input.
        """
        earlier = session.exec(
            select(BridgeBlockHeader).where(
                BridgeBlockHeader.chain_id == chain_id,
                BridgeBlockHeader.height < new_height,
            )
        ).all()
        for h in earlier:
            h.confirmation_count += 1
            session.add(h)
            self._update_finality(chain_id, h, session, commit=False)
        if earlier:
            session.commit()

    def _update_finality(self, chain_id: str, header: BridgeBlockHeader, session: Any, commit: bool = True) -> None:
        """Update finality_confirmed flag based on confirmation count (B5)."""
        finality_blocks = getattr(settings, "bridge_finality_blocks", 6)
        if header.confirmation_count >= finality_blocks and not header.finality_confirmed:
            header.finality_confirmed = True
            session.add(header)
            if commit:
                session.commit()

    def _verify_block_header_signature(self, header: BridgeBlockHeader) -> bool:
        """Verify a block header's proposer signature (B4).

        Uses ``aitbc.bridge.verification.validate_block_header`` with the
        v0.7.1 validator set for membership checking. If no validator set
        is registered for the chain, only signature validity is checked
        (not membership). If the header has no signature, it's accepted
        only when ``bridge_block_signature_required`` is False.
        """
        sig_required = getattr(settings, "bridge_block_signature_required", True)
        if not header.signature:
            if sig_required:
                logger.warning("Block header has no signature and signatures are required")
                return False
            return True  # legacy mode — no signature required

        sdk_header = SDKHeader(
            chain_id=header.chain_id,
            height=header.height,
            hash=header.hash,
            parent_hash=header.parent_hash,
            proposer=header.proposer,
            state_root=header.state_root,
            signature=header.signature,
        )

        # v0.10.16: Validator-set membership is required for production release
        # paths. When bridge_release_enabled is True, a missing set is a hard
        # failure; otherwise only signature validity is checked.
        release_enabled = getattr(settings, "bridge_release_enabled", False)
        try:
            vset = self.get_validator_set(header.chain_id)
        except Exception as e:
            if release_enabled:
                logger.warning(
                    "Validator set lookup failed for chain=%s (%s) with release enabled; rejecting header",
                    header.chain_id,
                    e,
                )
                return False
            vset = None

        if release_enabled and vset is None:
            logger.warning(
                "No validator set registered for chain=%s and bridge_release_enabled=True; rejecting header",
                header.chain_id,
            )
            return False

        valid, error, _recovered = validate_block_header(sdk_header, vset)
        if not valid:
            logger.warning("Block header signature invalid: %s", error)
            return False
        return True

    def _verify_merkle_proof(self, state_root: str, proof: dict[str, Any]) -> bool:
        """Verify a Merkle proof against a state root (B3).

        Uses the Merkle Patricia Trie's ``verify_proof`` method via a
        wrapper that sets the expected root hash. The proof must include:
        - ``merkle_proof``: list of hex-encoded trie nodes
        - ``lock_tx_hash``: the key whose inclusion is being proven
        - ``lock_event``: the expected value at that key
        """
        merkle_proof = proof.get("merkle_proof", [])
        lock_key = proof.get("lock_tx_hash", "")
        lock_value = proof.get("lock_event", "")

        if not merkle_proof or not lock_key:
            logger.warning("Merkle proof missing required fields (merkle_proof, lock_tx_hash)")
            return False

        try:
            # Convert proof elements to bytes
            proof_bytes = []
            for p in merkle_proof:
                if isinstance(p, bytes):
                    proof_bytes.append(p)
                elif isinstance(p, str):
                    proof_bytes.append(bytes.fromhex(p.removeprefix("0x")))
                else:
                    logger.warning("Invalid merkle proof element type: %s", type(p))
                    return False

            # Use the Merkle Patricia Trie to verify
            trie = MerklePatriciaTrie()
            # The verify_proof method uses self.get_root() as the expected hash.
            # We need to verify against the remote state_root, so we patch
            # get_root to return the expected state root.
            state_root_bytes = bytes.fromhex(state_root.removeprefix("0x"))

            # Monkey-patch get_root to return the expected state root
            trie.get_root = lambda: state_root_bytes  # type: ignore[method-assign]

            key_bytes = lock_key.encode() if isinstance(lock_key, str) else lock_key
            value_bytes = lock_value.encode() if isinstance(lock_value, str) else lock_value

            return trie.verify_proof(key_bytes, value_bytes, proof_bytes)
        except Exception as e:
            logger.warning("Merkle proof verification error: %s", e)
            return False

    def _check_finality_for_transfer(self, header: BridgeBlockHeader, amount: int) -> bool:
        """Check if a block header has sufficient finality for a transfer (B5).

        Large transfers (>= bridge_large_transfer_threshold) require full
        finality (bridge_finality_blocks confirmations). Small transfers
        require only bridge_min_confirmations.
        """
        min_confirmations = getattr(settings, "bridge_min_confirmations", 3)
        finality_blocks = getattr(settings, "bridge_finality_blocks", 6)
        large_threshold = getattr(settings, "bridge_large_transfer_threshold", 10000)

        required = finality_blocks if amount >= large_threshold else min_confirmations
        if header.confirmation_count < required:
            logger.warning(
                "Insufficient finality: %d/%d confirmations (amount=%s, threshold=%s)",
                header.confirmation_count,
                required,
                amount,
                large_threshold,
            )
            return False
        return True

    def get_block_header_status(self, chain_id: str, height: int) -> dict[str, Any] | None:
        """Get a block header with finality status (B5 RPC helper)."""
        header = self._get_block_header(chain_id, height)
        if header is None:
            return None
        return {
            "chain_id": header.chain_id,
            "height": header.height,
            "hash": header.hash,
            "parent_hash": header.parent_hash,
            "proposer": header.proposer,
            "state_root": header.state_root,
            "signature": header.signature,
            "timestamp": header.timestamp.isoformat() if header.timestamp else None,
            "finality_confirmed": header.finality_confirmed,
            "confirmation_count": header.confirmation_count,
        }

    def get_oracle_status(self) -> dict[str, Any]:
        """Get bridge oracle/verification status (B7 RPC helper)."""
        # Count block headers per chain
        with self._session_for() as session:
            all_headers = session.exec(select(BridgeBlockHeader)).all()
            chain_counts: dict[str, int] = {}
            for h in all_headers:
                chain_counts[h.chain_id] = chain_counts.get(h.chain_id, 0) + 1
            finalized = sum(1 for h in all_headers if h.finality_confirmed)

        return {
            "verification_mode": getattr(settings, "bridge_verification_mode", "in_process"),
            "min_confirmations": getattr(settings, "bridge_min_confirmations", 3),
            "finality_blocks": getattr(settings, "bridge_finality_blocks", 6),
            "large_transfer_threshold": getattr(settings, "bridge_large_transfer_threshold", 10000),
            "block_headers_total": len(all_headers),
            "block_headers_finalized": finalized,
            "block_headers_per_chain": chain_counts,
            "release_enabled": getattr(settings, "bridge_release_enabled", False),
            "multisig_enabled": getattr(settings, "bridge_multisig_enabled", False),
        }
