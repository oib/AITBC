"""Pre-apply validation and era-prep helpers for ``BlockImportMixin`` (#1860).

Split out of ``aitbc_chain.sync_block_import`` (#1860): the methods are
byte-identical moves onto a mixin that ``BlockImportMixin`` inherits, so
every ``self._…`` call resolves exactly as before. Import
``aitbc_chain.sync_block_import`` first (it wires these mixins in); this
module is not meant to be imported directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import Session, select

from aitbc.crypto.signature_recovery import canonical_address

from .base_models import Block
from .base_models import Transaction as ChainTransaction
from .config import settings
from .consensus.multi_validator_poa import MultiValidatorPoA
from .cross_chain import bridge_lock_guard, bridge_root_shadow
from .cross_chain.bridge_leaf import lock_leaf_value, unknown_lock_leaf
from .cross_chain.bridge_tx_root import (
    assert_lock_debit,
    build_tx_bridge_trie,
    canonical_lock_fields,
    effective_lock_debit,
    resolve_lock_type,
    tx_only_root_active,
)
from .logger import get_logger
from .metrics import metrics_registry
from .state.pure_state_transition import _determine_tx_type
from .sync_base import SyncBase
from .sync_validator import ImportResult

if TYPE_CHECKING:
    from .sync_block_import import _AppendContext


logger = get_logger("aitbc_chain.sync_block_import")


class ImportValidationMixin(SyncBase):
    """Proposer schedule, bridge-state-root derivation and pre-apply era/signature checks."""

    if TYPE_CHECKING:
        # Provided by ``BlockImportMixin`` itself (sync_block_import.py).
        def _make_import_result(self, **kwargs: Any) -> ImportResult: ...

    def _get_multi_validator(self) -> MultiValidatorPoA | None:
        """Return a settings-only MultiValidatorPoA for schedule/role checks."""
        if not getattr(settings, "multi_validator_consensus_enabled", False):
            return None
        if not getattr(settings, "validator_set", ""):
            return None
        cache: MultiValidatorPoA | None = getattr(self, "_multi_validator_cache", None)
        if cache is not None:
            return cache
        multi_validator: MultiValidatorPoA | None
        try:
            multi_validator = MultiValidatorPoA.from_settings(self._chain_id)
        except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, ImportError, RuntimeError):
            logger.exception("Failed to build MultiValidatorPoA from settings for chain %s", self._chain_id)
            multi_validator = None
        self._multi_validator_cache = multi_validator
        return self._multi_validator_cache

    def _validate_proposer_schedule(
        self,
        session: Session,
        block_data: dict[str, Any],
        block: Block,
    ) -> None:
        """Verify the block proposer is an active validator scheduled for this height.

        Raises ValueError when the block should be rejected, allowing the caller
        to return an ImportResult without committing the block.
        """
        mv = self._get_multi_validator()
        if mv is None or not mv.validators:
            return

        # Only enforce the schedule for proposers that are actually in the
        # configured validator set.  Unknown proposers are still subject to the
        # signature and attestation checks in ProposerSignatureValidator.
        try:
            proposer_canonical = canonical_address(block.proposer)
        except (TypeError, ValueError):
            return
        if not any(canonical_address(v) == proposer_canonical for v in mv.validators):
            return

        parent_hash = block_data.get("parent_hash", "")
        parent_timestamp: Any = None
        if parent_hash and parent_hash != "0x00":
            parent_block = session.exec(
                select(Block).where(Block.chain_id == self._chain_id).where(Block.hash == parent_hash)
            ).first()
            if parent_block:
                parent_timestamp = parent_block.timestamp

        if not mv.validate_block(block, block.proposer, parent_timestamp):
            raise ValueError(f"Proposer {block.proposer} is not the scheduled/authorized proposer for height {block.height}")

    def _derive_bridge_state_root(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None,
        _probe: bool = False,
        *,
        tx_only_era: bool = False,
        successful_lock_hashes: set[str] | None = None,
        tx_height: int = 0,
    ) -> str:
        """Return the bridge event trie root for an imported block.

        Prefer the value carried in the P2P/bulk payload. If it is missing,
        rebuild it from the BRIDGE_LOCK transactions and CrossChainTransfer
        records so P2P-synced blocks do not store a NULL bridge_state_root.

        #1940 F5: in the tx-derived era the root is computed purely from the
        delivered (normalized) lock bodies through the shared contract —
        no CrossChainTransfer lookup, no synthesize-on-missing. Every lock
        body must carry actual apply-success evidence supplied by the caller;
        the carried root must be present and exactly equal or ValueError is
        raised so the caller rejects and rolls back the whole block.
        """
        if tx_only_era:
            return self._derive_bridge_state_root_tx_only(block_data, transactions, successful_lock_hashes, tx_height)
        return self._derive_bridge_state_root_legacy(session, block_data, transactions, _probe=_probe)

    def _derive_bridge_state_root_legacy(
        self,
        session: Session,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None,
        *,
        _probe: bool = False,
    ) -> str:
        """Legacy (pre-F5-era) bridge root: carried value or CCT-rebuild."""
        existing = block_data.get("bridge_state_root")
        if existing:
            if not _probe:
                # #1940 F4: the shadow root is observational — a speculative
                # probe apply must not run it.
                bridge_root_shadow.run_shadow_check(block_data, transactions, chain_id=self._chain_id, log=logger)
            return str(existing)
        from .base_models import CrossChainTransfer
        from .state.merkle_patricia_trie import MerklePatriciaTrie

        trie = MerklePatriciaTrie()
        lock_txs: list[dict[str, Any]] = []
        if transactions:
            for tx in transactions:
                tx_type = (tx.get("type") or (tx.get("payload") or {}).get("type", "")).upper()
                if tx_type == "BRIDGE_LOCK":
                    lock_txs.append(tx)
        if not lock_txs:
            return "0x" + trie.get_root().hex()
        # V-4 dry-run missing-data guard (flag-gated, logs/counts only —
        # the derived root below is computed exactly as before).
        block_height = int(block_data.get("height") or 0)
        if not _probe:
            bridge_lock_guard.run_guard_dryrun_dicts(lock_txs, height=block_height, chain_id=self._chain_id, log=logger)
        transfer_ids = [tx.get("tx_hash", "") for tx in lock_txs]
        records = session.exec(
            select(CrossChainTransfer).where(
                CrossChainTransfer.source_chain == self._chain_id,
                CrossChainTransfer.transfer_id.in_(transfer_ids),  # type: ignore[attr-defined]
            )
        ).all()
        record_map = {r.transfer_id: r for r in records}
        for tx in lock_txs:
            tx_hash = tx.get("tx_hash", "")
            record = record_map.get(tx_hash)
            if record is None:
                value = unknown_lock_leaf(tx_hash)
            else:
                value = lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, block_height)
            trie.put(tx_hash.encode(), value.encode())
        return "0x" + trie.get_root().hex()

    def _derive_bridge_state_root_tx_only(
        self,
        block_data: dict[str, Any],
        transactions: list[dict[str, Any]] | None,
        successful_lock_hashes: set[str] | None,
        tx_height: int,
    ) -> str:
        """#1940 F5 tx-derived era: root from delivered lock bodies only."""
        bodies: list[dict[str, Any]] = []
        for tx in transactions or []:
            tx_any: Any = tx
            if not isinstance(tx_any, dict):
                continue
            body = dict(tx_any)
            body["tx_hash"] = str(tx.get("tx_hash") or "")
            bodies.append(body)
        lock_hashes = {str(b.get("tx_hash") or "") for b in bodies if _determine_tx_type(b) == "BRIDGE_LOCK"}
        lock_hashes.discard("")
        if lock_hashes:
            if successful_lock_hashes is None:
                raise ValueError("BRIDGE_LOCK present without actual-success evidence")
            missing = lock_hashes - set(successful_lock_hashes)
            if missing:
                raise ValueError(f"BRIDGE_LOCK without actual apply success: {sorted(missing)}")
        trie = build_tx_bridge_trie(bodies, self._chain_id, tx_height)
        computed = "0x" + trie.get_root().hex()
        carried = block_data.get("bridge_state_root")
        if not carried:
            raise ValueError("missing bridge_state_root in tx-derived era")
        if str(carried) != computed:
            raise ValueError(f"bridge_state_root mismatch: carried {carried} != computed {computed}")
        return str(carried)

    def _prepare_tx_root_era(self, ctx: _AppendContext, transactions: list[dict[str, Any]] | None) -> ImportResult | None:
        """#1940 F5: resolve the tx-derived bridge-root era gate at
        ``block_height - 1`` and, when active, enforce the integer-height rule
        and scan declared BRIDGE_LOCK bodies for contract violations. Fills
        ``ctx.tx_only_root``/``ctx.gate_height``/``ctx.declared_lock_hashes``.
        Returns a rejection result or None."""
        block_data = ctx.block_data
        _height_raw = block_data.get("height")
        try:
            ctx.gate_height = int(_height_raw or 0)
        except (TypeError, ValueError):
            ctx.gate_height = 0
        ctx.tx_only_root = tx_only_root_active(ctx.session, self._chain_id, ctx.gate_height)
        if not ctx.tx_only_root:
            return None
        if not (isinstance(_height_raw, int) and not isinstance(_height_raw, bool)):
            if not ctx.probe:
                metrics_registry.increment("sync_blocks_rejected_total")
            logger.warning(
                "[SYNC] Block rejected: non-integer height %r in tx-derived bridge-root era",
                _height_raw,
            )
            return self._make_import_result(
                accepted=False,
                height=block_data.get("height", 0),
                block_hash=block_data.get("hash", ""),
                reason="non_integer_height_tx_root_era",
            )
        if transactions:
            return self._scan_declared_lock_txs(ctx, transactions)
        return None

    def _scan_declared_lock_txs(self, ctx: _AppendContext, transactions: list[dict[str, Any]]) -> ImportResult | None:
        """Declared-lock contract scan for the tx-derived bridge-root era.

        Normalization already ran above, but it only adds equal
        amount/value aliases and hoists the signed envelope — it
        can neither create nor hide an alias conflict, so the
        authoritative signed body still reaches these checks.
        Stored-row type disagreements involving BRIDGE_LOCK,
        canonical signed fields, and the outer amount/value debit
        alias all reject the whole sealed block here — it is
        never partially applied. Fills ``ctx.declared_lock_hashes``.
        """
        block_data = ctx.block_data
        _tx_hashes = [str(tx.get("tx_hash") or "") for tx in transactions if isinstance(tx, dict)]
        _stored_types: dict[str, str] = {}
        if _tx_hashes:
            for _h, _t in ctx.session.exec(
                select(ChainTransaction.tx_hash, ChainTransaction.type).where(
                    ChainTransaction.chain_id == self._chain_id,
                    ChainTransaction.tx_hash.in_(_tx_hashes),  # type: ignore[attr-defined]
                )
            ).all():
                _stored_types[_h] = _t
        for _tx_raw in transactions:
            _tx: Any = _tx_raw
            if not isinstance(_tx, dict):
                continue
            _tx_hash = str(_tx.get("tx_hash") or "")
            try:
                _eff = resolve_lock_type(_tx, _stored_types.get(_tx_hash))
                if _eff == "BRIDGE_LOCK":
                    if _tx_hash in ctx.declared_lock_hashes:
                        raise ValueError(f"duplicate BRIDGE_LOCK tx_hash {_tx_hash}")
                    ctx.declared_lock_hashes.add(_tx_hash)
                    _fields = canonical_lock_fields({**_tx, "tx_hash": _tx_hash}, _tx_hash, self._chain_id, ctx.gate_height)
                    assert_lock_debit(_fields, effective_lock_debit(_tx))
            except (TypeError, ValueError) as _e:
                if not ctx.probe:
                    metrics_registry.increment("sync_blocks_rejected_total")
                logger.warning(
                    "[SYNC] Block rejected: bridge lock contract violation at height %s: %s",
                    block_data.get("height"),
                    _e,
                )
                return self._make_import_result(
                    accepted=False,
                    height=block_data.get("height", 0),
                    block_hash=block_data.get("hash", ""),
                    reason=f"bridge_lock_contract_violation: {_e}",
                )
        return None

    def _verify_signed_tx_list_hash(
        self, ctx: _AppendContext, transactions: list[dict[str, Any]] | None
    ) -> ImportResult | None:
        """v20+: the signed block hash must reproduce over the delivered tx
        list — a relayed list that does not hash to it is rejected (#1064)."""
        block_data = ctx.block_data
        if ctx.block_version < 20 or not block_data.get("hash"):
            return None
        from .consensus.block_hash import compute_block_hash

        timestamp_str = block_data.get("timestamp", "")
        delivered_hashes = [str(tx.get("tx_hash", "")) for tx in transactions or []]
        recomputed = compute_block_hash(
            self._chain_id,
            int(block_data["height"]),
            str(block_data.get("parent_hash", "")),
            timestamp_str,
            delivered_hashes,
            str(block_data.get("proposer", "")),
            str(block_data.get("state_root") or ""),
            str(block_data.get("bridge_state_root") or ""),
            str(block_data.get("aux_state_root") or ""),
        )
        if recomputed == str(block_data["hash"]):
            return None
        if not ctx.probe:
            metrics_registry.increment("sync_blocks_rejected_total")
        logger.warning(
            ("[ATTEST-PROBE] " if ctx.probe else "")
            + "Block rejected at v20+: delivered tx list does not hash to the signed block hash at height %s",
            block_data["height"],
        )
        return self._make_import_result(
            accepted=False,
            height=block_data["height"],
            block_hash=block_data.get("hash", ""),
            reason="tx_list_hash_mismatch",
        )
