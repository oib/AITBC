"""Single block import, append, and fork resolution."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from aitbc.parallel import DependencyGraph, ParallelExecutor

from .base_models import Account, Block, _to_ait_address
from .base_models import Transaction as ChainTransaction
from .config import settings
from .logger import get_logger
from .metrics import metrics_registry
from .state import state_root_utils
from .state.pure_state_transition import (
    StateDelta,
    apply_delta_to_map,
    apply_deltas_to_db,
    compute_state_delta,
    extract_read_write_sets,
)
from .state.state_transition import get_state_transition
from .mempool import compute_tx_hash
from .sync_base import SyncBase
from .sync_validator import ImportResult

logger = get_logger(__name__)


class BlockImportMixin(SyncBase):
    """Import a single block, append it, and resolve chain forks."""

    # ponytail: Protocol base declares the attributes the concrete ChainSync sets.

    def import_block(
        self,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        skip_state_root_validation: bool = False,
    ) -> ImportResult:
        """Import a block from a remote peer.

        Handles:
        - Normal append (block extends our chain)
        - Fork resolution (block is on a longer chain)
        - Duplicate detection
        - Signature validation

        Args:
            block_data: Block data dictionary
            transactions: Optional list of transactions
            skip_state_root_validation: Skip state root validation (for bulk import)
        """
        start = time.perf_counter()
        height = block_data.get("height", -1)
        block_hash = block_data.get("hash", "")
        if transactions is None:
            transactions = block_data.get("transactions") or []
        parent_hash = block_data.get("parent_hash", "")
        metrics_registry.increment("sync_blocks_received_total")
        if self._validate_signatures:
            valid, reason = self._validator.validate_block_signature(block_data)
            if not valid:
                metrics_registry.increment("sync_blocks_rejected_total")
                logger.warning("Block rejected: signature validation failed", extra={"height": height, "reason": reason})
                return ImportResult(accepted=False, height=height, block_hash=block_hash, reason=reason)
        # The in-memory replay cache must be scoped to one block. A rejected
        # block is rolled back, but if the cache is not cleared the next import
        # attempt reports "replay attack" for transactions that were never
        # actually persisted.
        get_state_transition().reset_processed_cache()
        with self._session_factory() as session:
            if height == 0 and block_data.get("block_metadata"):
                is_valid, reason = self._validate_genesis_metadata(block_data, session)
                if not is_valid:
                    metrics_registry.increment("sync_state_root_rejected_total")
                    logger.error(
                        "Genesis block metadata validation failed: %s", reason, extra={"height": height, "hash": block_hash}
                    )
                    return ImportResult(accepted=False, height=height, block_hash=block_hash, reason=reason)
            existing = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == block_hash)
            ).first()
            if existing:
                metrics_registry.increment("sync_blocks_duplicate_total")
                return ImportResult(accepted=False, height=height, block_hash=block_hash, reason="Block already exists")
            our_head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(text("height DESC")).limit(1)
            ).first()
            our_height = our_head.height if our_head else -1
            gap = height - our_height
            logger.info(
                "Import block check: remote height=%s, local height=%s (gap=%s), parent=%s, block=%s",
                height,
                our_height,
                gap,
                parent_hash,
                block_hash,
            )
            if height == our_height + 1:
                parent_exists = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
                ).first()
                if parent_exists or (height == 0 and parent_hash == "0x00"):
                    result = self._append_block(session, block_data, transactions, skip_state_root_validation)
                    duration = time.perf_counter() - start
                    metrics_registry.observe("sync_import_duration_seconds", duration)
                    return result
                # Peer is one height ahead but the parent is not our tip: a fork
                # where the peer is *ahead* of us. `_resolve_fork` only runs when
                # height <= our_height, so this used to fall through to
                # "Unhandled import case" and stall catch-up forever (V23-90).
                metrics_registry.increment("sync_divergence_rejected_total")
                our_hash = our_head.hash if our_head else ""
                return ImportResult(
                    accepted=False,
                    height=height,
                    block_hash=block_hash,
                    reason=(
                        f"Divergent chain: next block parent {parent_hash[:16]}... "
                        f"is not our head {our_hash[:16]}... at height {our_height}"
                    ),
                    diverged=True,
                )
            if height <= our_height:
                existing_at_height = session.exec(
                    select(Block).where(Block.chain_id == self._chain_id).where(Block.height == height)
                ).first()
                if existing_at_height and existing_at_height.hash != block_hash:
                    if our_head:
                        return self._resolve_fork(session, block_data, transactions, our_head)
                metrics_registry.increment("sync_blocks_stale_total")
                return ImportResult(
                    accepted=False, height=height, block_hash=block_hash, reason=f"Stale block (our height: {our_height})"
                )
            if height > our_height + 1:
                metrics_registry.increment("sync_blocks_gap_total")
                return ImportResult(
                    accepted=False,
                    height=height,
                    block_hash=block_hash,
                    reason=f"Gap detected (our height: {our_height}, received: {height})",
                )
        return ImportResult(accepted=False, height=height, block_hash=block_hash, reason="Unhandled import case")

    def _append_block(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None = None,
        skip_state_root_validation: bool = False,
    ) -> ImportResult:
        """Append a block to the chain tip.

        Args:
            session: Database session
            block_data: Block data dictionary
            transactions: Optional list of transactions
            skip_state_root_validation: Skip state root validation (for bulk import)
        """
        from datetime import UTC, datetime

        block_hash = block_data["hash"]

        # Normalize transaction data from blocks-range (Transaction model dumps use
        # sender/recipient/value/tx_hash) to the signed transaction shape the state
        # transition expects (from/to/amount/fee/nonce/type/chain_id/signature/payload).
        if transactions:
            normalized = []
            for raw_tx in transactions:
                norm = dict(raw_tx)
                if "from" not in norm and "sender" in norm:
                    norm["from"] = norm["sender"]
                if "to" not in norm and "recipient" in norm:
                    norm["to"] = norm["recipient"]
                if "amount" not in norm and "value" in norm:
                    norm["amount"] = norm["value"]
                if "signature" not in norm:
                    norm["signature"] = ""
                if "chain_id" not in norm:
                    norm["chain_id"] = self._chain_id
                # Block broadcasts from the proposer carry the raw signed
                # transaction content and do not include the pre-computed
                # tx_hash.  Recompute it here so every downstream path
                # (parallel/sequential, state transition, Transaction record)
                # uses a consistent, non-empty hash.
                if not norm.get("tx_hash"):
                    norm["tx_hash"] = compute_tx_hash(norm)
                normalized.append(norm)
            transactions = normalized

        timestamp_str = block_data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now(UTC)
        except (ValueError, TypeError):
            timestamp = datetime.now(UTC)
        tx_count = block_data.get("tx_count", 0)
        if transactions:
            tx_count = len(transactions)
        block = Block(
            chain_id=self._chain_id,
            height=block_data["height"],
            hash=block_data["hash"],
            parent_hash=block_data["parent_hash"],
            proposer=block_data.get("proposer", "unknown"),
            timestamp=timestamp,
            tx_count=tx_count,
            state_root=block_data.get("state_root"),
            # Persist the signature this block was just validated against. Dropping
            # it made the check single-use: the block verified once on the way in and
            # was then stored unsigned, so this node could never re-serve proof of who
            # proposed it. One sync hop stripped authorship from the whole chain.
            signature=block_data.get("signature", ""),
            block_metadata=block_data.get("block_metadata"),
        )
        session.add(block)
        if transactions:
            # Parallel transaction validation path (v0.6.1).
            # When enabled and the conflict rate is low enough, transactions are
            # partitioned into conflict-free groups and their state deltas are
            # computed in parallel using pure functions (no DB access). Deltas are
            # applied to an in-memory account_map in tx-index order (deterministic)
            # so the resulting state root matches the sequential path exactly.
            parallel_applied = False
            if settings.parallel_tx_validation:
                # Build dependency graph from read/write sets.
                graph = DependencyGraph()
                tx_hash_to_data: dict[str, dict[str, Any]] = {}
                tx_hash_to_index: dict[str, int] = {}
                for idx, tx_data in enumerate(transactions):
                    tx_hash = tx_data.get("tx_hash", "")
                    tx_hash_to_data[tx_hash] = tx_data
                    tx_hash_to_index[tx_hash] = idx
                    read_set, write_set = extract_read_write_sets(tx_data)
                    graph.add_transaction(tx_hash, read_set, write_set, index=idx)
                groups = graph.get_conflict_groups()
                # Fall back to sequential if too many transactions conflict.
                if groups and graph.conflict_rate() <= settings.conflict_threshold:
                    # Batch-fetch all sender/recipient accounts into account_map.
                    unique_addresses: set[str] = set()
                    for tx_data in transactions:
                        sender_addr = _to_ait_address(tx_data.get("from", ""))
                        recipient_addr = _to_ait_address(tx_data.get("to", ""))
                        if sender_addr:
                            unique_addresses.add(sender_addr)
                        if recipient_addr:
                            unique_addresses.add(recipient_addr)
                    account_map: dict[str, Account] = {}
                    if unique_addresses:
                        existing_accounts = session.exec(
                            select(Account).where(
                                Account.chain_id == self._chain_id,
                                Account.address.in_(unique_addresses),  # type: ignore[attr-defined]
                            )
                        ).all()
                        account_map = {acc.address: acc for acc in existing_accounts}
                    # Batch-fetch tx hashes already in the DB (duplicate detection).
                    existing_tx_hashes: set[str] = set()
                    all_tx_hashes = [tx_data.get("tx_hash", "") for tx_data in transactions]
                    if all_tx_hashes:
                        existing_rows = session.exec(
                            select(ChainTransaction.tx_hash).where(
                                ChainTransaction.chain_id == self._chain_id,
                                ChainTransaction.tx_hash.in_(all_tx_hashes),  # type: ignore[attr-defined]
                            )
                        ).all()
                        existing_tx_hashes = set(existing_rows)
                    # Execute groups sequentially; within each group, deltas are
                    # computed in parallel (group members are conflict-free).
                    executor = ParallelExecutor(max_workers=settings.parallel_workers)
                    all_deltas: list[StateDelta] = []
                    try:

                        def _compute_delta(tx_data: dict[str, Any]) -> StateDelta:
                            txh = tx_data.get("tx_hash", "")
                            return compute_state_delta(account_map, tx_data, self._chain_id, txh, existing_tx_hashes)

                        for group in groups:
                            # Update nonces from account_map before processing each group
                            # (conflicting txs in later groups need updated nonces)
                            for txh in group:
                                tx_data = tx_hash_to_data[txh]
                                sender = _to_ait_address(tx_data.get("from", ""))
                                sender_account = account_map.get(sender)
                                if sender_account:
                                    tx_data["nonce"] = sender_account.nonce
                                    tx_data["value"] = tx_data.get("amount", 0)
                            group_txs = [tx_hash_to_data[txh] for txh in group]
                            group_results = executor.execute_groups([group_txs], _compute_delta)[0]
                            # Apply successful deltas to account_map in tx-index
                            # order within the group (deterministic). Group members
                            # are conflict-free so application order does not affect
                            # the final state, but we keep index order for safety.
                            group_results_sorted = sorted(group_results, key=lambda d: tx_hash_to_index.get(d.tx_hash, 0))
                            for delta in group_results_sorted:
                                if delta.success:
                                    apply_delta_to_map(account_map, delta, self._chain_id)
                                    existing_tx_hashes.add(delta.tx_hash)
                            all_deltas.extend(group_results_sorted)
                    finally:
                        executor.close()
                    # Collect successful deltas in tx-index order (deterministic).
                    successful_deltas = sorted(
                        [d for d in all_deltas if d.success],
                        key=lambda d: tx_hash_to_index.get(d.tx_hash, 0),
                    )
                    # Batch-write all deltas to the DB.
                    apply_deltas_to_db(session, successful_deltas, self._chain_id)
                    # Create Transaction records for all successful txs.
                    for delta in successful_deltas:
                        tx_data = tx_hash_to_data.get(delta.tx_hash, {})
                        db_tx = ChainTransaction(
                            chain_id=self._chain_id,
                            tx_hash=delta.tx_hash,
                            block_height=block_data["height"],
                            # Raw, not the canonicalised delta: these are signed (V23-65).
                            sender=tx_data.get("from", delta.sender),
                            recipient=tx_data.get("to", delta.recipient),
                            payload=tx_data.get("payload", {}),
                            type=delta.tx_type,
                            value=tx_data.get("value", tx_data.get("amount", 0)),
                            fee=tx_data.get("fee", 0),
                            nonce=tx_data.get("nonce", 0),
                            status="confirmed",
                        )
                        session.add(db_tx)
                    # Log failed transactions.
                    for delta in all_deltas:
                        if not delta.success:
                            logger.warning("[SYNC] Failed to apply transaction %s: %s", delta.tx_hash, delta.error)
                    parallel_applied = True
            if not parallel_applied:
                # Sequential path (fallback when parallel_tx_validation is off
                # or the conflict rate exceeds the threshold).
                for tx_data in transactions:
                    sender_addr = _to_ait_address(tx_data.get("from", ""))
                    recipient_addr = _to_ait_address(tx_data.get("to", ""))
                    int(tx_data.get("amount", 0) or 0)
                    int(tx_data.get("fee", 0) or 0)
                    tx_hash = tx_data.get("tx_hash", "")
                    sender_acct = session.get(Account, (self._chain_id, sender_addr))
                    if sender_acct is None:
                        sender_acct = Account(chain_id=self._chain_id, address=sender_addr, balance=0, nonce=0)
                        session.add(sender_acct)
                        session.flush()
                    recipient_acct = session.get(Account, (self._chain_id, recipient_addr))
                    if recipient_acct is None:
                        recipient_acct = Account(chain_id=self._chain_id, address=recipient_addr, balance=0, nonce=0)
                        session.add(recipient_acct)
                        session.flush()
                    state_transition = get_state_transition()
                    success, error_msg = state_transition.apply_transaction(session, self._chain_id, tx_data, tx_hash)
                    if not success:
                        logger.warning("[SYNC] Failed to apply transaction %s: %s", tx_hash, error_msg)
                    tx_type = tx_data.get("type", "TRANSFER")
                    if tx_type:
                        tx_type = tx_type.upper()
                    else:
                        tx_type = "TRANSFER"
                    db_tx = ChainTransaction(
                        chain_id=self._chain_id,
                        tx_hash=tx_hash,
                        block_height=block_data["height"],
                        # Raw, not the canonicalised locals: these are signed (V23-65).
                        sender=tx_data.get("from", sender_addr),
                        recipient=tx_data.get("to", recipient_addr),
                        payload=tx_data.get("payload", {}),
                        type=tx_type,
                        value=tx_data.get("value", tx_data.get("amount", 0)),
                        fee=tx_data.get("fee", 0),
                        nonce=tx_data.get("nonce", 0),
                        status="confirmed",
                    )
                    session.add(db_tx)
        if block_data.get("state_root") and (not skip_state_root_validation):
            session.flush()
            # Compute state root from the full account state. The previous
            # "incremental" approach created a fresh trie per call but only
            # populated it with accounts touched in this block — producing an
            # empty trie (root=0x00..00) for blocks with no transactions and a
            # wrong root for blocks with transactions. Since the trie is not
            # persisted across blocks, a full recompute is the only correct option.
            computed_hex = state_root_utils.compute_state_root_full(session, self._chain_id)
            computed_root = bytes.fromhex(computed_hex.replace("0x", "")) if computed_hex else None
            try:
                expected_root = bytes.fromhex(str(block_data.get("state_root")).replace("0x", ""))
            except ValueError:
                expected_root = None
            if expected_root is None or len(expected_root) != 32:
                metrics_registry.increment("sync_state_root_rejected_total")
                session.rollback()
                self._track_rejection(self._chain_id)
                logger.error(
                    "[SYNC] Invalid state root at height %s: %s - BLOCK REJECTED",
                    block_data["height"],
                    block_data.get("state_root"),
                )
                self._check_and_trigger_resync(self._chain_id)
                return ImportResult(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_hash,
                    reason=f"Invalid state root: {block_data.get('state_root')}",
                )
            elif computed_root != expected_root:
                metrics_registry.increment("sync_state_root_rejected_total")
                session.rollback()
                self._track_rejection(self._chain_id)
                logger.error(
                    "[SYNC] State root mismatch at height %s: expected %s, computed %s - BLOCK REJECTED",
                    block_data["height"],
                    expected_root.hex(),
                    computed_root.hex(),  # type: ignore[union-attr]
                )
                self._check_and_trigger_resync(self._chain_id)
                return ImportResult(
                    accepted=False,
                    height=block_data["height"],
                    block_hash=block_hash,
                    reason=f"State root mismatch: expected {expected_root.hex()}, computed {computed_root.hex()}",  # type: ignore[union-attr]
                )
        session.commit()
        self._reset_rejection_counter(self._chain_id)
        metrics_registry.increment("sync_blocks_accepted_total")
        metrics_registry.set_gauge("sync_chain_height", float(block_data["height"]))
        logger.info(
            "Imported block",
            extra={
                "height": block_data["height"],
                "hash": block_data["hash"],
                "proposer": block_data.get("proposer"),
                "tx_count": tx_count,
            },
        )
        return ImportResult(
            accepted=True, height=block_data["height"], block_hash=block_data["hash"], reason="Appended to chain"
        )

    def _resolve_fork(
        self, session: Session, block_data: dict[str, Any], transactions: list[dict[str, Any]] | None, our_head: Block
    ) -> ImportResult:
        """Resolve a fork using longest-chain rule.

        For PoA, we use a simple rule: if the incoming block's height is at or below
        our head and the parent chain is longer, we reorg. Otherwise, we keep our chain.
        Since we only receive one block at a time, we can only detect the fork — actual
        reorg requires the full competing chain. For now, we log the fork and reject
        unless the block has a strictly higher height.
        """
        fork_height = block_data.get("height", -1)
        our_height = our_head.height
        fork_chain_id = block_data.get("chain_id", "")
        fork_hash = block_data.get("hash", "")
        our_hash = our_head.hash if our_head else ""
        metrics_registry.increment("sync_forks_detected_total")
        logger.warning(
            "Fork detected at height %s (our height: %s, fork hash: %s..., our hash: %s...)",
            fork_height,
            our_height,
            fork_hash[:16],
            our_hash[:16],
            extra={
                "fork_height": fork_height,
                "our_height": our_height,
                "fork_hash": fork_hash,
                "our_hash": our_hash,
                "fork_chain_id": fork_chain_id,
                "our_chain_id": self._chain_id,
            },
        )
        if fork_chain_id and fork_chain_id != self._chain_id:
            return ImportResult(
                accepted=False,
                height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Incompatible chain: block from chain '{fork_chain_id}' does not match our chain '{self._chain_id}' (heights: {fork_height} vs {our_height})",
            )
        if fork_height <= our_height:
            # This is the only path out of _resolve_fork that production reaches: import_block
            # calls it solely when `height <= our_height`, so the reorg code below is unreachable
            # (V23-90). The rejection is permanent until an operator resolves it, which is what
            # `diverged` tells the caller — the old reason said "our chain is longer", which reads
            # like a healthy outcome and hid a 46-hour outage.
            metrics_registry.increment("sync_divergence_rejected_total")
            return ImportResult(
                accepted=False,
                height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=(
                    f"Divergent chain: we hold a different block at height {fork_height} "
                    f"(ours {our_hash[:16]}..., peer {fork_hash[:16]}...); our head is {our_height}"
                ),
                diverged=True,
            )
        reorg_depth = our_height - fork_height + 1
        if reorg_depth > self._max_reorg_depth:
            metrics_registry.increment("sync_reorg_rejected_total")
            return ImportResult(
                accepted=False,
                height=fork_height,
                block_hash=block_data.get("hash", ""),
                reason=f"Reorg depth {reorg_depth} exceeds max {self._max_reorg_depth}",
            )
        blocks_to_remove = session.exec(
            select(Block)
            .where(Block.chain_id == self._chain_id)
            .where(Block.height >= fork_height)
            .order_by(text("height DESC"))
        ).all()
        removed_count = 0
        for old_block in blocks_to_remove:
            old_txs = session.exec(
                select(ChainTransaction)
                .where(ChainTransaction.chain_id == self._chain_id)
                .where(ChainTransaction.block_height == old_block.height)
            ).all()
            for tx in old_txs:
                session.delete(tx)
            session.delete(old_block)
            removed_count += 1
        session.commit()
        metrics_registry.increment("sync_reorgs_total")
        metrics_registry.observe("sync_reorg_depth", float(removed_count))
        logger.warning("Chain reorg performed", extra={"removed_blocks": removed_count, "new_height": fork_height})
        result = self._append_block(session, block_data, transactions)
        result.reorged = True
        result.reorg_depth = removed_count
        return result

    def get_sync_status(self) -> dict[str, Any]:
        """Get current sync status and metrics."""
        with self._session_factory() as session:
            head = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).order_by(text("height DESC")).limit(1)
            ).first()
            total_blocks = session.exec(select(Block).where(Block.chain_id == self._chain_id)).all()
            total_txs = session.exec(select(ChainTransaction).where(ChainTransaction.chain_id == self._chain_id)).all()
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
