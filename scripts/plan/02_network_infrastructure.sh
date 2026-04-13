#!/bin/bash

# Phase 2: Network Infrastructure Setup Script
# Implements P2P discovery, dynamic peer management, and mesh routing

set -e

echo "=== PHASE 2: NETWORK INFRASTRUCTURE SETUP ==="

# Configuration
NETWORK_DIR="/opt/aitbc/apps/blockchain-node/src/aitbc_chain/network"
TEST_NODES=("node1" "node2" "node3" "node4" "node5")
BOOTSTRAP_NODES=("10.1.223.93:8000" "10.1.223.40:8000")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Function to backup existing network files
backup_network() {
    log_info "Backing up existing network files..."
    if [ -d "$NETWORK_DIR" ]; then
        cp -r "$NETWORK_DIR" "${NETWORK_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
        log_info "Backup completed"
    fi
}

# Function to create P2P discovery service
create_p2p_discovery() {
    log_info "Creating P2P discovery service..."
    
    cat > "$NETWORK_DIR/discovery.py" << 'EOF'
"""
P2P Node Discovery Service
Handles bootstrap nodes and peer discovery for mesh network
"""

import asyncio
import json
import time
import hashlib
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import socket
import struct

class NodeStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ERROR = "error"

@dataclass
class PeerNode:
    node_id: str
    address: str
    port: int
    public_key: str
    last_seen: float
    status: NodeStatus
    capabilities: List[str]
    reputation: float
    connection_count: int

@dataclass
class DiscoveryMessage:
    message_type: str
    node_id: str
    address: str
    port: int
    timestamp: float
    signature: str

class P2PDiscovery:
    """P2P node discovery and management service"""
    
    def __init__(self, local_node_id: str, local_address: str, local_port: int):
        self.local_node_id = local_node_id
        self.local_address = local_address
        self.local_port = local_port
        self.peers: Dict[str, PeerNode] = {}
        self.bootstrap_nodes: List[Tuple[str, int]] = []
        self.discovery_interval = 30  # seconds
        self.peer_timeout = 300  # 5 minutes
        self.max_peers = 50
        self.running = False
        
    def add_bootstrap_node(self, address: str, port: int):
        """Add bootstrap node for initial connection"""
        self.bootstrap_nodes.append((address, port))
    
    def generate_node_id(self, hostname: str, address: str, port: int, public_key: str) -> str:
        """Generate unique node ID from hostname, address, port, and public key"""
        content = f"{hostname}:{address}:{port}:{public_key}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def start_discovery(self):
        """Start the discovery service"""
        self.running = True
        log_info(f"Starting P2P discovery for node {self.local_node_id}")
        
        # Start discovery tasks
        tasks = [
            asyncio.create_task(self._discovery_loop()),
            asyncio.create_task(self._peer_health_check()),
            asyncio.create_task(self._listen_for_discovery())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            log_error(f"Discovery service error: {e}")
        finally:
            self.running = False
    
    async def stop_discovery(self):
        """Stop the discovery service"""
        self.running = False
        log_info("Stopping P2P discovery service")
    
    async def _discovery_loop(self):
        """Main discovery loop"""
        while self.running:
            try:
                # Connect to bootstrap nodes if no peers
                if len(self.peers) == 0:
                    await self._connect_to_bootstrap_nodes()
                
                # Discover new peers
                await self._discover_peers()
                
                # Wait before next discovery cycle
                await asyncio.sleep(self.discovery_interval)
                
            except Exception as e:
                log_error(f"Discovery loop error: {e}")
                await asyncio.sleep(5)
    
    async def _connect_to_bootstrap_nodes(self):
        """Connect to bootstrap nodes"""
        for address, port in self.bootstrap_nodes:
            if (address, port) != (self.local_address, self.local_port):
                await self._connect_to_peer(address, port)
    
    async def _connect_to_peer(self, address: str, port: int) -> bool:
        """Connect to a specific peer"""
        try:
            # Create discovery message
            message = DiscoveryMessage(
                message_type="hello",
                node_id=self.local_node_id,
                address=self.local_address,
                port=self.local_port,
                timestamp=time.time(),
                signature=""  # Would be signed in real implementation
            )
            
            # Send discovery message
            success = await self._send_discovery_message(address, port, message)
            
            if success:
                log_info(f"Connected to peer {address}:{port}")
                return True
            else:
                log_warn(f"Failed to connect to peer {address}:{port}")
                return False
                
        except Exception as e:
            log_error(f"Error connecting to peer {address}:{port}: {e}")
            return False
    
    async def _send_discovery_message(self, address: str, port: int, message: DiscoveryMessage) -> bool:
        """Send discovery message to peer"""
        try:
            reader, writer = await asyncio.open_connection(address, port)
            
            # Send message
            message_data = json.dumps(asdict(message)).encode()
            writer.write(message_data)
            await writer.drain()
            
            # Wait for response
            response_data = await reader.read(4096)
            response = json.loads(response_data.decode())
            
            writer.close()
            await writer.wait_closed()
            
            # Process response
            if response.get("message_type") == "hello_response":
                await self._handle_hello_response(response)
                return True
            
            return False
            
        except Exception as e:
            log_debug(f"Failed to send discovery message to {address}:{port}: {e}")
            return False
    
    async def _handle_hello_response(self, response: Dict):
        """Handle hello response from peer"""
        try:
            peer_node_id = response["node_id"]
            peer_address = response["address"]
            peer_port = response["port"]
            peer_capabilities = response.get("capabilities", [])
            
            # Create peer node
            peer = PeerNode(
                node_id=peer_node_id,
                address=peer_address,
                port=peer_port,
                public_key=response.get("public_key", ""),
                last_seen=time.time(),
                status=NodeStatus.ONLINE,
                capabilities=peer_capabilities,
                reputation=1.0,
                connection_count=0
            )
            
            # Add to peers
            self.peers[peer_node_id] = peer
            
            log_info(f"Added peer {peer_node_id} from {peer_address}:{peer_port}")
            
        except Exception as e:
            log_error(f"Error handling hello response: {e}")
    
    async def _discover_peers(self):
        """Discover new peers from existing connections"""
        for peer in list(self.peers.values()):
            if peer.status == NodeStatus.ONLINE:
                await self._request_peer_list(peer)
    
    async def _request_peer_list(self, peer: PeerNode):
        """Request peer list from connected peer"""
        try:
            message = DiscoveryMessage(
                message_type="get_peers",
                node_id=self.local_node_id,
                address=self.local_address,
                port=self.local_port,
                timestamp=time.time(),
                signature=""
            )
            
            success = await self._send_discovery_message(peer.address, peer.port, message)
            
            if success:
                log_debug(f"Requested peer list from {peer.node_id}")
            
        except Exception as e:
            log_error(f"Error requesting peer list from {peer.node_id}: {e}")
    
    async def _peer_health_check(self):
        """Check health of connected peers"""
        while self.running:
            try:
                current_time = time.time()
                
                # Check for offline peers
                for peer_id, peer in list(self.peers.items()):
                    if current_time - peer.last_seen > self.peer_timeout:
                        peer.status = NodeStatus.OFFLINE
                        log_warn(f"Peer {peer_id} went offline")
                
                # Remove offline peers
                self.peers = {
                    peer_id: peer for peer_id, peer in self.peers.items()
                    if peer.status != NodeStatus.OFFLINE or current_time - peer.last_seen < self.peer_timeout * 2
                }
                
                # Limit peer count
                if len(self.peers) > self.max_peers:
                    # Remove peers with lowest reputation
                    sorted_peers = sorted(
                        self.peers.items(),
                        key=lambda x: x[1].reputation
                    )
                    
                    for peer_id, _ in sorted_peers[:len(self.peers) - self.max_peers]:
                        del self.peers[peer_id]
                        log_info(f"Removed peer {peer_id} due to peer limit")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                log_error(f"Peer health check error: {e}")
                await asyncio.sleep(30)
    
    async def _listen_for_discovery(self):
        """Listen for incoming discovery messages"""
        server = await asyncio.start_server(
            self._handle_discovery_connection,
            self.local_address,
            self.local_port
        )
        
        log_info(f"Discovery server listening on {self.local_address}:{self.local_port}")
        
        async with server:
            await server.serve_forever()
    
    async def _handle_discovery_connection(self, reader, writer):
        """Handle incoming discovery connection"""
        try:
            # Read message
            data = await reader.read(4096)
            message = json.loads(data.decode())
            
            # Process message
            response = await self._process_discovery_message(message)
            
            # Send response
            response_data = json.dumps(response).encode()
            writer.write(response_data)
            await writer.drain()
            
            writer.close()
            await writer.wait_closed()
            
        except Exception as e:
            log_error(f"Error handling discovery connection: {e}")
    
    async def _process_discovery_message(self, message: Dict) -> Dict:
        """Process incoming discovery message"""
        message_type = message.get("message_type")
        node_id = message.get("node_id")
        
        if message_type == "hello":
            # Respond with peer information
            return {
                "message_type": "hello_response",
                "node_id": self.local_node_id,
                "address": self.local_address,
                "port": self.local_port,
                "public_key": "",  # Would include actual public key
                "capabilities": ["consensus", "mempool", "rpc"],
                "timestamp": time.time()
            }
        
        elif message_type == "get_peers":
            # Return list of known peers
            peer_list = []
            for peer in self.peers.values():
                if peer.status == NodeStatus.ONLINE:
                    peer_list.append({
                        "node_id": peer.node_id,
                        "address": peer.address,
                        "port": peer.port,
                        "capabilities": peer.capabilities,
                        "reputation": peer.reputation
                    })
            
            return {
                "message_type": "peers_response",
                "node_id": self.local_node_id,
                "peers": peer_list,
                "timestamp": time.time()
            }
        
        else:
            return {
                "message_type": "error",
                "error": "Unknown message type",
                "timestamp": time.time()
            }
    
    def get_peer_count(self) -> int:
        """Get number of connected peers"""
        return len([p for p in self.peers.values() if p.status == NodeStatus.ONLINE])
    
    def get_peer_list(self) -> List[PeerNode]:
        """Get list of connected peers"""
        return [p for p in self.peers.values() if p.status == NodeStatus.ONLINE]
    
    def update_peer_reputation(self, node_id: str, delta: float) -> bool:
        """Update peer reputation"""
        if node_id not in self.peers:
            return False
        
        peer = self.peers[node_id]
        peer.reputation = max(0.0, min(1.0, peer.reputation + delta))
        return True

# Global discovery instance
discovery_instance: Optional[P2PDiscovery] = None

def get_discovery() -> Optional[P2PDiscovery]:
    """Get global discovery instance"""
    return discovery_instance

def create_discovery(node_id: str, address: str, port: int) -> P2PDiscovery:
    """Create and set global discovery instance"""
    global discovery_instance
    discovery_instance = P2PDiscovery(node_id, address, port)
    return discovery_instance
EOF

    log_info "P2P discovery service created"
}

# Function to create peer health monitoring
create_peer_health_monitoring() {
    log_info "Creating peer health monitoring..."
    
    cat > "$NETWORK_DIR/health.py" << 'EOF'
"""
Peer Health Monitoring Service
Monitors peer liveness and performance metrics
"""

import asyncio
import time
import ping3
import statistics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .discovery import PeerNode, NodeStatus

class HealthMetric(Enum):
    LATENCY = "latency"
    AVAILABILITY = "availability"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"

@dataclass
class HealthStatus:
    node_id: str
    status: NodeStatus
    last_check: float
    latency_ms: float
    availability_percent: float
    throughput_mbps: float
    error_rate_percent: float
    consecutive_failures: int
    health_score: float

class PeerHealthMonitor:
    """Monitors health and performance of peer nodes"""
    
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self.health_status: Dict[str, HealthStatus] = {}
        self.running = False
        self.latency_history: Dict[str, List[float]] = {}
        self.max_history_size = 100
        
        # Health thresholds
        self.max_latency_ms = 1000
        self.min_availability_percent = 90.0
        self.min_health_score = 0.5
        self.max_consecutive_failures = 3
    
    async def start_monitoring(self, peers: Dict[str, PeerNode]):
        """Start health monitoring for peers"""
        self.running = True
        log_info("Starting peer health monitoring")
        
        while self.running:
            try:
                await self._check_all_peers(peers)
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                log_error(f"Health monitoring error: {e}")
                await asyncio.sleep(10)
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self.running = False
        log_info("Stopping peer health monitoring")
    
    async def _check_all_peers(self, peers: Dict[str, PeerNode]):
        """Check health of all peers"""
        tasks = []
        
        for node_id, peer in peers.items():
            if peer.status == NodeStatus.ONLINE:
                task = asyncio.create_task(self._check_peer_health(peer))
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_peer_health(self, peer: PeerNode):
        """Check health of individual peer"""
        start_time = time.time()
        
        try:
            # Check latency
            latency = await self._measure_latency(peer.address, peer.port)
            
            # Check availability
            availability = await self._check_availability(peer)
            
            # Check throughput
            throughput = await self._measure_throughput(peer)
            
            # Calculate health score
            health_score = self._calculate_health_score(latency, availability, throughput)
            
            # Update health status
            self._update_health_status(peer, NodeStatus.ONLINE, latency, availability, throughput, 0.0, health_score)
            
            # Reset consecutive failures
            if peer.node_id in self.health_status:
                self.health_status[peer.node_id].consecutive_failures = 0
            
        except Exception as e:
            log_error(f"Health check failed for peer {peer.node_id}: {e}")
            
            # Handle failure
            consecutive_failures = self.health_status.get(peer.node_id, HealthStatus(peer.node_id, NodeStatus.OFFLINE, 0, 0, 0, 0, 0, 0, 0.0)).consecutive_failures + 1
            
            if consecutive_failures >= self.max_consecutive_failures:
                self._update_health_status(peer, NodeStatus.OFFLINE, 0, 0, 0, 100.0, 0.0)
            else:
                self._update_health_status(peer, NodeStatus.ERROR, 0, 0, 0, 0.0, consecutive_failures, 0.0)
    
    async def _measure_latency(self, address: str, port: int) -> float:
        """Measure network latency to peer"""
        try:
            # Use ping3 for basic latency measurement
            latency = ping3.ping(address, timeout=2)
            
            if latency is not None:
                latency_ms = latency * 1000
                
                # Update latency history
                node_id = f"{address}:{port}"
                if node_id not in self.latency_history:
                    self.latency_history[node_id] = []
                
                self.latency_history[node_id].append(latency_ms)
                
                # Limit history size
                if len(self.latency_history[node_id]) > self.max_history_size:
                    self.latency_history[node_id].pop(0)
                
                return latency_ms
            else:
                return float('inf')
                
        except Exception as e:
            log_debug(f"Latency measurement failed for {address}:{port}: {e}")
            return float('inf')
    
    async def _check_availability(self, peer: PeerNode) -> float:
        """Check peer availability by attempting connection"""
        try:
            start_time = time.time()
            
            # Try to connect to peer
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(peer.address, peer.port),
                timeout=5.0
            )
            
            connection_time = (time.time() - start_time) * 1000
            
            writer.close()
            await writer.wait_closed()
            
            # Calculate availability based on recent history
            node_id = peer.node_id
            if node_id in self.health_status:
                # Simple availability calculation based on success rate
                recent_status = self.health_status[node_id]
                if recent_status.status == NodeStatus.ONLINE:
                    return min(100.0, recent_status.availability_percent + 5.0)
                else:
                    return max(0.0, recent_status.availability_percent - 10.0)
            else:
                return 100.0  # First successful connection
                
        except Exception as e:
            log_debug(f"Availability check failed for {peer.node_id}: {e}")
            return 0.0
    
    async def _measure_throughput(self, peer: PeerNode) -> float:
        """Measure network throughput to peer"""
        try:
            # Simple throughput test using small data transfer
            test_data = b"x" * 1024  # 1KB test data
            
            start_time = time.time()
            
            reader, writer = await asyncio.open_connection(peer.address, peer.port)
            
            # Send test data
            writer.write(test_data)
            await writer.drain()
            
            # Wait for echo response (if peer supports it)
            response = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            
            transfer_time = time.time() - start_time
            
            writer.close()
            await writer.wait_closed()
            
            # Calculate throughput in Mbps
            bytes_transferred = len(test_data) + len(response)
            throughput_mbps = (bytes_transferred * 8) / (transfer_time * 1024 * 1024)
            
            return throughput_mbps
            
        except Exception as e:
            log_debug(f"Throughput measurement failed for {peer.node_id}: {e}")
            return 0.0
    
    def _calculate_health_score(self, latency: float, availability: float, throughput: float) -> float:
        """Calculate overall health score"""
        # Latency score (lower is better)
        latency_score = max(0.0, 1.0 - (latency / self.max_latency_ms))
        
        # Availability score
        availability_score = availability / 100.0
        
        # Throughput score (higher is better, normalized to 10 Mbps)
        throughput_score = min(1.0, throughput / 10.0)
        
        # Weighted average
        health_score = (
            latency_score * 0.3 +
            availability_score * 0.4 +
            throughput_score * 0.3
        )
        
        return health_score
    
    def _update_health_status(self, peer: PeerNode, status: NodeStatus, latency: float, 
                            availability: float, throughput: float, error_rate: float,
                            consecutive_failures: int = 0, health_score: float = 0.0):
        """Update health status for peer"""
        self.health_status[peer.node_id] = HealthStatus(
            node_id=peer.node_id,
            status=status,
            last_check=time.time(),
            latency_ms=latency,
            availability_percent=availability,
            throughput_mbps=throughput,
            error_rate_percent=error_rate,
            consecutive_failures=consecutive_failures,
            health_score=health_score
        )
        
        # Update peer status in discovery
        peer.status = status
        peer.last_seen = time.time()
    
    def get_health_status(self, node_id: str) -> Optional[HealthStatus]:
        """Get health status for specific peer"""
        return self.health_status.get(node_id)
    
    def get_all_health_status(self) -> Dict[str, HealthStatus]:
        """Get health status for all peers"""
        return self.health_status.copy()
    
    def get_average_latency(self, node_id: str) -> Optional[float]:
        """Get average latency for peer"""
        node_key = f"{self.health_status.get(node_id, HealthStatus('', NodeStatus.OFFLINE, 0, 0, 0, 0, 0, 0, 0.0)).node_id}"
        
        if node_key in self.latency_history and self.latency_history[node_key]:
            return statistics.mean(self.latency_history[node_key])
        
        return None
    
    def get_healthy_peers(self) -> List[str]:
        """Get list of healthy peers"""
        return [
            node_id for node_id, status in self.health_status.items()
            if status.health_score >= self.min_health_score
        ]
    
    def get_unhealthy_peers(self) -> List[str]:
        """Get list of unhealthy peers"""
        return [
            node_id for node_id, status in self.health_status.items()
            if status.health_score < self.min_health_score
        ]

# Global health monitor
health_monitor: Optional[PeerHealthMonitor] = None

def get_health_monitor() -> Optional[PeerHealthMonitor]:
    """Get global health monitor"""
    return health_monitor

def create_health_monitor(check_interval: int = 60) -> PeerHealthMonitor:
    """Create and set global health monitor"""
    global health_monitor
    health_monitor = PeerHealthMonitor(check_interval)
    return health_monitor
EOF

    log_info "Peer health monitoring created"
}

# Function to create dynamic peer management
create_dynamic_peer_management() {
    log_info "Creating dynamic peer management..."
    
    cat > "$NETWORK_DIR/peers.py" << 'EOF'
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
EOF

    log_info "Dynamic peer management created"
}

# Function to create network topology optimization
create_topology_optimization() {
    log_info "Creating network topology optimization..."
    
    cat > "$NETWORK_DIR/topology.py" << 'EOF'
"""
Network Topology Optimization
Optimizes peer connection strategies for network performance
"""

import asyncio
import networkx as nx
import time
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from .discovery import PeerNode, P2PDiscovery
from .health import PeerHealthMonitor, HealthStatus

class TopologyStrategy(Enum):
    SMALL_WORLD = "small_world"
    SCALE_FREE = "scale_free"
    MESH = "mesh"
    HYBRID = "hybrid"

@dataclass
class ConnectionWeight:
    source: str
    target: str
    weight: float
    latency: float
    bandwidth: float
    reliability: float

class NetworkTopology:
    """Manages and optimizes network topology"""
    
    def __init__(self, discovery: P2PDiscovery, health_monitor: PeerHealthMonitor):
        self.discovery = discovery
        self.health_monitor = health_monitor
        self.graph = nx.Graph()
        self.strategy = TopologyStrategy.HYBRID
        self.optimization_interval = 300  # 5 minutes
        self.max_degree = 8
        self.min_degree = 3
        self.running = False
        
        # Topology metrics
        self.avg_path_length = 0
        self.clustering_coefficient = 0
        self.network_efficiency = 0
    
    async def start_optimization(self):
        """Start topology optimization service"""
        self.running = True
        log_info("Starting network topology optimization")
        
        # Initialize graph
        await self._build_initial_graph()
        
        while self.running:
            try:
                await self._optimize_topology()
                await self._calculate_metrics()
                await asyncio.sleep(self.optimization_interval)
            except Exception as e:
                log_error(f"Topology optimization error: {e}")
                await asyncio.sleep(30)
    
    async def stop_optimization(self):
        """Stop topology optimization service"""
        self.running = False
        log_info("Stopping network topology optimization")
    
    async def _build_initial_graph(self):
        """Build initial network graph from current peers"""
        self.graph.clear()
        
        # Add all peers as nodes
        for peer in self.discovery.get_peer_list():
            self.graph.add_node(peer.node_id, **{
                'address': peer.address,
                'port': peer.port,
                'reputation': peer.reputation,
                'capabilities': peer.capabilities
            })
        
        # Add edges based on current connections
        await self._add_connection_edges()
    
    async def _add_connection_edges(self):
        """Add edges for current peer connections"""
        peers = self.discovery.get_peer_list()
        
        # In a real implementation, this would use actual connection data
        # For now, create a mesh topology
        for i, peer1 in enumerate(peers):
            for peer2 in peers[i+1:]:
                if self._should_connect(peer1, peer2):
                    weight = await self._calculate_connection_weight(peer1, peer2)
                    self.graph.add_edge(peer1.node_id, peer2.node_id, weight=weight)
    
    def _should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Determine if two peers should be connected"""
        # Check degree constraints
        if (self.graph.degree(peer1.node_id) >= self.max_degree or 
            self.graph.degree(peer2.node_id) >= self.max_degree):
            return False
        
        # Check strategy-specific rules
        if self.strategy == TopologyStrategy.SMALL_WORLD:
            return self._small_world_should_connect(peer1, peer2)
        elif self.strategy == TopologyStrategy.SCALE_FREE:
            return self._scale_free_should_connect(peer1, peer2)
        elif self.strategy == TopologyStrategy.MESH:
            return self._mesh_should_connect(peer1, peer2)
        elif self.strategy == TopologyStrategy.HYBRID:
            return self._hybrid_should_connect(peer1, peer2)
        
        return False
    
    def _small_world_should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Small world topology connection logic"""
        # Connect to nearby peers and some random long-range connections
        import random
        
        if random.random() < 0.1:  # 10% random connections
            return True
        
        # Connect based on geographic or network proximity (simplified)
        return random.random() < 0.3  # 30% of nearby connections
    
    def _scale_free_should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Scale-free topology connection logic"""
        # Prefer connecting to high-degree nodes (rich-get-richer)
        degree1 = self.graph.degree(peer1.node_id)
        degree2 = self.graph.degree(peer2.node_id)
        
        # Higher probability for nodes with higher degree
        connection_probability = (degree1 + degree2) / (2 * self.max_degree)
        return random.random() < connection_probability
    
    def _mesh_should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Full mesh topology connection logic"""
        # Connect to all peers (within degree limits)
        return True
    
    def _hybrid_should_connect(self, peer1: PeerNode, peer2: PeerNode) -> bool:
        """Hybrid topology connection logic"""
        # Combine multiple strategies
        import random
        
        # 40% small world, 30% scale-free, 30% mesh
        strategy_choice = random.random()
        
        if strategy_choice < 0.4:
            return self._small_world_should_connect(peer1, peer2)
        elif strategy_choice < 0.7:
            return self._scale_free_should_connect(peer1, peer2)
        else:
            return self._mesh_should_connect(peer1, peer2)
    
    async def _calculate_connection_weight(self, peer1: PeerNode, peer2: PeerNode) -> float:
        """Calculate connection weight between two peers"""
        # Get health metrics
        health1 = self.health_monitor.get_health_status(peer1.node_id)
        health2 = self.health_monitor.get_health_status(peer2.node_id)
        
        # Calculate weight based on health, reputation, and performance
        weight = 1.0
        
        if health1 and health2:
            # Factor in health scores
            weight *= (health1.health_score + health2.health_score) / 2
        
        # Factor in reputation
        weight *= (peer1.reputation + peer2.reputation) / 2
        
        # Factor in latency (inverse relationship)
        if health1 and health1.latency_ms > 0:
            weight *= min(1.0, 1000 / health1.latency_ms)
        
        return max(0.1, weight)  # Minimum weight of 0.1
    
    async def _optimize_topology(self):
        """Optimize network topology"""
        log_info("Optimizing network topology")
        
        # Analyze current topology
        await self._analyze_topology()
        
        # Identify optimization opportunities
        improvements = await self._identify_improvements()
        
        # Apply improvements
        for improvement in improvements:
            await self._apply_improvement(improvement)
    
    async def _analyze_topology(self):
        """Analyze current network topology"""
        if len(self.graph.nodes()) == 0:
            return
        
        # Calculate basic metrics
        if nx.is_connected(self.graph):
            self.avg_path_length = nx.average_shortest_path_length(self.graph, weight='weight')
        else:
            self.avg_path_length = float('inf')
        
        self.clustering_coefficient = nx.average_clustering(self.graph)
        
        # Calculate network efficiency
        self.network_efficiency = nx.global_efficiency(self.graph)
        
        log_info(f"Topology metrics - Path length: {self.avg_path_length:.2f}, "
                f"Clustering: {self.clustering_coefficient:.2f}, "
                f"Efficiency: {self.network_efficiency:.2f}")
    
    async def _identify_improvements(self) -> List[Dict]:
        """Identify topology improvements"""
        improvements = []
        
        # Check for disconnected nodes
        if not nx.is_connected(self.graph):
            components = list(nx.connected_components(self.graph))
            if len(components) > 1:
                improvements.append({
                    'type': 'connect_components',
                    'components': components
                })
        
        # Check degree distribution
        degrees = dict(self.graph.degree())
        low_degree_nodes = [node for node, degree in degrees.items() if degree < self.min_degree]
        high_degree_nodes = [node for node, degree in degrees.items() if degree > self.max_degree]
        
        if low_degree_nodes:
            improvements.append({
                'type': 'increase_degree',
                'nodes': low_degree_nodes
            })
        
        if high_degree_nodes:
            improvements.append({
                'type': 'decrease_degree',
                'nodes': high_degree_nodes
            })
        
        # Check for inefficient paths
        if self.avg_path_length > 6:  # Too many hops
            improvements.append({
                'type': 'add_shortcuts',
                'target_path_length': 4
            })
        
        return improvements
    
    async def _apply_improvement(self, improvement: Dict):
        """Apply topology improvement"""
        improvement_type = improvement['type']
        
        if improvement_type == 'connect_components':
            await self._connect_components(improvement['components'])
        elif improvement_type == 'increase_degree':
            await self._increase_node_degree(improvement['nodes'])
        elif improvement_type == 'decrease_degree':
            await self._decrease_node_degree(improvement['nodes'])
        elif improvement_type == 'add_shortcuts':
            await self._add_shortcuts(improvement['target_path_length'])
    
    async def _connect_components(self, components: List[Set[str]]):
        """Connect disconnected components"""
        log_info(f"Connecting {len(components)} disconnected components")
        
        # Connect components by adding edges between representative nodes
        for i in range(len(components) - 1):
            component1 = list(components[i])
            component2 = list(components[i + 1])
            
            # Select best nodes to connect
            node1 = self._select_best_connection_node(component1)
            node2 = self._select_best_connection_node(component2)
            
            # Add connection
            if node1 and node2:
                peer1 = self.discovery.peers.get(node1)
                peer2 = self.discovery.peers.get(node2)
                
                if peer1 and peer2:
                    await self._establish_connection(peer1, peer2)
    
    async def _increase_node_degree(self, nodes: List[str]):
        """Increase degree of low-degree nodes"""
        for node_id in nodes:
            peer = self.discovery.peers.get(node_id)
            if not peer:
                continue
            
            # Find best candidates for connection
            candidates = await self._find_connection_candidates(peer, max_connections=2)
            
            for candidate_peer in candidates:
                await self._establish_connection(peer, candidate_peer)
    
    async def _decrease_node_degree(self, nodes: List[str]):
        """Decrease degree of high-degree nodes"""
        for node_id in nodes:
            # Remove lowest quality connections
            edges = list(self.graph.edges(node_id, data=True))
            
            # Sort by weight (lowest first)
            edges.sort(key=lambda x: x[2].get('weight', 1.0))
            
            # Remove excess connections
            excess_count = self.graph.degree(node_id) - self.max_degree
            for i in range(min(excess_count, len(edges))):
                edge = edges[i]
                await self._remove_connection(edge[0], edge[1])
    
    async def _add_shortcuts(self, target_path_length: float):
        """Add shortcut connections to reduce path length"""
        # Find pairs of nodes with long shortest paths
        all_pairs = dict(nx.all_pairs_shortest_path_length(self.graph))
        
        long_paths = []
        for node1, paths in all_pairs.items():
            for node2, distance in paths.items():
                if node1 != node2 and distance > target_path_length:
                    long_paths.append((node1, node2, distance))
        
        # Sort by path length (longest first)
        long_paths.sort(key=lambda x: x[2], reverse=True)
        
        # Add shortcuts for longest paths
        for node1_id, node2_id, _ in long_paths[:5]:  # Limit to 5 shortcuts
            peer1 = self.discovery.peers.get(node1_id)
            peer2 = self.discovery.peers.get(node2_id)
            
            if peer1 and peer2 and not self.graph.has_edge(node1_id, node2_id):
                await self._establish_connection(peer1, peer2)
    
    def _select_best_connection_node(self, nodes: List[str]) -> Optional[str]:
        """Select best node for inter-component connection"""
        best_node = None
        best_score = 0
        
        for node_id in nodes:
            peer = self.discovery.peers.get(node_id)
            if not peer:
                continue
            
            # Score based on reputation and health
            health = self.health_monitor.get_health_status(node_id)
            score = peer.reputation
            
            if health:
                score *= health.health_score
            
            if score > best_score:
                best_score = score
                best_node = node_id
        
        return best_node
    
    async def _find_connection_candidates(self, peer: PeerNode, max_connections: int = 3) -> List[PeerNode]:
        """Find best candidates for new connections"""
        candidates = []
        
        for candidate_peer in self.discovery.get_peer_list():
            if (candidate_peer.node_id == peer.node_id or 
                self.graph.has_edge(peer.node_id, candidate_peer.node_id)):
                continue
            
            # Score candidate
            score = await self._calculate_connection_weight(peer, candidate_peer)
            candidates.append((candidate_peer, score))
        
        # Sort by score and return top candidates
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [candidate for candidate, _ in candidates[:max_connections]]
    
    async def _establish_connection(self, peer1: PeerNode, peer2: PeerNode):
        """Establish connection between two peers"""
        try:
            # In a real implementation, this would establish actual network connection
            weight = await self._calculate_connection_weight(peer1, peer2)
            
            self.graph.add_edge(peer1.node_id, peer2.node_id, weight=weight)
            
            log_info(f"Established connection between {peer1.node_id} and {peer2.node_id}")
            
        except Exception as e:
            log_error(f"Failed to establish connection between {peer1.node_id} and {peer2.node_id}: {e}")
    
    async def _remove_connection(self, node1_id: str, node2_id: str):
        """Remove connection between two nodes"""
        try:
            if self.graph.has_edge(node1_id, node2_id):
                self.graph.remove_edge(node1_id, node2_id)
                log_info(f"Removed connection between {node1_id} and {node2_id}")
        except Exception as e:
            log_error(f"Failed to remove connection between {node1_id} and {node2_id}: {e}")
    
    def get_topology_metrics(self) -> Dict:
        """Get current topology metrics"""
        return {
            'node_count': len(self.graph.nodes()),
            'edge_count': len(self.graph.edges()),
            'avg_degree': sum(dict(self.graph.degree()).values()) / len(self.graph.nodes()) if self.graph.nodes() else 0,
            'avg_path_length': self.avg_path_length,
            'clustering_coefficient': self.clustering_coefficient,
            'network_efficiency': self.network_efficiency,
            'is_connected': nx.is_connected(self.graph),
            'strategy': self.strategy.value
        }
    
    def get_visualization_data(self) -> Dict:
        """Get data for network visualization"""
        nodes = []
        edges = []
        
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            peer = self.discovery.peers.get(node_id)
            
            nodes.append({
                'id': node_id,
                'address': node_data.get('address', ''),
                'reputation': node_data.get('reputation', 0),
                'degree': self.graph.degree(node_id)
            })
        
        for edge in self.graph.edges(data=True):
            edges.append({
                'source': edge[0],
                'target': edge[1],
                'weight': edge[2].get('weight', 1.0)
            })
        
        return {
            'nodes': nodes,
            'edges': edges
        }

# Global topology manager
topology_manager: Optional[NetworkTopology] = None

def get_topology_manager() -> Optional[NetworkTopology]:
    """Get global topology manager"""
    return topology_manager

def create_topology_manager(discovery: P2PDiscovery, health_monitor: PeerHealthMonitor) -> NetworkTopology:
    """Create and set global topology manager"""
    global topology_manager
    topology_manager = NetworkTopology(discovery, health_monitor)
    return topology_manager
EOF

    log_info "Network topology optimization created"
}

# Function to create network partition handling
create_partition_handling() {
    log_info "Creating network partition handling..."
    
    cat > "$NETWORK_DIR/partition.py" << 'EOF'
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
EOF

    log_info "Network partition handling created"
}

# Function to create network recovery mechanisms
create_recovery_mechanisms() {
    log_info "Creating network recovery mechanisms..."
    
    cat > "$NETWORK_DIR/recovery.py" << 'EOF'
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
EOF

    log_info "Network recovery mechanisms created"
}

# Function to create network tests
create_network_tests() {
    log_info "Creating network test suite..."
    
    mkdir -p "/opt/aitbc/apps/blockchain-node/tests/network"
    
    cat > "/opt/aitbc/apps/blockchain-node/tests/network/test_discovery.py" << 'EOF'
"""
Tests for P2P Discovery Service
"""

import pytest
import asyncio
from unittest.mock import Mock, patch

from aitbc_chain.network.discovery import P2PDiscovery, PeerNode, NodeStatus

class TestP2PDiscovery:
    """Test cases for P2P discovery service"""
    
    def setup_method(self):
        """Setup test environment"""
        self.discovery = P2PDiscovery("test-node", "127.0.0.1", 8000)
        
        # Add bootstrap nodes
        self.discovery.add_bootstrap_node("127.0.0.1", 8001)
        self.discovery.add_bootstrap_node("127.0.0.1", 8002)
    
    def test_generate_node_id(self):
        """Test node ID generation"""
        hostname = "node1.example.com"
        address = "127.0.0.1"
        port = 8000
        public_key = "test_public_key"

        node_id = self.discovery.generate_node_id(hostname, address, port, public_key)

        assert isinstance(node_id, str)
        assert len(node_id) == 64  # SHA256 hex length

        # Test consistency
        node_id2 = self.discovery.generate_node_id(hostname, address, port, public_key)
        assert node_id == node_id2
    
    def test_add_bootstrap_node(self):
        """Test adding bootstrap node"""
        initial_count = len(self.discovery.bootstrap_nodes)
        
        self.discovery.add_bootstrap_node("127.0.0.1", 8003)
        
        assert len(self.discovery.bootstrap_nodes) == initial_count + 1
        assert ("127.0.0.1", 8003) in self.discovery.bootstrap_nodes
    
    def test_generate_node_id_consistency(self):
        """Test node ID generation consistency"""
        hostname = "node2.example.com"
        address = "192.168.1.1"
        port = 9000
        public_key = "test_key"

        node_id1 = self.discovery.generate_node_id(hostname, address, port, public_key)
        node_id2 = self.discovery.generate_node_id(hostname, address, port, public_key)

        assert node_id1 == node_id2

        # Different inputs should produce different IDs
        node_id3 = self.discovery.generate_node_id(hostname, "192.168.1.2", port, public_key)
        assert node_id1 != node_id3
    
    def test_get_peer_count_empty(self):
        """Test getting peer count with no peers"""
        assert self.discovery.get_peer_count() == 0
    
    def test_get_peer_list_empty(self):
        """Test getting peer list with no peers"""
        assert self.discovery.get_peer_list() == []
    
    def test_update_peer_reputation_new_peer(self):
        """Test updating reputation for non-existent peer"""
        result = self.discovery.update_peer_reputation("nonexistent", 0.1)
        assert result is False
    
    def test_update_peer_reputation_bounds(self):
        """Test reputation bounds"""
        # Add a test peer
        peer = PeerNode(
            node_id="test_peer",
            address="127.0.0.1",
            port=8001,
            public_key="test_key",
            last_seen=0,
            status=NodeStatus.ONLINE,
            capabilities=["test"],
            reputation=0.5,
            connection_count=0
        )
        self.discovery.peers["test_peer"] = peer
        
        # Try to increase beyond 1.0
        result = self.discovery.update_peer_reputation("test_peer", 0.6)
        assert result is True
        assert self.discovery.peers["test_peer"].reputation == 1.0
        
        # Try to decrease below 0.0
        result = self.discovery.update_peer_reputation("test_peer", -1.5)
        assert result is True
        assert self.discovery.peers["test_peer"].reputation == 0.0

if __name__ == "__main__":
    pytest.main([__file__])
EOF

    log_info "Network test suite created"
}

# Function to setup test network
setup_test_network() {
    log_info "Setting up network infrastructure test environment..."
    
    # Create test network configuration
    cat > "/opt/aitbc/config/network_test.json" << 'EOF'
{
    "network_name": "network-test",
    "discovery": {
        "bootstrap_nodes": [
            "10.1.223.93:8000",
            "10.1.223.40:8000",
            "10.1.223.93:8001"
        ],
        "discovery_interval": 30,
        "peer_timeout": 300,
        "max_peers": 50
    },
    "health_monitoring": {
        "check_interval": 60,
        "max_latency_ms": 1000,
        "min_availability_percent": 90.0,
        "min_health_score": 0.5,
        "max_consecutive_failures": 3
    },
    "peer_management": {
        "max_connections": 50,
        "min_connections": 8,
        "connection_retry_interval": 300,
        "ban_threshold": 0.1,
        "auto_reconnect": true,
        "auto_ban_malicious": true,
        "load_balance": true
    },
    "topology": {
        "strategy": "hybrid",
        "optimization_interval": 300,
        "max_degree": 8,
        "min_degree": 3
    },
    "partition_handling": {
        "detection_interval": 30,
        "recovery_timeout": 300,
        "max_partition_size": 0.4,
        "min_connected_nodes": 3,
        "partition_detection_threshold": 0.3
    },
    "recovery": {
        "strategy": "adaptive",
        "recovery_interval": 60,
        "max_recovery_attempts": 3,
        "recovery_timeout": 300,
        "emergency_threshold": 0.1
    }
}
EOF

    log_info "Network test configuration created"
}

# Function to run network tests
run_network_tests() {
    log_info "Running network infrastructure tests..."
    
    cd /opt/aitbc/apps/blockchain-node
    
    # Install test dependencies if needed
    if ! python -c "import networkx" 2>/dev/null; then
        log_info "Installing networkx..."
        pip install networkx
    fi
    
    # Run tests
    python -m pytest tests/network/ -v
    
    if [ $? -eq 0 ]; then
        log_info "All network tests passed!"
    else
        log_error "Some network tests failed!"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting Phase 2: Network Infrastructure Setup"
    
    # Create necessary directories
    mkdir -p "$NETWORK_DIR"
    mkdir -p "/opt/aitbc/config"
    
    # Execute setup steps
    backup_network
    create_p2p_discovery
    create_peer_health_monitoring
    create_dynamic_peer_management
    create_topology_optimization
    create_partition_handling
    create_recovery_mechanisms
    create_network_tests
    setup_test_network
    
    # Run tests
    if run_network_tests; then
        log_info "Phase 2 network infrastructure setup completed successfully!"
        log_info "Next steps:"
        log_info "1. Configure network parameters"
        log_info "2. Start network services"
        log_info "3. Test peer discovery and health monitoring"
        log_info "4. Proceed to Phase 3: Economic Layer"
    else
        log_error "Phase 2 setup failed - check test output"
        return 1
    fi
}

# Execute main function
main "$@"
