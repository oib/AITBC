"""
Bridge Manager
Manages island bridging with manual approval for federated mesh
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from enum import Enum

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class BridgeState(Enum):
    """Bridge connection state"""

    PENDING = "pending"
    APPROVED = "approved"
    ACTIVE = "active"
    REJECTED = "rejected"
    TERMINATED = "terminated"


@dataclass
class BridgeConnection:
    """Represents a bridge connection between islands"""

    bridge_id: str
    source_island_id: str
    target_island_id: str
    source_node_id: str
    target_node_id: str | None
    state: BridgeState
    requested_at: float
    approved_at: float | None = None
    activated_at: float | None = None
    terminated_at: float | None = None
    rejection_reason: str | None = None


class BridgeManager:
    """Manages island bridging with manual approval"""

    def __init__(self, local_node_id: str, local_island_id: str):
        self.local_node_id = local_node_id
        self.local_island_id = local_island_id
        self.bridges: dict[str, BridgeConnection] = {}
        self.active_bridges: dict[str, str] = {}
        self.pending_requests: dict[str, str] = {}
        self.running = False

    def request_bridge(self, target_island_id: str) -> str:
        """
        Request a bridge to another island

        Returns:
            Bridge request ID
        """
        if target_island_id == self.local_island_id:
            logger.warning("Cannot bridge to own island")
            return ""
        if target_island_id in self.active_bridges:
            logger.warning("Already have active bridge to %s", target_island_id)
            return self.active_bridges[target_island_id]
        if target_island_id in self.pending_requests:
            logger.warning("Already have pending bridge request to %s", target_island_id)
            return self.pending_requests[target_island_id]
        bridge_id = str(uuid.uuid4())
        bridge = BridgeConnection(
            bridge_id=bridge_id,
            source_island_id=self.local_island_id,
            target_island_id=target_island_id,
            source_node_id=self.local_node_id,
            target_node_id=None,
            state=BridgeState.PENDING,
            requested_at=time.time(),
        )
        self.bridges[bridge_id] = bridge
        self.pending_requests[target_island_id] = bridge_id
        logger.info("Requested bridge to island %s (bridge_id: %s)", target_island_id, bridge_id)
        return bridge_id

    def approve_bridge_request(self, bridge_id: str, approving_node_id: str) -> bool:
        """
        Approve a bridge request

        Args:
            bridge_id: Bridge request ID
            approving_node_id: Node ID approving the bridge

        Returns:
            True if successful, False otherwise
        """
        if bridge_id not in self.bridges:
            logger.warning("Unknown bridge request %s", bridge_id)
            return False
        bridge = self.bridges[bridge_id]
        if bridge.state != BridgeState.PENDING:
            logger.warning("Bridge %s not in pending state", bridge_id)
            return False
        bridge.state = BridgeState.APPROVED
        bridge.target_node_id = approving_node_id
        bridge.approved_at = time.time()
        if bridge.target_island_id in self.pending_requests:
            del self.pending_requests[bridge.target_island_id]
        self.active_bridges[bridge.target_island_id] = bridge_id
        logger.info("Approved bridge request %s to island %s", bridge_id, bridge.target_island_id)
        return True

    def reject_bridge_request(self, bridge_id: str, reason: str = "") -> bool:
        """
        Reject a bridge request

        Args:
            bridge_id: Bridge request ID
            reason: Rejection reason

        Returns:
            True if successful, False otherwise
        """
        if bridge_id not in self.bridges:
            logger.warning("Unknown bridge request %s", bridge_id)
            return False
        bridge = self.bridges[bridge_id]
        if bridge.state != BridgeState.PENDING:
            logger.warning("Bridge %s not in pending state", bridge_id)
            return False
        bridge.state = BridgeState.REJECTED
        bridge.rejection_reason = reason
        if bridge.target_island_id in self.pending_requests:
            del self.pending_requests[bridge.target_island_id]
        logger.info("Rejected bridge request %s (reason: %s)", bridge_id, reason)
        return True

    def establish_bridge(self, bridge_id: str) -> bool:
        """
        Establish an active bridge connection

        Args:
            bridge_id: Bridge ID to establish

        Returns:
            True if successful, False otherwise
        """
        if bridge_id not in self.bridges:
            logger.warning("Unknown bridge %s", bridge_id)
            return False
        bridge = self.bridges[bridge_id]
        if bridge.state != BridgeState.APPROVED:
            logger.warning("Bridge %s not approved", bridge_id)
            return False
        bridge.state = BridgeState.ACTIVE
        bridge.activated_at = time.time()
        logger.info("Established active bridge %s to island %s", bridge_id, bridge.target_island_id)
        return True

    def terminate_bridge(self, island_id: str) -> bool:
        """
        Terminate a bridge to an island

        Args:
            island_id: Target island ID

        Returns:
            True if successful, False otherwise
        """
        if island_id not in self.active_bridges:
            logger.warning("No active bridge to island %s", island_id)
            return False
        bridge_id = self.active_bridges[island_id]
        bridge = self.bridges[bridge_id]
        bridge.state = BridgeState.TERMINATED
        bridge.terminated_at = time.time()
        del self.active_bridges[island_id]
        logger.info("Terminated bridge to island %s", island_id)
        return True

    def get_bridge_status(self, island_id: str) -> BridgeConnection | None:
        """
        Get bridge status for a specific island

        Args:
            island_id: Target island ID

        Returns:
            Bridge connection if exists, None otherwise
        """
        if island_id in self.active_bridges:
            bridge_id = self.active_bridges[island_id]
            return self.bridges[bridge_id]
        if island_id in self.pending_requests:
            bridge_id = self.pending_requests[island_id]
            return self.bridges[bridge_id]
        return None

    def get_all_bridges(self) -> list[BridgeConnection]:
        """Get all bridge connections"""
        return list(self.bridges.values())

    def get_active_bridges(self) -> list[BridgeConnection]:
        """Get all active bridge connections"""
        return [self.bridges[bridge_id] for bridge_id in self.active_bridges.values()]

    def get_pending_requests(self) -> list[BridgeConnection]:
        """Get all pending bridge requests"""
        return [self.bridges[bridge_id] for bridge_id in self.pending_requests.values()]

    def is_bridged_to_island(self, island_id: str) -> bool:
        """Check if node has active bridge to an island"""
        return island_id in self.active_bridges

    def has_pending_request(self, island_id: str) -> bool:
        """Check if node has pending bridge request to an island"""
        return island_id in self.pending_requests

    async def start(self) -> None:
        """Start bridge manager"""
        self.running = True
        logger.info("Starting bridge manager")
        tasks = [asyncio.create_task(self._request_timeout_monitor())]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error("Bridge manager error: %s", e)
        finally:
            self.running = False

    async def stop(self) -> None:
        """Stop bridge manager"""
        self.running = False
        logger.info("Stopping bridge manager")

    async def _request_timeout_monitor(self) -> None:
        """Monitor bridge requests and handle timeouts"""
        while self.running:
            try:
                current_time = time.time()
                expired_requests = []
                for island_id, bridge_id in list(self.pending_requests.items()):
                    bridge = self.bridges[bridge_id]
                    if current_time - bridge.requested_at > 3600:
                        expired_requests.append((island_id, bridge_id))
                for island_id, bridge_id in expired_requests:
                    bridge = self.bridges[bridge_id]
                    bridge.state = BridgeState.REJECTED
                    bridge.rejection_reason = "Request timeout"
                    del self.pending_requests[island_id]
                    logger.info("Removed expired bridge request %s to island %s", bridge_id, island_id)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error("Bridge request timeout monitor error: %s", e)
                await asyncio.sleep(10)


bridge_manager_instance: BridgeManager | None = None


def get_bridge_manager() -> BridgeManager | None:
    """Get global bridge manager instance"""
    return bridge_manager_instance


def create_bridge_manager(node_id: str, island_id: str) -> BridgeManager:
    """Create and set global bridge manager instance"""
    global bridge_manager_instance
    bridge_manager_instance = BridgeManager(node_id, island_id)
    return bridge_manager_instance
