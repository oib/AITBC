"""Post-apply state/aux root finalisation and verification for ``BlockImportMixin`` (#1860).

Split out of ``aitbc_chain.sync_block_import`` (#1860): the methods are
byte-identical moves onto a mixin that ``BlockImportMixin`` inherits, so
every ``self._…`` call resolves exactly as before. Import
``aitbc_chain.sync_block_import`` first (it wires these mixins in); this
module is not meant to be imported directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base_models import Block
from .config import settings
from .logger import get_logger
from .metrics import metrics_registry
from .state import side_root_shadow, state_root_utils
from .sync_base import SyncBase
from .sync_validator import ImportResult

if TYPE_CHECKING:
    from sqlmodel import Session

    from .sync_block_import import _AppendContext


logger = get_logger("aitbc_chain.sync_block_import")


class ImportRootsMixin(SyncBase):
    """Lock-evidence, block-root, required-root, state-root and aux-root checks before commit."""

    if TYPE_CHECKING:
        # Provided by sibling mixins / ``BlockImportMixin`` itself.
        def _make_import_result(self, **kwargs: Any) -> ImportResult: ...

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
        ) -> str: ...

        def _describe_local_state_divergence(self, session: Session, parent_height: int) -> str | None: ...

    def _check_lock_apply_evidence(self, ctx: _AppendContext) -> ImportResult | None:
        """#1940 F5: every declared/effectively-typed lock must have actually
        applied — a failed, skipped or hidden lock rejects the whole block and
        rolls back every write above."""
        if not ctx.tx_only_root or ctx.declared_lock_hashes == ctx.successful_lock_hashes:
            return None
        _failed = sorted(ctx.declared_lock_hashes - ctx.successful_lock_hashes)
        if not ctx.probe:
            metrics_registry.increment("sync_blocks_rejected_total")
        ctx.session.rollback()
        if not ctx.probe:
            self._track_rejection(self._chain_id)
        logger.warning(
            "[SYNC] Block rejected: BRIDGE_LOCK without actual apply success at height %s: %s",
            ctx.block_data.get("height"),
            _failed,
        )
        return self._make_import_result(
            accepted=False,
            height=ctx.block_data.get("height", 0),
            block_hash=ctx.block_hash,
            reason=f"bridge_lock_apply_failed: {_failed}",
        )

    def _finalize_block_roots(
        self, ctx: _AppendContext, block: Block, transactions: list[dict[str, Any]] | None
    ) -> ImportResult | None:
        """Fill in the state/bridge roots and metadata now that transactions
        have been applied, then stage the block.  This keeps the schedule
        check above from touching any state."""
        block_data = ctx.block_data
        block.state_root = block_data.get("state_root")
        if ctx.tx_only_root:
            try:
                block.bridge_state_root = self._derive_bridge_state_root(
                    ctx.session,
                    block_data,
                    transactions,
                    tx_only_era=True,
                    successful_lock_hashes=ctx.successful_lock_hashes,
                    tx_height=ctx.gate_height,
                )
            except ValueError as _bridge_err:
                # #1940 F5: missing/mismatched carried root or missing
                # success evidence — reject and roll back, never synthesize.
                if not ctx.probe:
                    metrics_registry.increment("sync_blocks_rejected_total")
                ctx.session.rollback()
                if not ctx.probe:
                    self._track_rejection(self._chain_id)
                logger.warning(
                    "[SYNC] Block rejected: tx-derived bridge root violation at height %s: %s",
                    block_data.get("height"),
                    _bridge_err,
                )
                return self._make_import_result(
                    accepted=False,
                    height=block_data.get("height", 0),
                    block_hash=ctx.block_hash,
                    reason=f"bridge_root_violation: {_bridge_err}",
                )
        else:
            # Gate-off: the original three-argument derive call, outside the
            # new-era ValueError catch — legacy behavior byte-identical.
            block.bridge_state_root = self._derive_bridge_state_root(ctx.session, block_data, transactions, _probe=ctx.probe)
        # v14 (V-3): the header's committed side-table root. Stored only at
        # v14+ — below the activation the field does not exist and any value a
        # peer supplies is ignored, so replayed pre-v14 blocks keep NULL.
        block.aux_state_root = (
            str(block_data["aux_state_root"]) if ctx.block_version >= 14 and block_data.get("aux_state_root") else None
        )
        block.block_metadata = block_data.get("block_metadata")
        ctx.session.add(block)
        return None

    def _check_required_state_root(self, ctx: _AppendContext) -> ImportResult | None:
        """#1325 (e): a block that omits its root cannot be allowed to skip the
        required-root comparison — vote-only attestation leans on it."""
        block_data = ctx.block_data
        require_root_height = getattr(settings, "sync_require_state_root_height", None)
        if not (
            require_root_height is not None
            and not block_data.get("state_root")
            and not ctx.skip_state_root_validation
            and int(block_data["height"]) >= int(require_root_height)
        ):
            return None
        if not ctx.probe:
            metrics_registry.increment("sync_state_root_missing_rejected_total")
        ctx.session.rollback()
        self._track_rejection(self._chain_id)
        logger.error(
            ctx.reject_tag + " Missing state root at height %s (required from %s) - BLOCK REJECTED",
            block_data["height"],
            require_root_height,
        )
        return self._make_import_result(
            accepted=False,
            height=block_data["height"],
            block_hash=ctx.block_hash,
            reason="Missing state root",
        )

    def _verify_state_root(self, ctx: _AppendContext) -> ImportResult | None:
        """Recompute the full account-state root and compare it to the
        committed header root. Two very different faults produced the same
        rejection before, and only one of them is about the incoming block —
        see ``_describe_local_state_divergence``."""
        block_data = ctx.block_data
        ctx.check_deadline()
        if not (block_data.get("state_root") and (not ctx.skip_state_root_validation)):
            return None
        ctx.session.flush()
        # Compute state root from the full account state. The previous
        # "incremental" approach created a fresh trie per call but only
        # populated it with accounts touched in this block — producing an
        # empty trie (root=0x00..00) for blocks with no transactions and a
        # wrong root for blocks with transactions. Since the trie is not
        # persisted across blocks, a full recompute is the only correct option.
        computed_hex = state_root_utils.compute_state_root_full(ctx.session, self._chain_id, deadline=ctx.probe_deadline)
        computed_root = bytes.fromhex(computed_hex.replace("0x", "")) if computed_hex else None
        try:
            expected_root = bytes.fromhex(str(block_data.get("state_root")).replace("0x", ""))
        except ValueError:
            expected_root = None
        if expected_root is None or len(expected_root) != 32:
            if not ctx.probe:
                metrics_registry.increment("sync_state_root_rejected_total")
            ctx.session.rollback()
            self._track_rejection(self._chain_id)
            logger.error(
                ctx.reject_tag + " Invalid state root at height %s: %s - BLOCK REJECTED",
                block_data["height"],
                block_data.get("state_root"),
            )

            return self._make_import_result(
                accepted=False,
                height=block_data["height"],
                block_hash=ctx.block_hash,
                reason=f"Invalid state root: {block_data.get('state_root')}",
            )
        if computed_root == expected_root:
            return None
        if not ctx.probe:
            metrics_registry.increment("sync_state_root_rejected_total")
        ctx.session.rollback()
        self._track_rejection(self._chain_id)
        # If our own account state has drifted away from our head, re-applying
        # the block on top of state that already contains it can never
        # reproduce the expected root, so the node retries forever. hub2
        # emitted 866 identical "BLOCK REJECTED" lines over six hours pointing
        # at block 1300 while the actual fault was a single local account row
        # one transaction ahead of its own head.
        divergence = self._describe_local_state_divergence(ctx.session, block_data["height"] - 1)
        if divergence:
            if not ctx.probe:
                metrics_registry.increment("sync_local_state_divergence_total")
            logger.error(
                ctx.reject_tag + " Local state diverged from our own head %s: %s. "
                "Block %s cannot be imported until local state is repaired; "
                "retrying will not help - BLOCK REJECTED",
                block_data["height"] - 1,
                divergence,
                block_data["height"],
            )
            return self._make_import_result(
                accepted=False,
                height=block_data["height"],
                block_hash=ctx.block_hash,
                reason=(f"Local state diverged from head {block_data['height'] - 1}: {divergence}"),
                diverged=True,
            )
        logger.error(
            ctx.reject_tag + " State root mismatch at height %s: expected %s, computed %s - BLOCK REJECTED",
            block_data["height"],
            expected_root.hex(),
            computed_root.hex(),  # type: ignore[union-attr]
        )

        return self._make_import_result(
            accepted=False,
            height=block_data["height"],
            block_hash=ctx.block_hash,
            reason=f"State root mismatch: expected {expected_root.hex()}, computed {computed_root.hex()}",  # type: ignore[union-attr]
        )

    def _verify_aux_root(self, ctx: _AppendContext) -> ImportResult | None:
        """v14 (V-3): the block commits to the 13-table side-table root over the
        committed set after this block's transactions applied. Recompute it
        against local state — a mismatch means the proposer's committed state
        and ours disagree in a way the account-level state_root does not see,
        so the block is rejected rather than sealing a divergence."""
        block_data = ctx.block_data
        if ctx.skip_state_root_validation or ctx.block_version < 14:
            return None
        ctx.session.flush()
        computed_aux = side_root_shadow.committed_fingerprint(
            ctx.session.connection().connection, ctx.block_version, deadline=ctx.probe_deadline
        )["fingerprint"]
        recorded_aux = block_data.get("aux_state_root")
        if not recorded_aux or computed_aux == str(recorded_aux):
            return None
        if not side_root_shadow.aux_check_verifiable(ctx.block_version):
            # The era set includes tables whose only writers were
            # node-local RPC/aux paths (stake, edge_node_registration):
            # the sealed digest mixed the sealer's own local rows and
            # cannot be reproduced here — a mismatch cannot distinguish
            # real divergence from legitimate local rows, so the check
            # runs compare-only for these eras rather than stalling
            # replay of history no node can re-verify.
            if not ctx.probe:
                metrics_registry.increment("sync_aux_root_unverifiable_total")
            logger.warning(
                ctx.reject_tag + " Aux state root mismatch at height %s on an "
                "unverifiable era (v%s): expected %s, computed %s - "
                "compare-only, block not rejected",
                block_data["height"],
                ctx.block_version,
                recorded_aux,
                computed_aux,
            )
            return None
        if not ctx.probe:
            metrics_registry.increment("sync_aux_root_rejected_total")
        ctx.session.rollback()
        self._track_rejection(self._chain_id)
        logger.error(
            ctx.reject_tag + " Aux state root mismatch at height %s: expected %s, computed %s - BLOCK REJECTED",
            block_data["height"],
            recorded_aux,
            computed_aux,
        )
        return self._make_import_result(
            accepted=False,
            height=block_data["height"],
            block_hash=ctx.block_hash,
            reason=f"Aux state root mismatch: expected {recorded_aux}, computed {computed_aux}",
        )
