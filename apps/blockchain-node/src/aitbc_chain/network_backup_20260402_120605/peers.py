"""
Dynamic Peer Management
Handles peer join/leave operations and connection management
"""

import asyncio
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from .discovery import PeerNode, NodeStatus, P2PDiscovery
from .health import PeerHealthMonitor, HealthStatus

class PeerAction(Enum):
    JOIN = "join"
    LEAVE = "leave"
    DEMOTE = "demote"
    PROMOTE = "promote"
    BAN = "ban"

@dataclass
class PeerEvent:
    action: PeerAction
    node_id: str
    timestamp: float
    reason: str
    metadata: Dict

class DynamicPeerManager:
    """Manages dynamic peer connections and lifecycle"""
    
    def __init__(self, discovery: P2PDiscovery, health_monitor: PeerHealthMonitor):
        self.discovery = discovery
        self.health_monitor = health_monitor
        self.peer_events: List[PeerEvent] = []
        self.max_connections = 50
        self.min_connections = 8
        self.connection_retry_interval = 300  # 5 minutes
        self.ban_threshold = 0.1  # Reputation below this gets banned
        self.running = False
        
        # Peer management policies
        self.auto_reconnect = True
        self.auto_ban_malicious = True
        self.load_balance = True
    
    async def start_management(self):
        """Start peer management service"""
        self.running = True
        log_info("Starting dynamic peer management")
        
        while self.running:
            try:
                await self._manage_peer_connections()
                await self._enforce_peer_policies()
                await self._optimize_topology()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                log_error(f"Peer management error: {e}")
                await asyncio.sleep(10)
    
    async def stop_management(self):
        """Stop peer management service"""
        self.running = False
        log_info("Stopping dynamic peer management")
    
    async def _manage_peer_connections(self):
        """Manage peer connections based on current state"""
        current_peers = self.discovery.get_peer_count()
        
        if current_peers < self.min_connections:
            await self._discover_new_peers()
        elif current_peers > self.max_connections:
            await self._remove_excess_peers()
        
        # Reconnect to disconnected peers
        if self.auto_reconnect:
            await self._reconnect_disconnected_peers()
    
    async def _discover_new_peers(self):
        """Discover and connect to new peers"""
        log_info(f"Peer count ({self.discovery.get_peer_count()}) below minimum ({self.min_connections}), discovering new peers")
        
        # Request peer lists from existing connections
        for peer in self.discovery.get_peer_list():
            await self.discovery._request_peer_list(peer)
        
        # Try to connect to bootstrap nodes
        await self.discovery._connect_to_bootstrap_nodes()
    
    async def _remove_excess_peers(self):
        """Remove excess peers based on quality metrics"""
        log_info(f"Peer count ({self.discovery.get_peer_count()}) above maximum ({self.max_connections}), removing excess peers")
        
        peers = self.discovery.get_peer_list()
        
        # Sort peers by health score and reputation
        sorted_peers = sorted(
            peers,
            key=lambda p: (
                self.health_monitor.get_health_status(p.node_id).health_score if 
                self.health_monitor.get_health_status(p.node_id) else 0.0,
                p.reputation
            )
        )
        
        # Remove lowest quality peers
        excess_count = len(peers) - self.max_connections
        for i in range(excess_count):
            peer_to_remove = sorted_peers[i]
            await self._remove_peer(peer_to_remove.node_id, "Excess peer removed")
    
    async def _reconnect_disconnected_peers(self):
        """Reconnect to peers that went offline"""
        # Get recently disconnected peers
        all_health = self.health_monitor.get_all_health_status()
        
        for node_id, health in all_health.items():
            if (health.status == NodeStatus.OFFLINE and 
                time.time() - health.last_check < self.connection_retry_interval):
                
                # Try to reconnect
                peer = self.discovery.peers.get(node_id)
                if peer:
                    success = await self.discovery._connect_to_peer(peer.address, peer.port)
                    if success:
                        log_info(f"Reconnected to peer {node_id}")
    
    async def _enforce_peer_policies(self):
        """Enforce peer management policies"""
        if self.auto_ban_malicious:
            await self._ban_malicious_peers()
        
        await self._update_peer_reputations()
    
    async def _ban_malicious_peers(self):
        """Ban peers with malicious behavior"""
        for peer in self.discovery.get_peer_list():
            if peer.reputation < self.ban_threshold:
                await self._ban_peer(peer.node_id, "Reputation below threshold")
    
    async def _update_peer_reputations(self):
        """Update peer reputations based on health metrics"""
        for peer in self.discovery.get_peer_list():
            health = self.health_monitor.get_health_status(peer.node_id)
            
            if health:
                # Update reputation based on health score
                reputation_delta = (health.health_score - 0.5) * 0.1  # Small adjustments
                self.discovery.update_peer_reputation(peer.node_id, reputation_delta)
    
    async def _optimize_topology(self):
        """Optimize network topology for better performance"""
        if not self.load_balance:
            return
        
        peers = self.discovery.get_peer_list()
        healthy_peers = self.health_monitor.get_healthy_peers()
        
        # Prioritize connections to healthy peers
        for peer in peers:
            if peer.node_id not in healthy_peers:
                # Consider replacing unhealthy peer
                await self._consider_peer_replacement(peer)
    
    async def _consider_peer_replacement(self, unhealthy_peer: PeerNode):
        """Consider replacing unhealthy peer with better alternative"""
        # This would implement logic to find and connect to better peers
        # For now, just log the consideration
        log_info(f"Considering replacement for unhealthy peer {unhealthy_peer.node_id}")
    
    async def add_peer(self, address: str, port: int, public_key: str = "") -> bool:
        """Manually add a new peer"""
        try:
            success = await self.discovery._connect_to_peer(address, port)
            
            if success:
                # Record peer join event
                self._record_peer_event(PeerAction.JOIN, f"{address}:{port}", "Manual peer addition")
                log_info(f"Successfully added peer {address}:{port}")
                return True
            else:
                log_warn(f"Failed to add peer {address}:{port}")
                return False
                
        except Exception as e:
            log_error(f"Error adding peer {address}:{port}: {e}")
            return False
    
    async def remove_peer(self, node_id: str, reason: str = "Manual removal") -> bool:
        """Manually remove a peer"""
        return await self._remove_peer(node_id, reason)
    
    async def _remove_peer(self, node_id: str, reason: str) -> bool:
        """Remove peer from network"""
        try:
            if node_id in self.discovery.peers:
                peer = self.discovery.peers[node_id]
                
                # Close connection if open
                # This would be implemented with actual connection management
                
                # Remove from discovery
                del self.discovery.peers[node_id]
                
                # Remove from health monitoring
                if node_id in self.health_monitor.health_status:
                    del self.health_monitor.health_status[node_id]
                
                # Record peer leave event
                self._record_peer_event(PeerAction.LEAVE, node_id, reason)
                
                log_info(f"Removed peer {node_id}: {reason}")
                return True
            else:
                log_warn(f"Peer {node_id} not found for removal")
                return False
                
        except Exception as e:
            log_error(f"Error removing peer {node_id}: {e}")
            return False
    
    async def ban_peer(self, node_id: str, reason: str = "Banned by administrator") -> bool:
        """Ban a peer from the network"""
        return await self._ban_peer(node_id, reason)
    
    async def _ban_peer(self, node_id: str, reason: str) -> bool:
        """Ban peer and prevent reconnection"""
        success = await self._remove_peer(node_id, f"BANNED: {reason}")
        
        if success:
            # Record ban event
            self._record_peer_event(PeerAction.BAN, node_id, reason)
            
            # Add to ban list (would be persistent in real implementation)
            log_info(f"Banned peer {node_id}: {reason}")
        
        return success
    
    async def promote_peer(self, node_id: str) -> bool:
        """Promote peer to higher priority"""
        try:
            if node_id in self.discovery.peers:
                peer = self.discovery.peers[node_id]
                
                # Increase reputation
                self.discovery.update_peer_reputation(node_id, 0.1)
                
                # Record promotion event
                self._record_peer_event(PeerAction.PROMOTE, node_id, "Peer promoted")
                
                log_info(f"Promoted peer {node_id}")
                return True
            else:
                log_warn(f"Peer {node_id} not found for promotion")
                return False
                
        except Exception as e:
            log_error(f"Error promoting peer {node_id}: {e}")
            return False
    
    async def demote_peer(self, node_id: str) -> bool:
        """Demote peer to lower priority"""
        try:
            if node_id in self.discovery.peers:
                peer = self.discovery.peers[node_id]
                
                # Decrease reputation
                self.discovery.update_peer_reputation(node_id, -0.1)
                
                # Record demotion event
                self._record_peer_event(PeerAction.DEMOTE, node_id, "Peer demoted")
                
                log_info(f"Demoted peer {node_id}")
                return True
            else:
                log_warn(f"Peer {node_id} not found for demotion")
                return False
                
        except Exception as e:
            log_error(f"Error demoting peer {node_id}: {e}")
            return False
    
    def _record_peer_event(self, action: PeerAction, node_id: str, reason: str, metadata: Dict = None):
        """Record peer management event"""
        event = PeerEvent(
            action=action,
            node_id=node_id,
            timestamp=time.time(),
            reason=reason,
            metadata=metadata or {}
        )
        
        self.peer_events.append(event)
        
        # Limit event history size
        if len(self.peer_events) > 1000:
            self.peer_events = self.peer_events[-500:]  # Keep last 500 events
    
    def get_peer_events(self, node_id: Optional[str] = None, limit: int = 100) -> List[PeerEvent]:
        """Get peer management events"""
        events = self.peer_events
        
        if node_id:
            events = [e for e in events if e.node_id == node_id]
        
        return events[-limit:]
    
    def get_peer_statistics(self) -> Dict:
        """Get peer management statistics"""
        peers = self.discovery.get_peer_list()
        health_status = self.health_monitor.get_all_health_status()
        
        stats = {
            "total_peers": len(peers),
            "healthy_peers": len(self.health_monitor.get_healthy_peers()),
            "unhealthy_peers": len(self.health_monitor.get_unhealthy_peers()),
            "average_reputation": sum(p.reputation for p in peers) / len(peers) if peers else 0,
            "average_health_score": sum(h.health_score for h in health_status.values()) / len(health_status) if health_status else 0,
            "recent_events": len([e for e in self.peer_events if time.time() - e.timestamp < 3600])  # Last hour
        }
        
        return stats

# Global peer manager
peer_manager: Optional[DynamicPeerManager] = None

def get_peer_manager() -> Optional[DynamicPeerManager]:
    """Get global peer manager"""
    return peer_manager

def create_peer_manager(discovery: P2PDiscovery, health_monitor: PeerHealthMonitor) -> DynamicPeerManager:
    """Create and set global peer manager"""
    global peer_manager
    peer_manager = DynamicPeerManager(discovery, health_monitor)
    return peer_manager
