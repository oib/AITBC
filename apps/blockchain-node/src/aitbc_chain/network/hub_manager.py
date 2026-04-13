"""
Hub Manager
Manages hub operations, peer list sharing, and hub registration for federated mesh
"""

import asyncio
import logging
import time
import json
import os
import socket
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from ..config import settings

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

    def __init__(self, local_node_id: str, local_address: str, local_port: int, island_id: str, island_name: str, redis_url: Optional[str] = None):
        self.local_node_id = local_node_id
        self.local_address = local_address
        self.local_port = local_port
        self.island_id = island_id
        self.island_name = island_name
        self.island_chain_id = settings.island_chain_id or settings.chain_id or f"ait-{island_id[:8]}"
        self.redis_url = redis_url or "redis://localhost:6379"

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
        self._redis = None

        # Initialize island peers for our island
        self.island_peers[self.island_id] = set()
    
    async def _connect_redis(self):
        """Connect to Redis"""
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url)
            await self._redis.ping()
            logger.info(f"Connected to Redis for hub persistence: {self.redis_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False

    async def _persist_hub_registration(self, hub_info: HubInfo) -> bool:
        """Persist hub registration to Redis"""
        try:
            if not self._redis:
                await self._connect_redis()

            if not self._redis:
                logger.warning("Redis not available, skipping persistence")
                return False

            key = f"hub:{hub_info.node_id}"
            value = json.dumps(asdict(hub_info), default=str)
            await self._redis.setex(key, 3600, value)  # TTL: 1 hour
            logger.info(f"Persisted hub registration to Redis: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to persist hub registration: {e}")
            return False

    async def _remove_hub_registration(self, node_id: str) -> bool:
        """Remove hub registration from Redis"""
        try:
            if not self._redis:
                await self._connect_redis()

            if not self._redis:
                logger.warning("Redis not available, skipping removal")
                return False

            key = f"hub:{node_id}"
            await self._redis.delete(key)
            logger.info(f"Removed hub registration from Redis: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove hub registration: {e}")
            return False

    async def _load_hub_registration(self) -> Optional[HubInfo]:
        """Load hub registration from Redis"""
        try:
            if not self._redis:
                await self._connect_redis()

            if not self._redis:
                return None

            key = f"hub:{self.local_node_id}"
            value = await self._redis.get(key)
            if value:
                data = json.loads(value)
                return HubInfo(**data)
            return None
        except Exception as e:
            logger.error(f"Failed to load hub registration: {e}")
            return None

    def _get_blockchain_credentials(self) -> dict:
        """Get blockchain credentials from keystore"""
        try:
            credentials = {}

            # Get genesis block hash from genesis.json
            genesis_candidates = [
                str(settings.db_path.parent / 'genesis.json'),
                f"/var/lib/aitbc/data/{settings.chain_id}/genesis.json",
                '/var/lib/aitbc/data/ait-mainnet/genesis.json',
            ]
            for genesis_path in genesis_candidates:
                if os.path.exists(genesis_path):
                    with open(genesis_path, 'r') as f:
                        genesis_data = json.load(f)
                        if 'blocks' in genesis_data and len(genesis_data['blocks']) > 0:
                            genesis_block = genesis_data['blocks'][0]
                            credentials['genesis_block_hash'] = genesis_block.get('hash', '')
                        credentials['genesis_block'] = genesis_data
                    break

            # Get genesis address from keystore
            keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
            if os.path.exists(keystore_path):
                with open(keystore_path, 'r') as f:
                    keys = json.load(f)
                    # Get first key's address
                    for key_id, key_data in keys.items():
                        # Extract address from public key or use key_id
                        credentials['genesis_address'] = key_id
                        break

            # Add chain info
            credentials['chain_id'] = self.island_chain_id
            credentials['island_id'] = self.island_id
            credentials['island_name'] = self.island_name

            # Add RPC endpoint (local)
            rpc_host = self.local_address
            if rpc_host in {"0.0.0.0", "127.0.0.1", "localhost", ""}:
                rpc_host = settings.hub_discovery_url or socket.gethostname()
            credentials['rpc_endpoint'] = f"http://{rpc_host}:8006"
            credentials['p2p_port'] = self.local_port

            return credentials
        except Exception as e:
            logger.error(f"Failed to get blockchain credentials: {e}")
            return {}

    async def handle_join_request(self, join_request: dict) -> Optional[dict]:
        """
        Handle island join request from a new node

        Args:
            join_request: Dictionary containing join request data

        Returns:
            dict: Join response with member list and credentials, or None if failed
        """
        try:
            requested_island_id = join_request.get('island_id')

            # Validate island ID
            if requested_island_id != self.island_id:
                logger.warning(f"Join request for island {requested_island_id} does not match our island {self.island_id}")
                return None

            # Get all island members
            members = []
            for node_id, peer_info in self.peer_registry.items():
                if peer_info.island_id == self.island_id:
                    members.append({
                        'node_id': peer_info.node_id,
                        'address': peer_info.address,
                        'port': peer_info.port,
                        'is_hub': peer_info.is_hub,
                        'public_address': peer_info.public_address,
                        'public_port': peer_info.public_port
                    })

            # Include self in member list
            members.append({
                'node_id': self.local_node_id,
                'address': self.local_address,
                'port': self.local_port,
                'is_hub': True,
                'public_address': self.known_hubs.get(self.local_node_id, {}).public_address if self.local_node_id in self.known_hubs else None,
                'public_port': self.known_hubs.get(self.local_node_id, {}).public_port if self.local_node_id in self.known_hubs else None
            })

            # Get blockchain credentials
            credentials = self._get_blockchain_credentials()

            # Build response
            response = {
                'type': 'join_response',
                'island_id': self.island_id,
                'island_name': self.island_name,
                'island_chain_id': self.island_chain_id or f"ait-{self.island_id[:8]}",
                'members': members,
                'credentials': credentials
            }

            logger.info(f"Sent join_response to node {join_request.get('node_id')} with {len(members)} members")
            return response

        except Exception as e:
            logger.error(f"Error handling join request: {e}")
            return None

    def register_gpu_offer(self, offer_data: dict) -> bool:
        """Register a GPU marketplace offer in the hub"""
        try:
            offer_id = offer_data.get('offer_id')
            if offer_id:
                self.gpu_offers[offer_id] = offer_data
                logger.info(f"Registered GPU offer: {offer_id}")
                return True
        except Exception as e:
            logger.error(f"Error registering GPU offer: {e}")
        return False

    def register_gpu_bid(self, bid_data: dict) -> bool:
        """Register a GPU marketplace bid in the hub"""
        try:
            bid_id = bid_data.get('bid_id')
            if bid_id:
                self.gpu_bids[bid_id] = bid_data
                logger.info(f"Registered GPU bid: {bid_id}")
                return True
        except Exception as e:
            logger.error(f"Error registering GPU bid: {e}")
        return False

    def register_gpu_provider(self, node_id: str, gpu_info: dict) -> bool:
        """Register a GPU provider in the hub"""
        try:
            self.gpu_providers[node_id] = gpu_info
            logger.info(f"Registered GPU provider: {node_id}")
            return True
        except Exception as e:
            logger.error(f"Error registering GPU provider: {e}")
        return False

    def register_exchange_order(self, order_data: dict) -> bool:
        """Register an exchange order in the hub"""
        try:
            order_id = order_data.get('order_id')
            if order_id:
                self.exchange_orders[order_id] = order_data
                
                # Update order book
                pair = order_data.get('pair')
                side = order_data.get('side')
                if pair and side:
                    if pair not in self.exchange_order_books:
                        self.exchange_order_books[pair] = {'bids': [], 'asks': []}
                    
                    if side == 'buy':
                        self.exchange_order_books[pair]['bids'].append(order_data)
                    elif side == 'sell':
                        self.exchange_order_books[pair]['asks'].append(order_data)
                
                logger.info(f"Registered exchange order: {order_id}")
                return True
        except Exception as e:
            logger.error(f"Error registering exchange order: {e}")
        return False

    def get_gpu_offers(self) -> list:
        """Get all GPU offers"""
        return list(self.gpu_offers.values())

    def get_gpu_bids(self) -> list:
        """Get all GPU bids"""
        return list(self.gpu_bids.values())

    def get_gpu_providers(self) -> list:
        """Get all GPU providers"""
        return list(self.gpu_providers.values())

    def get_exchange_order_book(self, pair: str) -> dict:
        """Get order book for a specific trading pair"""
        return self.exchange_order_books.get(pair, {'bids': [], 'asks': []})

    async def register_as_hub(self, public_address: Optional[str] = None, public_port: Optional[int] = None) -> bool:
        """Register this node as a hub"""
        if self.is_hub:
            logger.warning("Already registered as hub")
            return False

        self.is_hub = True
        self.hub_status = HubStatus.REGISTERED
        self.registered_at = time.time()

        # Add self to known hubs
        hub_info = HubInfo(
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
        self.known_hubs[self.local_node_id] = hub_info

        # Persist to Redis
        await self._persist_hub_registration(hub_info)

        logger.info(f"Registered as hub for island {self.island_id}")
        return True
    
    async def unregister_as_hub(self) -> bool:
        """Unregister this node as a hub"""
        if not self.is_hub:
            logger.warning("Not registered as hub")
            return False

        self.is_hub = False
        self.hub_status = HubStatus.UNREGISTERED
        self.registered_at = None

        # Remove from Redis
        await self._remove_hub_registration(self.local_node_id)

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
