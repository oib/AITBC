"""
Base transport interface for AITBC Python SDK
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator, Union, List
import asyncio
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


class TransportError(Exception):
    """Base exception for transport errors"""
    pass


class TransportConnectionError(TransportError):
    """Raised when transport fails to connect"""
    pass


class TransportRequestError(TransportError):
    """Raised when transport request fails"""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class Transport(ABC):
    """Abstract base class for all transports"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._connected = False
        self._lock = asyncio.Lock()
        self._connection_attempts = 0
        self._max_connection_attempts = config.get('max_connection_attempts', 3)
        self._retry_delay = config.get('retry_delay', 1)
    
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
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Make a request"""
        pass
    
    @abstractmethod
    async def stream(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream responses"""
        pass
    
    async def health_check(self) -> bool:
        """Check if transport is healthy"""
        try:
            if not self._connected:
                return False
            
            # Default health check - make a ping request
            await self.request('GET', '/health')
            return True
        except Exception as e:
            logger.warning(f"Transport health check failed: {e}")
            return False
    
    async def ensure_connected(self) -> None:
        """Ensure transport is connected, with retry logic"""
        async with self._lock:
            if self._connected:
                return
            
            while self._connection_attempts < self._max_connection_attempts:
                try:
                    await self.connect()
                    self._connection_attempts = 0
                    return
                except Exception as e:
                    self._connection_attempts += 1
                    logger.warning(f"Connection attempt {self._connection_attempts} failed: {e}")
                    
                    if self._connection_attempts < self._max_connection_attempts:
                        await asyncio.sleep(self._retry_delay * self._connection_attempts)
                    else:
                        raise TransportConnectionError(
                            f"Failed to connect after {self._max_connection_attempts} attempts"
                        )
    
    @property
    def is_connected(self) -> bool:
        """Check if transport is connected"""
        return self._connected
    
    @property
    def chain_id(self) -> Optional[int]:
        """Get the chain ID this transport is connected to"""
        return self.config.get('chain_id')
    
    @property
    def network_name(self) -> Optional[str]:
        """Get the network name"""
        return self.config.get('network_name')
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """Update configuration"""
        self.config.update(updates)
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()


class BatchTransport(Transport):
    """Transport mixin for batch operations"""
    
    @abstractmethod
    async def batch_request(
        self,
        requests: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Make multiple requests in batch"""
        pass


class CachedTransport(Transport):
    """Transport mixin for caching responses"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = config.get('cache_ttl', 300)  # 5 minutes
        self._cache_timestamps: Dict[str, float] = {}
    
    async def cached_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cache_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make request with caching"""
        # Only cache GET requests
        if method.upper() != 'GET':
            return await self.request(method, path, data, params, headers)
        
        # Generate cache key
        if not cache_key:
            import hashlib
            import json
            cache_data = json.dumps({
                'method': method,
                'path': path,
                'params': params
            }, sort_keys=True)
            cache_key = hashlib.md5(cache_data.encode()).hexdigest()
        
        # Check cache
        if cache_key in self._cache:
            timestamp = self._cache_timestamps.get(cache_key, 0)
            if asyncio.get_event_loop().time() - timestamp < self._cache_ttl:
                return self._cache[cache_key]
        
        # Make request
        response = await self.request(method, path, data, params, headers)
        
        # Cache response
        self._cache[cache_key] = response
        self._cache_timestamps[cache_key] = asyncio.get_event_loop().time()
        
        return response
    
    def clear_cache(self, pattern: Optional[str] = None) -> None:
        """Clear cached responses"""
        if pattern:
            import re
            regex = re.compile(pattern)
            keys_to_remove = [k for k in self._cache.keys() if regex.match(k)]
            for key in keys_to_remove:
                del self._cache[key]
                if key in self._cache_timestamps:
                    del self._cache_timestamps[key]
        else:
            self._cache.clear()
            self._cache_timestamps.clear()


class RateLimitedTransport(Transport):
    """Transport mixin for rate limiting"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._rate_limit = config.get('rate_limit', 60)  # requests per minute
        self._rate_window = config.get('rate_window', 60)  # seconds
        self._requests: List[float] = []
        self._rate_lock = asyncio.Lock()
    
    async def _check_rate_limit(self) -> None:
        """Check if request is within rate limit"""
        async with self._rate_lock:
            now = asyncio.get_event_loop().time()
            
            # Remove old requests outside the window
            self._requests = [req_time for req_time in self._requests 
                            if now - req_time < self._rate_window]
            
            # Check if we're at the limit
            if len(self._requests) >= self._rate_limit:
                # Calculate wait time
                oldest_request = min(self._requests)
                wait_time = self._rate_window - (now - oldest_request)
                
                if wait_time > 0:
                    logger.warning(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                    await asyncio.sleep(wait_time)
            
            # Add current request
            self._requests.append(now)
    
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Make request with rate limiting"""
        await self._check_rate_limit()
        return await super().request(method, path, data, params, headers, timeout)
