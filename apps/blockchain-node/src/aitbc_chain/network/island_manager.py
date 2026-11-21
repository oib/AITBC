"""
Island Manager
Manages island membership, multi-island support, and island operations for federated mesh
"""

import asyncio
import fcntl
import json
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging

from ..config import settings

logger = get_logger(__name__)


class IslandStatus(Enum):
    """Island membership status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    BRIDGING = "bridging"


@dataclass
class IslandMembership:
    """Represents a node's membership in an island"""

    island_id: str
    island_name: str
    chain_ids: list[str]
    status: IslandStatus
    joined_at: float
    is_hub: bool = False
    peer_count: int = 0
    role: str = "follower"

    @property
    def chain_id(self) -> str:
        """Backward compat: returns first chain_id."""
        return self.chain_ids[0] if self.chain_ids else ""


@dataclass
class BridgeRequest:
    """Represents a bridge request to another island"""

    request_id: str
    source_island_id: str
    target_island_id: str
    source_node_id: str
    timestamp: float
    status: str = "pending"


class IslandManager:
    """Manages island membership and operations for federated mesh"""

    def __init__(
        self,
        local_node_id: str,
        default_island_id: str,
        default_chain_id: str,
        is_hub: bool | None = None,
        role: str | None = None,
        state_path: str | Path | None = None,
    ):
        self.local_node_id = local_node_id
        self.default_island_id = default_island_id
        self.default_chain_id = default_chain_id
        self.is_hub = is_hub if is_hub is not None else settings.is_hub
        self.role = role if role is not None else settings.blockchain_mode
        # state_path=None → auto: AITBC_ISLAND_STATE_FILE, else an
        # ``islands.json`` beside chain.db so every uvicorn worker (and the
        # separate blockchain-node vs blockchain-rpc processes) shares one
        # membership store (#2389). ``state_path="memory"`` or the env value
        # ``memory``/``none``/``off`` keeps the legacy per-process behaviour
        # for tests and dev.
        mode = str(state_path).lower() if state_path is not None else ""
        self._state_forced_memory = mode in ("memory", "none", "off")
        self._state_path_arg = None if state_path is None or self._state_forced_memory else Path(state_path)
        self._resolved_state_path: Path | None = None
        self._state_mode_locked = self._state_forced_memory
        self.islands: dict[str, IslandMembership] = {}
        self.bridge_requests: dict[str, BridgeRequest] = {}
        self.active_bridges: set[str] = set()
        self.island_peers: dict[str, set[str]] = {}
        self.running = False
        self._initialize_default_island()
        self._load_state()

    # ------------------------------------------------------------------
    # shared-state persistence (#2389)
    # ------------------------------------------------------------------

    def _resolve_state_path(self) -> Path | None:
        """State file path, or None for in-memory mode. Resolved lazily so
        the module-level singleton picks up the engine once the app is up."""
        if self._state_path_arg is not None:
            return self._state_path_arg
        if self._state_mode_locked:
            return self._resolved_state_path
        mode = os.getenv("AITBC_ISLAND_STATE_FILE", "").strip()
        if mode.lower() in ("memory", "none", "off"):
            self._state_mode_locked = True
            return None
        if mode:
            self._resolved_state_path = Path(mode)
        else:
            try:
                from ..chain_id import ChainIdNotConfigured
                from ..database import ChainDbMissingError, ForeignChainDbError, get_engine

                db = get_engine().url.database
            except (ChainIdNotConfigured, ChainDbMissingError, ForeignChainDbError, ValueError, OSError):
                # engine not up yet / unavailable — retry next call
                return None
            if not db or db == ":memory:":
                self._state_mode_locked = True
                self._resolved_state_path = None
                return None
            self._resolved_state_path = Path(db).parent / "islands.json"
        self._state_mode_locked = True
        return self._resolved_state_path

    @staticmethod
    def _membership_to_dict(membership: IslandMembership) -> dict[str, Any]:
        # peer_count is derived per-process from island_peers — never persisted.
        return {
            "island_id": membership.island_id,
            "island_name": membership.island_name,
            "chain_ids": list(membership.chain_ids),
            "status": membership.status.value,
            "joined_at": membership.joined_at,
            "is_hub": membership.is_hub,
            "role": membership.role,
        }

    @staticmethod
    def _membership_from_dict(raw: dict[str, Any]) -> IslandMembership:
        return IslandMembership(
            island_id=str(raw["island_id"]),
            island_name=str(raw.get("island_name", "")),
            chain_ids=[str(c) for c in raw.get("chain_ids") or []],
            status=IslandStatus(str(raw["status"])),
            joined_at=float(raw.get("joined_at", 0.0)),
            is_hub=bool(raw.get("is_hub", False)),
            role=str(raw.get("role", "follower")),
        )

    def _default_membership(self) -> IslandMembership:
        return IslandMembership(
            island_id=self.default_island_id,
            island_name="default",
            chain_ids=[self.default_chain_id],
            status=IslandStatus.ACTIVE,
            joined_at=time.time(),
            is_hub=self.is_hub,
            role=self.role,
        )

    def _initialize_default_island(self) -> None:
        """Initialize with default island membership"""
        self.islands[self.default_island_id] = self._default_membership()
        self.island_peers[self.default_island_id] = set()
        logger.info("Initialized with default island: %s (hub=%s, role=%s)", self.default_island_id, self.is_hub, self.role)

    def _load_state(self) -> None:
        """Reload memberships from the shared state file (no lock — the file
        is replaced atomically, so a torn read is impossible)."""
        path = self._resolve_state_path()
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text())
            persisted = {
                str(k): self._membership_from_dict(v) for k, v in (data.get("islands") or {}).items() if isinstance(v, dict)
            }
        except (OSError, ValueError, TypeError, KeyError) as e:
            logger.error("Island state file %s unreadable/corrupt: %s", path, e)
            return
        # peer_count is per-process (derived from island_peers); recompute it
        # after syncing the peer sets below rather than trusting the cache.
        self.islands = persisted
        if self.default_island_id not in self.islands:
            # The default island is always a membership of this node — never
            # let a state file written before it existed hide it.
            self.islands[self.default_island_id] = self._default_membership()
        for island_id in self.islands:
            self.island_peers.setdefault(island_id, set())
        for island_id in list(self.island_peers):
            if island_id not in self.islands:
                del self.island_peers[island_id]
        for island_id, membership in self.islands.items():
            membership.peer_count = len(self.island_peers.get(island_id, set()))

    def _save_state(self) -> None:
        path = self._resolve_state_path()
        if path is None:
            return
        payload = {
            "version": 1,
            "islands": {iid: self._membership_to_dict(m) for iid, m in self.islands.items()},
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, path)
        except OSError as e:
            logger.error("Failed to persist island state to %s: %s", path, e)

    @contextmanager
    def _state_transaction(self) -> Iterator[None]:
        """Exclusive cross-process mutation: flock, reload, yield, save."""
        path = self._resolve_state_path()
        if path is None:
            yield
            return
        lock_path = path.with_name(path.name + ".lock")
        try:
            lock_file = open(lock_path, "a+b")
        except OSError as e:
            logger.error("Island state lock %s unavailable: %s — operating unlocked", lock_path, e)
            self._load_state()
            yield
            self._save_state()
            return
        with lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                self._load_state()
                yield
                self._save_state()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _refresh(self) -> None:
        """Reads see the latest committed state in file mode."""
        if self._resolve_state_path() is not None:
            self._load_state()

    async def start(self) -> None:
        """Start island manager"""
        self.running = True
        logger.info("Starting island manager for node %s", self.local_node_id)
        tasks = [
            create_task_with_logging(self._bridge_request_monitor(), name="island_bridge_request_monitor"),
            create_task_with_logging(self._island_health_check(), name="island_health_check"),
        ]
        try:
            await asyncio.gather(*tasks)
        except (OSError, ValueError, TypeError, RuntimeError, AttributeError, LookupError) as e:
            logger.error("Island manager error: %s", e)
        finally:
            self.running = False

    async def stop(self) -> None:
        """Stop island manager"""
        self.running = False
        logger.info("Stopping island manager")

    def join_island(
        self,
        island_id: str,
        island_name: str,
        chain_id: str | list[str],
        is_hub: bool = False,
        role: str = "follower",
    ) -> bool:
        """Join an island. Accepts single chain_id (str) or multiple chain_ids (list)."""
        chain_ids = [chain_id] if isinstance(chain_id, str) else list(chain_id)
        if not chain_ids:
            logger.warning("Cannot join island %s with empty chain_ids", island_id)
            return False
        with self._state_transaction():
            if island_id in self.islands:
                logger.warning("Already member of island %s", island_id)
                return False
            self.islands[island_id] = IslandMembership(
                island_id=island_id,
                island_name=island_name,
                chain_ids=chain_ids,
                status=IslandStatus.ACTIVE,
                joined_at=time.time(),
                is_hub=is_hub,
                role=role,
            )
        self.island_peers[island_id] = set()
        logger.info("Joined island %s (name: %s, chains: %s)", island_id, island_name, chain_ids)
        return True

    def leave_island(self, island_id: str) -> str:
        """Leave an island. Cleans up all chain resources.

        Returns a machine-readable code: ``"left"``, ``"forbidden_default"``
        or ``"not_member"``.
        """
        if island_id == self.default_island_id:
            logger.warning("Cannot leave default island")
            return "forbidden_default"
        with self._state_transaction():
            membership = self.islands.get(island_id)
            if membership is None:
                logger.warning("Not member of island %s", island_id)
                return "not_member"
            chain_ids = list(membership.chain_ids)
            del self.islands[island_id]
        # Clean up chain resources (databases) outside the state lock.
        for chain_id in chain_ids:
            try:
                from ..database import shutdown_db

                shutdown_db(chain_id)
                logger.info("Shut down database for chain %s on island %s", chain_id, island_id)
            except (
                ImportError,
                SQLAlchemyError,
                OSError,
                ValueError,
                TypeError,
                RuntimeError,
                AttributeError,
                LookupError,
            ) as e:
                logger.warning("Failed to shut down database for chain %s: %s", chain_id, e)
        if island_id in self.active_bridges:
            self.active_bridges.remove(island_id)
        self.island_peers.pop(island_id, None)
        logger.info("Left island %s (cleaned up %d chains)", island_id, len(chain_ids))
        return "left"

    def request_bridge(self, target_island_id: str) -> str:
        """Request bridge to another island"""
        self._refresh()
        if target_island_id in self.islands:
            logger.warning("Already member of island %s", target_island_id)
            return ""
        request_id = str(uuid.uuid4())
        request = BridgeRequest(
            request_id=request_id,
            source_island_id=self.default_island_id,
            target_island_id=target_island_id,
            source_node_id=self.local_node_id,
            timestamp=time.time(),
            status="pending",
        )
        self.bridge_requests[request_id] = request
        logger.info("Requested bridge to island %s (request_id: %s)", target_island_id, request_id)
        return request_id

    def approve_bridge_request(self, request_id: str) -> bool:
        """Approve a bridge request"""
        if request_id not in self.bridge_requests:
            logger.warning("Unknown bridge request %s", request_id)
            return False
        request = self.bridge_requests[request_id]
        request.status = "approved"
        bridge_chain_id = f"bridge-{request.target_island_id[:8]}"
        self.join_island(
            request.target_island_id,
            f"bridge-{request.target_island_id[:8]}",
            bridge_chain_id,
            is_hub=False,
        )
        self.active_bridges.add(request.target_island_id)
        logger.info("Approved bridge request %s to island %s", request_id, request.target_island_id)
        return True

    def reject_bridge_request(self, request_id: str) -> bool:
        """Reject a bridge request"""
        if request_id not in self.bridge_requests:
            logger.warning("Unknown bridge request %s", request_id)
            return False
        request = self.bridge_requests[request_id]
        request.status = "rejected"
        logger.info("Rejected bridge request %s from island %s", request_id, request.source_island_id)
        return True

    def get_island_peers(self, island_id: str) -> set[str]:
        """Get peers in a specific island"""
        return self.island_peers.get(island_id, set()).copy()

    def add_island_peer(self, island_id: str, node_id: str) -> None:
        """Add a peer to an island"""
        if island_id not in self.island_peers:
            self.island_peers[island_id] = set()
        self.island_peers[island_id].add(node_id)
        if island_id in self.islands:
            self.islands[island_id].peer_count = len(self.island_peers[island_id])

    def remove_island_peer(self, island_id: str, node_id: str) -> None:
        """Remove a peer from an island"""
        if island_id in self.island_peers:
            self.island_peers[island_id].discard(node_id)
            if island_id in self.islands:
                self.islands[island_id].peer_count = len(self.island_peers[island_id])

    def get_island_info(self, island_id: str) -> IslandMembership | None:
        """Get information about an island"""
        self._refresh()
        return self.islands.get(island_id)

    def get_all_islands(self) -> list[IslandMembership]:
        """Get all island memberships"""
        self._refresh()
        return list(self.islands.values())

    def get_active_bridges(self) -> list[str]:
        """Get list of active bridge island IDs"""
        return list(self.active_bridges)

    def get_bridge_requests(self) -> list[BridgeRequest]:
        """Get all bridge requests"""
        return list(self.bridge_requests.values())

    def is_member_of_island(self, island_id: str) -> bool:
        """Check if node is member of an island"""
        self._refresh()
        return island_id in self.islands

    def is_bridged_to_island(self, island_id: str) -> bool:
        """Check if node has active bridge to an island"""
        return island_id in self.active_bridges

    async def _bridge_request_monitor(self) -> None:
        """Monitor bridge requests and handle timeouts"""
        while self.running:
            try:
                current_time = time.time()
                expired_requests = [
                    req_id
                    for req_id, req in self.bridge_requests.items()
                    if current_time - req.timestamp > 3600 and req.status == "pending"
                ]
                for req_id in expired_requests:
                    del self.bridge_requests[req_id]
                    logger.info("Removed expired bridge request %s", req_id)
                await asyncio.sleep(60)
            except (OSError, ValueError, TypeError, RuntimeError, AttributeError, LookupError) as e:
                logger.error("Bridge request monitor error: %s", e)
                await asyncio.sleep(10)

    def _mark_island_inactive(self, island_id: str, joined_at: float, current_time: float) -> None:
        """Persist an ACTIVE→INACTIVE health transition through the shared
        state transaction (reload-inside-lock, so a sibling worker's leave
        or re-join is never clobbered)."""
        with self._state_transaction():
            membership = self.islands.get(island_id)
            if (
                membership is None
                or island_id == self.default_island_id
                or membership.status != IslandStatus.ACTIVE
                or membership.joined_at != joined_at
            ):
                return
            if len(self.island_peers.get(island_id, set())) != 0:
                return
            if current_time - membership.joined_at <= 600:
                return
            membership.status = IslandStatus.INACTIVE
            logger.warning("Island %s marked as inactive (no peers)", island_id)

    async def _island_health_check(self) -> None:
        """Check health of island memberships"""
        while self.running:
            try:
                current_time = time.time()
                stale: list[tuple[str, float]] = []
                for island_id, membership in list(self.islands.items()):
                    if island_id == self.default_island_id:
                        continue
                    peer_count = len(self.island_peers.get(island_id, set()))
                    if peer_count == 0 and membership.status == IslandStatus.ACTIVE:
                        if current_time - membership.joined_at > 600:
                            stale.append((island_id, membership.joined_at))
                for island_id, joined_at in stale:
                    self._mark_island_inactive(island_id, joined_at, current_time)
                await asyncio.sleep(30)
            except (OSError, ValueError, TypeError, RuntimeError, AttributeError, LookupError) as e:
                logger.error("Island health check error: %s", e)
                await asyncio.sleep(10)


island_manager_instance: IslandManager | None = None


def get_island_manager() -> IslandManager | None:
    """Get global island manager instance"""
    return island_manager_instance


def create_island_manager(
    node_id: str,
    default_island_id: str,
    default_chain_id: str,
    is_hub: bool | None = None,
    role: str | None = None,
    state_path: str | Path | None = None,
) -> IslandManager:
    """Create and set global island manager instance"""
    global island_manager_instance
    island_manager_instance = IslandManager(
        node_id, default_island_id, default_chain_id, is_hub=is_hub, role=role, state_path=state_path
    )
    return island_manager_instance
