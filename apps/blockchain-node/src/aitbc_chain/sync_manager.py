"""Single owner of block and state sync for a chain node."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aitbc.async_tasks import create_task_with_logging
from aitbc.sync import PeerCapability, PeerCapabilityTracker, SyncSourceResolver

from .config import settings
from .database import init_db, session_scope
from .gossip.broker import TopicSubscription, create_backend, gossip_broker
from .logger import get_logger
from .metrics import metrics_registry
from .subscription_client import SubscriptionClient
from .sync import ChainSync
from .sync_divergence import clear_divergence, report_divergence
from .sync_validator import ImportResult

logger = get_logger(__name__)


class SyncMode(StrEnum):
    DISCONNECTED = "disconnected"
    CATCH_UP = "catch_up"
    PUSH = "push"
    SYNCED = "synced"
    STATE_SYNC = "state_sync"
    ERROR = "error"
    SKIPPED = "skipped"


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
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SyncManager:
    """Owns all block and state sync for one or more chains.

    Runs in its own process or can be embedded in aitbc-blockchain-node.
    When embedded it does not take over the node's gossip_broker lifecycle
    and does not start a separate database initialisation path.
    """

    def __init__(
        self,
        chains: list[str] | None = None,
        node_id: str | None = None,
        proposer_id: str | None = None,
        production_chains: list[str] | None = None,
        use_gossip: bool | None = None,
        use_subscription: bool | None = None,
        own_gossip: bool = False,
        skip_init_db: bool = False,
    ) -> None:
        self._chains = chains or self._resolve_chains()
        self._node_id = node_id or settings.proposer_id or settings.p2p_node_id or "unknown"
        self._proposer_id = proposer_id or settings.proposer_id or ""
        self._production_chains = set(production_chains or self._resolve_production_chains())
        self._use_gossip = use_gossip if use_gossip is not None else getattr(settings, "sync_manager_use_gossip", True)
        self._use_subscription = (
            use_subscription if use_subscription is not None else getattr(settings, "sync_manager_use_subscription", True)
        )
        self._own_gossip = own_gossip
        self._skip_init_db = skip_init_db
        self._source_resolver = SyncSourceResolver(
            sync_sources=settings.chain_sync_sources,
            default_url=settings.default_peer_rpc_url,
        )
        self._peer_tracker = PeerCapabilityTracker()
        self._chain_states: dict[str, ChainSyncState] = {}
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self._subscription_clients: list[SubscriptionClient] = []
        self._gossip_started = False

        # Block-level deduplication so multiple push paths (gossip and
        # subscription) cannot import the same block twice.
        self._dedup_ttl = getattr(settings, "sync_manager_block_dedup_ttl", 300.0)
        self._dedup_max_size = getattr(settings, "sync_manager_block_dedup_max_size", 10000)
        self._seen_blocks: OrderedDict[tuple[str, str], float] = OrderedDict()

        # Rejection/divergence counters that outlive a single ChainSync call.
        self._rejection_counts: dict[str, int] = {}
        self._consecutive_divergence: dict[str, int] = {}

    @staticmethod
    def _resolve_chains() -> list[str]:
        chains = [c.strip() for c in settings.supported_chains.split(",") if c.strip()]
        if not chains and settings.chain_id:
            chains = [settings.chain_id]
        return chains

    @staticmethod
    def _resolve_production_chains() -> list[str]:
        """Return the list of chains this node is configured to produce blocks for."""
        chains_str = getattr(settings, "block_production_chains", "")
        if not chains_str:
            return []
        return [c.strip() for c in chains_str.split(",") if c.strip()]

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

        if self._own_gossip:
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
            if not self._skip_init_db:
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
        for client in self._subscription_clients:
            try:
                await client.stop()
            except Exception as e:
                logger.warning("Error stopping subscription client: %s", e)
        for state in self._chain_states.values():
            if state.bulk_task and not state.bulk_task.done():
                state.bulk_task.cancel()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._own_gossip:
            await gossip_broker.shutdown()

    def register_sync_peer(
        self,
        chain_id: str,
        peer_id: str,
        rpc_url: str,
        block_range: tuple[int, int],
        has_state: bool = True,
    ) -> None:
        """Register a peer with the ChainSync for a given chain."""
        state = self._chain_states.get(chain_id)
        if state and state.chain_sync:
            state.chain_sync.register_sync_peer(peer_id, rpc_url, block_range, has_state)
        self._peer_tracker.register_peer(
            PeerCapability(peer_id=peer_id, rpc_url=rpc_url, block_range=block_range, has_state=has_state)
        )

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
            self.register_sync_peer(
                chain_id=chain_id,
                peer_id=url,
                rpc_url=url,
                block_range=(0, 2**31 - 1),
                has_state=True,
            )
            logger.info("Registered parallel sync peer", extra={"chain_id": chain_id, "peer": url})

    def _should_sync_remote(self, chain_id: str, source_url: str | None) -> bool:
        """Do not pull a chain from the default peer if we produce it locally."""
        if not source_url:
            return False
        if not self._source_resolver.is_fallback_source(chain_id):
            return True
        if (
            chain_id in self._production_chains
            and settings.blockchain_mode == "hub"
            and not settings.multi_validator_consensus_enabled
        ):
            logger.info(
                "Skipping sync for locally-produced chain %s (no remote source configured)",
                chain_id,
            )
            return False
        return True

    def _should_skip_block(self, chain_id: str, block_data: dict[str, Any]) -> bool:
        """Skip blocks this node produced itself."""
        if settings.blockchain_mode != "hub":
            return False
        if block_data.get("proposer") != self._proposer_id:
            return False
        if chain_id in self._production_chains:
            return True
        return False

    def _prune_seen_blocks(self) -> None:
        now = time.monotonic()
        expired: list[tuple[str, str]] = []
        for key, ts in self._seen_blocks.items():
            if now - ts > self._dedup_ttl:
                expired.append(key)
            else:
                break
        for key in expired:
            del self._seen_blocks[key]
        while len(self._seen_blocks) > self._dedup_max_size:
            self._seen_blocks.popitem(last=False)

    def _block_hash(self, block_data: dict[str, Any]) -> str:
        if isinstance(block_data, dict) and "hash" in block_data:
            return str(block_data["hash"])
        payload = json.dumps(block_data, sort_keys=True, default=str)
        return "0x" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def handle_block(
        self,
        chain_id: str,
        block_data: dict[str, Any],
        source: str = "gossip",
    ) -> ImportResult:
        """Import a block through a deduplication layer.

        This is the single entry point for all block push paths (gossip,
        subscription, or future transports).
        """
        if not isinstance(block_data, dict):
            logger.warning("Unexpected block message type", extra={"type": type(block_data), "source": source})
            return ImportResult(accepted=False, height=-1, block_hash="", reason="Non-dict block message")

        if self._should_skip_block(chain_id, block_data):
            logger.debug(
                "Skipping self-proposed block %s from %s",
                block_data.get("height"),
                source,
            )
            return ImportResult(
                accepted=False,
                height=block_data.get("height", -1),
                block_hash=block_data.get("hash", ""),
                reason="Self-proposed block",
            )

        block_hash = self._block_hash(block_data)
        state = self._chain_states.get(chain_id)
        if not state or not state.chain_sync:
            return ImportResult(
                accepted=False,
                height=block_data.get("height", -1),
                block_hash=block_hash,
                reason="Chain not managed by SyncManager",
            )

        async with state.lock:
            self._prune_seen_blocks()
            key = (chain_id, block_hash)
            now = time.monotonic()
            if key in self._seen_blocks and now - self._seen_blocks[key] <= self._dedup_ttl:
                logger.debug(
                    "Block already imported (dedup)",
                    extra={"chain_id": chain_id, "height": block_data.get("height"), "hash": block_hash, "source": source},
                )
                return ImportResult(
                    accepted=False,
                    height=block_data.get("height", -1),
                    block_hash=block_hash,
                    reason="Block already imported (dedup)",
                )

            result = state.chain_sync.import_block(
                block_data,
                transactions=block_data.get("transactions"),
                skip_state_root_validation=not settings.sync_state_root_validation_enabled,
            )

            # Cache the block hash for accepted results and for permanent rejection
            # reasons, so that the same block delivered over multiple transports
            # (gossip + subscription) does not produce duplicate import attempts.
            # Transient reasons (gaps, divergence, state-root mismatches) must not be
            # cached because the block can become valid after catch-up / state sync.
            transient_reason = (
                "Gap detected" in result.reason
                or result.diverged
                or "state root" in result.reason.lower()
                or "stale" in result.reason.lower()
            )
            if result.accepted or not transient_reason:
                self._seen_blocks[key] = now

            if result.accepted:
                state.last_push_at = time.time()
                state.last_local_height = block_data.get("height", state.last_local_height)
                if state.mode in (SyncMode.CATCH_UP, SyncMode.ERROR):
                    state.mode = SyncMode.PUSH
                self._reset_rejection_counts(chain_id)
                self._consecutive_divergence.pop(chain_id, None)
                clear_divergence(chain_id)
                logger.info(
                    "Block imported via %s sync",
                    source,
                    extra={
                        "chain_id": chain_id,
                        "height": block_data.get("height"),
                        "hash": block_hash,
                        "source": source,
                    },
                )
                if source == "subscription":
                    metrics_registry.increment("subscription_blocks_received_total")
                metrics_registry.increment("sync_manager_blocks_received_total")
                return result

            logger.debug(
                "Block not accepted via %s (height=%s): %s",
                source,
                block_data.get("height"),
                result.reason,
                extra={"chain_id": chain_id, "hash": block_hash, "source": source, "reason": result.reason},
            )

            if "Gap detected" in result.reason:
                state.mode = SyncMode.CATCH_UP
                await self._maybe_force_bulk(chain_id)
            elif result.diverged:
                self._consecutive_divergence[chain_id] = self._consecutive_divergence.get(chain_id, 0) + 1
                threshold = getattr(settings, "divergence_after_rejections", 3)
                if self._consecutive_divergence[chain_id] >= threshold:
                    div = state.chain_sync.detect_divergence(
                        self._source_resolver.get_sync_source(chain_id) or "",
                        block_data.get("height", -1),
                        block_hash,
                    )
                    if div is not None:
                        report_divergence(chain_id, div)
            else:
                self._consecutive_divergence.pop(chain_id, None)
                if self._is_state_root_rejection(result.reason):
                    rejection_count = state.chain_sync._rejection_counts.get(chain_id, 0)
                    threshold = settings.auto_resync_after_rejections
                    if rejection_count >= threshold and settings.auto_resync_enabled:
                        logger.warning(
                            "State root rejection threshold reached (%s/%s) for chain %s, forcing catch-up",
                            rejection_count,
                            threshold,
                            chain_id,
                        )
                        await self._maybe_force_bulk(chain_id)

            return result

    @staticmethod
    def _is_state_root_rejection(reason: str) -> bool:
        return "state root" in reason.lower()

    def _reset_rejection_counts(self, chain_id: str) -> None:
        state = self._chain_states.get(chain_id)
        if state and state.chain_sync:
            state.chain_sync._reset_rejection_counter(chain_id)

    async def _maybe_force_bulk(self, chain_id: str) -> None:
        """Start a bulk pull for chain_id if one is not already running."""
        state = self._chain_states.get(chain_id)
        if not state or not state.chain_sync:
            return

        source_url = self._source_resolver.get_sync_source(chain_id)
        if not self._should_sync_remote(chain_id, source_url):
            return

        if state.bulk_task and not state.bulk_task.done():
            return

        state.bulk_task = create_task_with_logging(
            self._bulk_pull(chain_id, source_url),
            name=f"sync_manager_bulk_{chain_id}",
        )

    async def _chain_loop(self, chain_id: str) -> None:
        state = self._chain_states[chain_id]

        if self._use_gossip:
            state.gossip_sub = await gossip_broker.subscribe(f"blocks.{chain_id}")
            gossip_task = create_task_with_logging(
                self._gossip_consumer(chain_id),
                name=f"sync_manager_gossip_{chain_id}",
            )
            self._tasks.append(gossip_task)

        if self._use_subscription:
            source_url = self._source_resolver.get_sync_source(chain_id)
            if source_url and self._should_sync_remote(chain_id, source_url):
                client = SubscriptionClient(
                    source_url,
                    self._node_id,
                    chain_id,
                    on_block=block_data_callback(self, chain_id),
                )
                self._subscription_clients.append(client)
                sub_task = create_task_with_logging(
                    client.start(),
                    name=f"sync_manager_subscription_{chain_id}",
                )
                self._tasks.append(sub_task)

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
                await self.handle_block(chain_id, block_data, source="gossip")
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
        if not source_url or not self._should_sync_remote(chain_id, source_url):
            state.mode = (
                SyncMode.SKIPPED
                if source_url and not self._should_sync_remote(chain_id, source_url)
                else SyncMode.DISCONNECTED
            )
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

        if gap > getattr(settings, "auto_sync_threshold", 10) or state.mode == SyncMode.CATCH_UP:
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
                # When the node is fully caught up, delta sync would otherwise be
                # called with from_height == to_height, which the source endpoint
                # rejects as an invalid zero-block range. Ask for the diff of the
                # last block instead (to_height - 1 -> to_height) so the state sync
                # actually validates the head instead of falling back to a full sync.
                if state.last_local_height == state.last_remote_height and state.last_remote_height > 0:
                    delta_from = state.last_remote_height - 1
                    delta_to = state.last_remote_height
                else:
                    delta_from = state.last_local_height
                    delta_to = state.last_remote_height
                await state.chain_sync.delta_sync_from(source_url, delta_from, delta_to)
            except Exception as e:
                logger.warning("State sync failed for %s: %s", chain_id, e)
            state.mode = SyncMode.SYNCED

        if gap == 0:
            return getattr(settings, "sync_manager_synced_poll_interval", 30.0)
        return poll

    async def _bulk_pull(self, chain_id: str, source_url: str) -> int:
        state = self._chain_states[chain_id]
        if not state.chain_sync:
            return 0

        state.chain_sync.register_sync_peer(
            source_url,
            source_url,
            (0, 2**31 - 1),
            has_state=True,
        )

        logger.info("Starting bulk pull", extra={"chain_id": chain_id, "source": source_url})
        imported = await state.chain_sync.bulk_import_from(source_url)
        return imported


def block_data_callback(manager: SyncManager, chain_id: str) -> Any:
    """Build a callback the SubscriptionClient can call when a block arrives."""
    from functools import partial

    return partial(manager.handle_block, chain_id, source="subscription")
