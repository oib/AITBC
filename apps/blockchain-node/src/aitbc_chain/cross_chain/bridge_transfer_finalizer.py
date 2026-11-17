"""Cross-chain bridge transfer — Chain-header sync, relayer worklist, finalizer loop, and ledger write-back."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Any

from sqlalchemy.orm import raiseload
from sqlmodel import select


from ..config import settings
from ..logger import get_logger
from ..metrics import metrics_registry
from ..models import Block, BridgeBlockHeader, CrossChainTransfer, Transaction
from .bridge_base import BridgeBase
from .bridge_types import BridgeStatus, BridgeTransfer

logger = get_logger(__name__)

# Share of ``bridge_finalizer_pass_timeout`` given to a pass's cooperative
# deadline. The deadline must fire *inside* the wait_for watchdog: equal
# budgets meant a pass that stopped on its own deadline still tripped the
# watchdog and was logged and counted as abandoned (BRIDGE-FINALIZER-
# DEADLINE-MARGIN-1). The watchdog stays the backstop for a pass that
# ignores the deadline entirely (wedged on a sqlite lock, say).
_FINALIZER_DEADLINE_FRACTION = 0.8


class BridgeTransferFinalizerMixin(BridgeBase):
    def _finalize_confirmed_transfers(self, chain_id: str, deadline: float | None = None) -> int:
        """Move 'confirmed' transfers to 'completed' once the release tx is in a block.

        A transfer is only considered finalised when the BRIDGE_RELEASE
        transaction has been sealed into a produced block on the target chain.
        """
        finalized = 0
        with self._session_for(chain_id) as session:
            records = session.exec(
                select(CrossChainTransfer).where(
                    CrossChainTransfer.target_chain == chain_id,
                    CrossChainTransfer.status == "confirmed",
                    CrossChainTransfer.target_tx_hash.is_not(None),  # type: ignore[union-attr]
                )
            ).all()
            for record in records:
                if deadline is not None and time.monotonic() >= deadline:
                    logger.info(
                        "Bridge finalize for %s hit the pass deadline after %s finalized; deferring the rest",
                        chain_id,
                        finalized,
                    )
                    break
                tx = session.exec(
                    select(Transaction).where(
                        Transaction.chain_id == chain_id,
                        Transaction.tx_hash == record.target_tx_hash,
                        Transaction.block_height.is_not(None),  # type: ignore[union-attr]
                    )
                ).first()
                if not tx:
                    continue
                record.status = "completed"
                session.add(record)
                # Mirror the final state on the source chain.
                try:
                    with self._session_for(record.source_chain) as src_session:
                        src_record = src_session.get(CrossChainTransfer, record.transfer_id)
                        if src_record and src_record.status != "completed":
                            src_record.status = "completed"
                            src_record.target_tx_hash = record.target_tx_hash
                            src_record.proof_hash = record.proof_hash
                            src_record.confirm_time = record.confirm_time
                            src_session.add(src_record)
                            src_session.commit()
                except Exception:
                    logger.exception("Failed to update source-chain bridge record for %s", record.transfer_id)
                session.commit()
                finalized += 1
                # #696: mirror the terminal state in the shared ledger.
                self._ledger_writeback(
                    record.transfer_id,
                    "completed",
                    target_tx_hash=record.target_tx_hash,
                    proof_hash=record.proof_hash,
                )
                in_memory = self._pending_transfers.get(record.transfer_id)
                if in_memory:
                    in_memory.status = BridgeStatus.completed
                    in_memory.target_tx_hash = record.target_tx_hash
                    in_memory.confirm_time = record.confirm_time
        return finalized

    def _known_chains(self) -> list[str]:
        """All chain IDs this node may hold bridge state for.

        Union of ``supported_chains`` (locally produced/followed chains),
        ``bridge_supported_chains`` (chains the bridge is configured to
        serve) and the node's default ``chain_id``.
        """
        seen: set[str] = set()
        for raw in (
            getattr(settings, "supported_chains", ""),
            getattr(settings, "bridge_supported_chains", ""),
            str(getattr(settings, "chain_id", "") or ""),
        ):
            for chain in str(raw or "").split(","):
                chain = chain.strip()
                if chain:
                    seen.add(chain)
        return sorted(seen)

    def _chain_db_ready(self, chain_id: str) -> bool:
        """True when this node holds an initialized bridge store for ``chain_id``.

        ``bridge_supported_chains`` may list chains produced by other nodes;
        this node holds no store for those, and the db layer refuses to
        create or open one. Probe the file's existence, mark the chain
        unavailable, and let the finalizer skip it — transfers targeting it
        keep their honest non-terminal state.

        The negative verdict is re-probed every
        ``bridge_chain_unavailable_retry_seconds`` (default 300): a probe that
        failed on a transient condition (store file not yet created, sqlite
        lock held by the producing process during startup) must not silence
        the chain for the rest of the process's lifetime — a permanent cache
        entry is exactly how a finalizer pass goes quiet with only a single
        INFO line to show for it.
        """
        unavailable = getattr(self, "_unavailable_bridge_chains", None)
        if unavailable is None:
            self._unavailable_bridge_chains: dict[str, float] = {}
            unavailable = self._unavailable_bridge_chains
        retry_after = float(getattr(settings, "bridge_chain_unavailable_retry_seconds", 300))
        failed_at = unavailable.get(chain_id)
        if failed_at is not None and (time.monotonic() - failed_at) < retry_after:
            return False
        try:
            with self._session_for(chain_id) as session:
                # Select the full row, not a single column: a stale DB may
                # have the table without GAP-47 columns (release_amount etc.)
                # and only a full-row select detects that.
                session.exec(select(CrossChainTransfer).limit(1)).first()
            if failed_at is not None:
                unavailable.pop(chain_id, None)
                logger.info(
                    "Bridge store for chain %s became available on re-probe; resuming finalizer passes for it",
                    chain_id,
                )
            return True
        except Exception as e:
            unavailable[chain_id] = time.monotonic()
            log = logger.debug if failed_at is not None else logger.info
            log(
                "Bridge store for chain %s is not initialized on this node (%s); "
                "skipping it in finalizer passes — transfers targeting it stay pending",
                chain_id,
                e,
            )
            return False

    def _sync_local_chain_headers(self, chain_id: str, deadline: float | None = None) -> int:
        """Store bridge block headers for locally known blocks of ``chain_id``.

        GAP-47: the bridge proof path needs stored ``BridgeBlockHeader`` rows
        to verify finality, but nothing ever populated them — the RPC intake
        endpoint is admin-gated and no internal caller existed. A node that
        produces (or fully syncs) a chain already holds the authoritative
        signed headers in its ``block`` table, so mirror them into
        ``bridge_block_header`` here. ``store_block_header`` derives
        confirmation counts and finality from stored data, so this also makes
        ``_check_finality_for_transfer`` reachable for real transfers.
        """
        # #1290: single writer per chain. Every app-lifespan process (each
        # --workers uvicorn process of the RPC and island-RPC units) runs this
        # mirror against the same chain.db; the flock lets one mirror at a
        # time and the rest skip to the next pass.
        with self._bridge_header_writer_lock(chain_id) as is_writer:  # type: ignore[attr-defined]
            if not is_writer:
                logger.debug(
                    "Bridge header sync for %s skipped: another process holds the writer lock",
                    chain_id,
                )
                return 0
            with self._session_for(chain_id) as session:
                try:
                    head = session.exec(
                        select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)  # type: ignore[attr-defined]
                    ).first()
                except Exception as e:  # noqa: BLE001 - head probe failure reports height 0
                    logger.debug("bridge head probe failed for %s: %s", chain_id, type(e).__name__)
                    return 0
                if head is None:
                    return 0
                last_stored = session.exec(
                    select(BridgeBlockHeader.height)
                    .where(BridgeBlockHeader.chain_id == chain_id)
                    .order_by(BridgeBlockHeader.height.desc())  # type: ignore[attr-defined]
                    .limit(1)
                ).first()
                finality_blocks = int(getattr(settings, "bridge_finality_blocks", 6))
                if last_stored is None:
                    # First run: backfill only the recent finality window — older
                    # headers cannot become relevant to a pending transfer and a
                    # full-history backfill would needlessly grow the table.
                    start_height = max(0, head.height - 2 * finality_blocks - 5)
                else:
                    start_height = int(last_stored) + 1
                # Bounded per pass: an unbounded select loads every block from the
                # gap start to the chain head into memory at once, and a node that
                # has been down long enough for that to matter is exactly the node
                # that cannot afford it. A host behind by more than one batch
                # catches up over successive passes rather than in one, which still
                # converges with room to spare: 500 headers every
                # ``bridge_monitor_interval`` (60s) against roughly one block a
                # minute of production. Both halves -- the bound and the
                # convergence -- are pinned by test_bridge_header_sync_bound.py.
                batch = max(1, int(getattr(settings, "bridge_header_sync_batch", 500)))
                new_blocks = session.exec(
                    # Only header fields are stored below — suppress the selectin
                    # transactions/receipts eager-loads, they are wasted work here.
                    select(Block)
                    .options(raiseload("*"))
                    .where(Block.chain_id == chain_id, Block.height >= start_height)
                    .order_by(Block.height.asc())  # type: ignore[attr-defined]
                    .limit(batch)
                ).all()
                # #1305: the resume-at-last_stored sync never revisits stored
                # rows, so a fork heal leaves mirror rows holding the orphaned
                # hash forever. Re-verify the recent window against the
                # canonical block table each pass and repair mismatches via
                # the update-capable store path (the batch path skips
                # existing heights, so it cannot repair).
                verify_window = max(1, int(getattr(settings, "bridge_header_verify_window", 128)))
                verify_floor = max(0, int(head.height) - verify_window)
                mirror_rows = session.exec(
                    select(BridgeBlockHeader.height, BridgeBlockHeader.hash).where(
                        BridgeBlockHeader.chain_id == chain_id,
                        BridgeBlockHeader.height >= verify_floor,
                    )
                ).all()
                canonical_rows = session.exec(
                    select(Block.height, Block.hash).where(
                        Block.chain_id == chain_id,
                        Block.height >= verify_floor,
                    )
                ).all()
                canonical_hash = {int(height): str(block_hash).lower() for height, block_hash in canonical_rows}
                stale_rows = [
                    (int(mirror_height), str(mirror_hash))
                    for mirror_height, mirror_hash in mirror_rows
                    if canonical_hash.get(int(mirror_height)) != str(mirror_hash).lower()
                ][:batch]
        stored = self._store_new_block_headers(chain_id, new_blocks, deadline)
        self._repair_stale_chain_headers(chain_id, stale_rows, deadline)
        return stored

    def _repair_stale_chain_headers(
        self, chain_id: str, stale_rows: list[tuple[int, str]], deadline: float | None = None
    ) -> int:
        """Repair mirror rows whose hash diverged from the canonical block (#1305).

        Runs after the new-header store, outside the writer flock — same
        position as the store itself, which relies on skip-existing plus the
        header lock retry rather than the flock for write safety. Repairs go
        through ``_store_block_header_once`` because it updates existing rows;
        ``_store_header_batch`` would skip them. Bounded by the caller's slice
        and the pass deadline; each repair is rare (fork heals only).
        """
        if not stale_rows:
            return 0
        repaired = 0
        with self._session_for(chain_id) as session:
            canonical = session.exec(
                select(Block)
                .options(raiseload("*"))
                .where(
                    Block.chain_id == chain_id,
                    Block.height.in_([height for height, _ in stale_rows]),  # type: ignore[attr-defined]
                )
            ).all()
        blocks_by_height = {int(block.height): block for block in canonical}
        for height, mirror_hash in stale_rows:
            if deadline is not None and time.monotonic() >= deadline:
                logger.info(
                    "Bridge header repair for %s hit the pass deadline after %s repairs; deferring the rest",
                    chain_id,
                    repaired,
                )
                break
            block = blocks_by_height.get(height)
            if block is None:
                # Mirror row with no canonical block at that height — cannot
                # repair without authoritative data; leave for investigation.
                logger.warning(
                    "Bridge header row for %s height %s has no canonical block; skipping repair",
                    chain_id,
                    height,
                )
                continue
            try:
                self._run_with_header_lock_retry(  # type: ignore[attr-defined]
                    lambda b=block: self._store_block_header_once(self._block_header_payload(b)),  # type: ignore[attr-defined]
                    chain_id,
                    deadline,
                )
            except Exception:
                logger.exception("Failed to repair stale bridge header for %s at height %s", chain_id, height)
                continue
            repaired += 1
            metrics_registry.increment("bridge_header_stale_rows_repaired_total")
            logger.warning(
                "Repaired stale bridge header for %s at height %s: mirror had %s, canonical is %s",
                chain_id,
                height,
                mirror_hash,
                block.hash,
            )
        return repaired

    @staticmethod
    def _block_header_payload(block: Any) -> dict[str, Any]:
        """Header fields mirrored from a canonical block row (store + repair share this)."""
        return {
            "chain_id": block.chain_id,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash,
            "proposer": block.proposer,
            "state_root": block.state_root or "",
            "bridge_state_root": block.bridge_state_root or "",
            "signature": block.signature or "",
        }

    def _store_new_block_headers(self, chain_id: str, new_blocks: Any, deadline: float | None = None) -> int:
        """Store selected blocks as bridge headers in commit_batch-sized transactions."""
        stored = 0
        commit_batch = max(1, int(getattr(settings, "bridge_header_commit_batch", 50)))
        pending: list[dict] = []
        for block in new_blocks:
            if deadline is not None and time.monotonic() >= deadline:
                logger.info(
                    "Bridge header sync for %s hit the pass deadline after %s stored; committing and deferring the rest",
                    chain_id,
                    stored,
                )
                break
            pending.append(self._block_header_payload(block))
            if len(pending) >= commit_batch:
                if not self._flush_header_batch(chain_id, pending, block.height, deadline):
                    pending.clear()
                    break
                stored += len(pending)
                pending.clear()
        if pending and self._flush_header_batch(chain_id, pending, None, deadline):
            stored += len(pending)
        return stored

    def _flush_header_batch(
        self, chain_id: str, pending: list[dict], at_height: int | None, deadline: float | None = None
    ) -> bool:
        """One commit for a pending header batch; False means the caller should stop.

        #1290: a sqlite "database is locked" retries with capped backoff
        (bounded by the pass deadline) instead of dropping the batch on the
        first busy_timeout expiry; non-lock errors keep the old fail-fast.
        """
        try:
            self._run_with_header_lock_retry(lambda: self._store_header_batch(chain_id, pending), chain_id, deadline)  # type: ignore[attr-defined]
        except Exception:
            # at_height is None for the trailing partial flush, so name the batch itself.
            logger.exception(
                "Failed to store bridge header batch for %s at height=%s (batch %s..%s, %d headers)",
                chain_id,
                at_height,
                pending[0]["height"],
                pending[-1]["height"],
                len(pending),
            )
            return False
        return True

    def _ledger_register(self, record: CrossChainTransfer) -> None:
        """Best-effort write-through registration with the shared ledger (#696).

        No-op when ``BRIDGE_LEDGER_URL`` is unset; failures are logged inside
        the client and never propagate — the local row is the fallback.
        """
        try:
            from .bridge_ledger import ledger_enabled, register_transfer

            if ledger_enabled():
                register_transfer(record)
        except Exception:
            logger.exception("Bridge ledger register failed for %s", record.transfer_id)

    def _ledger_writeback(
        self,
        transfer_id: str,
        status: str,
        target_tx_hash: str | None = None,
        proof_hash: str | None = None,
    ) -> None:
        """Best-effort status writeback to the shared ledger (#696)."""
        try:
            from .bridge_ledger import ledger_enabled, write_status

            if ledger_enabled():
                write_status(transfer_id, status, target_tx_hash=target_tx_hash, proof_hash=proof_hash)
        except Exception:
            logger.exception("Bridge ledger status writeback failed for %s", transfer_id)

    def _ledger_local_record(self, row: dict[str, Any]) -> CrossChainTransfer | None:
        """Materialise a service-side pending row into the local source-chain store.

        ``build_proof``/``confirm_transfer`` read the ``CrossChainTransfer``
        record from the local store of the transfer's source chain; a row that
        only exists in the shared ledger would otherwise relay as "Transfer
        not found". The upsert is keyed on ``transfer_id`` and never overwrites
        a row the local store already holds.
        """
        transfer_id = str(row.get("transfer_id") or "")
        source_chain = str(row.get("source_chain") or "")
        if not transfer_id or not source_chain:
            return None
        try:
            with self._session_for(source_chain) as session:
                record = session.get(CrossChainTransfer, transfer_id)
                if record is None:
                    lock_time = row.get("lock_time")
                    record = CrossChainTransfer(
                        transfer_id=transfer_id,
                        source_chain=source_chain,
                        target_chain=str(row.get("target_chain") or ""),
                        sender=str(row.get("sender") or ""),
                        recipient=str(row.get("recipient") or ""),
                        amount=int(row.get("amount") or 0),
                        asset=str(row.get("asset") or "native"),
                        status="pending",
                        source_tx_hash=row.get("source_tx_hash") or transfer_id,
                        lock_time=datetime.fromisoformat(lock_time) if isinstance(lock_time, str) else None,
                        release_amount=row.get("release_amount"),
                    )
                    session.add(record)
                    session.commit()
                    session.refresh(record)
                return record
        except Exception:
            logger.exception("Bridge relayer: failed to materialise ledger row %s locally", transfer_id[:16])
            return None

    def _pending_worklist(self, chain_id: str, own_chain: str) -> list[BridgeTransfer]:
        """Relayer worklist for source chain ``chain_id``.

        #696: when ``BRIDGE_LEDGER_URL`` is set the list comes from the shared
        ledger's ``GET /pending?target_chain=<own_chain>`` instead of the local
        ``status='pending'`` scan — an unreachable service yields an empty list
        (skip the pass). Unset URL = today's local-scan behaviour.
        """
        from .bridge_ledger import fetch_pending, ledger_enabled

        if not ledger_enabled():
            return [
                t for t in self.list_pending_transfers(chain_id) if t.source_chain == chain_id and t.target_chain == own_chain
            ]
        rows = fetch_pending(own_chain)
        if rows is None:
            return []
        worklist: list[BridgeTransfer] = []
        for row in rows:
            if row.get("source_chain") != chain_id:
                continue
            record = self._ledger_local_record(row)
            if record is not None and record.status == "pending":
                worklist.append(self._build_transfer_from_record(record))
        return worklist

    def _relay_pending_transfers(self, chain_id: str, deadline: float | None = None) -> int:
        """Confirm pending source-chain transfers whose lock has finality.

        GAP-47 relayer: for each transfer locked on ``chain_id``, once the
        lock transaction is sealed in a block and that block's stored header
        has enough confirmations, build the real Merkle proof and run the
        normal ``confirm_transfer`` verification + release path. Transfers
        that cannot yet settle (lock unsealed, finality pending, validator
        set missing) stay ``pending`` — the honest intermediate state.

        Scope (#662): this process only relays transfers whose target is its
        OWN ``settings.chain_id``. ``confirm_transfer`` queues the
        BRIDGE_RELEASE into this process's mempool, and only the proposer of
        this node's own chain drains that mempool — relaying a transfer that
        targets another chain would mint a release tx no block producer ever
        seals, stranding the lock. A bc-2 rpc therefore relays only
        bc-2-target transfers and an island rpc only island-target ones; the
        rpc of the target chain sees the pending row because it follows the
        source chain's store.
        """
        relayed = 0
        own_chain = str(getattr(settings, "chain_id", "") or "")
        pending = self._pending_worklist(chain_id, own_chain)
        for transfer in pending:
            if deadline is not None and time.monotonic() >= deadline:
                logger.info(
                    "Bridge relayer for %s hit the pass deadline after %s relayed; deferring the rest",
                    chain_id,
                    relayed,
                )
                break
            if not self._chain_db_ready(transfer.target_chain):
                # The release must be written to the target chain's store;
                # when this node does not host it, the transfer keeps its
                # honest pending/locked state instead of erroring each pass.
                logger.debug(
                    "Bridge relayer: target store for %s unavailable here; %s stays pending",
                    transfer.target_chain,
                    transfer.transfer_id[:16],
                )
                continue
            try:
                proof = self.build_proof(transfer.transfer_id, source_chain=chain_id)
            except ValueError as e:
                # Lock not sealed into a block yet, or the source block is not
                # available — normal intermediate state, retry next pass.
                logger.debug("Bridge relayer: %s not ready for confirm: %s", transfer.transfer_id[:16], e)
                continue
            except Exception:
                logger.exception("Bridge relayer: failed to build proof for %s", transfer.transfer_id[:16])
                continue
            try:
                confirmed = self.confirm_transfer(transfer.transfer_id, proof)
                relayed += 1
                # #696: monotonic writeback to the shared ledger so the row
                # the relayer consumed leaves the pending worklist.
                self._ledger_writeback(
                    transfer.transfer_id,
                    "confirmed",
                    target_tx_hash=confirmed.target_tx_hash,
                    proof_hash=hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest(),
                )
            except ValueError as e:
                # Finality/threshold/validator-set failures stay pending; the
                # record keeps its honest state and we retry next interval.
                logger.debug("Bridge relayer: confirm for %s rejected: %s", transfer.transfer_id[:16], e)
            except Exception:
                logger.exception("Bridge relayer: confirm failed for %s", transfer.transfer_id[:16])
        return relayed

    def _report_abandoned_pass(self, abandoned: dict[str, int], chain_id: str, pass_timeout: float) -> None:
        """Count consecutive watchdog abandonments per chain; CRITICAL on repeats —
        an abandoned to_thread worker cannot be cancelled, so back-to-back
        abandonments mean the pass is wedged or too big to finish."""
        streak = abandoned.get(chain_id, 0) + 1
        abandoned[chain_id] = streak
        if streak >= 2:
            logger.critical(
                "Bridge finalizer pass for chain %s abandoned %d consecutive times (>%ss each); worker threads cannot be cancelled — investigate the pass work or the writer it waits on",
                chain_id,
                streak,
                pass_timeout,
            )
        else:
            logger.error(
                "Bridge finalizer pass for chain %s exceeded %ss; worker thread abandoned, other chains continue",
                chain_id,
                pass_timeout,
            )

    async def start_finalizer(self) -> None:
        """Background loop that finalises bridge releases once they are block-sealed.

        Each pass (every ``bridge_monitor_interval`` seconds) runs three real
        phases on every known chain (GAP-47):
        1. mirror newly produced/synced block headers into the bridge header
           table so proofs have a finality anchor,
        2. relay pending transfers: build their Merkle proof and run the
           standard confirm path once the lock has finality,
        3. mark confirmed transfers ``completed`` once the release tx is
           sealed on the target chain.

        Each pass runs on a worker thread, never on the event loop -- see the
        comment on the call below.
        """
        interval = getattr(settings, "bridge_monitor_interval", 60)
        relayer_enabled = getattr(settings, "bridge_relayer_enabled", True) and getattr(
            settings, "bridge_release_enabled", False
        )
        # Chains whose worker-thread pass has not returned yet. to_thread
        # cannot be cancelled once running: a pass that blocks inside sqlite
        # (the producing process holding a write lock, or a long backfill
        # commit at ~0.75 headers/second) would otherwise stall the whole
        # loop — every later chain's phases go silent with nothing logged,
        # which is how a relay phase can never fire while the loop looks
        # healthy. Each pass gets ``bridge_finalizer_pass_timeout`` seconds;
        # on timeout the worker is abandoned (marked in-flight so passes for
        # the same chain never stack) and the loop moves on to the next chain.
        pass_timeout = float(getattr(settings, "bridge_finalizer_pass_timeout", 900))
        inflight = getattr(self, "_finalizer_inflight", None)
        if inflight is None:
            self._finalizer_inflight: set[str] = set()
            inflight = self._finalizer_inflight
        abandoned = getattr(self, "_finalizer_abandoned", None)
        if abandoned is None:
            self._finalizer_abandoned: dict[str, int] = {}
            abandoned = self._finalizer_abandoned
        while True:
            try:
                for chain_id in self._known_chains():
                    if chain_id in inflight:
                        logger.debug(
                            "Bridge finalizer pass for chain %s still running in a worker thread; skipping",
                            chain_id,
                        )
                        continue
                    inflight.add(chain_id)

                    deadline = time.monotonic() + pass_timeout * _FINALIZER_DEADLINE_FRACTION

                    def _run(cid: str = chain_id, pass_deadline: float = deadline) -> None:
                        # The mark is cleared inside the worker so it is
                        # released when the pass actually returns — not when
                        # wait_for gave up on it — which keeps two passes for
                        # the same chain from ever running concurrently.
                        try:
                            self._finalizer_pass(cid, relayer_enabled, pass_deadline)
                            abandoned[cid] = 0
                        finally:
                            inflight.discard(cid)

                    # Every phase of a pass is synchronous SQLModel work, and the
                    # first pass after a restart is a backfill: one commit per
                    # block the bridge header table is behind, measured at 0.75
                    # headers/second. Called inline it never yielded, and this
                    # coroutine is started as a task during lifespan startup --
                    # so uvicorn never finished starting and the RPC socket
                    # stayed unbound for the whole backfill, while systemd
                    # reported the unit active (running) throughout.
                    #
                    # to_thread is sound here: _finalizer_pass and everything it
                    # calls are plain ``def``, and every session is opened inside
                    # the call from a NullPool engine with check_same_thread
                    # disabled, so no session or connection crosses a thread.
                    try:
                        await asyncio.wait_for(asyncio.to_thread(_run), timeout=pass_timeout)
                    except TimeoutError:
                        self._report_abandoned_pass(abandoned, chain_id, pass_timeout)
                    except Exception:
                        logger.exception("Bridge finalizer pass failed for chain %s", chain_id)
            except Exception:
                logger.exception("Bridge release finalizer loop failed")
            await asyncio.sleep(interval)

    def _finalizer_pass(self, chain_id: str, relayer_enabled: bool, deadline: float | None = None) -> None:
        """Run one finalizer pass for a single chain: header sync, relay, finalize.

        ``deadline`` is a time.monotonic() budget the caller derives from
        ``bridge_finalizer_pass_timeout``: each phase checkpoints it between
        items so a pass commits what it has and returns instead of being
        abandoned mid-transaction by the to_thread watchdog.
        """
        if not self._chain_db_ready(chain_id):
            return

        try:
            stored = self._sync_local_chain_headers(chain_id, deadline)
            if stored:
                logger.debug("Stored %s bridge headers for chain %s", stored, chain_id)
        except Exception:
            logger.exception("Bridge header sync failed for chain %s", chain_id)
        self._finalizer_relay_and_finalize(chain_id, relayer_enabled, deadline)

    def _finalizer_relay_and_finalize(self, chain_id: str, relayer_enabled: bool, deadline: float | None) -> None:
        """Relay + finalize phases of a pass, gated on the shared deadline."""

        def _expired() -> bool:
            return deadline is not None and time.monotonic() >= deadline

        if relayer_enabled and not _expired():
            try:
                relayed = self._relay_pending_transfers(chain_id, deadline)
                if relayed:
                    logger.info("Relayed %s bridge transfers on chain %s", relayed, chain_id)
            except Exception:
                logger.exception("Bridge relayer failed for chain %s", chain_id)
        if not _expired():
            try:
                count = self._finalize_confirmed_transfers(chain_id, deadline)
                if count:
                    logger.info("Finalized %s bridge transfers on chain %s", count, chain_id)
            except Exception:
                logger.exception("Bridge finalizer failed for chain %s", chain_id)

    def _build_transfer_from_record(self, record: CrossChainTransfer, proof: dict[str, Any] | None = None) -> BridgeTransfer:
        """Build BridgeTransfer from database record."""
        return BridgeTransfer(
            transfer_id=record.transfer_id,
            source_chain=record.source_chain,
            target_chain=record.target_chain,
            sender=record.sender,
            recipient=record.recipient,
            amount=record.amount,
            asset=record.asset,
            status=BridgeStatus(record.status),
            source_tx_hash=record.source_tx_hash,
            target_tx_hash=record.target_tx_hash,
            lock_time=record.lock_time,
            confirm_time=record.confirm_time,
            proof=proof,
        )
