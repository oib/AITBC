"""
Network Recovery Mechanisms
Implements automatic network healing and recovery procedures
"""

import asyncio
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from .discovery import P2PDiscovery, PeerNode
from .health import PeerHealthMonitor
from .partition import NetworkPartitionManager, PartitionState

class RecoveryStrategy(Enum):
    AGGRESSIVE = "aggressive"
    CONSERVATIVE = "conservative"
    ADAPTIVE = "adaptive"

class RecoveryTrigger(Enum):
    PARTITION_DETECTED = "partition_detected"
    HIGH_LATENCY = "high_latency"
    PEER_FAILURE = "peer_failure"
    MANUAL = "manual"

@dataclass
class RecoveryAction:
    action_type: str
    target_node: str
    priority: int
    created_at: float
    attempts: int
    max_attempts: int
    success: bool

class NetworkRecoveryManager:
    """Manages automatic network recovery procedures"""
    
    def __init__(self, discovery: P2PDiscovery, health_monitor: PeerHealthMonitor, 
                 partition_manager: NetworkPartitionManager):
        self.discovery = discovery
        self.health_monitor = health_monitor
        self.partition_manager = partition_manager
        self.recovery_strategy = RecoveryStrategy.ADAPTIVE
        self.recovery_actions: List[RecoveryAction] = []
        self.running = False
        self.recovery_interval = 60  # seconds
        
        # Recovery parameters
        self.max_recovery_attempts = 3
        self.recovery_timeout = 300  # 5 minutes
        self.emergency_threshold = 0.1  # 10% of network remaining
    
    async def start_recovery_service(self):
        """Start network recovery service"""
        self.running = True
        log_info("Starting network recovery service")
        
        while self.running:
            try:
                await self._process_recovery_actions()
                await self._monitor_network_health()
                await self._adaptive_strategy_adjustment()
                await asyncio.sleep(self.recovery_interval)
            except Exception as e:
                log_error(f"Recovery service error: {e}")
                await asyncio.sleep(10)
    
    async def stop_recovery_service(self):
        """Stop network recovery service"""
        self.running = False
        log_info("Stopping network recovery service")
    
    async def trigger_recovery(self, trigger: RecoveryTrigger, target_node: Optional[str] = None, 
                             metadata: Dict = None):
        """Trigger recovery procedure"""
        log_info(f"Recovery triggered: {trigger.value}")
        
        if trigger == RecoveryTrigger.PARTITION_DETECTED:
            await self._handle_partition_recovery()
        elif trigger == RecoveryTrigger.HIGH_LATENCY:
            await self._handle_latency_recovery(target_node)
        elif trigger == RecoveryTrigger.PEER_FAILURE:
            await self._handle_peer_failure_recovery(target_node)
        elif trigger == RecoveryTrigger.MANUAL:
            await self._handle_manual_recovery(target_node, metadata)
    
    async def _handle_partition_recovery(self):
        """Handle partition recovery"""
        log_info("Starting partition recovery")
        
        # Get partition status
        partition_status = self.partition_manager.get_partition_status()
        
        if partition_status['state'] == PartitionState.PARTITIONED.value:
            # Create recovery actions for partition
            await self._create_partition_recovery_actions(partition_status)
    
    async def _create_partition_recovery_actions(self, partition_status: Dict):
        """Create recovery actions for partition"""
        local_partition_size = self.partition_manager.get_local_partition_size()
        
        # Emergency recovery if partition is too small
        if local_partition_size < len(self.discovery.peers) * self.emergency_threshold:
            await self._create_emergency_recovery_actions()
        else:
            await self._create_standard_recovery_actions()
    
    async def _create_emergency_recovery_actions(self):
        """Create emergency recovery actions"""
        log_warn("Creating emergency recovery actions")
        
        # Try all bootstrap nodes
        for address, port in self.discovery.bootstrap_nodes:
            action = RecoveryAction(
                action_type="bootstrap_connect",
                target_node=f"{address}:{port}",
                priority=1,  # Highest priority
                created_at=time.time(),
                attempts=0,
                max_attempts=5,
                success=False
            )
            self.recovery_actions.append(action)
        
        # Try alternative discovery methods
        action = RecoveryAction(
            action_type="alternative_discovery",
            target_node="broadcast",
            priority=2,
            created_at=time.time(),
            attempts=0,
            max_attempts=3,
            success=False
        )
        self.recovery_actions.append(action)
    
    async def _create_standard_recovery_actions(self):
        """Create standard recovery actions"""
        # Reconnect to recently lost peers
        health_status = self.health_monitor.get_all_health_status()
        
        for node_id, health in health_status.items():
            if health.status.value == "offline":
                peer = self.discovery.peers.get(node_id)
                if peer:
                    action = RecoveryAction(
                        action_type="reconnect_peer",
                        target_node=node_id,
                        priority=3,
                        created_at=time.time(),
                        attempts=0,
                        max_attempts=3,
                        success=False
                    )
                    self.recovery_actions.append(action)
    
    async def _handle_latency_recovery(self, target_node: str):
        """Handle high latency recovery"""
        log_info(f"Starting latency recovery for node {target_node}")
        
        # Find alternative paths
        action = RecoveryAction(
            action_type="find_alternative_path",
            target_node=target_node,
            priority=4,
            created_at=time.time(),
            attempts=0,
            max_attempts=2,
            success=False
        )
        self.recovery_actions.append(action)
    
    async def _handle_peer_failure_recovery(self, target_node: str):
        """Handle peer failure recovery"""
        log_info(f"Starting peer failure recovery for node {target_node}")
        
        # Replace failed peer
        action = RecoveryAction(
            action_type="replace_peer",
            target_node=target_node,
            priority=3,
            created_at=time.time(),
            attempts=0,
            max_attempts=3,
            success=False
        )
        self.recovery_actions.append(action)
    
    async def _handle_manual_recovery(self, target_node: Optional[str], metadata: Dict):
        """Handle manual recovery"""
        recovery_type = metadata.get('type', 'standard')
        
        if recovery_type == 'force_reconnect':
            await self._force_reconnect(target_node)
        elif recovery_type == 'reset_network':
            await self._reset_network()
        elif recovery_type == 'bootstrap_only':
            await self._bootstrap_only_recovery()
    
    async def _process_recovery_actions(self):
        """Process pending recovery actions"""
        # Sort actions by priority
        sorted_actions = sorted(
            [a for a in self.recovery_actions if not a.success],
            key=lambda x: x.priority
        )
        
        for action in sorted_actions[:5]:  # Process max 5 actions per cycle
            if action.attempts >= action.max_attempts:
                # Mark as failed and remove
                log_warn(f"Recovery action failed after {action.attempts} attempts: {action.action_type}")
                self.recovery_actions.remove(action)
                continue
            
            # Execute action
            success = await self._execute_recovery_action(action)
            
            if success:
                action.success = True
                log_info(f"Recovery action succeeded: {action.action_type}")
            else:
                action.attempts += 1
                log_debug(f"Recovery action attempt {action.attempts} failed: {action.action_type}")
    
    async def _execute_recovery_action(self, action: RecoveryAction) -> bool:
        """Execute individual recovery action"""
        try:
            if action.action_type == "bootstrap_connect":
                return await self._execute_bootstrap_connect(action)
            elif action.action_type == "alternative_discovery":
                return await self._execute_alternative_discovery(action)
            elif action.action_type == "reconnect_peer":
                return await self._execute_reconnect_peer(action)
            elif action.action_type == "find_alternative_path":
                return await self._execute_find_alternative_path(action)
            elif action.action_type == "replace_peer":
                return await self._execute_replace_peer(action)
            else:
                log_warn(f"Unknown recovery action type: {action.action_type}")
                return False
                
        except Exception as e:
            log_error(f"Error executing recovery action {action.action_type}: {e}")
            return False
    
    async def _execute_bootstrap_connect(self, action: RecoveryAction) -> bool:
        """Execute bootstrap connect action"""
        address, port = action.target_node.split(':')
        
        try:
            success = await self.discovery._connect_to_peer(address, int(port))
            if success:
                log_info(f"Bootstrap connect successful to {address}:{port}")
            return success
        except Exception as e:
            log_error(f"Bootstrap connect failed to {address}:{port}: {e}")
            return False
    
    async def _execute_alternative_discovery(self) -> bool:
        """Execute alternative discovery action"""
        try:
            # Try multicast discovery
            await self._multicast_discovery()
            
            # Try DNS discovery
            await self._dns_discovery()
            
            # Check if any new peers were discovered
            new_peers = len(self.discovery.get_peer_list())
            return new_peers > 0
            
        except Exception as e:
            log_error(f"Alternative discovery failed: {e}")
            return False
    
    async def _execute_reconnect_peer(self, action: RecoveryAction) -> bool:
        """Execute peer reconnection action"""
        peer = self.discovery.peers.get(action.target_node)
        if not peer:
            return False
        
        try:
            success = await self.discovery._connect_to_peer(peer.address, peer.port)
            if success:
                log_info(f"Reconnected to peer {action.target_node}")
            return success
        except Exception as e:
            log_error(f"Reconnection failed for peer {action.target_node}: {e}")
            return False
    
    async def _execute_find_alternative_path(self, action: RecoveryAction) -> bool:
        """Execute alternative path finding action"""
        # This would implement finding alternative network paths
        # For now, just try to reconnect through different peers
        log_info(f"Finding alternative path for node {action.target_node}")
        
        # Try connecting through other peers
        for peer in self.discovery.get_peer_list():
            if peer.node_id != action.target_node:
                # In a real implementation, this would route through the peer
                success = await self.discovery._connect_to_peer(peer.address, peer.port)
                if success:
                    return True
        
        return False
    
    async def _execute_replace_peer(self, action: RecoveryAction) -> bool:
        """Execute peer replacement action"""
        log_info(f"Attempting to replace peer {action.target_node}")
        
        # Find replacement peer
        replacement = await self._find_replacement_peer()
        
        if replacement:
            # Remove failed peer
            await self.discovery._remove_peer(action.target_node, "Peer replacement")
            
            # Add replacement peer
            success = await self.discovery._connect_to_peer(replacement[0], replacement[1])
            
            if success:
                log_info(f"Successfully replaced peer {action.target_node} with {replacement[0]}:{replacement[1]}")
                return True
        
        return False
    
    async def _find_replacement_peer(self) -> Optional[Tuple[str, int]]:
        """Find replacement peer from known sources"""
        # Try bootstrap nodes first
        for address, port in self.discovery.bootstrap_nodes:
            peer_id = f"{address}:{port}"
            if peer_id not in self.discovery.peers:
                return (address, port)
        
        return None
    
    async def _monitor_network_health(self):
        """Monitor network health for recovery triggers"""
        # Check for high latency
        health_status = self.health_monitor.get_all_health_status()
        
        for node_id, health in health_status.items():
            if health.latency_ms > 2000:  # 2 seconds
                await self.trigger_recovery(RecoveryTrigger.HIGH_LATENCY, node_id)
    
    async def _adaptive_strategy_adjustment(self):
        """Adjust recovery strategy based on network conditions"""
        if self.recovery_strategy != RecoveryStrategy.ADAPTIVE:
            return
        
        # Count recent failures
        recent_failures = len([
            action for action in self.recovery_actions
            if not action.success and time.time() - action.created_at < 300
        ])
        
        # Adjust strategy based on failure rate
        if recent_failures > 10:
            self.recovery_strategy = RecoveryStrategy.CONSERVATIVE
            log_info("Switching to conservative recovery strategy")
        elif recent_failures < 3:
            self.recovery_strategy = RecoveryStrategy.AGGRESSIVE
            log_info("Switching to aggressive recovery strategy")
    
    async def _force_reconnect(self, target_node: Optional[str]):
        """Force reconnection to specific node or all nodes"""
        if target_node:
            peer = self.discovery.peers.get(target_node)
            if peer:
                await self.discovery._connect_to_peer(peer.address, peer.port)
        else:
            # Reconnect to all peers
            for peer in self.discovery.get_peer_list():
                await self.discovery._connect_to_peer(peer.address, peer.port)
    
    async def _reset_network(self):
        """Reset network connections"""
        log_warn("Resetting network connections")
        
        # Clear all peers
        self.discovery.peers.clear()
        
        # Restart discovery
        await self.discovery._connect_to_bootstrap_nodes()
    
    async def _bootstrap_only_recovery(self):
        """Recover using bootstrap nodes only"""
        log_info("Starting bootstrap-only recovery")
        
        # Clear current peers
        self.discovery.peers.clear()
        
        # Connect only to bootstrap nodes
        for address, port in self.discovery.bootstrap_nodes:
            await self.discovery._connect_to_peer(address, port)
    
    async def _multicast_discovery(self):
        """Multicast discovery implementation"""
        # Implementation would use UDP multicast
        log_debug("Executing multicast discovery")
    
    async def _dns_discovery(self):
        """DNS discovery implementation"""
        # Implementation would query DNS records
        log_debug("Executing DNS discovery")
    
    def get_recovery_status(self) -> Dict:
        """Get current recovery status"""
        pending_actions = [a for a in self.recovery_actions if not a.success]
        successful_actions = [a for a in self.recovery_actions if a.success]
        
        return {
            'strategy': self.recovery_strategy.value,
            'pending_actions': len(pending_actions),
            'successful_actions': len(successful_actions),
            'total_actions': len(self.recovery_actions),
            'recent_failures': len([
                a for a in self.recovery_actions
                if not a.success and time.time() - a.created_at < 300
            ]),
            'actions': [
                {
                    'type': a.action_type,
                    'target': a.target_node,
                    'priority': a.priority,
                    'attempts': a.attempts,
                    'max_attempts': a.max_attempts,
                    'created_at': a.created_at
                }
                for a in pending_actions[:10]  # Return first 10
            ]
        }

# Global recovery manager
recovery_manager: Optional[NetworkRecoveryManager] = None

def get_recovery_manager() -> Optional[NetworkRecoveryManager]:
    """Get global recovery manager"""
    return recovery_manager

def create_recovery_manager(discovery: P2PDiscovery, health_monitor: PeerHealthMonitor, 
                          partition_manager: NetworkPartitionManager) -> NetworkRecoveryManager:
    """Create and set global recovery manager"""
    global recovery_manager
    recovery_manager = NetworkRecoveryManager(discovery, health_monitor, partition_manager)
    return recovery_manager
