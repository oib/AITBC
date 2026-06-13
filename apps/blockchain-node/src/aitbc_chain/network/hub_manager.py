# mypy: ignore-errors
"""
Hub Manager
Manages hub operations, peer list sharing, and hub registration for federated mesh
"""
import asyncio
import json
import os
import socket
import time
from dataclasses import asdict, dataclass
from enum import Enum
from aitbc import DATA_DIR, KEYSTORE_DIR, get_logger
from ..config import settings
logger = get_logger(__name__)

class HubStatus(Enum):
    """Hub registration status"""
    REGISTERED = 'registered'
    UNREGISTERED = 'unregistered'
    PENDING = 'pending'

@dataclass
class HubInfo:
    """Information about a hub node"""
    node_id: str
    address: str
    port: int
    island_id: str
    island_name: str
    public_address: str | None = None
    public_port: int | None = None
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
    public_address: str | None = None
    public_port: int | None = None
    last_seen: float = 0

class HubManager:
    """Manages hub operations for federated mesh"""

    def __init__(self, local_node_id: str, local_address: str, local_port: int, island_id: str, island_name: str, redis_url: str | None=None):
        self.local_node_id = local_node_id
        self.local_address = local_address
        self.local_port = local_port
        self.island_id = island_id
        self.island_name = island_name
        self.island_chain_id = settings.island_chain_id or settings.chain_id or f'ait-{island_id[:8]}'
        self.redis_url = redis_url or 'redis://localhost:6379'
        self.is_hub = False
        self.hub_status = HubStatus.UNREGISTERED
        self.registered_at: float | None = None
        self.known_hubs: dict[str, HubInfo] = {}
        self.peer_registry: dict[str, PeerInfo] = {}
        self.island_peers: dict[str, set[str]] = {}
        self.running = False
        self._redis = None
        self.island_peers[self.island_id] = set()

    async def _connect_redis(self):
        """Connect to Redis"""
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url)
            await self._redis.ping()
            logger.info('Connected to Redis for hub persistence: %s', self.redis_url)
            return True
        except Exception as e:
            logger.error('Failed to connect to Redis: %s', e)
            return False

    async def _persist_hub_registration(self, hub_info: HubInfo) -> bool:
        """Persist hub registration to Redis"""
        try:
            if not self._redis:
                await self._connect_redis()
            if not self._redis:
                logger.warning('Redis not available, skipping persistence')
                return False
            key = f'hub:{hub_info.node_id}'
            value = json.dumps(asdict(hub_info), default=str)
            await self._redis.setex(key, 3600, value)
            logger.info('Persisted hub registration to Redis: %s', key)
            return True
        except Exception as e:
            logger.error('Failed to persist hub registration: %s', e)
            return False

    async def _remove_hub_registration(self, node_id: str) -> bool:
        """Remove hub registration from Redis"""
        try:
            if not self._redis:
                await self._connect_redis()
            if not self._redis:
                logger.warning('Redis not available, skipping removal')
                return False
            key = f'hub:{node_id}'
            await self._redis.delete(key)
            logger.info('Removed hub registration from Redis: %s', key)
            return True
        except Exception as e:
            logger.error('Failed to remove hub registration: %s', e)
            return False

    async def _load_hub_registration(self) -> HubInfo | None:
        """Load hub registration from Redis"""
        try:
            if not self._redis:
                await self._connect_redis()
            if not self._redis:
                return None
            key = f'hub:{self.local_node_id}'
            value = await self._redis.get(key)
            if value:
                data = json.loads(value)
                return HubInfo(**data)
            return None
        except Exception as e:
            logger.error('Failed to load hub registration: %s', e)
            return None

    def _get_blockchain_credentials(self) -> dict:
        """Get blockchain credentials from keystore"""
        try:
            credentials = {}
            genesis_candidates = [str(settings.db_path.parent / 'genesis.json'), f'{DATA_DIR}/data/{settings.chain_id}/genesis.json', f'{DATA_DIR}/data/ait-mainnet/genesis.json']
            for genesis_path in genesis_candidates:
                if os.path.exists(genesis_path):
                    with open(genesis_path) as f:
                        genesis_data = json.load(f)
                        if 'blocks' in genesis_data and len(genesis_data['blocks']) > 0:
                            genesis_block = genesis_data['blocks'][0]
                            credentials['genesis_block_hash'] = genesis_block.get('hash', '')
                        credentials['genesis_block'] = genesis_data
                    break
            keystore_path = str(KEYSTORE_DIR / 'validator_keys.json')
            if os.path.exists(keystore_path):
                with open(keystore_path) as f:
                    keys = json.load(f)
                    for key_id, key_data in keys.items():
                        credentials['genesis_address'] = key_id
                        break
            credentials['chain_id'] = self.island_chain_id
            credentials['island_id'] = self.island_id
            credentials['island_name'] = self.island_name
            rpc_host = self.local_address
            if rpc_host in {'0.0.0.0', '127.0.0.1', 'localhost', ''}:
                rpc_host = settings.hub_discovery_url or socket.gethostname()
            credentials['rpc_endpoint'] = f'http://{rpc_host}:8006'
            credentials['p2p_port'] = self.local_port
            return credentials
        except Exception as e:
            logger.error('Failed to get blockchain credentials: %s', e)
            return {}

    async def handle_join_request(self, join_request: dict) -> dict | None:
        """
        Handle island join request from a new node

        Args:
            join_request: Dictionary containing join request data

        Returns:
            dict: Join response with member list and credentials, or None if failed
        """
        try:
            requested_island_id = join_request.get('island_id')
            if requested_island_id != self.island_id:
                logger.warning('Join request for island %s does not match our island %s', requested_island_id, self.island_id)
                return None
            members = []
            for node_id, peer_info in self.peer_registry.items():
                if peer_info.island_id == self.island_id:
                    members.append({'node_id': peer_info.node_id, 'address': peer_info.address, 'port': peer_info.port, 'is_hub': peer_info.is_hub, 'public_address': peer_info.public_address, 'public_port': peer_info.public_port})
            members.append({'node_id': self.local_node_id, 'address': self.local_address, 'port': self.local_port, 'is_hub': True, 'public_address': self.known_hubs.get(self.local_node_id, {}).public_address if self.local_node_id in self.known_hubs else None, 'public_port': self.known_hubs.get(self.local_node_id, {}).public_port if self.local_node_id in self.known_hubs else None})
            credentials = self._get_blockchain_credentials()
            response = {'type': 'join_response', 'island_id': self.island_id, 'island_name': self.island_name, 'island_chain_id': self.island_chain_id or f'ait-{self.island_id[:8]}', 'members': members, 'credentials': credentials}
            logger.info('Sent join_response to node %s with %s members', join_request.get('node_id'), len(members))
            return response
        except Exception as e:
            logger.error('Error handling join request: %s', e)
            return None

    def register_gpu_offer(self, offer_data: dict) -> bool:
        """Register a GPU marketplace offer in the hub"""
        try:
            offer_id = offer_data.get('offer_id')
            if offer_id:
                self.gpu_offers[offer_id] = offer_data
                logger.info('Registered GPU offer: %s', offer_id)
                return True
        except Exception as e:
            logger.error('Error registering GPU offer: %s', e)
        return False

    def register_gpu_bid(self, bid_data: dict) -> bool:
        """Register a GPU marketplace bid in the hub"""
        try:
            bid_id = bid_data.get('bid_id')
            if bid_id:
                self.gpu_bids[bid_id] = bid_data
                logger.info('Registered GPU bid: %s', bid_id)
                return True
        except Exception as e:
            logger.error('Error registering GPU bid: %s', e)
        return False

    def register_gpu_provider(self, node_id: str, gpu_info: dict) -> bool:
        """Register a GPU provider in the hub"""
        try:
            self.gpu_providers[node_id] = gpu_info
            logger.info('Registered GPU provider: %s', node_id)
            return True
        except Exception as e:
            logger.error('Error registering GPU provider: %s', e)
        return False

    def register_exchange_order(self, order_data: dict) -> bool:
        """Register an exchange order in the hub"""
        try:
            order_id = order_data.get('order_id')
            if order_id:
                self.exchange_orders[order_id] = order_data
                pair = order_data.get('pair')
                side = order_data.get('side')
                if pair and side:
                    if pair not in self.exchange_order_books:
                        self.exchange_order_books[pair] = {'bids': [], 'asks': []}
                    if side == 'buy':
                        self.exchange_order_books[pair]['bids'].append(order_data)
                    elif side == 'sell':
                        self.exchange_order_books[pair]['asks'].append(order_data)
                logger.info('Registered exchange order: %s', order_id)
                return True
        except Exception as e:
            logger.error('Error registering exchange order: %s', e)
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

    async def register_as_hub(self, public_address: str | None=None, public_port: int | None=None) -> bool:
        """Register this node as a hub"""
        if self.is_hub:
            logger.warning('Already registered as hub')
            return False
        self.is_hub = True
        self.hub_status = HubStatus.REGISTERED
        self.registered_at = time.time()
        hub_info = HubInfo(node_id=self.local_node_id, address=self.local_address, port=self.local_port, island_id=self.island_id, island_name=self.island_name, public_address=public_address, public_port=public_port, registered_at=time.time(), last_seen=time.time())
        self.known_hubs[self.local_node_id] = hub_info
        await self._persist_hub_registration(hub_info)
        logger.info('Registered as hub for island %s', self.island_id)
        return True

    async def unregister_as_hub(self) -> bool:
        """Unregister this node as a hub"""
        if not self.is_hub:
            logger.warning('Not registered as hub')
            return False
        self.is_hub = False
        self.hub_status = HubStatus.UNREGISTERED
        self.registered_at = None
        await self._remove_hub_registration(self.local_node_id)
        if self.local_node_id in self.known_hubs:
            del self.known_hubs[self.local_node_id]
        logger.info('Unregistered as hub for island %s', self.island_id)
        return True

    def register_peer(self, peer_info: PeerInfo) -> bool:
        """Register a peer in the registry"""
        self.peer_registry[peer_info.node_id] = peer_info
        if peer_info.island_id not in self.island_peers:
            self.island_peers[peer_info.island_id] = set()
        self.island_peers[peer_info.island_id].add(peer_info.node_id)
        if peer_info.is_hub and peer_info.node_id in self.known_hubs:
            self.known_hubs[peer_info.node_id].peer_count = len(self.island_peers.get(peer_info.island_id, set()))
        logger.debug('Registered peer %s in island %s', peer_info.node_id, peer_info.island_id)
        return True

    def unregister_peer(self, node_id: str) -> bool:
        """Unregister a peer from the registry"""
        if node_id not in self.peer_registry:
            return False
        peer_info = self.peer_registry[node_id]
        if peer_info.island_id in self.island_peers:
            self.island_peers[peer_info.island_id].discard(node_id)
        del self.peer_registry[node_id]
        if node_id in self.known_hubs:
            self.known_hubs[node_id].peer_count = len(self.island_peers.get(self.known_hubs[node_id].island_id, set()))
        logger.debug('Unregistered peer %s', node_id)
        return True

    def add_known_hub(self, hub_info: HubInfo):
        """Add a known hub to the registry"""
        self.known_hubs[hub_info.node_id] = hub_info
        logger.info('Added known hub %s for island %s', hub_info.node_id, hub_info.island_id)

    def remove_known_hub(self, node_id: str) -> bool:
        """Remove a known hub from the registry"""
        if node_id not in self.known_hubs:
            return False
        del self.known_hubs[node_id]
        logger.info('Removed known hub %s', node_id)
        return True

    def get_peer_list(self, island_id: str) -> list[PeerInfo]:
        """Get peer list for a specific island"""
        peers = []
        for node_id, peer_info in self.peer_registry.items():
            if peer_info.island_id == island_id:
                peers.append(peer_info)
        return peers

    def get_hub_list(self, island_id: str | None=None) -> list[HubInfo]:
        """Get list of known hubs, optionally filtered by island"""
        hubs = []
        for hub_info in self.known_hubs.values():
            if island_id is None or hub_info.island_id == island_id:
                hubs.append(hub_info)
        return hubs

    def get_island_peers(self, island_id: str) -> set[str]:
        """Get set of peer node IDs in an island"""
        return self.island_peers.get(island_id, set()).copy()

    def get_peer_count(self, island_id: str) -> int:
        """Get number of peers in an island"""
        return len(self.island_peers.get(island_id, set()))

    def get_hub_info(self, node_id: str) -> HubInfo | None:
        """Get information about a specific hub"""
        return self.known_hubs.get(node_id)

    def get_peer_info(self, node_id: str) -> PeerInfo | None:
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
        logger.info('Starting hub manager for node %s', self.local_node_id)
        tasks = [asyncio.create_task(self._hub_health_check()), asyncio.create_task(self._peer_cleanup())]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error('Hub manager error: %s', e)
        finally:
            self.running = False

    async def stop(self):
        """Stop hub manager"""
        self.running = False
        logger.info('Stopping hub manager')

    async def _hub_health_check(self):
        """Check health of known hubs"""
        while self.running:
            try:
                current_time = time.time()
                offline_hubs = []
                for node_id, hub_info in self.known_hubs.items():
                    if current_time - hub_info.last_seen > 600:
                        offline_hubs.append(node_id)
                        logger.warning('Hub %s appears to be offline', node_id)
                for node_id in offline_hubs:
                    if node_id != self.local_node_id:
                        self.remove_known_hub(node_id)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error('Hub health check error: %s', e)
                await asyncio.sleep(10)

    async def _peer_cleanup(self):
        """Clean up stale peer entries"""
        while self.running:
            try:
                current_time = time.time()
                stale_peers = []
                for node_id, peer_info in self.peer_registry.items():
                    if current_time - peer_info.last_seen > 300:
                        stale_peers.append(node_id)
                for node_id in stale_peers:
                    self.unregister_peer(node_id)
                    logger.debug('Removed stale peer %s', node_id)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error('Peer cleanup error: %s', e)
                await asyncio.sleep(10)
hub_manager_instance: HubManager | None = None

def get_hub_manager() -> HubManager | None:
    """Get global hub manager instance"""
    return hub_manager_instance

def create_hub_manager(node_id: str, address: str, port: int, island_id: str, island_name: str) -> HubManager:
    """Create and set global hub manager instance"""
    global hub_manager_instance
    hub_manager_instance = HubManager(node_id, address, port, island_id, island_name)
    return hub_manager_instance