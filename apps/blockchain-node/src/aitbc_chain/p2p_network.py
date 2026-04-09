#!/usr/bin/env python3
"""
P2P Network Service using Direct TCP connections
Handles decentralized peer-to-peer mesh communication between blockchain nodes
"""

import asyncio
import json
import logging
from .mempool import get_mempool, compute_tx_hash
from typing import Dict, Any, Optional, Set, Tuple

logger = logging.getLogger(__name__)

class P2PNetworkService:
    def __init__(self, host: str, port: int, node_id: str, peers: str = ""):
        self.host = host
        self.port = port
        self.node_id = node_id
        
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

        self._background_tasks = []

    async def start(self):
        """Start P2P network service"""
        logger.info(f"Starting P2P network mesh service on {self.host}:{self.port}")
        logger.info(f"Node ID: {self.node_id}")
        
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
                        for tx_hash, pending_tx in mempool._transactions.items():
                            if tx_hash not in self.seen_txs:
                                self.seen_txs.add(tx_hash)
                                txs_to_broadcast.append(pending_tx.content)
                                
                elif hasattr(mempool, '_conn'): # DatabaseMempool
                    with mempool._lock:
                        cursor = mempool._conn.execute(
                            "SELECT tx_hash, content FROM mempool WHERE chain_id = ?",
                            ('ait-mainnet',)
                        )
                        for row in cursor.fetchall():
                            tx_hash = row[0]
                            if tx_hash not in self.seen_txs:
                                self.seen_txs.add(tx_hash)
                                import json
                                txs_to_broadcast.append(json.loads(row[1]))

                for tx in txs_to_broadcast:
                    msg = {'type': 'new_transaction', 'tx': tx}
                    writers = list(self.active_connections.values())
                    for writer in writers:
                        await self._send_message(writer, msg)
                        
            except Exception as e:
                logger.error(f"Error in mempool sync loop: {e}")
                
            await asyncio.sleep(2)

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
                for node_id, writer in self.active_connections.items():
                    peer_ip = writer.get_extra_info('peername')[0]
                    # We might want to resolve hostname -> IP but keeping it simple:
                    if peer_ip == host or (host == "aitbc1" and peer_ip.startswith("10.")):
                         already_connected_ip = True
                         break
                         
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
            
            # Send handshake immediately
            handshake = {
                'type': 'handshake',
                'node_id': self.node_id,
                'listen_port': self.port
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
            
            if not peer_node_id or peer_node_id == self.node_id:
                logger.warning(f"Peer {addr} provided invalid or self node_id: {peer_node_id}")
                writer.close()
                return
                
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
            
            # Reply with our handshake
            reply_handshake = {
                'type': 'handshake',
                'node_id': self.node_id,
                'listen_port': self.port
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

    async def _listen_to_stream(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, endpoint: Tuple[str, int], outbound: bool, peer_id: str = None):
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
                            if not peer_id or peer_id == self.node_id:
                                logger.warning(f"Invalid handshake reply from {addr}. Closing.")
                                break
                                
                            if peer_id in self.active_connections:
                                logger.info(f"Already connected to node {peer_id}. Closing duplicate outbound.")
                                break
                                
                            self.active_connections[peer_id] = writer
                            logger.info(f"Outbound handshake complete. Connected to node {peer_id}")
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
                        pass # Ignore subsequent handshakes
                    elif msg_type == 'new_transaction':
                        tx_data = message.get('tx')
                        if tx_data:
                            try:
                                tx_hash = compute_tx_hash(tx_data)
                                if not hasattr(self, 'seen_txs'):
                                    self.seen_txs = set()
                                    
                                if tx_hash not in self.seen_txs:
                                    logger.info(f"Received new P2P transaction: {tx_hash}")
                                    self.seen_txs.add(tx_hash)
                                    mempool = get_mempool()
                                    # Add to local mempool
                                    mempool.add(tx_data)
                                    
                                    # Forward to other peers (Gossip)
                                    forward_msg = {'type': 'new_transaction', 'tx': tx_data}
                                    writers = list(self.active_connections.values())
                                    for w in writers:
                                        if w != writer: # Don't send back to sender
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
            except Exception:
                pass

    async def _send_message(self, writer: asyncio.StreamWriter, message: dict):
        """Helper to send a JSON message over a stream"""
        try:
            data = json.dumps(message) + '\n'
            writer.write(data.encode())
            await writer.drain()
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def _ping_peers_loop(self):
        """Periodically broadcast pings to all active connections to keep them alive"""
        while not self._stop_event.is_set():
            await asyncio.sleep(20)
            ping_msg = {'type': 'ping', 'node_id': self.node_id}
            
            # Make a copy of writers to avoid dictionary changed during iteration error
            writers = list(self.active_connections.values())
            for writer in writers:
                await self._send_message(writer, ping_msg)


async def run_p2p_service(host: str, port: int, node_id: str, peers: str):
    """Run P2P service"""
    service = P2PNetworkService(host, port, node_id, peers)
    await service.start()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC Direct TCP P2P Mesh Network")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=7070, help="Bind port")
    parser.add_argument("--node-id", required=True, help="Node identifier (required for handshake)")
    parser.add_argument("--peers", default="", help="Comma separated list of initial peers to dial (ip:port)")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        asyncio.run(run_p2p_service(args.host, args.port, args.node_id, args.peers))
    except KeyboardInterrupt:
        logger.info("P2P service stopped by user")

if __name__ == "__main__":
    main()
