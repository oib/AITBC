"""
Island Manager
Manages island membership, multi-island support, and island operations for federated mesh
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import time

logger = logging.getLogger(__name__)


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
    chain_id: str
    status: IslandStatus
    joined_at: float
    is_hub: bool = False
    peer_count: int = 0


@dataclass
class BridgeRequest:
    """Represents a bridge request to another island"""
    request_id: str
    source_island_id: str
    target_island_id: str
    source_node_id: str
    timestamp: float
    status: str = "pending"  # pending, approved, rejected


class IslandManager:
    """Manages island membership and operations for federated mesh"""
    
    def __init__(self, local_node_id: str, default_island_id: str, default_chain_id: str):
        self.local_node_id = local_node_id
        self.default_island_id = default_island_id
        self.default_chain_id = default_chain_id
        
        # Island memberships
        self.islands: Dict[str, IslandMembership] = {}
        
        # Bridge requests
        self.bridge_requests: Dict[str, BridgeRequest] = {}
        
        # Active bridges
        self.active_bridges: Set[str] = set()  # island_ids we're bridged to
        
        # Island peers (island_id -> set of node_ids)
        self.island_peers: Dict[str, Set[str]] = {}
        
        self.running = False
        
        # Initialize with default island
        self._initialize_default_island()
    
    def _initialize_default_island(self):
        """Initialize with default island membership"""
        self.islands[self.default_island_id] = IslandMembership(
            island_id=self.default_island_id,
            island_name="default",
            chain_id=self.default_chain_id,
            status=IslandStatus.ACTIVE,
            joined_at=time.time(),
            is_hub=False
        )
        self.island_peers[self.default_island_id] = set()
        logger.info(f"Initialized with default island: {self.default_island_id}")
    
    async def start(self):
        """Start island manager"""
        self.running = True
        logger.info(f"Starting island manager for node {self.local_node_id}")
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self._bridge_request_monitor()),
            asyncio.create_task(self._island_health_check())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Island manager error: {e}")
        finally:
            self.running = False
    
    async def stop(self):
        """Stop island manager"""
        self.running = False
        logger.info("Stopping island manager")
    
    def join_island(self, island_id: str, island_name: str, chain_id: str, is_hub: bool = False) -> bool:
        """Join an island"""
        if island_id in self.islands:
            logger.warning(f"Already member of island {island_id}")
            return False
        
        self.islands[island_id] = IslandMembership(
            island_id=island_id,
            island_name=island_name,
            chain_id=chain_id,
            status=IslandStatus.ACTIVE,
            joined_at=time.time(),
            is_hub=is_hub
        )
        self.island_peers[island_id] = set()
        
        logger.info(f"Joined island {island_id} (name: {island_name}, chain: {chain_id})")
        return True
    
    def leave_island(self, island_id: str) -> bool:
        """Leave an island"""
        if island_id == self.default_island_id:
            logger.warning("Cannot leave default island")
            return False
        
        if island_id not in self.islands:
            logger.warning(f"Not member of island {island_id}")
            return False
        
        # Remove from active bridges if present
        if island_id in self.active_bridges:
            self.active_bridges.remove(island_id)
        
        del self.islands[island_id]
        if island_id in self.island_peers:
            del self.island_peers[island_id]
        
        logger.info(f"Left island {island_id}")
        return True
    
    def request_bridge(self, target_island_id: str) -> str:
        """Request bridge to another island"""
        if target_island_id in self.islands:
            logger.warning(f"Already member of island {target_island_id}")
            return ""
        
        request_id = str(uuid.uuid4())
        request = BridgeRequest(
            request_id=request_id,
            source_island_id=self.default_island_id,
            target_island_id=target_island_id,
            source_node_id=self.local_node_id,
            timestamp=time.time(),
            status="pending"
        )
        
        self.bridge_requests[request_id] = request
        logger.info(f"Requested bridge to island {target_island_id} (request_id: {request_id})")
        
        return request_id
    
    def approve_bridge_request(self, request_id: str) -> bool:
        """Approve a bridge request"""
        if request_id not in self.bridge_requests:
            logger.warning(f"Unknown bridge request {request_id}")
            return False
        
        request = self.bridge_requests[request_id]
        request.status = "approved"
        
        # Add target island to our membership
        self.join_island(request.target_island_id, f"bridge-{request.target_island_id[:8]}", f"bridge-{request.target_island_id[:8]}", is_hub=False)
        
        # Mark as active bridge
        self.active_bridges.add(request.target_island_id)
        
        logger.info(f"Approved bridge request {request_id} to island {request.target_island_id}")
        return True
    
    def reject_bridge_request(self, request_id: str) -> bool:
        """Reject a bridge request"""
        if request_id not in self.bridge_requests:
            logger.warning(f"Unknown bridge request {request_id}")
            return False
        
        request = self.bridge_requests[request_id]
        request.status = "rejected"
        
        logger.info(f"Rejected bridge request {request_id} from island {request.source_island_id}")
        return True
    
    def get_island_peers(self, island_id: str) -> Set[str]:
        """Get peers in a specific island"""
        return self.island_peers.get(island_id, set()).copy()
    
    def add_island_peer(self, island_id: str, node_id: str):
        """Add a peer to an island"""
        if island_id not in self.island_peers:
            self.island_peers[island_id] = set()
        
        self.island_peers[island_id].add(node_id)
        
        # Update peer count
        if island_id in self.islands:
            self.islands[island_id].peer_count = len(self.island_peers[island_id])
    
    def remove_island_peer(self, island_id: str, node_id: str):
        """Remove a peer from an island"""
        if island_id in self.island_peers:
            self.island_peers[island_id].discard(node_id)
            
            # Update peer count
            if island_id in self.islands:
                self.islands[island_id].peer_count = len(self.island_peers[island_id])
    
    def get_island_info(self, island_id: str) -> Optional[IslandMembership]:
        """Get information about an island"""
        return self.islands.get(island_id)
    
    def get_all_islands(self) -> List[IslandMembership]:
        """Get all island memberships"""
        return list(self.islands.values())
    
    def get_active_bridges(self) -> List[str]:
        """Get list of active bridge island IDs"""
        return list(self.active_bridges)
    
    def get_bridge_requests(self) -> List[BridgeRequest]:
        """Get all bridge requests"""
        return list(self.bridge_requests.values())
    
    def is_member_of_island(self, island_id: str) -> bool:
        """Check if node is member of an island"""
        return island_id in self.islands
    
    def is_bridged_to_island(self, island_id: str) -> bool:
        """Check if node has active bridge to an island"""
        return island_id in self.active_bridges
    
    async def _bridge_request_monitor(self):
        """Monitor bridge requests and handle timeouts"""
        while self.running:
            try:
                current_time = time.time()
                
                # Remove expired requests (older than 1 hour)
                expired_requests = [
                    req_id for req_id, req in self.bridge_requests.items()
                    if current_time - req.timestamp > 3600 and req.status == "pending"
                ]
                
                for req_id in expired_requests:
                    del self.bridge_requests[req_id]
                    logger.info(f"Removed expired bridge request {req_id}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Bridge request monitor error: {e}")
                await asyncio.sleep(10)
    
    async def _island_health_check(self):
        """Check health of island memberships"""
        while self.running:
            try:
                # Check for inactive islands (no peers for 10 minutes)
                current_time = time.time()
                
                for island_id, membership in list(self.islands.items()):
                    if island_id == self.default_island_id:
                        continue  # Don't deactivate default island
                    
                    peer_count = len(self.island_peers.get(island_id, set()))
                    
                    if peer_count == 0 and membership.status == IslandStatus.ACTIVE:
                        # Check how long it's been inactive
                        if current_time - membership.joined_at > 600:  # 10 minutes
                            membership.status = IslandStatus.INACTIVE
                            logger.warning(f"Island {island_id} marked as inactive (no peers)")
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Island health check error: {e}")
                await asyncio.sleep(10)


# Global island manager instance
island_manager_instance: Optional[IslandManager] = None


def get_island_manager() -> Optional[IslandManager]:
    """Get global island manager instance"""
    return island_manager_instance


def create_island_manager(node_id: str, default_island_id: str, default_chain_id: str) -> IslandManager:
    """Create and set global island manager instance"""
    global island_manager_instance
    island_manager_instance = IslandManager(node_id, default_island_id, default_chain_id)
    return island_manager_instance
