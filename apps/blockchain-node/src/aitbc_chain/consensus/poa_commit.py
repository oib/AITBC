"""Header signing/hashing, bridge state root, and block commit for ``PoAProposer`` (poa split).

Import ``aitbc_chain.consensus.poa`` first (it wires these
mixins into ``PoAProposer``); this module is not meant to be imported
directly."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .block_hash import compute_block_hash
from .poa import _PoaBaseMixin, _active_consensus_domain, _sanitize_metric_suffix, _sign_consensus

from ..config import settings
from ..cross_chain.bridge_leaf import lock_leaf_value, unknown_lock_leaf
from ..metrics import block_height, metrics_registry
from ..models import Block, CrossChainTransfer
from ..state import side_root_shadow
from ..state.block_deltas import BlockDeltaJournal
from ..state.state_transition import get_block_version
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


class _CommitMixin(_PoaBaseMixin):
    def _empty_bridge_root(self) -> str:
        """Return the bridge event trie root for a block with no lock events."""
        from ..state.merkle_patricia_trie import MerklePatriciaTrie

        return "0x" + MerklePatriciaTrie().get_root().hex()

    def _sign_block_hash_for(self, proposer: str, block: Block) -> str:
        """Sign the canonical block header with the private key of the given proposer."""
        private_key = self._validator_keys.get(proposer) or getattr(settings, "proposer_key", None)
        if not private_key:
            self._logger.debug("No private key for proposer %s; block signature omitted", proposer)
            return ""
        try:
            from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_PROPOSAL

            domain = _active_consensus_domain(block.height, DOMAIN_BLOCK_PROPOSAL)
            return _sign_consensus(self._block_header_message(block), private_key, domain)
        except (ImportError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            self._logger.warning("Failed to sign block header for %s: %s", proposer, e)
            return ""

    def _commit_and_record_block(
        self,
        session: Session,
        block: Block,
        proposer: str,
        interval_seconds: float | None,
        timestamp: datetime,
    ) -> None:
        """Commit the signed block and update caches, metrics and proposer state."""
        session.add(block)
        journal = BlockDeltaJournal.get(session)
        if journal is not None:
            journal.persist(session)
        try:
            session.commit()
        except (SQLAlchemyError, OSError) as exc:
            # #1740: a disk-full/I/O-error commit leaves quick_check green —
            # quarantine on the error shape so import/propose/attest all
            # refuse instead of the proposer retrying into a dead disk.
            from ..database import quarantine_chain_db_for_error

            if quarantine_chain_db_for_error(self._config.chain_id, exc, session=session) is not None:
                session.rollback()
                self._logger.error(
                    "[PROPOSE] chain.db quarantined during block commit on chain %s",
                    self._config.chain_id,
                )
            raise
        # V-3 shadow (flag-gated, compare-only — never affects the sealed block).
        side_root_shadow.on_block_sealed(
            session, self._config.chain_id, block.height, block_version=get_block_version(block, block.height)
        )
        # Invalidate the in-process block header cache for the new block
        # so stale entries are not served by rpc/blocks.py.
        from ..block_cache import get_block_header_cache

        get_block_header_cache().invalidate(self._config.chain_id, height=block.height, hash=block.hash)
        metrics_registry.increment("blocks_proposed_total")
        metrics_registry.set_gauge("chain_head_height", float(block.height))
        if interval_seconds is not None and interval_seconds >= 0:
            metrics_registry.observe("block_interval_seconds", interval_seconds)
            metrics_registry.set_gauge("poa_last_block_interval_seconds", float(interval_seconds))
        proposer_suffix = _sanitize_metric_suffix(proposer)
        metrics_registry.increment(f"poa_blocks_proposed_total_{proposer_suffix}")
        if self._last_proposer_id is not None and self._last_proposer_id != proposer:
            metrics_registry.increment("poa_proposer_switches_total")
        self._last_proposer_id = proposer
        self._last_block_timestamp = timestamp
        block_height.set(block.height)
        self._logger.info("Proposed block", extra={"height": block.height, "hash": block.hash, "proposer": block.proposer})

    def _compute_bridge_state_root(
        self, session: Session, processed_txs: list[Any], chain_id: str, height: int | None = None
    ) -> str:
        """Build a Merkle trie from the BRIDGE_LOCK events in this block.

        The trie key is the lock transfer ID and the value is the canonical
        lock event string. The root hash becomes ``block.bridge_state_root``
        and is used by bridge proofs to prove inclusion of a lock.
        """
        # #1940 F5: in the tx-derived bridge-root era the trie is built
        # purely from the successfully processed transaction bodies — the
        # authoritative tx.tx_hash is the key and no CrossChainTransfer
        # record is consulted (absent or stale rows cannot diverge it).
        from ..cross_chain.bridge_tx_root import build_tx_bridge_trie, tx_only_root_active

        if height is not None and tx_only_root_active(session, chain_id, height):
            bodies = []
            for tx in processed_txs:
                content = tx.content if isinstance(tx.content, dict) else {}
                body = dict(content)
                body["tx_hash"] = tx.tx_hash
                bodies.append(body)
            trie = build_tx_bridge_trie(bodies, chain_id, height)
            return "0x" + trie.get_root().hex()

        from ..state.merkle_patricia_trie import MerklePatriciaTrie

        trie = MerklePatriciaTrie()
        lock_txs = [tx for tx in processed_txs if (tx.content or {}).get("type", "").upper() == "BRIDGE_LOCK"]
        if not lock_txs:
            return "0x" + trie.get_root().hex()
        transfer_ids = [tx.tx_hash for tx in lock_txs]
        records = session.exec(
            select(CrossChainTransfer).where(
                CrossChainTransfer.source_chain == chain_id,
                CrossChainTransfer.transfer_id.in_(transfer_ids),  # type: ignore[attr-defined]
            )
        ).all()
        record_map = {r.transfer_id: r for r in records}
        for tx in lock_txs:
            record = record_map.get(tx.tx_hash)
            if record is None:
                value = unknown_lock_leaf(tx.tx_hash)
            else:
                value = lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, height)
            trie.put(tx.tx_hash.encode(), value.encode())
        return "0x" + trie.get_root().hex()

    def _block_header_message(self, block: Block) -> dict[str, Any]:
        """Canonical header message that the bridge verifier signs/verifies."""
        return {
            "chain_id": block.chain_id,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash,
            "proposer": block.proposer,
            "state_root": block.state_root or "",
            "bridge_state_root": block.bridge_state_root or "",
        }

    def _compute_block_hash(
        self,
        height: int,
        parent_hash: str,
        timestamp: datetime,
        transactions: list[Any] | None = None,
        proposer: str = "",
        state_root: str | None = None,
        bridge_state_root: str | None = None,
        aux_state_root: str | None = None,
    ) -> str:
        tx_hashes = []
        if transactions:
            tx_hashes = [tx.tx_hash for tx in transactions]
        # v0.7.2: block hash binds the state roots and proposer so that bridge
        # proofs can be anchored to a signed block header. The formula lives
        # in consensus.block_hash so remote attesters recompute the identical
        # digest when binding an attestation request's tx list to the header.
        # v14 adds the aux term only when set, keeping pre-v14 digests
        # byte-identical.
        return compute_block_hash(
            self._config.chain_id,
            height,
            parent_hash,
            timestamp,
            tx_hashes,
            proposer,
            state_root,
            bridge_state_root,
            aux_state_root,
        )

    def _sign_block_hash(self, block: Block) -> str:
        """Sign a block header with the proposer's private key (v0.7.2).

        The signed message is the canonical-JSON encoding of the block header
        fields that the bridge verifier expects (chain_id, height, hash,
        parent_hash, proposer, state_root, bridge_state_root). This makes the
        same signature verifiable by both PoA consensus and bridge proof
        verification.

        Returns the hex signature, or empty string if no private key is
        configured (legacy mode — block signature verification skipped).
        """
        from ..config import settings

        private_key = getattr(settings, "proposer_key", None)
        if not private_key:
            self._logger.debug("No proposer_key configured; block signature omitted")
            return ""
        try:
            from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_PROPOSAL

            domain = _active_consensus_domain(block.height, DOMAIN_BLOCK_PROPOSAL)
            message = self._block_header_message(block)
            return _sign_consensus(message, private_key, domain)
        except (ImportError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            self._logger.warning("Failed to sign block header: %s", e)
            return ""
