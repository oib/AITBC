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
    public_address: Optional[str] = None
    public_port: Optional[int] = None
    island_id: str = ""  # Island membership
    island_chain_id: str = ""  # Chain ID for this island
    is_hub: bool = False  # Hub capability

@dataclass
class DiscoveryMessage:
    message_type: str
    node_id: str
    address: str
    port: int
    island_id: str  # UUID-based island ID
    island_chain_id: str  # Chain ID for this island
    is_hub: bool  # Hub capability
    public_address: Optional[str] = None  # Public endpoint address
    public_port: Optional[int] = None  # Public endpoint port
    timestamp: float = 0
    signature: str = ""

class P2PDiscovery:
    """P2P node discovery and management service"""
    
    def __init__(self, local_node_id: str, local_address: str, local_port: int, 
                 island_id: str = "", island_chain_id: str = "", is_hub: bool = False,
                 public_endpoint: Optional[Tuple[str, int]] = None):
        self.local_node_id = local_node_id
        self.local_address = local_address
        self.local_port = local_port
        self.island_id = island_id
        self.island_chain_id = island_chain_id
        self.is_hub = is_hub
        self.public_endpoint = public_endpoint
        
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
            # Create discovery message with island information
            public_addr = self.public_endpoint[0] if self.public_endpoint else None
            public_port = self.public_endpoint[1] if self.public_endpoint else None
            
            message = DiscoveryMessage(
                message_type="hello",
                node_id=self.local_node_id,
                address=self.local_address,
                port=self.local_port,
                island_id=self.island_id,
                island_chain_id=self.island_chain_id,
                is_hub=self.is_hub,
                public_address=public_addr,
                public_port=public_port,
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
            peer_island_id = response.get("island_id", "")
            peer_island_chain_id = response.get("island_chain_id", "")
            peer_is_hub = response.get("is_hub", False)
            peer_public_address = response.get("public_address")
            peer_public_port = response.get("public_port")
            peer_capabilities = response.get("capabilities", [])
            
            # Create peer node with island information
            peer = PeerNode(
                node_id=peer_node_id,
                address=peer_address,
                port=peer_port,
                public_key=response.get("public_key", ""),
                last_seen=time.time(),
                status=NodeStatus.ONLINE,
                capabilities=peer_capabilities,
                reputation=1.0,
                connection_count=0,
                public_address=peer_public_address,
                public_port=peer_public_port,
                island_id=peer_island_id,
                island_chain_id=peer_island_chain_id,
                is_hub=peer_is_hub
            )
            
            # Add to peers
            self.peers[peer_node_id] = peer
            
            log_info(f"Added peer {peer_node_id} from {peer_address}:{peer_port} (island: {peer_island_id}, hub: {peer_is_hub})")
            
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
        
        public_addr = self.public_endpoint[0] if self.public_endpoint else None
        public_port = self.public_endpoint[1] if self.public_endpoint else None
        
        if message_type == "hello":
            # Respond with peer information including island data
            return {
                "message_type": "hello_response",
                "node_id": self.local_node_id,
                "address": self.local_address,
                "port": self.local_port,
                "island_id": self.island_id,
                "island_chain_id": self.island_chain_id,
                "is_hub": self.is_hub,
                "public_address": public_addr,
                "public_port": public_port,
                "public_key": "",  # Would include actual public key
                "capabilities": ["consensus", "mempool", "rpc"],
                "timestamp": time.time()
            }
        
        elif message_type == "get_peers":
            # Return list of known peers with island information
            peer_list = []
            for peer in self.peers.values():
                if peer.status == NodeStatus.ONLINE:
                    peer_list.append({
                        "node_id": peer.node_id,
                        "address": peer.address,
                        "port": peer.port,
                        "island_id": peer.island_id,
                        "island_chain_id": peer.island_chain_id,
                        "is_hub": peer.is_hub,
                        "public_address": peer.public_address,
                        "public_port": peer.public_port,
                        "capabilities": peer.capabilities,
                        "reputation": peer.reputation
                    })
            
            return {
                "message_type": "peers_response",
                "node_id": self.local_node_id,
                "peers": peer_list,
                "timestamp": time.time()
            }
        
        elif message_type == "get_hubs":
            # Return list of hub nodes
            hub_list = []
            for peer in self.peers.values():
                if peer.status == NodeStatus.ONLINE and peer.is_hub:
                    hub_list.append({
                        "node_id": peer.node_id,
                        "address": peer.address,
                        "port": peer.port,
                        "island_id": peer.island_id,
                        "public_address": peer.public_address,
                        "public_port": peer.public_port,
                    })
            
            return {
                "message_type": "hubs_response",
                "node_id": self.local_node_id,
                "hubs": hub_list,
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
