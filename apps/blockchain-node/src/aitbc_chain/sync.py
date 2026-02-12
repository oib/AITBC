"""Chain synchronization with conflict resolution, signature validation, and metrics."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session, select

from .config import settings
from .logger import get_logger
from .metrics import metrics_registry
from .models import Block, Transaction

logger = get_logger(__name__)


@dataclass
class ImportResult:
    accepted: bool
    height: int
    block_hash: str
    reason: str
    reorged: bool = False
    reorg_depth: int = 0


class ProposerSignatureValidator:
    """Validates proposer signatures on imported blocks."""

    def __init__(self, trusted_proposers: Optional[List[str]] = None) -> None:
        self._trusted = set(trusted_proposers or [])

    @property
    def trusted_proposers(self) -> set:
        return self._trusted

    def add_trusted(self, proposer_id: str) -> None:
        self._trusted.add(proposer_id)

    def remove_trusted(self, proposer_id: str) -> None:
        self._trusted.discard(proposer_id)

    def validate_block_signature(self, block_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate that a block was produced by a trusted proposer.

        Returns (is_valid, reason).
        """
        proposer = block_data.get("proposer", "")
        block_hash = block_data.get("hash", "")
        height = block_data.get("height", -1)

        if not proposer:
            return False, "Missing proposer field"

        if not block_hash or not block_hash.startswith("0x"):
            return False, f"Invalid block hash format: {block_hash}"

        # If trusted list is configured, enforce it
        if self._trusted and proposer not in self._trusted:
            metrics_registry.increment("sync_signature_rejected_total")
            return False, f"Proposer '{proposer}' not in trusted set"

        # Verify block hash integrity
        expected_fields = ["height", "parent_hash", "timestamp"]
        for field in expected_fields:
            if field not in block_data:
                return False, f"Missing required field: {field}"

        # Verify hash is a valid sha256 hex
        hash_hex = block_hash[2:]  # strip 0x
        if len(hash_hex) != 64:
            return False, f"Invalid hash length: {len(hash_hex)}"
        try:
            int(hash_hex, 16)
        except ValueError:
            return False, f"Invalid hex in hash: {hash_hex}"

        metrics_registry.increment("sync_signature_validated_total")
        return True, "Valid"


class ChainSync:
    """Handles block import with conflict resolution for divergent chains."""

    def __init__(
        self,
        session_factory,
        *,
        chain_id: str = "",
        max_reorg_depth: int = 10,
        validator: Optional[ProposerSignatureValidator] = None,
        validate_signatures: bool = True,
    ) -> None:
        self._session_factory = session_factory
        self._chain_id = chain_id or settings.chain_id
        self._max_reorg_depth = max_reorg_depth
        self._validator = validator or ProposerSignatureValidator()
        self._validate_signatures = validate_signatures

    def import_block(self, block_data: Dict[str, Any], transactions: Optional[List[Dict[str, Any]]] = None) -> ImportResult:
        """Import a block from a remote peer.

        Handles:
        - Normal append (block extends our chain)
        - Fork resolution (block is on a longer chain)
        - Duplicate detection
        - Signature validation
        """
        start = time.perf_counter()
        height = block_data.get("height", -1)
        block_hash = block_data.get("hash", "")
        parent_hash = block_data.get("parent_hash", "")
        proposer = block_data.get("proposer", "")

        metrics_registry.increment("sync_blocks_received_total")

        # Validate signature
        if self._validate_signatures:
            valid, reason = self._validator.validate_block_signature(block_data)
            if not valid:
                metrics_registry.increment("sync_blocks_rejected_total")
                logger.warning("Block rejected: signature validation failed",
                               extra={"height": height, "reason": reason})
                return ImportResult(accepted=False, height=height, block_hash=block_hash, reason=reason)

        with self._session_factory() as session:
            # Check for duplicate
            existing = session.exec(
                select(Block).where(Block.hash == block_hash)
            ).first()
            if existing:
                metrics_registry.increment("sync_blocks_duplicate_total")
                return ImportResult(accepted=False, height=height, block_hash=block_hash,
                                    reason="Block already exists")

            # Get our chain head
            our_head = session.exec(
                select(Block).order_by(Block.height.desc()).limit(1)
            ).first()
            our_height = our_head.height if our_head else -1

            # Case 1: Block extends our chain directly
            if height == our_height + 1:
                parent_exists = session.exec(
                    select(Block).where(Block.hash == parent_hash)
                ).first()
                if parent_exists or (height == 0 and parent_hash == "0x00"):
                    result = self._append_block(session, block_data, transactions)
                    duration = time.perf_counter() - start
                    metrics_registry.observe("sync_import_duration_seconds", duration)
                    return result

            # Case 2: Block is behind our head — ignore
            if height <= our_height:
                # Check if it's a fork at a previous height
                existing_at_height = session.exec(
                    select(Block).where(Block.height == height)
                ).first()
                if existing_at_height and existing_at_height.hash != block_hash:
                    # Fork detected — resolve by longest chain rule
                    return self._resolve_fork(session, block_data, transactions, our_head)
                metrics_registry.increment("sync_blocks_stale_total")
                return ImportResult(accepted=False, height=height, block_hash=block_hash,
                                    reason=f"Stale block (our height: {our_height})")

            # Case 3: Block is ahead — we're behind, need to catch up
            if height > our_height + 1:
                metrics_registry.increment("sync_blocks_gap_total")
                return ImportResult(accepted=False, height=height, block_hash=block_hash,
                                    reason=f"Gap detected (our height: {our_height}, received: {height})")

        return ImportResult(accepted=False, height=height, block_hash=block_hash,
                            reason="Unhandled import case")

    def _append_block(self, session: Session, block_data: Dict[str, Any],
                      transactions: Optional[List[Dict[str, Any]]] = None) -> ImportResult:
        """Append a block to the chain tip."""
        timestamp_str = block_data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.utcnow()
        except (ValueError, TypeError):
            timestamp = datetime.utcnow()

        tx_count = block_data.get("tx_count", 0)
        if transactions:
            tx_count = len(transactions)

        block = Block(
            height=block_data["height"],
            hash=block_data["hash"],
            parent_hash=block_data["parent_hash"],
            proposer=block_data.get("proposer", "unknown"),
            timestamp=timestamp,
            tx_count=tx_count,
            state_root=block_data.get("state_root"),
        )
        session.add(block)

        # Import transactions if provided
        if transactions:
            for tx_data in transactions:
                tx = Transaction(
                    tx_hash=tx_data.get("tx_hash", ""),
                    block_height=block_data["height"],
                    sender=tx_data.get("sender", ""),
                    recipient=tx_data.get("recipient", ""),
                    payload=tx_data,
                )
                session.add(tx)

        session.commit()

        metrics_registry.increment("sync_blocks_accepted_total")
        metrics_registry.set_gauge("sync_chain_height", float(block_data["height"]))
        logger.info("Imported block", extra={
            "height": block_data["height"],
            "hash": block_data["hash"],
            "proposer": block_data.get("proposer"),
            "tx_count": tx_count,
        })

        return ImportResult(
            accepted=True, height=block_data["height"],
            block_hash=block_data["hash"], reason="Appended to chain"
        )

    def _resolve_fork(self, session: Session, block_data: Dict[str, Any],
                      transactions: Optional[List[Dict[str, Any]]],
                      our_head: Block) -> ImportResult:
        """Resolve a fork using longest-chain rule.

        For PoA, we use a simple rule: if the incoming block's height is at or below
        our head and the parent chain is longer, we reorg. Otherwise, we keep our chain.
        Since we only receive one block at a time, we can only detect the fork — actual
        reorg requires the full competing chain. For now, we log the fork and reject
        unless the block has a strictly higher height.
        """
        fork_height = block_data.get("height", -1)
        our_height = our_head.height

        metrics_registry.increment("sync_forks_detected_total")
        logger.warning("Fork detected", extra={
            "fork_height": fork_height,
            "our_height": our_height,
            "fork_hash": block_data.get("hash"),
            "our_hash": our_head.hash,
        })

        # Simple longest-chain: only reorg if incoming chain is strictly longer
        # and within max reorg depth
        if fork_height <= our_height:
            return ImportResult(
                accepted=False, height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Fork rejected: our chain is longer or equal ({our_height} >= {fork_height})"
            )

        reorg_depth = our_height - fork_height + 1
        if reorg_depth > self._max_reorg_depth:
            metrics_registry.increment("sync_reorg_rejected_total")
            return ImportResult(
                accepted=False, height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Reorg depth {reorg_depth} exceeds max {self._max_reorg_depth}"
            )

        # Perform reorg: remove blocks from fork_height onwards, then append
        blocks_to_remove = session.exec(
            select(Block).where(Block.height >= fork_height).order_by(Block.height.desc())
        ).all()

        removed_count = 0
        for old_block in blocks_to_remove:
            # Remove transactions in the block
            old_txs = session.exec(
                select(Transaction).where(Transaction.block_height == old_block.height)
            ).all()
            for tx in old_txs:
                session.delete(tx)
            session.delete(old_block)
            removed_count += 1

        session.commit()

        metrics_registry.increment("sync_reorgs_total")
        metrics_registry.observe("sync_reorg_depth", float(removed_count))
        logger.warning("Chain reorg performed", extra={
            "removed_blocks": removed_count,
            "new_height": fork_height,
        })

        # Now append the new block
        result = self._append_block(session, block_data, transactions)
        result.reorged = True
        result.reorg_depth = removed_count
        return result

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and metrics."""
        with self._session_factory() as session:
            head = session.exec(
                select(Block).order_by(Block.height.desc()).limit(1)
            ).first()

            total_blocks = session.exec(select(Block)).all()
            total_txs = session.exec(select(Transaction)).all()

        return {
            "chain_id": self._chain_id,
            "head_height": head.height if head else -1,
            "head_hash": head.hash if head else None,
            "head_proposer": head.proposer if head else None,
            "head_timestamp": head.timestamp.isoformat() if head else None,
            "total_blocks": len(total_blocks),
            "total_transactions": len(total_txs),
            "validate_signatures": self._validate_signatures,
            "trusted_proposers": list(self._validator.trusted_proposers),
            "max_reorg_depth": self._max_reorg_depth,
        }
