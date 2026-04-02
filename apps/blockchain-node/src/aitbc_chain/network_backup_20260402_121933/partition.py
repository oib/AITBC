"""
Network Partition Detection and Recovery
Handles network split detection and automatic recovery
"""

import asyncio
import time
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .discovery import P2PDiscovery, PeerNode, NodeStatus
from .health import PeerHealthMonitor, HealthStatus

class PartitionState(Enum):
    HEALTHY = "healthy"
    PARTITIONED = "partitioned"
    RECOVERING = "recovering"
    ISOLATED = "isolated"

@dataclass
class PartitionInfo:
    partition_id: str
    nodes: Set[str]
    leader: Optional[str]
    size: int
    created_at: float
    last_seen: float

class NetworkPartitionManager:
    """Manages network partition detection and recovery"""
    
    def __init__(self, discovery: P2PDiscovery, health_monitor: PeerHealthMonitor):
        self.discovery = discovery
        self.health_monitor = health_monitor
        self.current_state = PartitionState.HEALTHY
        self.partitions: Dict[str, PartitionInfo] = {}
        self.local_partition_id = None
        self.detection_interval = 30  # seconds
        self.recovery_timeout = 300  # 5 minutes
        self.max_partition_size = 0.4  # Max 40% of network in one partition
        self.running = False
        
        # Partition detection thresholds
        self.min_connected_nodes = 3
        self.partition_detection_threshold = 0.3  # 30% of network unreachable
    
    async def start_partition_monitoring(self):
        """Start partition monitoring service"""
        self.running = True
        log_info("Starting network partition monitoring")
        
        while self.running:
            try:
                await self._detect_partitions()
                await self._handle_partitions()
                await asyncio.sleep(self.detection_interval)
            except Exception as e:
                log_error(f"Partition monitoring error: {e}")
                await asyncio.sleep(10)
    
    async def stop_partition_monitoring(self):
        """Stop partition monitoring service"""
        self.running = False
        log_info("Stopping network partition monitoring")
    
    async def _detect_partitions(self):
        """Detect network partitions"""
        current_peers = self.discovery.get_peer_list()
        total_nodes = len(current_peers) + 1  # +1 for local node
        
        # Check connectivity
        reachable_nodes = set()
        unreachable_nodes = set()
        
        for peer in current_peers:
            health = self.health_monitor.get_health_status(peer.node_id)
            if health and health.status == NodeStatus.ONLINE:
                reachable_nodes.add(peer.node_id)
            else:
                unreachable_nodes.add(peer.node_id)
        
        # Calculate partition metrics
        reachable_ratio = len(reachable_nodes) / total_nodes if total_nodes > 0 else 0
        
        log_info(f"Network connectivity: {len(reachable_nodes)}/{total_nodes} reachable ({reachable_ratio:.2%})")
        
        # Detect partition
        if reachable_ratio < (1 - self.partition_detection_threshold):
            await self._handle_partition_detected(reachable_nodes, unreachable_nodes)
        else:
            await self._handle_partition_healed()
    
    async def _handle_partition_detected(self, reachable_nodes: Set[str], unreachable_nodes: Set[str]):
        """Handle detected network partition"""
        if self.current_state == PartitionState.HEALTHY:
            log_warn(f"Network partition detected! Reachable: {len(reachable_nodes)}, Unreachable: {len(unreachable_nodes)}")
            self.current_state = PartitionState.PARTITIONED
            
            # Create partition info
            partition_id = self._generate_partition_id(reachable_nodes)
            self.local_partition_id = partition_id
            
            self.partitions[partition_id] = PartitionInfo(
                partition_id=partition_id,
                nodes=reachable_nodes.copy(),
                leader=None,
                size=len(reachable_nodes),
                created_at=time.time(),
                last_seen=time.time()
            )
            
            # Start recovery procedures
            asyncio.create_task(self._start_partition_recovery())
    
    async def _handle_partition_healed(self):
        """Handle healed network partition"""
        if self.current_state in [PartitionState.PARTITIONED, PartitionState.RECOVERING]:
            log_info("Network partition healed!")
            self.current_state = PartitionState.HEALTHY
            
            # Clear partition info
            self.partitions.clear()
            self.local_partition_id = None
    
    async def _handle_partitions(self):
        """Handle active partitions"""
        if self.current_state == PartitionState.PARTITIONED:
            await self._maintain_partition()
        elif self.current_state == PartitionState.RECOVERING:
            await self._monitor_recovery()
    
    async def _maintain_partition(self):
        """Maintain operations during partition"""
        if not self.local_partition_id:
            return
        
        partition = self.partitions.get(self.local_partition_id)
        if not partition:
            return
        
        # Update partition info
        current_peers = set(peer.node_id for peer in self.discovery.get_peer_list())
        partition.nodes = current_peers
        partition.last_seen = time.time()
        partition.size = len(current_peers)
        
        # Select leader if none exists
        if not partition.leader:
            partition.leader = self._select_partition_leader(current_peers)
            log_info(f"Selected partition leader: {partition.leader}")
    
    async def _start_partition_recovery(self):
        """Start partition recovery procedures"""
        log_info("Starting partition recovery procedures")
        
        recovery_tasks = [
            asyncio.create_task(self._attempt_reconnection()),
            asyncio.create_task(self._bootstrap_from_known_nodes()),
            asyncio.create_task(self._coordinate_with_other_partitions())
        ]
        
        try:
            await asyncio.gather(*recovery_tasks, return_exceptions=True)
        except Exception as e:
            log_error(f"Partition recovery error: {e}")
    
    async def _attempt_reconnection(self):
        """Attempt to reconnect to unreachable nodes"""
        if not self.local_partition_id:
            return
        
        partition = self.partitions[self.local_partition_id]
        
        # Try to reconnect to known unreachable nodes
        all_known_peers = self.discovery.peers.copy()
        
        for node_id, peer in all_known_peers.items():
            if node_id not in partition.nodes:
                # Try to reconnect
                success = await self.discovery._connect_to_peer(peer.address, peer.port)
                
                if success:
                    log_info(f"Reconnected to node {node_id} during partition recovery")
    
    async def _bootstrap_from_known_nodes(self):
        """Bootstrap network from known good nodes"""
        # Try to connect to bootstrap nodes
        for address, port in self.discovery.bootstrap_nodes:
            try:
                success = await self.discovery._connect_to_peer(address, port)
                if success:
                    log_info(f"Bootstrap successful to {address}:{port}")
                    break
            except Exception as e:
                log_debug(f"Bootstrap failed to {address}:{port}: {e}")
    
    async def _coordinate_with_other_partitions(self):
        """Coordinate with other partitions (if detectable)"""
        # In a real implementation, this would use partition detection protocols
        # For now, just log the attempt
        log_info("Attempting to coordinate with other partitions")
    
    async def _monitor_recovery(self):
        """Monitor partition recovery progress"""
        if not self.local_partition_id:
            return
        
        partition = self.partitions[self.local_partition_id]
        
        # Check if recovery is taking too long
        if time.time() - partition.created_at > self.recovery_timeout:
            log_warn("Partition recovery timeout, considering extended recovery strategies")
            await self._extended_recovery_strategies()
    
    async def _extended_recovery_strategies(self):
        """Implement extended recovery strategies"""
        # Try alternative discovery methods
        await self._alternative_discovery()
        
        # Consider network reconfiguration
        await self._network_reconfiguration()
    
    async def _alternative_discovery(self):
        """Try alternative peer discovery methods"""
        log_info("Trying alternative discovery methods")
        
        # Try DNS-based discovery
        await self._dns_discovery()
        
        # Try multicast discovery
        await self._multicast_discovery()
    
    async def _dns_discovery(self):
        """DNS-based peer discovery"""
        # In a real implementation, this would query DNS records
        log_debug("Attempting DNS-based discovery")
    
    async def _multicast_discovery(self):
        """Multicast-based peer discovery"""
        # In a real implementation, this would use multicast packets
        log_debug("Attempting multicast discovery")
    
    async def _network_reconfiguration(self):
        """Reconfigure network for partition resilience"""
        log_info("Reconfiguring network for partition resilience")
        
        # Increase connection retry intervals
        # Adjust topology for better fault tolerance
        # Enable alternative communication channels
    
    def _generate_partition_id(self, nodes: Set[str]) -> str:
        """Generate unique partition ID"""
        import hashlib
        
        sorted_nodes = sorted(nodes)
        content = "|".join(sorted_nodes)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _select_partition_leader(self, nodes: Set[str]) -> Optional[str]:
        """Select leader for partition"""
        if not nodes:
            return None
        
        # Select node with highest reputation
        best_node = None
        best_reputation = 0
        
        for node_id in nodes:
            peer = self.discovery.peers.get(node_id)
            if peer and peer.reputation > best_reputation:
                best_reputation = peer.reputation
                best_node = node_id
        
        return best_node
    
    def get_partition_status(self) -> Dict:
        """Get current partition status"""
        return {
            'state': self.current_state.value,
            'local_partition_id': self.local_partition_id,
            'partition_count': len(self.partitions),
            'partitions': {
                pid: {
                    'size': info.size,
                    'leader': info.leader,
                    'created_at': info.created_at,
                    'last_seen': info.last_seen
                }
                for pid, info in self.partitions.items()
            }
        }
    
    def is_partitioned(self) -> bool:
        """Check if network is currently partitioned"""
        return self.current_state in [PartitionState.PARTITIONED, PartitionState.RECOVERING]
    
    def get_local_partition_size(self) -> int:
        """Get size of local partition"""
        if not self.local_partition_id:
            return 0
        
        partition = self.partitions.get(self.local_partition_id)
        return partition.size if partition else 0

# Global partition manager
partition_manager: Optional[NetworkPartitionManager] = None

def get_partition_manager() -> Optional[NetworkPartitionManager]:
    """Get global partition manager"""
    return partition_manager

def create_partition_manager(discovery: P2PDiscovery, health_monitor: PeerHealthMonitor) -> NetworkPartitionManager:
    """Create and set global partition manager"""
    global partition_manager
    partition_manager = NetworkPartitionManager(discovery, health_monitor)
    return partition_manager
