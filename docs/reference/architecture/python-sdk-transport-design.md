# Python SDK Transport Abstraction Design

## Overview

This document outlines the design for a pluggable transport abstraction layer in the AITBC Python SDK, enabling support for multiple networks and cross-chain operations.

## Architecture

### Current SDK Structure
```
AITBCClient
├── Jobs API
├── Marketplace API
├── Wallet API
├── Receipts API
└── Direct HTTP calls to coordinator
```

### Proposed Transport-Based Structure
```
AITBCClient
├── Transport Layer (Pluggable)
│   ├── HTTPTransport
│   ├── WebSocketTransport
│   └── CrossChainTransport
├── Jobs API
├── Marketplace API
├── Wallet API
├── Receipts API
└── Settlement API (New)
```

## Transport Interface

### Base Transport Class

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
import asyncio

class Transport(ABC):
    """Abstract base class for all transports"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._connected = False
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection"""
        pass
    
    @abstractmethod
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make a request"""
        pass
    
    @abstractmethod
    async def stream(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream responses"""
        pass
    
    @property
    def is_connected(self) -> bool:
        """Check if transport is connected"""
        return self._connected
    
    @property
    def chain_id(self) -> Optional[int]:
        """Get the chain ID this transport is connected to"""
        return self.config.get('chain_id')
```

### HTTP Transport Implementation

```python
import aiohttp
from typing import AsyncIterator

class HTTPTransport(Transport):
    """HTTP transport for REST API calls"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config['base_url']
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = config.get('timeout', 30)
    
    async def connect(self) -> None:
        """Create HTTP session"""
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.config.get('default_headers', {})
        )
        self._connected = True
    
    async def disconnect(self) -> None:
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
        self._connected = False
    
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request"""
        if not self.session:
            await self.connect()
        
        url = f"{self.base_url}{path}"
        
        async with self.session.request(
            method=method,
            url=url,
            json=data,
            params=params,
            headers=headers
        ) as response:
            if response.status >= 400:
                error_data = await response.json()
                raise APIError(error_data.get('error', 'Unknown error'))
            
            return await response.json()
    
    async def stream(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream HTTP responses (not supported for basic HTTP)"""
        raise NotImplementedError("HTTP transport does not support streaming")
```

### WebSocket Transport Implementation

```python
import websockets
import json
from typing import AsyncIterator

class WebSocketTransport(Transport):
    """WebSocket transport for real-time updates"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.ws_url = config['ws_url']
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self._subscriptions: Dict[str, Any] = {}
    
    async def connect(self) -> None:
        """Connect to WebSocket"""
        self.websocket = await websockets.connect(
            self.ws_url,
            extra_headers=self.config.get('headers', {})
        )
        self._connected = True
        
        # Start message handler
        asyncio.create_task(self._handle_messages())
    
    async def disconnect(self) -> None:
        """Disconnect WebSocket"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self._connected = False
    
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Send request via WebSocket"""
        if not self.websocket:
            await self.connect()
        
        message = {
            'id': self._generate_id(),
            'method': method,
            'path': path,
            'data': data,
            'params': params
        }
        
        await self.websocket.send(json.dumps(message))
        response = await self.websocket.recv()
        return json.loads(response)
    
    async def stream(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream responses from WebSocket"""
        if not self.websocket:
            await self.connect()
        
        # Subscribe to stream
        subscription_id = self._generate_id()
        message = {
            'id': subscription_id,
            'method': 'subscribe',
            'path': path,
            'data': data
        }
        
        await self.websocket.send(json.dumps(message))
        
        # Yield messages as they come
        async for message in self.websocket:
            data = json.loads(message)
            if data.get('subscription_id') == subscription_id:
                yield data
    
    async def _handle_messages(self):
        """Handle incoming WebSocket messages"""
        async for message in self.websocket:
            data = json.loads(message)
            # Handle subscriptions and other messages
            pass
```

### Cross-Chain Transport Implementation

```python
from ..settlement.manager import BridgeManager
from ..settlement.bridges.base import SettlementMessage, SettlementResult

class CrossChainTransport(Transport):
    """Transport for cross-chain settlements"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.bridge_manager = BridgeManager(config.get('storage'))
        self.base_transport = config.get('base_transport')
    
    async def connect(self) -> None:
        """Initialize bridge manager"""
        await self.bridge_manager.initialize(config.get('bridges', {}))
        if self.base_transport:
            await self.base_transport.connect()
        self._connected = True
    
    async def disconnect(self) -> None:
        """Disconnect all bridges"""
        if self.base_transport:
            await self.base_transport.disconnect()
        self._connected = False
    
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Handle cross-chain requests"""
        if path.startswith('/settlement/'):
            return await self._handle_settlement_request(method, path, data)
        
        # Forward to base transport for other requests
        if self.base_transport:
            return await self.base_transport.request(
                method, path, data, params, headers
            )
        
        raise NotImplementedError(f"Path {path} not supported")
    
    async def settle_cross_chain(
        self,
        message: SettlementMessage,
        bridge_name: Optional[str] = None
    ) -> SettlementResult:
        """Settle message across chains"""
        return await self.bridge_manager.settle_cross_chain(
            message, bridge_name
        )
    
    async def estimate_settlement_cost(
        self,
        message: SettlementMessage,
        bridge_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Estimate settlement cost"""
        return await self.bridge_manager.estimate_settlement_cost(
            message, bridge_name
        )
    
    async def _handle_settlement_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handle settlement-specific requests"""
        if method == 'POST' and path == '/settlement/cross-chain':
            message = SettlementMessage(**data)
            result = await self.settle_cross_chain(message)
            return {
                'message_id': result.message_id,
                'status': result.status.value,
                'transaction_hash': result.transaction_hash
            }
        
        elif method == 'GET' and path.startswith('/settlement/'):
            message_id = path.split('/')[-1]
            result = await self.bridge_manager.get_settlement_status(message_id)
            return {
                'message_id': message_id,
                'status': result.status.value,
                'error_message': result.error_message
            }
        
        else:
            raise ValueError(f"Unsupported settlement request: {method} {path}")
```

## Multi-Network Client

### Network Configuration

```python
@dataclass
class NetworkConfig:
    """Configuration for a network"""
    name: str
    chain_id: int
    transport: Transport
    is_default: bool = False
    bridges: List[str] = None

class MultiNetworkClient:
    """Client supporting multiple networks"""
    
    def __init__(self):
        self.networks: Dict[int, NetworkConfig] = {}
        self.default_network: Optional[int] = None
    
    def add_network(self, config: NetworkConfig) -> None:
        """Add a network configuration"""
        self.networks[config.chain_id] = config
        if config.is_default or self.default_network is None:
            self.default_network = config.chain_id
    
    def get_transport(self, chain_id: Optional[int] = None) -> Transport:
        """Get transport for a network"""
        network_id = chain_id or self.default_network
        if network_id not in self.networks:
            raise ValueError(f"Network {network_id} not configured")
        
        return self.networks[network_id].transport
    
    async def connect_all(self) -> None:
        """Connect to all configured networks"""
        for config in self.networks.values():
            await config.transport.connect()
    
    async def disconnect_all(self) -> None:
        """Disconnect from all networks"""
        for config in self.networks.values():
            await config.transport.disconnect()
```

## Updated SDK Client

### New Client Implementation

```python
class AITBCClient:
    """AITBC client with pluggable transports"""
    
    def __init__(
        self,
        transport: Optional[Union[Transport, Dict[str, Any]]] = None,
        multi_network: bool = False
    ):
        if multi_network:
            self._init_multi_network(transport or {})
        else:
            self._init_single_network(transport or {})
    
    def _init_single_network(self, transport_config: Dict[str, Any]) -> None:
        """Initialize single network client"""
        if isinstance(transport_config, Transport):
            self.transport = transport_config
        else:
            # Default to HTTP transport
            self.transport = HTTPTransport(transport_config)
        
        self.multi_network = False
        self._init_apis()
    
    def _init_multi_network(self, configs: Dict[str, Any]) -> None:
        """Initialize multi-network client"""
        self.multi_network_client = MultiNetworkClient()
        
        # Configure networks
        for name, config in configs.get('networks', {}).items():
            transport = self._create_transport(config)
            network_config = NetworkConfig(
                name=name,
                chain_id=config['chain_id'],
                transport=transport,
                is_default=config.get('default', False)
            )
            self.multi_network_client.add_network(network_config)
        
        self.multi_network = True
        self._init_apis()
    
    def _create_transport(self, config: Dict[str, Any]) -> Transport:
        """Create transport from config"""
        transport_type = config.get('type', 'http')
        
        if transport_type == 'http':
            return HTTPTransport(config)
        elif transport_type == 'websocket':
            return WebSocketTransport(config)
        elif transport_type == 'crosschain':
            return CrossChainTransport(config)
        else:
            raise ValueError(f"Unknown transport type: {transport_type}")
    
    def _init_apis(self) -> None:
        """Initialize API clients"""
        if self.multi_network:
            self.jobs = MultiNetworkJobsAPI(self.multi_network_client)
            self.settlement = MultiNetworkSettlementAPI(self.multi_network_client)
        else:
            self.jobs = JobsAPI(self.transport)
            self.settlement = SettlementAPI(self.transport)
        
        # Other APIs remain the same but use the transport
        self.marketplace = MarketplaceAPI(self.transport)
        self.wallet = WalletAPI(self.transport)
        self.receipts = ReceiptsAPI(self.transport)
    
    async def connect(self) -> None:
        """Connect to network(s)"""
        if self.multi_network:
            await self.multi_network_client.connect_all()
        else:
            await self.transport.connect()
    
    async def disconnect(self) -> None:
        """Disconnect from network(s)"""
        if self.multi_network:
            await self.multi_network_client.disconnect_all()
        else:
            await self.transport.disconnect()
```

## Usage Examples

### Single Network with HTTP Transport

```python
from aitbc import AITBCClient, HTTPTransport

# Create client with HTTP transport
transport = HTTPTransport({
    'base_url': 'https://api.aitbc.io',
    'timeout': 30,
    'default_headers': {'X-API-Key': 'your-key'}
})

client = AITBCClient(transport)
await client.connect()

# Use APIs normally
job = await client.jobs.create({...})
```

### Multi-Network Configuration

```python
from aitbc import AITBCClient

config = {
    'networks': {
        'ethereum': {
            'type': 'http',
            'chain_id': 1,
            'base_url': 'https://api.aitbc.io',
            'default': True
        },
        'polygon': {
            'type': 'http',
            'chain_id': 137,
            'base_url': 'https://polygon-api.aitbc.io'
        },
        'arbitrum': {
            'type': 'crosschain',
            'chain_id': 42161,
            'base_transport': HTTPTransport({
                'base_url': 'https://arbitrum-api.aitbc.io'
            }),
            'bridges': {
                'layerzero': {'enabled': True},
                'chainlink': {'enabled': True}
            }
        }
    }
}

client = AITBCClient(config, multi_network=True)
await client.connect()

# Create job on specific network
job = await client.jobs.create({...}, chain_id=137)

# Settle across chains
settlement = await client.settlement.settle_cross_chain(
    job_id=job['id'],
    target_chain_id=42161,
    bridge_name='layerzero'
)
```

### Cross-Chain Settlement

```python
# Create job on Ethereum
job = await client.jobs.create({
    'name': 'cross-chain-ai-job',
    'target_chain': 42161,  # Arbitrum
    'requires_cross_chain_settlement': True
})

# Wait for completion
result = await client.jobs.wait_for_completion(job['id'])

# Settle to Arbitrum
settlement = await client.settlement.settle_cross_chain(
    job_id=job['id'],
    target_chain_id=42161,
    bridge_name='layerzero'
)

# Monitor settlement
status = await client.settlement.get_status(settlement['message_id'])
```

## Migration Guide

### From Current SDK

```python
# Old way
client = AITBCClient(api_key='key', base_url='url')

# New way (backward compatible)
client = AITBCClient({
    'base_url': 'url',
    'default_headers': {'X-API-Key': 'key'}
})

# Or with explicit transport
transport = HTTPTransport({
    'base_url': 'url',
    'default_headers': {'X-API-Key': 'key'}
})
client = AITBCClient(transport)
```

## Benefits

1. **Flexibility**: Easy to add new transport types
2. **Multi-Network**: Support for multiple blockchains
3. **Cross-Chain**: Built-in support for cross-chain settlements
4. **Backward Compatible**: Existing code continues to work
5. **Testable**: Easy to mock transports for testing
6. **Extensible**: Plugin architecture for custom transports

---

*Document Version: 1.0*
*Last Updated: 2025-01-10*
*Owner: SDK Team*
