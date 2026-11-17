"""Mempool eviction and import-rejection persistence for ``BlockImportMixin`` (#1860).

Split out of ``aitbc_chain.sync_block_import`` (#1860): the methods are
byte-identical moves onto a mixin that ``BlockImportMixin`` inherits, so
every ``self._…`` call resolves exactly as before. Import
``aitbc_chain.sync_block_import`` first (it wires these mixins in); this
module is not meant to be imported directly.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from .base_models import Transaction as ChainTransaction
from .logger import get_logger
from .sync_base import SyncBase


logger = get_logger("aitbc_chain.sync_block_import")


class ImportMempoolMixin(SyncBase):
    """Post-commit mempool eviction and rejected-transaction persistence."""

    def _evict_included_from_mempool(self, transactions: list[dict[str, Any]]) -> None:
        """Drop just-included transactions from the local mempool.

        Only proposers drain the mempool (poa.py); on followers a confirmed
        transaction would sit there until size-cap eviction, evicting real
        pending txs ahead of dead ones. ``tx_hash`` is always populated by the
        normalization loop above. Best-effort: a mempool failure must never
        turn into a block-import failure.
        """
        try:
            from .mempool import get_mempool, _tx_slot_key

            mempool = get_mempool()
            evicted = 0
            for tx in transactions:
                tx_hash = tx.get("tx_hash")
                if tx_hash and mempool.remove(tx_hash, self._chain_id):
                    evicted += 1
                # A sealed (sender, nonce) kills any different-hash pending
                # row on that slot — release it now instead of refusing
                # resubmits for the full TTL (Refs #717). Only a sealed tx
                # that itself held a slot can consume one: unsigned
                # protocol-internal txs carry a placeholder nonce and must
                # not trigger the sweep (#796).
                sender = tx.get("from") or tx.get("sender")
                nonce = tx.get("nonce")
                if isinstance(sender, str) and sender and isinstance(nonce, int) and _tx_slot_key(tx) is not None:
                    superseded = mempool.remove_superseded(self._chain_id, sender, nonce)
                    if superseded:
                        logger.info(
                            "Dropped %d superseded pending tx(s) for (%s, nonce %d)",
                            superseded,
                            sender,
                            nonce,
                        )
            if evicted:
                logger.info("Evicted %s included transaction(s) from mempool", evicted)
        except Exception as exc:  # noqa: BLE001 - mempool backend is pluggable; eviction is best-effort
            logger.warning("Mempool eviction after block import failed: %s", exc)

    @staticmethod
    def _block_rejected_txs(block_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Apply-rejected tx identities the proposer stamped in block_metadata (#1248)."""
        raw = block_data.get("block_metadata")
        if not raw:
            return []
        try:
            metadata = json.loads(raw) if isinstance(raw, str) else raw
        except (RecursionError, TypeError, ValueError):
            return []
        entries = metadata.get("rejected_txs") if isinstance(metadata, dict) else None
        if not isinstance(entries, list):
            return []
        return [e for e in entries if isinstance(e, dict) and isinstance(e.get("tx_hash"), str) and e["tx_hash"]]

    def _persist_import_rejections(self, session: Session, block_data: dict[str, Any]) -> None:
        """Write service-state ``rejected`` rows for txs the proposer reports as
        apply-rejected, so every host's chain.db carries the terminal marker
        the mempool admission and sweeper paths consult (R14-M1, #1248).

        Sparse rows: the full envelope never left the proposer's mempool, so
        only the slot-identifying fields travel in block_metadata. A row
        already ``confirmed`` is left untouched — sealing beats rejection.
        Best-effort per entry: a malformed metadata entry must not fail the
        block import.
        """
        entries = self._block_rejected_txs(block_data)
        if not entries:
            return
        height = int(block_data.get("height") or 0)
        proposer = str(block_data.get("proposer") or "")
        for e in entries:
            tx_hash = e["tx_hash"]
            nonce = e.get("nonce")
            try:
                existing = session.exec(
                    select(ChainTransaction).where(
                        ChainTransaction.chain_id == self._chain_id,
                        ChainTransaction.tx_hash == tx_hash,
                    )
                ).first()
                metadata_note = f"apply-rejected by proposer {proposer} at height {height}: {e.get('reason', '')}"
                if existing is not None:
                    if existing.status != "confirmed":
                        existing.status = "rejected"
                        existing.tx_metadata = metadata_note
                        session.add(existing)
                    continue
                session.add(
                    ChainTransaction(
                        chain_id=self._chain_id,
                        tx_hash=tx_hash,
                        sender=str(e.get("sender") or ""),
                        recipient="",
                        payload={},
                        nonce=nonce if isinstance(nonce, int) and not isinstance(nonce, bool) else 0,
                        value=0,
                        fee=0,
                        type=str(e.get("type") or "TRANSFER").upper(),
                        status="rejected",
                        block_height=None,
                        tx_metadata=metadata_note,
                    )
                )
            except (SQLAlchemyError, ValueError, TypeError, KeyError, AttributeError) as exc:
                logger.warning("Failed to record import-side rejection for tx %s: %s", tx_hash, exc)

    def _evict_rejected_from_mempool(self, block_data: dict[str, Any]) -> None:
        """Drop apply-rejected txs this block's metadata names from the local
        mempool — they can never seal and otherwise squat their (sender,
        nonce) slot until TTL (R14-M1, #1248). Best-effort: a mempool failure
        must never turn into a block-import failure."""
        entries = self._block_rejected_txs(block_data)
        if not entries:
            return
        try:
            from .mempool import get_mempool

            mempool = get_mempool()
            evicted = 0
            for e in entries:
                if mempool.remove(e["tx_hash"], self._chain_id):
                    evicted += 1
                    # #1999: name the tx and the proposer's verdict reason —
                    # the count-only summary left probes unable to tell which
                    # rejection fired.
                    logger.info(
                        "Evicted apply-rejected tx %s from mempool at height %s (reason: %s)",
                        e["tx_hash"],
                        block_data.get("height"),
                        e.get("reason") or "unspecified",
                    )
            if evicted:
                logger.info(
                    "Evicted %d apply-rejected tx(s) from mempool at height %s",
                    evicted,
                    block_data.get("height"),
                )
        except Exception as exc:  # noqa: BLE001 - mempool backend is pluggable; eviction is best-effort
            logger.warning("Rejected-tx mempool eviction failed: %s", exc)
