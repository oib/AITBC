"""Proposer loop lifecycle, sync gating, and parent-state repair for ``PoAProposer`` (poa split).

Import ``aitbc_chain.consensus.poa`` first (it wires these
mixins into ``PoAProposer``); this module is not meant to be imported
directly."""

from __future__ import annotations

import asyncio
import traceback
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from . import poa as _poa
from .poa import _PoaBaseMixin

from ..base_models import _to_ait_address
from ..config import settings
from ..metrics import metrics_registry
from ..models import Block, Transaction
from ..state.state_root_utils import compute_state_root_full as _compute_state_root
from ..state.state_transition import _ensure_account, get_block_version
from aitbc.async_tasks import create_task_with_logging
from sqlmodel import Session, select


class _LifecycleMixin(_PoaBaseMixin):
    if TYPE_CHECKING:

        def _abandon_tick_from_loop(self, *args: Any, **kwargs: Any) -> Any: ...
        def _ensure_genesis_block(self, *args: Any, **kwargs: Any) -> Any: ...
        def _same_hash_retry_horizon_seconds(self, *args: Any, **kwargs: Any) -> Any: ...

    async def start(self) -> None:
        if self._task is not None:
            return
        from ..config import settings

        # Answering attestation requests is a validator duty, not a proposer duty:
        # a validator with ENABLE_BLOCK_PRODUCTION=false still has to sign other
        # validators' headers. Started before the block-production check because
        # it used to sit after it, so on a four-validator fleet where only two
        # nodes produce blocks the proposer could collect exactly one attestation
        # -- below MULTI_VALIDATOR_MIN_ATTESTATIONS=2 -- and every block was
        # dropped even though PBFT had reached quorum.
        if self._remote_attestation is not None:
            await self._remote_attestation.start()
            self._logger.info("Remote attestation listener started for chain %s", self._config.chain_id)

        if not getattr(settings, "enable_block_production", True):
            self._logger.info("Block production disabled, skipping PoA proposer loop")
            return
        self._logger.info("Starting PoA proposer loop", extra={"interval": self._config.interval_seconds})
        # #1298: surface the effective same-hash retry horizon at startup —
        # a 0 here means every retry stamps a fresh hash (the fleet-wide
        # silent-disable the fh1298-leg drill caught).
        retry_enabled = getattr(settings, "proposer_same_hash_retry_enabled", False)
        retry_horizon = self._same_hash_retry_horizon_seconds() if retry_enabled else 0.0
        metrics_registry.set_gauge("proposer_same_hash_retry_horizon_seconds", retry_horizon)
        self._logger.info(
            "Same-hash retry horizon %.1fs (enabled=%s)",
            retry_horizon,
            retry_enabled,
        )
        await self._ensure_genesis_block()
        head = self._fetch_chain_head()
        if head is not None:
            self._sync_pbft_to_head(head)
            self._last_block_timestamp = head.timestamp
            self._logger.info("Initialized last block timestamp from head", extra={"height": head.height})
        self._stop_event.clear()
        self._task = create_task_with_logging(self._run_loop(), name="poa_proposer_loop")

    async def stop(self) -> None:
        for republish_task in list(self._republish_tasks):  # #1268: seal re-announcers
            republish_task.cancel()
        # Mirrors start(): the attestation listener runs even when the proposer
        # loop does not, so it must be stopped before the "no loop" early return
        # or a non-producing validator would leak its gossip subscription.
        if self._remote_attestation is not None:
            try:
                await asyncio.wait_for(self._remote_attestation.stop(), timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._logger.warning("Remote attestation listener did not stop within timeout")
            self._logger.info("Remote attestation listener stopped for chain %s", self._config.chain_id)
        if self._task is None:
            return
        self._logger.info("Stopping PoA proposer loop")
        self._stop_event.set()  # noqa: unawaited-async — asyncio.Event.set() is synchronous
        self._task.cancel()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._logger.warning("PoA proposer loop did not stop within timeout")
        self._task = None
        self._same_hash_retry = None
        if self._multi_validator is not None:
            self._multi_validator.save_state()

    async def _run_loop(self) -> None:
        await asyncio.sleep(self._config.interval_seconds)
        from ..config import settings

        block_generation_mode = getattr(settings, "block_generation_mode", "hybrid")
        while not self._stop_event.is_set():
            if self._stop_event.is_set():
                break
            try:
                await self._abandon_tick_from_loop()
                proposed = await self._propose_block_with_watchdog()
                if proposed:
                    await self._wait_until_next_slot()
                elif block_generation_mode == "hybrid":
                    check_interval = self._config.interval_seconds / 4
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=check_interval)
                    except TimeoutError:
                        pass
                else:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self._config.interval_seconds)
                    except TimeoutError:
                        pass
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Failed to propose block: %s\n%s", exc, traceback.format_exc())
                await asyncio.sleep(1.0)

    async def _propose_block_with_watchdog(self, *, watchdog_after: float | None = None) -> bool:
        """Run one proposal iteration under a silence watchdog.

        The 1804 freeze is the reason this exists: the proposer task hung at
        20:09:31 on 31 Aug with no error, no traceback, and no further log for
        ~16h — every wait inside the pipeline was individually bounded, but
        nothing observed the iteration *itself* stalling. An iteration that
        outlives this threshold is a stalled proposer, not an idle one, and the
        journal should say so.

        `watchdog_after` is public only for tests; production should leave it at
        the default computed from `interval_seconds`.
        """
        if watchdog_after is None:
            watchdog_after = max(60.0, self._config.interval_seconds * 4)
        task = asyncio.ensure_future(self._propose_block())

        async def _watch() -> None:
            await asyncio.sleep(watchdog_after)
            if not task.done():
                phase = self._propose_phase or "unknown"
                self._logger.error(
                    "[PROPOSE] proposal iteration still running after %.0fs on chain %s "
                    "(phase=%s) — the proposer is stalled, not idle; check gossip, sync, and PBFT state",
                    watchdog_after,
                    self._config.chain_id,
                    phase,
                )
                metrics_registry.increment("poa_proposer_stalled_iterations_total")
                metrics_registry.increment(f"poa_proposer_stalled_iterations_total_phase_{phase}")

        watcher = asyncio.ensure_future(_watch())
        try:
            return await task
        finally:
            watcher.cancel()

    async def _wait_until_next_slot(self) -> None:
        head = self._fetch_chain_head()
        if head is None:
            return
        self._sync_pbft_to_head(head)
        now = datetime.now(UTC)
        head_timestamp = head.timestamp if head.timestamp.tzinfo is not None else head.timestamp.replace(tzinfo=UTC)
        elapsed = (now - head_timestamp).total_seconds()
        sleep_for = max(self._config.interval_seconds - elapsed, 0.1)
        if sleep_for <= 0:
            sleep_for = 0.1
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_for)
        except TimeoutError:
            return

    async def _ensure_synced_before_proposal(self) -> bool:
        """Wait until SyncManager reports a small enough gap, or timeout.

        Returns True if it is safe to propose, False if the node is too far
        behind and catch-up did not complete in time.
        """
        if self._sync_manager is None or not settings.sync_manager_enabled:
            return True
        status = self._sync_manager.get_sync_status(self._config.chain_id)
        max_gap = getattr(settings, "sync_manager_max_proposal_gap", 2)
        if status.get("gap", 0) <= max_gap:
            return True
        self._logger.warning(
            "[PROPOSE] Sync gap %s exceeds %s for chain %s, forcing catch-up before proposal",
            status.get("gap"),
            max_gap,
            self._config.chain_id,
        )
        await self._sync_manager.force_catch_up(self._config.chain_id)
        timeout = getattr(settings, "sync_manager_proposal_sync_timeout", 30)
        deadline = _poa.time.time() + timeout
        while _poa.time.time() < deadline:
            status = self._sync_manager.get_sync_status(self._config.chain_id)
            if status.get("gap", 0) <= max_gap:
                return True
            try:
                await asyncio.wait_for(asyncio.sleep(1), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        self._logger.warning("[PROPOSE] Timed out waiting for sync on chain %s, skipping proposal", self._config.chain_id)
        return False

    def _reapply_parent_block(self, session: Session, parent: Block) -> bool:
        """Re-apply a parent block's transactions to bring local account state forward.

        Multi-validator PoA can select a validator that has the parent block in its
        database but has not yet applied the parent's state transition (for example
        because the block arrived through gossip while the validator was about to
        propose). The local `state_root` then lags behind the canonical parent
        `state_root`, and the next block would be built on stale state.

        This fallback loads the parent's recorded transactions and re-runs the state
        transition. It is idempotent when the local state is actually behind, because
        the function is only reached when ``_compute_state_root`` disagrees with the
        parent header.
        """
        state_transition = _poa.get_state_transition()
        state_transition.reset_processed_cache()
        chain_id = self._config.chain_id
        tx_recs = session.exec(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                Transaction.block_height == parent.height,
            )
        ).all()
        if not tx_recs:
            self._logger.warning(
                "[PROPOSE] Parent block %s has no transactions and local state root %s does not match parent %s; cannot repair",
                parent.height,
                _compute_state_root(session, chain_id),
                parent.state_root,
            )
            return False
        # Re-apply under a savepoint: a failed repair must not leave flushed
        # rows in the session — a caller that continues with this session
        # would otherwise commit a half-repaired state. The `with` form also
        # covers an exception mid-loop: a bare begin_nested() would leave the
        # savepoint open. Failure exits still roll back explicitly — a clean
        # `with` exit would release the savepoint over half-applied work.
        repair_version = get_block_version(parent, parent.height)
        with session.begin_nested() as repair:
            for tx_rec in tx_recs:
                sender = _to_ait_address(tx_rec.sender or "")
                recipient = _to_ait_address(tx_rec.recipient or "")
                # v22 (CONSENSUS-STATE-001, #1169): no pre-apply sender insert —
                # apply_transaction owns account creation on its success paths,
                # matching the importer and build paths.
                if sender and repair_version < 22:
                    _ensure_account(session, chain_id, sender)
                # Do not create the recipient account here, matching the import
                # path (sync_block_import) and the build path below:
                # apply_transaction ensures the recipient itself on the paths
                # that credit it. Pre-creating added a phantom leaf for
                # zero-value types (GPU_MARKET offers carry to=0x0000…0000), so
                # a parent carrying that shape could never recompute to its own
                # recorded root — repair always failed on it (bc-2 fork at 1462).
                env = tx_rec.envelope if isinstance(tx_rec.envelope, dict) else None
                if env:
                    # Re-apply the signed original: rebuilding from row columns
                    # drops the signature, which the v9 apply gate rejects.
                    tx_data = dict(env)
                    tx_data["tx_hash"] = tx_rec.tx_hash
                    if "amount" in tx_data:
                        tx_data["value"] = tx_data["amount"]
                    tx_data.setdefault("signature", "")
                else:
                    tx_data = {
                        "from": sender,
                        "to": recipient,
                        "amount": tx_rec.value,
                        "value": tx_rec.value,
                        "fee": tx_rec.fee,
                        "nonce": tx_rec.nonce,
                        "type": (tx_rec.type or "TRANSFER").upper(),
                        "payload": tx_rec.payload or {},
                        "signature": "",
                    }
                # skip_dedup: these txs are already recorded in the transaction
                # table — that is where we loaded them from — so the admission
                # replay check would reject the re-apply it exists to perform.
                success, msg = state_transition.apply_transaction_guarded(
                    session,
                    chain_id,
                    tx_data,
                    tx_rec.tx_hash,
                    block_version=repair_version,
                    block_height=parent.height,
                    block_time=parent.timestamp,
                    skip_dedup=True,
                )
                if not success:
                    self._logger.error(
                        "[PROPOSE] Failed to re-apply parent tx %s at height %s: %s",
                        tx_rec.tx_hash,
                        parent.height,
                        msg,
                    )
                    repair.rollback()
                    return False
            session.flush()
            recomputed = _compute_state_root(session, chain_id)
            if recomputed != parent.state_root:
                self._logger.error(
                    "[PROPOSE] Parent block %s state still mismatched after re-apply: expected %s, got %s",
                    parent.height,
                    parent.state_root,
                    recomputed,
                )
                repair.rollback()
                return False
        self._logger.info(
            "[PROPOSE] Re-applied parent block %s; local state now matches %s",
            parent.height,
            parent.state_root,
        )
        return True
