"""
Hub Manager
Manages hub operations, peer list sharing, and hub registration for federated mesh
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HubStatus(Enum):
    """Hub registration status"""
    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    PENDING = "pending"


@dataclass
class HubInfo:
    """Information about a hub node"""
    node_id: str
    address: str
    port: int
    island_id: str
    island_name: str
    public_address: Optional[str] = None
    public_port: Optional[int] = None
    registered_at: float = 0
    last_seen: float = 0
    peer_count: int = 0


@dataclass
class PeerInfo:
    """Information about a peer"""
    node_id: str
    address: str
    port: int
    island_id: str
    is_hub: bool
    public_address: Optional[str] = None
    public_port: Optional[int] = None
    last_seen: float = 0


class HubManager:
    """Manages hub operations for federated mesh"""
    
    def __init__(self, local_node_id: str, local_address: str, local_port: int, island_id: str, island_name: str):
        self.local_node_id = local_node_id
        self.local_address = local_address
        self.local_port = local_port
        self.island_id = island_id
        self.island_name = island_name
        
        # Hub registration status
        self.is_hub = False
        self.hub_status = HubStatus.UNREGISTERED
        self.registered_at: Optional[float] = None
        
        # Known hubs
        self.known_hubs: Dict[str, HubInfo] = {}  # node_id -> HubInfo
        
        # Peer registry (for providing peer lists)
        self.peer_registry: Dict[str, PeerInfo] = {}  # node_id -> PeerInfo
        
        # Island peers (island_id -> set of node_ids)
        self.island_peers: Dict[str, Set[str]] = {}
        
        self.running = False
        
        # Initialize island peers for our island
        self.island_peers[self.island_id] = set()
    
    def register_as_hub(self, public_address: Optional[str] = None, public_port: Optional[int] = None) -> bool:
        """Register this node as a hub"""
        if self.is_hub:
            logger.warning("Already registered as hub")
            return False
        
        self.is_hub = True
        self.hub_status = HubStatus.REGISTERED
        self.registered_at = time.time()
        
        # Add self to known hubs
        self.known_hubs[self.local_node_id] = HubInfo(
            node_id=self.local_node_id,
            address=self.local_address,
            port=self.local_port,
            island_id=self.island_id,
            island_name=self.island_name,
            public_address=public_address,
            public_port=public_port,
            registered_at=time.time(),
            last_seen=time.time()
        )
        
        logger.info(f"Registered as hub for island {self.island_id}")
        return True
    
    def unregister_as_hub(self) -> bool:
        """Unregister this node as a hub"""
        if not self.is_hub:
            logger.warning("Not registered as hub")
            return False
        
        self.is_hub = False
        self.hub_status = HubStatus.UNREGISTERED
        self.registered_at = None
        
        # Remove self from known hubs
        if self.local_node_id in self.known_hubs:
            del self.known_hubs[self.local_node_id]
        
        logger.info(f"Unregistered as hub for island {self.island_id}")
        return True
    
    def register_peer(self, peer_info: PeerInfo) -> bool:
        """Register a peer in the registry"""
        self.peer_registry[peer_info.node_id] = peer_info
        
        # Add to island peers
        if peer_info.island_id not in self.island_peers:
            self.island_peers[peer_info.island_id] = set()
        self.island_peers[peer_info.island_id].add(peer_info.node_id)
        
        # Update hub peer count if peer is a hub
        if peer_info.is_hub and peer_info.node_id in self.known_hubs:
            self.known_hubs[peer_info.node_id].peer_count = len(self.island_peers.get(peer_info.island_id, set()))
        
        logger.debug(f"Registered peer {peer_info.node_id} in island {peer_info.island_id}")
        return True
    
    def unregister_peer(self, node_id: str) -> bool:
        """Unregister a peer from the registry"""
        if node_id not in self.peer_registry:
            return False
        
        peer_info = self.peer_registry[node_id]
        
        # Remove from island peers
        if peer_info.island_id in self.island_peers:
            self.island_peers[peer_info.island_id].discard(node_id)
        
        del self.peer_registry[node_id]
        
        # Update hub peer count
        if node_id in self.known_hubs:
            self.known_hubs[node_id].peer_count = len(self.island_peers.get(self.known_hubs[node_id].island_id, set()))
        
        logger.debug(f"Unregistered peer {node_id}")
        return True
    
    def add_known_hub(self, hub_info: HubInfo):
        """Add a known hub to the registry"""
        self.known_hubs[hub_info.node_id] = hub_info
        logger.info(f"Added known hub {hub_info.node_id} for island {hub_info.island_id}")
    
    def remove_known_hub(self, node_id: str) -> bool:
        """Remove a known hub from the registry"""
        if node_id not in self.known_hubs:
            return False
        
        del self.known_hubs[node_id]
        logger.info(f"Removed known hub {node_id}")
        return True
    
    def get_peer_list(self, island_id: str) -> List[PeerInfo]:
        """Get peer list for a specific island"""
        peers = []
        for node_id, peer_info in self.peer_registry.items():
            if peer_info.island_id == island_id:
                peers.append(peer_info)
        return peers
    
    def get_hub_list(self, island_id: Optional[str] = None) -> List[HubInfo]:
        """Get list of known hubs, optionally filtered by island"""
        hubs = []
        for hub_info in self.known_hubs.values():
            if island_id is None or hub_info.island_id == island_id:
                hubs.append(hub_info)
        return hubs
    
    def get_island_peers(self, island_id: str) -> Set[str]:
        """Get set of peer node IDs in an island"""
        return self.island_peers.get(island_id, set()).copy()
    
    def get_peer_count(self, island_id: str) -> int:
        """Get number of peers in an island"""
        return len(self.island_peers.get(island_id, set()))
    
    def get_hub_info(self, node_id: str) -> Optional[HubInfo]:
        """Get information about a specific hub"""
        return self.known_hubs.get(node_id)
    
    def get_peer_info(self, node_id: str) -> Optional[PeerInfo]:
        """Get information about a specific peer"""
        return self.peer_registry.get(node_id)
    
    def update_peer_last_seen(self, node_id: str):
        """Update the last seen time for a peer"""
        if node_id in self.peer_registry:
            self.peer_registry[node_id].last_seen = time.time()
        
        if node_id in self.known_hubs:
            self.known_hubs[node_id].last_seen = time.time()
    
    async def start(self):
        """Start hub manager"""
        self.running = True
        logger.info(f"Starting hub manager for node {self.local_node_id}")
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self._hub_health_check()),
            asyncio.create_task(self._peer_cleanup())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Hub manager error: {e}")
        finally:
            self.running = False
    
    async def stop(self):
        """Stop hub manager"""
        self.running = False
        logger.info("Stopping hub manager")
    
    async def _hub_health_check(self):
        """Check health of known hubs"""
        while self.running:
            try:
                current_time = time.time()
                
                # Check for offline hubs (not seen for 10 minutes)
                offline_hubs = []
                for node_id, hub_info in self.known_hubs.items():
                    if current_time - hub_info.last_seen > 600:
                        offline_hubs.append(node_id)
                        logger.warning(f"Hub {node_id} appears to be offline")
                
                # Remove offline hubs (keep self if we're a hub)
                for node_id in offline_hubs:
                    if node_id != self.local_node_id:
                        self.remove_known_hub(node_id)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Hub health check error: {e}")
                await asyncio.sleep(10)
    
    async def _peer_cleanup(self):
        """Clean up stale peer entries"""
        while self.running:
            try:
                current_time = time.time()
                
                # Remove peers not seen for 5 minutes
                stale_peers = []
                for node_id, peer_info in self.peer_registry.items():
                    if current_time - peer_info.last_seen > 300:
                        stale_peers.append(node_id)
                
                for node_id in stale_peers:
                    self.unregister_peer(node_id)
                    logger.debug(f"Removed stale peer {node_id}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Peer cleanup error: {e}")
                await asyncio.sleep(10)


# Global hub manager instance
hub_manager_instance: Optional[HubManager] = None


def get_hub_manager() -> Optional[HubManager]:
    """Get global hub manager instance"""
    return hub_manager_instance


def create_hub_manager(node_id: str, address: str, port: int, island_id: str, island_name: str) -> HubManager:
    """Create and set global hub manager instance"""
    global hub_manager_instance
    hub_manager_instance = HubManager(node_id, address, port, island_id, island_name)
    return hub_manager_instance
