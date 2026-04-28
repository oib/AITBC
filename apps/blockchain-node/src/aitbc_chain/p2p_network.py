#!/usr/bin/env python3
"""
P2P Network Service using Direct TCP connections
Handles decentralized peer-to-peer mesh communication between blockchain nodes
"""

import asyncio
import json
import logging
from .config import settings
from .mempool import get_mempool, compute_tx_hash
from .network.nat_traversal import NATTraversalService
from .network.island_manager import IslandManager
from .network.hub_manager import HubManager
from typing import Dict, Any, Optional, Set, Tuple, List

from aitbc import get_logger

logger = get_logger(__name__)

class P2PNetworkService:
    def __init__(self, host: str, port: int, node_id: str, peers: str = "", stun_servers: List[str] = None,
                 island_id: str = "", island_name: str = "default", is_hub: bool = False,
                 island_chain_id: str = "", chain_id: str = ""):
        self.host = host
        self.port = port
        self.node_id = node_id
        
        # Chain configuration
        self.chain_id = chain_id or island_chain_id or "ait-mainnet"
        
        # Island configuration
        self.island_id = island_id
        self.island_name = island_name
        self.is_hub = is_hub
        self.island_chain_id = island_chain_id or f"ait-{island_id[:8]}" if island_id else ""
        
        # Initial peers to dial (format: "ip:port,ip:port")
        self.initial_peers = []
        if peers:
            for p in peers.split(','):
                p = p.strip()
                if p:
                    parts = p.split(':')
                    if len(parts) == 2:
                        self.initial_peers.append((parts[0], int(parts[1])))

        self._server = None
        self._stop_event = asyncio.Event()
        
        # Active connections
        # Map of node_id -> writer stream
        self.active_connections: Dict[str, asyncio.StreamWriter] = {}
        # Set of active endpoints we've connected to prevent duplicate dialing
        self.connected_endpoints: Set[Tuple[str, int]] = set()
        
        # Public endpoint discovered via STUN
        self.public_endpoint: Optional[Tuple[str, int]] = None
        
        # NAT traversal service
        self.nat_traversal: Optional[NATTraversalService] = None
        if stun_servers:
            self.nat_traversal = NATTraversalService(stun_servers)
        
        # Island manager
        self.island_manager: Optional[IslandManager] = None
        
        # Hub manager
        self.hub_manager: Optional[HubManager] = None

        self._background_tasks = []

    async def start(self):
        """Start P2P network service"""
        logger.info(f"Starting P2P network mesh service on {self.host}:{self.port}")
        logger.info(f"Node ID: {self.node_id}")
        logger.info(f"Island ID: {self.island_id}")
        logger.info(f"Island Name: {self.island_name}")
        logger.info(f"Is Hub: {self.is_hub}")
        logger.info(f"Chain ID: {self.chain_id}")
        
        # Initialize island manager
        if self.island_id:
            self.island_manager = IslandManager(
                self.node_id,
                self.island_id,
                self.island_chain_id or f"ait-{self.island_id[:8]}"
            )
            logger.info("Initialized island manager")
        
        # Initialize hub manager if this node is a hub
        if self.is_hub:
            self.hub_manager = HubManager(
                self.node_id,
                self.host,
                self.port,
                self.island_id,
                self.island_name,
                settings.redis_url
            )
            await self.hub_manager.register_as_hub(self.public_endpoint[0] if self.public_endpoint else None,
                                                 self.public_endpoint[1] if self.public_endpoint else None)
            logger.info("Initialized hub manager")
        
        # Discover public endpoint via STUN if configured
        if self.nat_traversal:
            logger.info("Attempting STUN discovery for public endpoint...")
            try:
                await self.nat_traversal.discover_endpoint()
                self.public_endpoint = self.nat_traversal.get_public_endpoint()
                if self.public_endpoint:
                    logger.info(f"Discovered public endpoint: {self.public_endpoint[0]}:{self.public_endpoint[1]}")
                else:
                    logger.warning("STUN discovery failed, will use local address")
            except Exception as e:
                logger.error(f"STUN discovery error: {e}")
        
        # Create TCP server for inbound P2P connections
        self._server = await asyncio.start_server(
            self._handle_inbound_connection, 
            self.host, 
            self.port
        )
        
        logger.info(f"P2P service listening on {self.host}:{self.port}")
        
        # Start background task to dial known peers
        dial_task = asyncio.create_task(self._dial_peers_loop())
        self._background_tasks.append(dial_task)

        # Start background task to broadcast pings to active peers
        ping_task = asyncio.create_task(self._ping_peers_loop())
        self._background_tasks.append(ping_task)
        
        # Start background task to sync mempool
        mempool_task = asyncio.create_task(self._mempool_sync_loop())
        self._background_tasks.append(mempool_task)

        try:
            await self._stop_event.wait()
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop P2P network service"""
        logger.info("Stopping P2P network service")
        
        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
            
        # Close all active connections
        for writer in self.active_connections.values():
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        self.active_connections.clear()
        self.connected_endpoints.clear()

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    
    async def _send_message(self, writer: asyncio.StreamWriter, message: Dict[str, Any]):
        """Serialize and send a newline-delimited JSON message"""
        payload = json.dumps(message).encode() + b"\n"
        writer.write(payload)
        await writer.drain()


    async def _ping_peers_loop(self):
        """Periodically ping active peers to keep connections healthy"""
        while not self._stop_event.is_set():
            try:
                writers = list(self.active_connections.items())
                for peer_id, writer in writers:
                    try:
                        await self._send_message(writer, {'type': 'ping', 'node_id': self.node_id})
                    except Exception as e:
                        logger.debug(f"Failed to ping {peer_id}: {e}")
            except Exception as e:
                logger.error(f"Error in ping loop: {e}")

            await asyncio.sleep(10)


    async def _mempool_sync_loop(self):
        """Periodically check local mempool and broadcast new transactions to peers"""
        self.seen_txs = set()
        while not self._stop_event.is_set():
            try:
                mempool = get_mempool()
                
                # Different logic depending on if InMemory or Database
                txs_to_broadcast = []
                
                if hasattr(mempool, '_transactions'): # InMemoryMempool
                    with mempool._lock:
                        for chain_id, chain_transactions in mempool._transactions.items():
                            for tx_hash, pending_tx in chain_transactions.items():
                                seen_key = (chain_id, tx_hash)
                                if seen_key not in self.seen_txs:
                                    self.seen_txs.add(seen_key)
                                    txs_to_broadcast.append(pending_tx.content)
                                
                elif hasattr(mempool, '_conn'): # DatabaseMempool
                    with mempool._lock:
                        cursor = mempool._conn.execute(
                            "SELECT chain_id, tx_hash, content FROM mempool"
                        )
                        for row in cursor.fetchall():
                            chain_id = row[0]
                            tx_hash = row[1]
                            seen_key = (chain_id, tx_hash)
                            if seen_key not in self.seen_txs:
                                self.seen_txs.add(seen_key)
                                import json
                                txs_to_broadcast.append(json.loads(row[2]))

                logger.debug(f"Mempool sync loop iteration. txs_to_broadcast: {len(txs_to_broadcast)}")
                for tx in txs_to_broadcast:
                    msg = {'type': 'new_transaction', 'tx': tx}
                    writers = list(self.active_connections.values())
                    for writer in writers:
                        await self._send_message(writer, msg)
                        
            except Exception as e:
                logger.error(f"Error in mempool sync loop: {e}")
                
            await asyncio.sleep(1)

    async def _dial_peers_loop(self):
        """Background loop to continually try connecting to disconnected initial peers"""
        while not self._stop_event.is_set():
            for host, port in self.initial_peers:
                endpoint = (host, port)
                
                # Prevent dialing ourselves or already connected peers
                if endpoint in self.connected_endpoints:
                    continue
                    
                # Find if we are already connected to a peer with this host/ip by inbound connections
                # This prevents two nodes from endlessly redialing each other's listen ports
                already_connected_ip = False
                logger.debug(f"Checking if already connected to {host}, active connections: {len(self.active_connections)}")
                for node_id, writer in self.active_connections.items():
                    peer_ip = writer.get_extra_info('peername')[0]
                    logger.debug(f"Checking peer {node_id} with IP {peer_ip} against host {host}")
                    # Direct IP match
                    if peer_ip == host:
                        already_connected_ip = True
                        logger.debug(f"Match: peer_ip == host ({peer_ip} == {host})")
                        break
                    # Resolve hostname to IP and compare
                    try:
                        import socket
                        host_ip = socket.gethostbyname(host)
                        if peer_ip == host_ip:
                            already_connected_ip = True
                            logger.debug(f"Match: resolved {host} to {host_ip}, matches peer_ip {peer_ip}")
                            break
                    except socket.gaierror:
                        # Hostname resolution failed, skip this comparison
                        logger.debug(f"Could not resolve hostname {host}, skipping IP comparison")
                        pass
                         
                if already_connected_ip:
                    self.connected_endpoints.add(endpoint) # Mark so we don't try again
                    continue
                    
                # Attempt connection
                asyncio.create_task(self._dial_peer(host, port))
                
            # Wait before trying again
            await asyncio.sleep(10)

    async def _dial_peer(self, host: str, port: int):
        """Attempt to establish an outbound TCP connection to a peer"""
        endpoint = (host, port)
        try:
            reader, writer = await asyncio.open_connection(host, port)
            logger.info(f"Successfully dialed outbound peer at {host}:{port}")
            
            # Record that we're connected to this endpoint
            self.connected_endpoints.add(endpoint)
            
            # Send handshake immediately with island information
            handshake = {
                'type': 'handshake',
                'node_id': self.node_id,
                'listen_port': self.port,
                'chain_id': self.chain_id,
                'island_id': self.island_id,
                'island_name': self.island_name,
                'is_hub': self.is_hub,
                'island_chain_id': self.island_chain_id,
                'public_address': self.public_endpoint[0] if self.public_endpoint else None,
                'public_port': self.public_endpoint[1] if self.public_endpoint else None
            }
            await self._send_message(writer, handshake)
            
            # Start listening to this outbound connection
            await self._listen_to_stream(reader, writer, endpoint, outbound=True)
            
        except ConnectionRefusedError:
            logger.debug(f"Peer {host}:{port} refused connection (offline?)")
        except Exception as e:
            logger.debug(f"Failed to dial peer {host}:{port}: {e}")

    async def _handle_inbound_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming P2P TCP connections from other nodes"""
        addr = writer.get_extra_info('peername')
        logger.info(f"Incoming P2P connection from {addr}")
        
        # Wait for handshake
        try:
            # Add timeout for initial handshake
            data = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not data:
                writer.close()
                return
                
            message = json.loads(data.decode())
            if message.get('type') != 'handshake':
                logger.warning(f"Peer {addr} did not handshake first. Dropping.")
                writer.close()
                return
                
            peer_node_id = message.get('node_id')
            peer_listen_port = message.get('listen_port', 7070)
            peer_island_id = message.get('island_id', '')
            peer_island_name = message.get('island_name', '')
            peer_is_hub = message.get('is_hub', False)
            peer_island_chain_id = message.get('island_chain_id', '')
            peer_public_address = message.get('public_address')
            peer_public_port = message.get('public_port')
            
            if not peer_node_id or peer_node_id == self.node_id:
                logger.warning(f"Peer {addr} provided invalid or self node_id: {peer_node_id}")
                writer.close()
                return
            
            # Store peer's island information
            logger.info(f"Peer {peer_node_id} from island {peer_island_id} (hub: {peer_is_hub})")

            # Store peer's public endpoint if provided
            if peer_public_address and peer_public_port:
                logger.info(f"Peer {peer_node_id} public endpoint: {peer_public_address}:{peer_public_port}")

            # Accept handshake and store connection
            logger.info(f"Handshake accepted from node {peer_node_id} at {addr}")

            # If we already have a connection to this node, drop the new one to prevent duplicates
            if peer_node_id in self.active_connections:
                logger.info(f"Already connected to node {peer_node_id}. Dropping duplicate inbound.")
                writer.close()
                return

            self.active_connections[peer_node_id] = writer

            # Map their listening endpoint so we don't try to dial them
            remote_ip = addr[0]
            self.connected_endpoints.add((remote_ip, peer_listen_port))

            # Add peer to island manager if available
            if self.island_manager and peer_island_id:
                self.island_manager.add_island_peer(peer_island_id, peer_node_id)

            # Add peer to hub manager if available
            if self.hub_manager:
                from .network.hub_manager import PeerInfo
                self.hub_manager.register_peer(PeerInfo(
                    node_id=peer_node_id,
                    address=remote_ip,
                    port=peer_listen_port,
                    island_id=peer_island_id,
                    is_hub=peer_is_hub,
                    public_address=peer_public_address,
                    public_port=peer_public_port,
                    last_seen=asyncio.get_event_loop().time()
                ))

            # Reply with our handshake including island information
            reply_handshake = {
                'type': 'handshake',
                'node_id': self.node_id,
                'listen_port': self.port,
                'chain_id': self.chain_id,
                'island_id': self.island_id,
                'island_name': self.island_name,
                'is_hub': self.is_hub,
                'island_chain_id': self.island_chain_id,
                'public_address': self.public_endpoint[0] if self.public_endpoint else None,
                'public_port': self.public_endpoint[1] if self.public_endpoint else None
            }
            await self._send_message(writer, reply_handshake)

            # Listen for messages
            await self._listen_to_stream(reader, writer, (remote_ip, peer_listen_port), outbound=False, peer_id=peer_node_id)

        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for handshake from {addr}")
            writer.close()
        except Exception as e:
            logger.error(f"Error handling inbound connection from {addr}: {e}")
            writer.close()

    async def _listen_to_stream(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, endpoint: Tuple[str, int],
                                outbound: bool, peer_id: str = None):
        """Read loop for an established TCP stream (both inbound and outbound)"""
        addr = endpoint
        try:
            while not self._stop_event.is_set():
                data = await reader.readline()
                if not data:
                    break  # Connection closed remotely

                try:
                    message = json.loads(data.decode().strip())

                    msg_type = message.get('type')

                    # If this is an outbound connection, the first message MUST be their handshake reply
                    if outbound and peer_id is None:
                        if msg_type == 'handshake':
                            peer_id = message.get('node_id')
                            peer_island_id = message.get('island_id', '')
                            peer_is_hub = message.get('is_hub', False)

                            if not peer_id or peer_id == self.node_id:
                                logger.warning(f"Invalid handshake reply from {addr}. Closing.")
                                break

                            if peer_id in self.active_connections:
                                logger.info(f"Already connected to node {peer_id}. Closing duplicate outbound.")
                                break

                            self.active_connections[peer_id] = writer

                            # Add peer to island manager if available
                            if self.island_manager and peer_island_id:
                                self.island_manager.add_island_peer(peer_island_id, peer_id)

                            # Add peer to hub manager if available
                            if self.hub_manager:
                                from .network.hub_manager import PeerInfo
                                self.hub_manager.register_peer(PeerInfo(
                                    node_id=peer_id,
                                    address=addr[0],
                                    port=addr[1],
                                    island_id=peer_island_id,
                                    is_hub=peer_is_hub,
                                    public_address=message.get('public_address'),
                                    public_port=message.get('public_port'),
                                    last_seen=asyncio.get_event_loop().time()
                                ))

                            logger.info(f"Outbound handshake complete. Connected to node {peer_id} (island: {peer_island_id})")
                            continue
                        else:
                            logger.warning(f"Expected handshake reply from {addr}, got {msg_type}")
                            break

                    # Normal message handling
                    if msg_type == 'ping':
                        logger.debug(f"Received ping from {peer_id}")
                        await self._send_message(writer, {'type': 'pong', 'node_id': self.node_id})

                    elif msg_type == 'pong':
                        logger.debug(f"Received pong from {peer_id}")

                    elif msg_type == 'handshake':
                        pass  # Ignore subsequent handshakes
                    elif msg_type == 'join_request':
                        # Handle island join request (only if we're a hub)
                        if self.hub_manager:
                            logger.info(f"Received join_request from {peer_id}")
                            response = await self.hub_manager.handle_join_request(message)
                            if response:
                                await self._send_message(writer, response)
                        else:
                            logger.warning(f"Received join_request but not a hub, ignoring")
                    elif msg_type == 'join_response':
                        # Handle island join response (only if we requested to join)
                        logger.info(f"Received join_response from {peer_id}")
                        # Store the response for the CLI to retrieve
                        if not hasattr(self, '_join_response'):
                            self._join_response = {}
                        self._join_response[peer_id] = message
                    elif msg_type == 'gpu_provider_query':
                        # Handle GPU provider query
                        logger.info(f"Received gpu_provider_query from {peer_id}")
                        # Respond with GPU availability
                        gpu_response = {
                            'type': 'gpu_provider_response',
                            'node_id': self.node_id,
                            'gpu_available': self._get_gpu_count(),
                            'gpu_specs': self._get_gpu_specs()
                        }
                        await self._send_message(writer, gpu_response)
                    elif msg_type == 'gpu_provider_response':
                        # Handle GPU provider response
                        logger.info(f"Received gpu_provider_response from {peer_id}")
                        # Store the response for the CLI to retrieve
                        if not hasattr(self, '_gpu_provider_responses'):
                            self._gpu_provider_responses = {}
                        self._gpu_provider_responses[peer_id] = message
                    elif msg_type == 'new_transaction':
                        tx_data = message.get('tx')
                        if tx_data:
                            try:
                                tx_hash = compute_tx_hash(tx_data)
                                chain_id = tx_data.get('chain_id', settings.chain_id)
                                if not hasattr(self, 'seen_txs'):
                                    self.seen_txs = set()

                                seen_key = (chain_id, tx_hash)
                                if seen_key not in self.seen_txs:
                                    logger.info(f"Received new P2P transaction: {tx_hash}")
                                    self.seen_txs.add(seen_key)
                                    mempool = get_mempool()
                                    # Add to local mempool
                                    mempool.add(tx_data, chain_id=chain_id)

                                    # Forward to other peers (Gossip)
                                    forward_msg = {'type': 'new_transaction', 'tx': tx_data}
                                    writers = list(self.active_connections.values())
                                    for w in writers:
                                        if w != writer:  # Don't send back to sender
                                            await self._send_message(w, forward_msg)
                            except ValueError as e:
                                logger.debug(f"P2P tx rejected by mempool: {e}")
                            except Exception as e:
                                logger.error(f"P2P tx handling error: {e}")

                    else:
                        logger.info(f"Received {msg_type} from {peer_id}: {message}")
                        # In a real node, we would forward blocks/txs to the internal event bus here

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received from {addr}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Stream error with {addr}: {e}")
        finally:
            logger.info(f"Connection closed to {peer_id or addr}")
            if peer_id and peer_id in self.active_connections:
                del self.active_connections[peer_id]
            if endpoint in self.connected_endpoints:
                self.connected_endpoints.remove(endpoint)
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass

    def _get_gpu_count(self) -> int:
        """Get the number of available GPUs on this node"""
        try:
            # Try to read GPU count from system
            # This is a placeholder - in a real implementation, this would
            # query the actual GPU hardware or a configuration file
            import os
            gpu_config_path = '/var/lib/aitbc/gpu_config.json'
            if os.path.exists(gpu_config_path):
                with open(gpu_config_path, 'r') as f:
                    config = json.load(f)
                    return config.get('gpu_count', 0)
            return 0
        except Exception as e:
            logger.error(f"Error getting GPU count: {e}")
            return 0

    def _get_gpu_specs(self) -> dict:
        """Get GPU specifications for this node"""
        try:
            # Try to read GPU specs from system
            # This is a placeholder - in a real implementation, this would
            # query the actual GPU hardware or a configuration file
            import os
            gpu_config_path = '/var/lib/aitbc/gpu_config.json'
            if os.path.exists(gpu_config_path):
                with open(gpu_config_path, 'r') as f:
                    config = json.load(f)
                    return config.get('specs', {})
            return {}
        except Exception as e:
            logger.error(f"Error getting GPU specs: {e}")
            return {}

    async def send_join_request(self, hub_address: str, hub_port: int, island_id: str, island_name: str, node_id: str,
                                public_key_pem: str) -> Optional[dict]:
        """
        Send join request to a hub and wait for response

        Args:
            hub_address: Hub IP address or hostname
            hub_port: Hub port
            island_id: Island ID to join
            island_name: Island name
            node_id: Local node ID
            public_key_pem: Public key PEM

        Returns:
            dict: Join response from hub, or None if failed
        """
        try:
            # Connect to hub
            reader, writer = await asyncio.open_connection(hub_address, hub_port)
            logger.info(f"Connected to hub {hub_address}:{hub_port}")

            handshake = {
                'type': 'handshake',
                'node_id': node_id,
                'listen_port': self.port,
                'chain_id': self.chain_id,
                'island_id': island_id,
                'island_name': island_name,
                'is_hub': self.is_hub,
                'island_chain_id': self.island_chain_id,
                'public_address': self.public_endpoint[0] if self.public_endpoint else None,
                'public_port': self.public_endpoint[1] if self.public_endpoint else None,
            }
            await self._send_message(writer, handshake)
            logger.info("Sent handshake to hub")

            data = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not data:
                logger.warning("No handshake response from hub")
                writer.close()
                await writer.wait_closed()
                return None

            response = json.loads(data.decode().strip())
            if response.get('type') != 'handshake':
                logger.warning(f"Unexpected handshake response type: {response.get('type')}")
                writer.close()
                await writer.wait_closed()
                return None

            # Send join request
            join_request = {
                'type': 'join_request',
                'node_id': node_id,
                'island_id': island_id,
                'island_name': island_name,
                'public_key_pem': public_key_pem
            }
            await self._send_message(writer, join_request)
            logger.info(f"Sent join_request to hub")

            # Wait for join response (with timeout)
            try:
                data = await asyncio.wait_for(reader.readline(), timeout=30.0)
                if data:
                    response = json.loads(data.decode().strip())
                    if response.get('type') == 'join_response':
                        logger.info(f"Received join_response from hub")
                        writer.close()
                        await writer.wait_closed()
                        return response
                    else:
                        logger.warning(f"Unexpected response type: {response.get('type')}")
                else:
                    logger.warning("No response from hub")
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for join response")

            writer.close()
            await writer.wait_closed()
            return None

        except ConnectionRefusedError:
            logger.error(f"Hub {hub_address}:{hub_port} refused connection")
            return None
        except Exception as e:
            logger.error(f"Failed to send join request: {e}")
            return None


async def run_p2p_service(host: str, port: int, node_id: str, peers: str):
    """Run P2P service"""
    stun_servers = [server.strip() for server in settings.stun_servers.split(',') if server.strip()]
    service = P2PNetworkService(
        host,
        port,
        node_id,
        peers,
        stun_servers=stun_servers or None,
        island_id=settings.island_id,
        island_name=settings.island_name,
        is_hub=settings.is_hub,
        island_chain_id=settings.island_chain_id or settings.chain_id,
    )
    await service.start()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AITBC Direct TCP P2P Mesh Network")
    parser.add_argument("--host", default=settings.p2p_bind_host, help="Bind host")
    parser.add_argument("--port", type=int, default=7070, help="Bind port")
    parser.add_argument("--node-id", default="", help="Node identifier (defaults to settings.p2p_node_id)")
    parser.add_argument("--peers", default="", help="Comma separated list of initial peers to dial (ip:port)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        from .mempool import init_mempool
        import pathlib
        
        db_path = ""
        if settings.mempool_backend == "database":
            db_path = str(settings.db_path.parent / "mempool.db")
            
        init_mempool(
            backend=settings.mempool_backend,
            db_path=db_path,
            max_size=settings.mempool_max_size,
            min_fee=settings.min_fee
        )

        node_id = args.node_id or settings.p2p_node_id or settings.proposer_id
        if not node_id:
            raise ValueError("p2p node_id is required")

        asyncio.run(run_p2p_service(args.host, args.port, node_id, args.peers))
    except KeyboardInterrupt:
        logger.info("P2P service stopped by user")

if __name__ == "__main__":
    main()
