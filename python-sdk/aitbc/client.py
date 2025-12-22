"""
Main AITBC client with pluggable transport abstraction
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Union, List
from datetime import datetime

from .transport import (
    Transport, 
    HTTPTransport, 
    WebSocketTransport,
    MultiNetworkClient,
    NetworkConfig,
    TransportError
)
from .transport.base import BatchTransport, CachedTransport, RateLimitedTransport
from .apis.jobs import JobsAPI, MultiNetworkJobsAPI
from .apis.marketplace import MarketplaceAPI
from .apis.wallet import WalletAPI
from .apis.receipts import ReceiptsAPI
from .apis.settlement import SettlementAPI, MultiNetworkSettlementAPI

logger = logging.getLogger(__name__)


class AITBCClient:
    """AITBC client with pluggable transports and multi-network support"""
    
    def __init__(
        self,
        transport: Optional[Union[Transport, Dict[str, Any]]] = None,
        multi_network: bool = False,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize AITBC client
        
        Args:
            transport: Transport instance or configuration
            multi_network: Enable multi-network mode
            config: Additional configuration options
        """
        self.config = config or {}
        self._connected = False
        self._apis = {}
        
        # Initialize transport layer
        if multi_network:
            self._init_multi_network(transport or {})
        else:
            self._init_single_network(transport or self._get_default_config())
        
        # Initialize API clients
        self._init_apis()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for backward compatibility"""
        return {
            'type': 'http',
            'base_url': self.config.get('base_url', 'https://api.aitbc.io'),
            'timeout': self.config.get('timeout', 30),
            'api_key': self.config.get('api_key'),
            'default_headers': {
                'User-Agent': f'AITBC-Python-SDK/{self._get_version()}',
                'Content-Type': 'application/json'
            }
        }
    
    def _init_single_network(self, transport_config: Union[Transport, Dict[str, Any]]) -> None:
        """Initialize single network client"""
        if isinstance(transport_config, Transport):
            self.transport = transport_config
        else:
            # Create transport from config
            self.transport = self._create_transport(transport_config)
        
        self.multi_network = False
        self.multi_network_client = None
    
    def _init_multi_network(self, configs: Dict[str, Any]) -> None:
        """Initialize multi-network client"""
        self.multi_network_client = MultiNetworkClient(configs)
        self.multi_network = True
        self.transport = None  # Use multi_network_client instead
    
    def _create_transport(self, config: Dict[str, Any]) -> Transport:
        """Create transport from configuration"""
        transport_type = config.get('type', 'http')
        
        # Add API key to headers if provided
        if 'api_key' in config and 'default_headers' not in config:
            config['default_headers'] = {
                'X-API-Key': config['api_key'],
                'User-Agent': f'AITBC-Python-SDK/{self._get_version()}',
                'Content-Type': 'application/json'
            }
        
        # Create base transport
        if transport_type == 'http':
            transport = HTTPTransport(config)
        elif transport_type == 'websocket':
            transport = WebSocketTransport(config)
        elif transport_type == 'crosschain':
            # Will be implemented later
            raise NotImplementedError("CrossChain transport not yet implemented")
        else:
            raise ValueError(f"Unknown transport type: {transport_type}")
        
        # Apply mixins if enabled
        if config.get('cached', False):
            transport = CachedTransport(config)
        
        if config.get('rate_limited', False):
            transport = RateLimitedTransport(config)
        
        if config.get('batch', False):
            transport = BatchTransport(config)
        
        return transport
    
    def _init_apis(self) -> None:
        """Initialize API clients"""
        if self.multi_network:
            # Multi-network APIs
            self.jobs = MultiNetworkJobsAPI(self.multi_network_client)
            self.settlement = MultiNetworkSettlementAPI(self.multi_network_client)
            
            # Single-network APIs (use default network)
            default_transport = self.multi_network_client.get_transport()
            self.marketplace = MarketplaceAPI(default_transport)
            self.wallet = WalletAPI(default_transport)
            self.receipts = ReceiptsAPI(default_transport)
        else:
            # Single-network APIs
            self.jobs = JobsAPI(self.transport)
            self.marketplace = MarketplaceAPI(self.transport)
            self.wallet = WalletAPI(self.transport)
            self.receipts = ReceiptsAPI(self.transport)
            self.settlement = SettlementAPI(self.transport)
    
    async def connect(self) -> None:
        """Connect to network(s)"""
        if self.multi_network:
            await self.multi_network_client.connect_all()
        else:
            await self.transport.connect()
        
        self._connected = True
        logger.info("AITBC client connected")
    
    async def disconnect(self) -> None:
        """Disconnect from network(s)"""
        if self.multi_network:
            await self.multi_network_client.disconnect_all()
        elif self.transport:
            await self.transport.disconnect()
        
        self._connected = False
        logger.info("AITBC client disconnected")
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected"""
        if self.multi_network:
            return self.multi_network_client._connected
        elif self.transport:
            return self.transport.is_connected
        return False
    
    # Multi-network methods
    def add_network(self, network_config: NetworkConfig) -> None:
        """Add a network (multi-network mode only)"""
        if not self.multi_network:
            raise RuntimeError("Multi-network mode not enabled")
        
        self.multi_network_client.add_network(network_config)
    
    def remove_network(self, chain_id: int) -> None:
        """Remove a network (multi-network mode only)"""
        if not self.multi_network:
            raise RuntimeError("Multi-network mode not enabled")
        
        self.multi_network_client.remove_network(chain_id)
    
    def get_networks(self) -> List[NetworkConfig]:
        """Get all configured networks"""
        if not self.multi_network:
            raise RuntimeError("Multi-network mode not enabled")
        
        return self.multi_network_client.list_networks()
    
    def set_default_network(self, chain_id: int) -> None:
        """Set default network (multi-network mode only)"""
        if not self.multi_network:
            raise RuntimeError("Multi-network mode not enabled")
        
        self.multi_network_client.set_default_network(chain_id)
    
    async def switch_network(self, chain_id: int) -> None:
        """Switch to a different network (multi-network mode only)"""
        if not self.multi_network:
            raise RuntimeError("Multi-network mode not enabled")
        
        await self.multi_network_client.switch_network(chain_id)
    
    async def health_check(self) -> Union[bool, Dict[int, bool]]:
        """Check health of connection(s)"""
        if self.multi_network:
            return await self.multi_network_client.health_check_all()
        elif self.transport:
            return await self.transport.health_check()
        return False
    
    # Backward compatibility methods
    def get_api_key(self) -> Optional[str]:
        """Get API key (backward compatibility)"""
        if self.multi_network:
            # Get from default network
            default_network = self.multi_network_client.get_default_network()
            if default_network:
                return default_network.transport.get_config('api_key')
        elif self.transport:
            return self.transport.get_config('api_key')
        return None
    
    def set_api_key(self, api_key: str) -> None:
        """Set API key (backward compatibility)"""
        if self.multi_network:
            # Update all networks
            for network in self.multi_network_client.networks.values():
                network.transport.update_config({'api_key': api_key})
        elif self.transport:
            self.transport.update_config({'api_key': api_key})
    
    def get_base_url(self) -> Optional[str]:
        """Get base URL (backward compatibility)"""
        if self.multi_network:
            default_network = self.multi_network_client.get_default_network()
            if default_network:
                return default_network.transport.get_config('base_url')
        elif self.transport:
            return self.transport.get_config('base_url')
        return None
    
    # Utility methods
    def _get_version(self) -> str:
        """Get SDK version"""
        try:
            from . import __version__
            return __version__
        except ImportError:
            return "1.0.0"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        stats = {
            'multi_network': self.multi_network,
            'connected': self._connected,
            'version': self._get_version()
        }
        
        if self.multi_network:
            stats['networks'] = self.multi_network_client.get_network_stats()
        elif self.transport:
            if hasattr(self.transport, 'get_stats'):
                stats['transport'] = self.transport.get_stats()
            else:
                stats['transport'] = {
                    'connected': self.transport.is_connected,
                    'chain_id': self.transport.chain_id
                }
        
        return stats
    
    # Context managers
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()


# Convenience functions for backward compatibility
def create_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[int] = None,
    transport: Optional[Union[Transport, str]] = None,
    **kwargs
) -> AITBCClient:
    """
    Create AITBC client with backward-compatible interface
    
    Args:
        api_key: API key for authentication
        base_url: Base URL for the API
        timeout: Request timeout in seconds
        transport: Transport type ('http', 'websocket') or Transport instance
        **kwargs: Additional configuration options
    
    Returns:
        AITBCClient instance
    """
    config = {}
    
    # Build configuration
    if api_key:
        config['api_key'] = api_key
    if base_url:
        config['base_url'] = base_url
    if timeout:
        config['timeout'] = timeout
    
    # Add other config
    config.update(kwargs)
    
    # Handle transport parameter
    if isinstance(transport, Transport):
        return AITBCClient(transport=transport, config=config)
    elif transport:
        config['type'] = transport
    
    return AITBCClient(transport=config, config=config)


def create_multi_network_client(
    networks: Dict[str, Dict[str, Any]],
    default_network: Optional[str] = None,
    **kwargs
) -> AITBCClient:
    """
    Create multi-network AITBC client
    
    Args:
        networks: Dictionary of network configurations
        default_network: Name of default network
        **kwargs: Additional configuration options
    
    Returns:
        AITBCClient instance with multi-network support
    """
    config = {
        'networks': networks,
        **kwargs
    }
    
    client = AITBCClient(multi_network=True, config=config)
    
    # Set default network if specified
    if default_network:
        network = client.multi_network_client.find_network_by_name(default_network)
        if network:
            client.set_default_network(network.chain_id)
    
    return client


# Legacy aliases for backward compatibility
Client = AITBCClient
