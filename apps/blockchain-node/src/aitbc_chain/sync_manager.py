"""Single owner of block and state sync for a chain node."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from aitbc.async_tasks import create_task_with_logging
from aitbc.sync import PeerCapability, PeerCapabilityTracker, SyncSourceResolver

from .config import settings
from .database import init_db, session_scope
from .gossip.broker import TopicSubscription, create_backend, gossip_broker
from .logger import get_logger
from .sync import ChainSync

logger = get_logger(__name__)


class SyncMode(StrEnum):
    DISCONNECTED = "disconnected"
    CATCH_UP = "catch_up"
    PUSH = "push"
    SYNCED = "synced"
    STATE_SYNC = "state_sync"
    ERROR = "error"


@dataclass
class ChainSyncState:
    chain_id: str
    mode: SyncMode = SyncMode.DISCONNECTED
    chain_sync: ChainSync | None = None
    last_local_height: int = -1
    last_remote_height: int = -1
    last_push_at: float = 0.0
    last_bulk_at: float = 0.0
    last_state_sync_at: float = 0.0
    bulk_task: asyncio.Task | None = None
    bulk_backoff_until: float = 0.0
    bulk_error_count: int = 0
    gossip_sub: TopicSubscription | None = None
    error_count: int = 0


class SyncManager:
    """Owns all block and state sync for one or more chains.

    Runs in its own process or can be embedded in aitbc-blockchain-node.
    """

    def __init__(
        self,
        chains: list[str] | None = None,
        node_id: str | None = None,
    ) -> None:
        self._chains = chains or self._resolve_chains()
        self._node_id = node_id or settings.proposer_id or settings.p2p_node_id or "unknown"
        self._source_resolver = SyncSourceResolver(
            sync_sources=settings.chain_sync_sources,
            default_url=settings.default_peer_rpc_url,
        )
        self._peer_tracker = PeerCapabilityTracker()
        self._chain_states: dict[str, ChainSyncState] = {}
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self._gossip_started = False

    @staticmethod
    def _resolve_chains() -> list[str]:
        chains = [c.strip() for c in settings.supported_chains.split(",") if c.strip()]
        if not chains and settings.chain_id:
            chains = [settings.chain_id]
        return chains

    def get_sync_status(self, chain_id: str) -> dict[str, Any]:
        state = self._chain_states.get(chain_id)
        if not state:
            return {"chain_id": chain_id, "mode": "unknown"}
        return {
            "chain_id": chain_id,
            "mode": state.mode,
            "local_height": state.last_local_height,
            "remote_height": state.last_remote_height,
            "gap": max(0, state.last_remote_height - state.last_local_height),
            "last_push_seconds_ago": time.time() - state.last_push_at if state.last_push_at else None,
        }

    async def start(self) -> None:
        logger.info("Starting SyncManager", extra={"chains": self._chains, "node_id": self._node_id})

        backend = create_backend(
            settings.gossip_backend,
            broadcast_url=settings.gossip_broadcast_url,
            websocket_url=settings.gossip_websocket_url,
        )
        await gossip_broker.set_backend(backend)
        self._gossip_started = True

        for chain_id in self._chains:
            self._register_static_peers(chain_id)

        for chain_id in self._chains:
            state = ChainSyncState(chain_id=chain_id)
            self._chain_states[chain_id] = state
            init_db(chain_id)
            state.chain_sync = ChainSync(
                session_factory=lambda cid=chain_id: session_scope(cid),
                chain_id=chain_id,
                validate_signatures=settings.sync_validate_signatures,
                batch_size=settings.min_bulk_sync_batch_size,
                poll_interval=settings.periodic_sync_interval,
            )
            task = create_task_with_logging(
                self._chain_loop(chain_id),
                name=f"sync_manager_chain_{chain_id}",
            )
            self._tasks.append(task)

    async def stop(self) -> None:
        logger.info("Stopping SyncManager")
        self._stop_event.set()
        for state in self._chain_states.values():
            if state.bulk_task and not state.bulk_task.done():
                state.bulk_task.cancel()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await gossip_broker.shutdown()

    async def force_catch_up(self, chain_id: str) -> None:
        state = self._chain_states.get(chain_id)
        if state:
            state.mode = SyncMode.CATCH_UP

    def _register_static_peers(self, chain_id: str) -> None:
        extra = getattr(settings, "sync_parallel_peers", "")
        if not extra:
            return
        for entry in extra.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if ":" in entry and not entry.startswith("http"):
                cid, url = entry.split(":", 1)
                cid, url = cid.strip(), url.strip()
            else:
                cid, url = chain_id, entry
            if cid != chain_id:
                continue
            if not url.startswith("http"):
                url = f"http://{url}"
            self._peer_tracker.register_peer(
                PeerCapability(
                    peer_id=url,
                    rpc_url=url,
                    block_range=(0, 2**31 - 1),
                    has_state=True,
                )
            )
            logger.info("Registered parallel sync peer", extra={"chain_id": chain_id, "peer": url})

    async def _chain_loop(self, chain_id: str) -> None:
        state = self._chain_states[chain_id]
        gossip_task: asyncio.Task | None = None

        if getattr(settings, "sync_manager_use_gossip", True):
            state.gossip_sub = await gossip_broker.subscribe(f"blocks.{chain_id}")
            gossip_task = create_task_with_logging(
                self._gossip_consumer(chain_id),
                name=f"sync_manager_gossip_{chain_id}",
            )
            self._tasks.append(gossip_task)

        while not self._stop_event.is_set():
            interval = getattr(settings, "sync_manager_poll_interval", 5.0)
            try:
                interval = await self._tick(chain_id)
                state.error_count = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Sync loop error for %s: %s", chain_id, e)
                state.error_count += 1
                state.mode = SyncMode.ERROR
                interval = min(30, 2**state.error_count)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _gossip_consumer(self, chain_id: str) -> None:
        state = self._chain_states[chain_id]
        if not state.gossip_sub:
            return
        try:
            while not self._stop_event.is_set():
                try:
                    block_data = await asyncio.wait_for(state.gossip_sub.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if isinstance(block_data, str):
                    block_data = json.loads(block_data)
                if not isinstance(block_data, dict):
                    logger.warning("Unexpected gossip message type", extra={"type": type(block_data)})
                    continue
                height = block_data.get("height", 0)
                if not state.chain_sync:
                    continue
                try:
                    result = state.chain_sync.import_block(
                        block_data,
                        transactions=block_data.get("transactions"),
                        skip_state_root_validation=False,
                    )
                except Exception as import_exc:
                    logger.warning("Gossip import raised exception at height %s: %s", height, import_exc)
                    logger.debug("Gossip import traceback", exc_info=True)
                    continue
                if result.accepted:
                    state.last_push_at = time.time()
                    state.last_local_height = height
                    if state.mode in (SyncMode.CATCH_UP, SyncMode.ERROR):
                        state.mode = SyncMode.PUSH
                elif "Gap detected" in result.reason:
                    logger.info("Gossip gap at %s, switching to bulk pull", height)
                    state.mode = SyncMode.CATCH_UP
                else:
                    logger.debug("Gossip block %s not accepted: %s", height, result.reason)
        except asyncio.CancelledError:
            pass
        finally:
            if state.gossip_sub:
                state.gossip_sub.close()

    async def _tick(self, chain_id: str) -> float:
        state = self._chain_states[chain_id]
        if not state.chain_sync:
            return getattr(settings, "sync_manager_poll_interval", 5.0)

        poll = getattr(settings, "sync_manager_poll_interval", 5.0)

        if time.time() < state.bulk_backoff_until:
            return min(poll, state.bulk_backoff_until - time.time())

        if state.bulk_task and not state.bulk_task.done():
            try:
                done, _ = await asyncio.wait({state.bulk_task}, timeout=0.1)
                if not done:
                    return poll
                imported = state.bulk_task.result()
                state.last_bulk_at = time.time()
                state.bulk_task = None
                state.bulk_backoff_until = 0.0
                state.bulk_error_count = 0
                logger.info("Bulk pull completed", extra={"chain_id": chain_id, "imported": imported})
                state.error_count = 0
            except Exception as e:
                logger.error("Bulk pull failed for %s: %s", chain_id, e)
                state.bulk_task = None
                state.bulk_error_count += 1
                state.bulk_backoff_until = time.time() + min(60, 2**state.bulk_error_count)
                return min(poll, state.bulk_backoff_until - time.time())
            return poll

        source_url = self._source_resolver.get_sync_source(chain_id)
        if not source_url:
            state.mode = SyncMode.DISCONNECTED
            return poll

        try:
            _, remote_height = await state.chain_sync.peer_head_divergence(source_url)
            state.last_remote_height = remote_height
        except Exception as e:
            logger.warning("Failed to get remote head for %s: %s", chain_id, e)
            state.mode = SyncMode.DISCONNECTED
            return poll

        state.last_local_height = state.chain_sync.get_local_height()
        gap = max(0, state.last_remote_height - state.last_local_height)

        if gap > getattr(settings, "auto_sync_threshold", 10):
            state.mode = SyncMode.CATCH_UP
            state.bulk_task = create_task_with_logging(
                self._bulk_pull(chain_id, source_url),
                name=f"sync_manager_bulk_{chain_id}",
            )
            return poll

        state.mode = SyncMode.SYNCED if gap == 0 else SyncMode.PUSH

        if (
            gap <= getattr(settings, "state_sync_max_gap", 10)
            and state.mode == SyncMode.SYNCED
            and time.time() - state.last_state_sync_at > getattr(settings, "sync_manager_state_sync_interval", 300)
        ):
            state.mode = SyncMode.STATE_SYNC
            state.last_state_sync_at = time.time()
            try:
                await state.chain_sync.sync_state_from(source_url)
            except Exception as e:
                logger.warning("State sync failed for %s: %s", chain_id, e)
            state.mode = SyncMode.SYNCED

        return poll

    async def _bulk_pull(self, chain_id: str, source_url: str) -> int:
        state = self._chain_states[chain_id]
        if not state.chain_sync:
            return 0

        self._peer_tracker.register_peer(
            PeerCapability(
                peer_id=source_url,
                rpc_url=source_url,
                block_range=(0, 2**31 - 1),
                has_state=True,
            )
        )

        logger.info("Starting bulk pull", extra={"chain_id": chain_id, "source": source_url})
        imported = await state.chain_sync.bulk_import_from(source_url)
        return imported
