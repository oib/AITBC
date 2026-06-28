"""
P2P Network Service using Direct TCP connections
Handles decentralized peer-to-peer mesh communication between blockchain nodes
"""

import asyncio
import json
import os
from typing import Any

from aitbc.aitbc_logging import get_logger

from .config import settings
from .mempool import compute_tx_hash
from .network.hub_manager import HubManager
from .network.island_manager import IslandManager
from .network.nat_traversal import NATTraversalService

logger = get_logger("aitbc_chain.p2p_network")
_p2p_service_instance = None


def get_p2p_network() -> Any:
    """Get the global P2P network service instance"""
    return _p2p_service_instance


def set_p2p_network(service: Any) -> None:
    """Set the global P2P network service instance"""
    global _p2p_service_instance
    _p2p_service_instance = service


class P2PNetworkService:
    def __init__(
        self,
        host: str,
        port: int,
        node_id: str,
        peers: str = "",
        stun_servers: list[str] | None = None,
        island_id: str = "",
        island_name: str = "default",
        is_hub: bool = False,
        island_chain_id: str = "",
        chain_id: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.node_id = node_id
        self.chain_id = chain_id or island_chain_id or os.getenv("CHAIN_ID", "")
        self.island_id = island_id
        self.island_name = island_name
        self.is_hub = is_hub
        self.island_chain_id = island_chain_id or f"ait-{island_id[:8]}" if island_id else ""
        self.initial_peers = []
        if peers:
            for p in peers.split(","):
                p = p.strip()
                if p:
                    parts = p.split(":")
                    if len(parts) == 2:
                        self.initial_peers.append((parts[0], int(parts[1])))
        self._server: Any = None
        self._stop_event = asyncio.Event()
        self.active_connections: dict[str, asyncio.StreamWriter] = {}
        self.connected_endpoints: set[tuple[str, int]] = set()
        self.public_endpoint: tuple[str, int] | None = None
        self.nat_traversal: NATTraversalService | None = None
        if stun_servers:
            self.nat_traversal = NATTraversalService(stun_servers)
        self.island_manager: IslandManager | None = None
        self.hub_manager: HubManager | None = None
        self._background_tasks: list[asyncio.Task[Any]] = []
        # v0.6.2: Protocol versioning — track peers operating in legacy mode
        self._protocol_version: int = settings.gossip_protocol_version
        self._legacy_peers: set[str] = set()  # peer_ids with protocol_version < 2

    async def start(self) -> None:
        """Start P2P network service"""
        logger.info("Starting P2P network mesh service on %s:%s", self.host, self.port)
        logger.info("Node ID: %s", self.node_id)
        logger.info("Island ID: %s", self.island_id)
        logger.info("Island Name: %s", self.island_name)
        logger.info("Is Hub: %s", self.is_hub)
        logger.info("Chain ID: %s", self.chain_id)
        if self.island_id:
            self.island_manager = IslandManager(
                self.node_id, self.island_id, self.island_chain_id or f"ait-{self.island_id[:8]}"
            )
            logger.info("Initialized island manager")
        if self.is_hub:
            self.hub_manager = HubManager(
                self.node_id, self.host, self.port, self.island_id, self.island_name, settings.redis_url
            )
            await self.hub_manager.register_as_hub(
                self.public_endpoint[0] if self.public_endpoint else None,
                self.public_endpoint[1] if self.public_endpoint else None,
            )
            logger.info("Initialized hub manager")
        if self.nat_traversal:
            logger.info("Attempting STUN discovery for public endpoint...")
            try:
                await self.nat_traversal.discover_endpoint()
                self.public_endpoint = self.nat_traversal.get_public_endpoint()
                if self.public_endpoint:
                    logger.info("Discovered public endpoint: %s:%s", self.public_endpoint[0], self.public_endpoint[1])
                else:
                    logger.warning("STUN discovery failed, will use local address")
            except Exception as e:
                logger.error("STUN discovery error: %s", e)
        self._server = await asyncio.start_server(self._handle_inbound_connection, self.host, self.port)
        logger.info("P2P service listening on %s:%s", self.host, self.port)
        dial_task = asyncio.create_task(self._dial_peers_loop())
        self._background_tasks.append(dial_task)
        ping_task = asyncio.create_task(self._ping_peers_loop())
        self._background_tasks.append(ping_task)
        mempool_task = asyncio.create_task(self._mempool_sync_loop())
        self._background_tasks.append(mempool_task)
        try:
            await self._stop_event.wait()
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop P2P network service"""
        logger.info("Stopping P2P network service")
        for task in self._background_tasks:
            task.cancel()
        for writer in self.active_connections.values():
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # nosec B110 - intentional silent cleanup
                pass
        self.active_connections.clear()
        self.connected_endpoints.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _send_message(self, writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        """Serialize and send a newline-delimited JSON message (compressed when enabled)."""
        from .network.compression import encode_payload

        payload = (encode_payload(message)).encode() + b"\n"
        writer.write(payload)
        await writer.drain()

    async def broadcast_to_peers(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected peers"""
        writers = list(self.active_connections.values())
        for writer in writers:
            try:
                await self._send_message(writer, message)
            except Exception as e:
                logger.debug("Failed to broadcast to peer: %s", e)

    async def _ping_peers_loop(self) -> None:
        """Periodically ping active peers to keep connections healthy"""
        while not self._stop_event.is_set():
            try:
                writers = list(self.active_connections.items())
                for peer_id, writer in writers:
                    try:
                        await self._send_message(writer, {"type": "ping", "node_id": self.node_id})
                    except Exception as e:
                        logger.debug("Failed to ping %s: %s", peer_id, e)
            except Exception as e:
                logger.error("Error in ping loop: %s", e)
            await asyncio.sleep(10)

    async def _mempool_sync_loop(self) -> None:
        """Periodically check local mempool and broadcast new transactions to peers"""
        self.seen_txs: set[tuple[str, str]] = set()
        while not self._stop_event.is_set():
            try:
                from .mempool import get_mempool as get_mempool_instance

                mempool = get_mempool_instance()
                txs_to_broadcast = []
                if hasattr(mempool, "_transactions"):
                    with mempool._lock:
                        for chain_id, chain_transactions in mempool._transactions.items():
                            for tx_hash, pending_tx in chain_transactions.items():
                                seen_key = (chain_id, tx_hash)
                                if seen_key not in self.seen_txs:
                                    self.seen_txs.add(seen_key)
                                    txs_to_broadcast.append(pending_tx.content)
                elif hasattr(mempool, "_conn"):
                    with mempool._lock:
                        cursor = mempool._conn.execute("SELECT chain_id, tx_hash, content FROM mempool")
                        for row in cursor.fetchall():
                            chain_id = row[0]
                            tx_hash = row[1]
                            seen_key = (chain_id, tx_hash)
                            if seen_key not in self.seen_txs:
                                self.seen_txs.add(seen_key)
                                import json

                                txs_to_broadcast.append(json.loads(row[2]))
                logger.debug("Mempool sync loop iteration. txs_to_broadcast: %s", len(txs_to_broadcast))
                for tx in txs_to_broadcast:
                    msg = {"type": "new_transaction", "tx": tx}
                    writers = list(self.active_connections.values())
                    for writer in writers:
                        await self._send_message(writer, msg)
            except Exception as e:
                logger.error("Error in mempool sync loop: %s", e)
            await asyncio.sleep(1)

    async def _dial_peers_loop(self) -> None:
        """Background loop to continually try connecting to disconnected initial peers"""
        while not self._stop_event.is_set():
            for host, port in self.initial_peers:
                endpoint = (host, port)
                if endpoint in self.connected_endpoints:
                    continue
                already_connected_ip = False
                logger.debug("Checking if already connected to %s, active connections: %s", host, len(self.active_connections))
                for node_id, writer in self.active_connections.items():
                    peer_ip = writer.get_extra_info("peername")[0]
                    logger.debug("Checking peer %s with IP %s against host %s", node_id, peer_ip, host)
                    if peer_ip == host:
                        already_connected_ip = True
                        logger.debug("Match: peer_ip == host (%s == %s)", peer_ip, host)
                        break
                    try:
                        import socket

                        host_ip = socket.gethostbyname(host)
                        if peer_ip == host_ip:
                            already_connected_ip = True
                            logger.debug("Match: resolved %s to %s, matches peer_ip %s", host, host_ip, peer_ip)
                            break
                    except socket.gaierror:
                        logger.debug("Could not resolve hostname %s, skipping IP comparison", host)
                        pass
                if already_connected_ip:
                    self.connected_endpoints.add(endpoint)
                    continue
                asyncio.create_task(self._dial_peer(host, port))
            await asyncio.sleep(10)

    async def _dial_peer(self, host: str, port: int) -> None:
        """Attempt to establish an outbound TCP connection to a peer"""
        endpoint = (host, port)
        try:
            reader, writer = await asyncio.open_connection(host, port)
            logger.info("Successfully dialed outbound peer at %s:%s", host, port)
            self.connected_endpoints.add(endpoint)
            handshake = {
                "type": "handshake",
                "node_id": self.node_id,
                "listen_port": self.port,
                "chain_id": self.chain_id,
                "island_id": self.island_id,
                "island_name": self.island_name,
                "is_hub": self.is_hub,
                "island_chain_id": self.island_chain_id,
                "public_address": self.public_endpoint[0] if self.public_endpoint else None,
                "public_port": self.public_endpoint[1] if self.public_endpoint else None,
                "protocol_version": self._protocol_version,
                "block_height": self._get_block_height(),
            }
            await self._send_message(writer, handshake)
            await self._listen_to_stream(reader, writer, endpoint, outbound=True)
        except ConnectionRefusedError:
            logger.debug("Peer %s:%s refused connection (offline?)", host, port)
        except Exception as e:
            logger.debug("Failed to dial peer %s:%s: %s", host, port, e)

    async def _handle_inbound_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle incoming P2P TCP connections from other nodes"""
        addr = writer.get_extra_info("peername")
        logger.info("Incoming P2P connection from %s", addr)
        try:
            data = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not data:
                writer.close()
                return
            raw_data = data.decode()
            if not raw_data.strip():
                logger.warning("Received empty data from %s. Closing connection.", addr)
                writer.close()
                return
            try:
                from .network.compression import decode_payload

                message = decode_payload(raw_data)
            except json.JSONDecodeError as e:
                logger.warning("Received invalid JSON from %s: %s. Error: %s", addr, repr(raw_data[:100]), e)
                writer.close()
                return
            if message.get("type") != "handshake":
                logger.warning("Peer %s did not handshake first. Dropping.", addr)
                writer.close()
                return
            peer_node_id = message.get("node_id")
            peer_listen_port = message.get("listen_port", 7070)
            peer_island_id = message.get("island_id", "")
            message.get("island_name", "")
            peer_is_hub = message.get("is_hub", False)
            message.get("island_chain_id", "")
            peer_chain_id = message.get("chain_id", "")
            peer_public_address = message.get("public_address")
            peer_public_port = message.get("public_port")
            peer_protocol_version = message.get("protocol_version", 1)  # default to v1 (legacy)
            peer_block_height = message.get("block_height", 0)
            if not peer_node_id or peer_node_id == self.node_id:
                logger.warning("Peer %s provided invalid or self node_id: %s", addr, peer_node_id)
                writer.close()
                return
            if peer_chain_id and self.chain_id and (peer_chain_id != self.chain_id):
                logger.warning(
                    "Peer %s chain_id mismatch: %s != %s. Rejecting connection.", addr, peer_chain_id, self.chain_id
                )
                writer.close()
                return
            if (
                peer_island_id
                and self.island_id
                and (peer_island_id != self.island_id)
                and (not peer_is_hub)
                and (not self.is_hub)
            ):
                logger.warning(
                    "Peer %s island_id mismatch: %s != %s. Rejecting connection (neither is hub).",
                    addr,
                    peer_island_id,
                    self.island_id,
                )
                writer.close()
                return
            logger.info("Peer %s from island %s (hub: %s)", peer_node_id, peer_island_id, peer_is_hub)
            if peer_public_address and peer_public_port:
                logger.info("Peer %s public endpoint: %s:%s", peer_node_id, peer_public_address, peer_public_port)
            logger.info("Handshake accepted from node %s at %s", peer_node_id, addr)
            # v0.6.2: Track legacy peers (protocol_version < 2)
            if peer_protocol_version < self._protocol_version:
                self._legacy_peers.add(peer_node_id)
                logger.info(
                    "Peer %s using legacy protocol v%s (local v%s) — batching/prioritization disabled",
                    peer_node_id,
                    peer_protocol_version,
                    self._protocol_version,
                )
            if peer_block_height > 0:
                logger.debug("Peer %s block_height=%s", peer_node_id, peer_block_height)
            if peer_node_id in self.active_connections:
                logger.info("Already connected to node %s. Dropping duplicate inbound.", peer_node_id)
                writer.close()
                return
            self.active_connections[peer_node_id] = writer
            remote_ip = addr[0]
            self.connected_endpoints.add((remote_ip, peer_listen_port))
            if self.island_manager and peer_island_id:
                self.island_manager.add_island_peer(peer_island_id, peer_node_id)
            if self.hub_manager:
                from .network.hub_manager import PeerInfo

                self.hub_manager.register_peer(
                    PeerInfo(
                        node_id=peer_node_id,
                        address=remote_ip,
                        port=peer_listen_port,
                        island_id=peer_island_id,
                        is_hub=peer_is_hub,
                        public_address=peer_public_address,
                        public_port=peer_public_port,
                        last_seen=asyncio.get_event_loop().time(),
                    )
                )
            reply_handshake = {
                "type": "handshake",
                "node_id": self.node_id,
                "listen_port": self.port,
                "chain_id": self.chain_id,
                "island_id": self.island_id,
                "island_name": self.island_name,
                "is_hub": self.is_hub,
                "island_chain_id": self.island_chain_id,
                "public_address": self.public_endpoint[0] if self.public_endpoint else None,
                "public_port": self.public_endpoint[1] if self.public_endpoint else None,
                "protocol_version": self._protocol_version,
                "block_height": self._get_block_height(),
            }
            await self._send_message(writer, reply_handshake)
            await self._listen_to_stream(reader, writer, (remote_ip, peer_listen_port), outbound=False, peer_id=peer_node_id)
        except TimeoutError:
            logger.warning("Timeout waiting for handshake from %s", addr)
            writer.close()
        except Exception as e:
            logger.error("Error handling inbound connection from %s: %s", addr, e)
            writer.close()

    async def _listen_to_stream(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        endpoint: tuple[str, int],
        outbound: bool,
        peer_id: str | None = None,
    ) -> None:
        """Read loop for an established TCP stream (both inbound and outbound)"""
        addr = endpoint
        try:
            while not self._stop_event.is_set():
                data = await reader.readline()
                if not data:
                    break
                try:
                    from .network.compression import decode_payload

                    message = decode_payload(data.decode().strip())
                    msg_type = message.get("type")
                    if outbound and peer_id is None:
                        if msg_type == "handshake":
                            peer_id = message.get("node_id")
                            peer_island_id = message.get("island_id", "")
                            peer_is_hub = message.get("is_hub", False)
                            peer_chain_id = message.get("chain_id", "")
                            peer_protocol_version = message.get("protocol_version", 1)
                            if not peer_id or peer_id == self.node_id:
                                logger.warning("Invalid handshake reply from %s. Closing.", addr)
                                break
                            # v0.6.2: Track legacy peers
                            if peer_protocol_version < self._protocol_version:
                                self._legacy_peers.add(peer_id)
                                logger.info(
                                    "Peer %s using legacy protocol v%s — batching/prioritization disabled",
                                    peer_id,
                                    peer_protocol_version,
                                )
                            if peer_chain_id and self.chain_id and (peer_chain_id != self.chain_id):
                                logger.warning(
                                    "Peer %s chain_id mismatch: %s != %s. Closing connection.",
                                    addr,
                                    peer_chain_id,
                                    self.chain_id,
                                )
                                break
                            if peer_id in self.active_connections:
                                logger.info("Already connected to node %s. Closing duplicate outbound.", peer_id)
                                break
                            self.active_connections[peer_id] = writer
                            if self.island_manager and peer_island_id:
                                self.island_manager.add_island_peer(peer_island_id, peer_id)
                            if self.hub_manager:
                                from .network.hub_manager import PeerInfo

                                self.hub_manager.register_peer(
                                    PeerInfo(
                                        node_id=peer_id,
                                        address=addr[0],
                                        port=addr[1],
                                        island_id=peer_island_id,
                                        is_hub=peer_is_hub,
                                        public_address=message.get("public_address"),
                                        public_port=message.get("public_port"),
                                        last_seen=asyncio.get_event_loop().time(),
                                    )
                                )
                            logger.info(
                                "Outbound handshake complete. Connected to node %s (island: %s)", peer_id, peer_island_id
                            )
                            continue
                        else:
                            logger.warning("Expected handshake reply from %s, got %s", addr, msg_type)
                            break
                    if msg_type == "ping":
                        logger.debug("Received ping from %s", peer_id)
                        await self._send_message(writer, {"type": "pong", "node_id": self.node_id})
                    elif msg_type == "pong":
                        logger.debug("Received pong from %s", peer_id)
                    elif msg_type == "handshake":
                        pass
                    elif msg_type == "join_request":
                        if self.hub_manager:
                            logger.info("Received join_request from %s", peer_id)
                            response = await self.hub_manager.handle_join_request(message)
                            if response:
                                await self._send_message(writer, response)
                        else:
                            logger.warning("Received join_request but not a hub, ignoring")
                    elif msg_type == "join_response":
                        logger.info("Received join_response from %s", peer_id)
                        if not hasattr(self, "_join_response"):
                            self._join_response = {}
                        self._join_response[peer_id] = message
                    elif msg_type == "gpu_provider_query":
                        logger.info("Received gpu_provider_query from %s", peer_id)
                        gpu_response = {
                            "type": "gpu_provider_response",
                            "node_id": self.node_id,
                            "gpu_available": self._get_gpu_count(),
                            "gpu_specs": self._get_gpu_specs(),
                        }
                        await self._send_message(writer, gpu_response)
                    elif msg_type == "gpu_provider_response":
                        logger.info("Received gpu_provider_response from %s", peer_id)
                        if not hasattr(self, "_gpu_provider_responses"):
                            self._gpu_provider_responses = {}
                        self._gpu_provider_responses[peer_id] = message
                    elif msg_type == "new_transaction":
                        tx_data = message.get("tx")
                        if tx_data:
                            try:
                                tx_hash = compute_tx_hash(tx_data)
                                chain_id = tx_data.get("chain_id", settings.chain_id)
                                if not hasattr(self, "seen_txs"):
                                    self.seen_txs = set()
                                seen_key = (chain_id, tx_hash)
                                if seen_key not in self.seen_txs:
                                    logger.info("Received new P2P transaction: %s", tx_hash)
                                    self.seen_txs.add(seen_key)
                                    from .mempool import get_mempool as get_mempool_instance

                                    mempool = get_mempool_instance()
                                    mempool.add(tx_data, chain_id=chain_id)
                                    forward_msg = {"type": "new_transaction", "tx": tx_data}
                                    writers = list(self.active_connections.values())
                                    for w in writers:
                                        if w != writer:
                                            await self._send_message(w, forward_msg)
                            except ValueError as e:
                                logger.debug("P2P tx rejected by mempool: %s", e)
                            except Exception as e:
                                logger.error("P2P tx handling error: %s", e)
                    else:
                        logger.info("Received %s from %s: %s", msg_type, peer_id, message)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received from %s", addr)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Stream error with %s: %s", addr, e)
        finally:
            logger.info("Connection closed to %s", peer_id or addr)
            if peer_id and peer_id in self.active_connections:
                del self.active_connections[peer_id]
            # v0.6.2: Clean up legacy peer tracking on disconnect
            self._legacy_peers.discard(peer_id)
            if endpoint in self.connected_endpoints:
                self.connected_endpoints.remove(endpoint)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # nosec B110 - intentional silent cleanup
                pass

    def _get_gpu_count(self) -> int:
        """Get the number of available GPUs on this node"""
        try:
            import os

            gpu_config_path = "/var/lib/aitbc/gpu_config.json"
            if os.path.exists(gpu_config_path):
                with open(gpu_config_path) as f:
                    config = json.load(f)
                    return config.get("gpu_count", 0)  # type: ignore[no-any-return]
            return 0
        except Exception as e:
            logger.error("Error getting GPU count: %s", e)
            return 0

    def _get_gpu_specs(self) -> dict[str, Any]:
        """Get GPU specifications for this node"""
        try:
            import os

            gpu_config_path = "/var/lib/aitbc/gpu_config.json"
            if os.path.exists(gpu_config_path):
                with open(gpu_config_path) as f:
                    config = json.load(f)
                    return config.get("specs", {})  # type: ignore[no-any-return]
            return {}
        except Exception as e:
            logger.error("Error getting GPU specs: %s", e)
            return {}

    async def send_join_request(
        self, hub_address: str, hub_port: int, island_id: str, island_name: str, node_id: str, public_key_pem: str
    ) -> dict[str, Any] | None:
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
            reader, writer = await asyncio.open_connection(hub_address, hub_port)
            logger.info("Connected to hub %s:%s", hub_address, hub_port)
            handshake = {
                "type": "handshake",
                "node_id": node_id,
                "listen_port": self.port,
                "chain_id": self.chain_id,
                "island_id": island_id,
                "island_name": island_name,
                "is_hub": self.is_hub,
                "island_chain_id": self.island_chain_id,
                "public_address": self.public_endpoint[0] if self.public_endpoint else None,
                "public_port": self.public_endpoint[1] if self.public_endpoint else None,
            }
            await self._send_message(writer, handshake)
            logger.info("Sent handshake to hub")
            data = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not data:
                logger.warning("No handshake response from hub")
                writer.close()
                await writer.wait_closed()
                return None
            from .network.compression import decode_payload

            response = decode_payload(data.decode().strip())
            if response.get("type") != "handshake":
                logger.warning("Unexpected handshake response type: %s", response.get("type"))
                writer.close()
                await writer.wait_closed()
                return None
            join_request = {
                "type": "join_request",
                "node_id": node_id,
                "island_id": island_id,
                "island_name": island_name,
                "public_key_pem": public_key_pem,
            }
            await self._send_message(writer, join_request)
            logger.info("Sent join_request to hub")
            try:
                data = await asyncio.wait_for(reader.readline(), timeout=30.0)
                if data:
                    from .network.compression import decode_payload

                    response = decode_payload(data.decode().strip())
                    if response.get("type") == "join_response":
                        logger.info("Received join_response from hub")
                        writer.close()
                        await writer.wait_closed()
                        return response  # type: ignore[no-any-return]
                    else:
                        logger.warning("Unexpected response type: %s", response.get("type"))
                else:
                    logger.warning("No response from hub")
            except TimeoutError:
                logger.warning("Timeout waiting for join response")
            writer.close()
            await writer.wait_closed()
            return None
        except ConnectionRefusedError:
            logger.error("Hub %s:%s refused connection", hub_address, hub_port)
            return None
        except Exception as e:
            logger.error("Failed to send join request: %s", e)
            return None

    def _get_block_height(self) -> int:
        """Get the current block height for handshake capability exchange.

        Returns 0 if the chain is not yet initialized or an error occurs.
        """
        try:
            from .database import session_scope

            with session_scope(self.chain_id) as session:
                from .models import BlockHeader

                from sqlalchemy import select

                stmt = select(BlockHeader).order_by(BlockHeader.height.desc()).limit(1)
                block = session.exec(stmt).first()
                return block.height if block else 0
        except Exception:
            return 0

    def is_legacy_peer(self, peer_id: str) -> bool:
        """Check if a peer is operating in legacy mode (protocol version < 2)."""
        return peer_id in self._legacy_peers

    def get_legacy_peers(self) -> set[str]:
        """Return the set of peer IDs operating in legacy mode."""
        return set(self._legacy_peers)

    def get_protocol_version(self) -> int:
        """Return the local protocol version."""
        return self._protocol_version


async def run_p2p_service(host: str, port: int, node_id: str, peers: str) -> None:
    """Run P2P service"""
    stun_servers = [server.strip() for server in settings.stun_servers.split(",") if server.strip()]
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
    set_p2p_network(service)
    await service.start()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="AITBC Direct TCP P2P Mesh Network")
    parser.add_argument("--host", default=settings.p2p_bind_host, help="Bind host")
    parser.add_argument("--port", type=int, default=7070, help="Bind port")
    parser.add_argument("--node-id", default="", help="Node identifier (defaults to settings.p2p_node_id)")
    parser.add_argument("--peers", default="", help="Comma separated list of initial peers to dial (ip:port)")
    args = parser.parse_args()
    try:
        from .mempool import init_mempool

        db_url = ""
        if settings.mempool_backend == "database":
            db_url = settings.mempool_db_url
        init_mempool(
            backend=settings.mempool_backend, db_url=db_url, max_size=settings.mempool_max_size, min_fee=settings.min_fee
        )
        node_id = args.node_id or settings.p2p_node_id or settings.proposer_id
        if not node_id:
            raise ValueError("p2p node_id is required")
        asyncio.run(run_p2p_service(args.host, args.port, node_id, args.peers))
    except KeyboardInterrupt:
        logger.info("P2P service stopped by user")


if __name__ == "__main__":
    main()
