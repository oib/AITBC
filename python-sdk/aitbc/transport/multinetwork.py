"""
Multi-network support for AITBC Python SDK
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime

from .base import Transport, TransportError, TransportConnectionError
from .http import HTTPTransport
from .websocket import WebSocketTransport

logger = logging.getLogger(__name__)


@dataclass
class NetworkConfig:
    """Configuration for a network"""
    name: str
    chain_id: int
    transport: Transport
    is_default: bool = False
    bridges: List[str] = field(default_factory=list)
    explorer_url: Optional[str] = None
    rpc_url: Optional[str] = None
    native_token: str = "ETH"
    gas_token: Optional[str] = None


class MultiNetworkClient:
    """Client supporting multiple networks and cross-chain operations"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.networks: Dict[int, NetworkConfig] = {}
        self.default_network: Optional[int] = None
        self._connected = False
        self._connection_lock = asyncio.Lock()
        
        if config:
            self._load_config(config)
    
    def _load_config(self, config: Dict[str, Any]) -> None:
        """Load network configurations"""
        networks_config = config.get('networks', {})
        
        for name, net_config in networks_config.items():
            # Create transport
            transport = self._create_transport(net_config)
            
            # Create network config
            network = NetworkConfig(
                name=name,
                chain_id=net_config['chain_id'],
                transport=transport,
                is_default=net_config.get('default', False),
                bridges=net_config.get('bridges', []),
                explorer_url=net_config.get('explorer_url'),
                rpc_url=net_config.get('rpc_url'),
                native_token=net_config.get('native_token', 'ETH'),
                gas_token=net_config.get('gas_token')
            )
            
            self.add_network(network)
    
    def _create_transport(self, config: Dict[str, Any]) -> Transport:
        """Create transport from config"""
        transport_type = config.get('type', 'http')
        transport_config = config.copy()
        
        if transport_type == 'http':
            return HTTPTransport(transport_config)
        elif transport_type == 'websocket':
            return WebSocketTransport(transport_config)
        else:
            raise ValueError(f"Unknown transport type: {transport_type}")
    
    def add_network(self, network: NetworkConfig) -> None:
        """Add a network configuration"""
        if network.chain_id in self.networks:
            logger.warning(f"Network {network.chain_id} already exists, overwriting")
        
        self.networks[network.chain_id] = network
        
        # Set as default if marked or if no default exists
        if network.is_default or self.default_network is None:
            self.default_network = network.chain_id
        
        logger.info(f"Added network: {network.name} (chain_id: {network.chain_id})")
    
    def remove_network(self, chain_id: int) -> None:
        """Remove a network configuration"""
        if chain_id in self.networks:
            network = self.networks[chain_id]
            
            # Disconnect if connected
            if network.transport.is_connected:
                asyncio.create_task(network.transport.disconnect())
            
            del self.networks[chain_id]
            
            # Update default if necessary
            if self.default_network == chain_id:
                self.default_network = None
                # Set new default if other networks exist
                if self.networks:
                    self.default_network = next(iter(self.networks))
            
            logger.info(f"Removed network: {network.name} (chain_id: {chain_id})")
    
    def get_transport(self, chain_id: Optional[int] = None) -> Transport:
        """Get transport for a network"""
        network_id = chain_id or self.default_network
        
        if network_id is None:
            raise ValueError("No default network configured")
        
        if network_id not in self.networks:
            raise ValueError(f"Network {network_id} not configured")
        
        return self.networks[network_id].transport
    
    def get_network(self, chain_id: int) -> Optional[NetworkConfig]:
        """Get network configuration"""
        return self.networks.get(chain_id)
    
    def list_networks(self) -> List[NetworkConfig]:
        """List all configured networks"""
        return list(self.networks.values())
    
    def get_default_network(self) -> Optional[NetworkConfig]:
        """Get default network configuration"""
        if self.default_network:
            return self.networks.get(self.default_network)
        return None
    
    def set_default_network(self, chain_id: int) -> None:
        """Set default network"""
        if chain_id not in self.networks:
            raise ValueError(f"Network {chain_id} not configured")
        
        self.default_network = chain_id
        
        # Update all networks' default flag
        for net in self.networks.values():
            net.is_default = (net.chain_id == chain_id)
    
    async def connect_all(self) -> None:
        """Connect to all configured networks"""
        async with self._connection_lock:
            if self._connected:
                return
            
            logger.info(f"Connecting to {len(self.networks)} networks...")
            
            # Connect all transports
            tasks = []
            for chain_id, network in self.networks.items():
                task = asyncio.create_task(
                    self._connect_network(network),
                    name=f"connect_{network.name}"
                )
                tasks.append(task)
            
            # Wait for all connections
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for errors
            errors = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    network_name = list(self.networks.values())[i].name
                    errors.append(f"{network_name}: {result}")
                    logger.error(f"Failed to connect to {network_name}: {result}")
            
            if errors:
                raise TransportConnectionError(
                    f"Failed to connect to some networks: {'; '.join(errors)}"
                )
            
            self._connected = True
            logger.info("Connected to all networks")
    
    async def disconnect_all(self) -> None:
        """Disconnect from all networks"""
        async with self._connection_lock:
            if not self._connected:
                return
            
            logger.info("Disconnecting from all networks...")
            
            # Disconnect all transports
            tasks = []
            for network in self.networks.values():
                if network.transport.is_connected:
                    task = asyncio.create_task(
                        network.transport.disconnect(),
                        name=f"disconnect_{network.name}"
                    )
                    tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            self._connected = False
            logger.info("Disconnected from all networks")
    
    async def connect_network(self, chain_id: int) -> None:
        """Connect to a specific network"""
        network = self.networks.get(chain_id)
        if not network:
            raise ValueError(f"Network {chain_id} not configured")
        
        await self._connect_network(network)
    
    async def disconnect_network(self, chain_id: int) -> None:
        """Disconnect from a specific network"""
        network = self.networks.get(chain_id)
        if not network:
            raise ValueError(f"Network {chain_id} not configured")
        
        if network.transport.is_connected:
            await network.transport.disconnect()
    
    async def _connect_network(self, network: NetworkConfig) -> None:
        """Connect to a specific network"""
        try:
            if not network.transport.is_connected:
                await network.transport.connect()
                logger.info(f"Connected to {network.name}")
        except Exception as e:
            logger.error(f"Failed to connect to {network.name}: {e}")
            raise
    
    async def switch_network(self, chain_id: int) -> None:
        """Switch default network"""
        if chain_id not in self.networks:
            raise ValueError(f"Network {chain_id} not configured")
        
        # Connect if not connected
        network = self.networks[chain_id]
        if not network.transport.is_connected:
            await self._connect_network(network)
        
        # Set as default
        self.set_default_network(chain_id)
        logger.info(f"Switched to network: {network.name}")
    
    async def health_check_all(self) -> Dict[int, bool]:
        """Check health of all networks"""
        results = {}
        
        for chain_id, network in self.networks.items():
            try:
                results[chain_id] = await network.transport.health_check()
            except Exception as e:
                logger.warning(f"Health check failed for {network.name}: {e}")
                results[chain_id] = False
        
        return results
    
    async def broadcast_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        chain_ids: Optional[List[int]] = None
    ) -> Dict[int, Dict[str, Any]]:
        """Broadcast request to multiple networks"""
        if chain_ids is None:
            chain_ids = list(self.networks.keys())
        
        results = {}
        
        # Make requests in parallel
        tasks = {}
        for chain_id in chain_ids:
            if chain_id in self.networks:
                transport = self.networks[chain_id].transport
                task = asyncio.create_task(
                    transport.request(method, path, data, params, headers),
                    name=f"request_{chain_id}"
                )
                tasks[chain_id] = task
        
        # Wait for all requests
        for chain_id, task in tasks.items():
            try:
                results[chain_id] = await task
            except Exception as e:
                network_name = self.networks[chain_id].name
                logger.error(f"Request failed for {network_name}: {e}")
                results[chain_id] = {'error': str(e)}
        
        return results
    
    def get_network_stats(self) -> Dict[int, Dict[str, Any]]:
        """Get statistics for all networks"""
        stats = {}
        
        for chain_id, network in self.networks.items():
            network_stats = {
                'name': network.name,
                'chain_id': network.chain_id,
                'is_default': network.is_default,
                'bridges': network.bridges,
                'explorer_url': network.explorer_url,
                'rpc_url': network.rpc_url,
                'native_token': network.native_token,
                'gas_token': network.gas_token
            }
            
            # Add transport stats if available
            if hasattr(network.transport, 'get_stats'):
                network_stats['transport'] = network.transport.get_stats()
            
            stats[chain_id] = network_stats
        
        return stats
    
    def find_network_by_name(self, name: str) -> Optional[NetworkConfig]:
        """Find network by name"""
        for network in self.networks.values():
            if network.name == name:
                return network
        return None
    
    def find_networks_by_bridge(self, bridge: str) -> List[NetworkConfig]:
        """Find networks that support a specific bridge"""
        return [
            network for network in self.networks.values()
            if bridge in network.bridges
        ]
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect_all()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect_all()


class NetworkSwitcher:
    """Utility for switching between networks"""
    
    def __init__(self, client: MultiNetworkClient):
        self.client = client
        self._original_default: Optional[int] = None
    
    async def __aenter__(self):
        """Store original default network"""
        self._original_default = self.client.default_network
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Restore original default network"""
        if self._original_default:
            await self.client.switch_network(self._original_default)
    
    async def switch_to(self, chain_id: int):
        """Switch to specific network"""
        await self.client.switch_network(chain_id)
        return self
    
    async def switch_to_name(self, name: str):
        """Switch to network by name"""
        network = self.client.find_network_by_name(name)
        if not network:
            raise ValueError(f"Network {name} not found")
        
        await self.switch_to(network.chain_id)
        return self
