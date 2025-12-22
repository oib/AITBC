"""
Core components for AITBC Enterprise Connectors SDK
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import aiohttp
from aiohttp import ClientTimeout, ClientSession

from .auth import AuthHandler
from .rate_limiter import RateLimiter
from .metrics import MetricsCollector
from .exceptions import ConfigurationError


@dataclass
class ConnectorConfig:
    """Configuration for AITBC connectors"""
    
    # API Configuration
    base_url: str
    api_key: str
    api_version: str = "v1"
    
    # Connection Settings
    timeout: float = 30.0
    max_connections: int = 100
    max_retries: int = 3
    retry_backoff: float = 1.0
    
    # Rate Limiting
    rate_limit: Optional[int] = None  # Requests per second
    burst_limit: Optional[int] = None
    
    # Authentication
    auth_type: str = "bearer"  # bearer, basic, custom
    auth_config: Dict[str, Any] = field(default_factory=dict)
    
    # Webhooks
    webhook_secret: Optional[str] = None
    webhook_endpoint: Optional[str] = None
    
    # Monitoring
    enable_metrics: bool = True
    metrics_endpoint: Optional[str] = None
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Enterprise Features
    enterprise_id: Optional[str] = None
    tenant_id: Optional[str] = None
    region: Optional[str] = None
    
    def __post_init__(self):
        """Validate configuration"""
        if not self.base_url:
            raise ConfigurationError("base_url is required")
        if not self.api_key:
            raise ConfigurationError("api_key is required")
        
        # Set up logging
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper()),
            format=self.log_format
        )


class AITBCClient:
    """Main client for AITBC Enterprise Connectors"""
    
    def __init__(
        self,
        config: ConnectorConfig,
        session: Optional[ClientSession] = None,
        auth_handler: Optional[AuthHandler] = None,
        rate_limiter: Optional[RateLimiter] = None,
        metrics: Optional[MetricsCollector] = None
    ):
        self.config = config
        self.logger = logging.getLogger(f"aitbc.{self.__class__.__name__}")
        
        # Initialize components with dependency injection
        self._session = session or self._create_session()
        self._auth = auth_handler or AuthHandler(config)
        self._rate_limiter = rate_limiter or RateLimiter(config)
        self._metrics = metrics or MetricsCollector(config) if config.enable_metrics else None
        
        # Event handlers
        self._event_handlers: Dict[str, list] = {}
        
        # Connection state
        self._connected = False
        self._last_activity = None
    
    def _create_session(self) -> ClientSession:
        """Create HTTP session with configuration"""
        timeout = ClientTimeout(total=self.config.timeout)
        
        # Set up headers
        headers = {
            "User-Agent": f"AITBC-SDK/{__version__}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        return ClientSession(
            timeout=timeout,
            headers=headers,
            connector=aiohttp.TCPConnector(
                limit=self.config.max_connections,
                limit_per_host=self.config.max_connections // 4
            )
        )
    
    async def connect(self) -> None:
        """Establish connection to AITBC"""
        if self._connected:
            return
        
        try:
            # Test connection
            await self._test_connection()
            
            # Start metrics collection
            if self._metrics:
                await self._metrics.start()
            
            self._connected = True
            self._last_activity = datetime.utcnow()
            
            self.logger.info("Connected to AITBC")
            await self._emit_event("connected", {"timestamp": self._last_activity})
            
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close connection to AITBC"""
        if not self._connected:
            return
        
        try:
            # Stop metrics collection
            if self._metrics:
                await self._metrics.stop()
            
            # Close session
            await self._session.close()
            
            self._connected = False
            self.logger.info("Disconnected from AITBC")
            await self._emit_event("disconnected", {"timestamp": datetime.utcnow()})
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
    
    async def request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Make authenticated request to AITBC API"""
        if not self._connected:
            await self.connect()
        
        # Apply rate limiting
        if self.config.rate_limit:
            await self._rate_limiter.acquire()
        
        # Prepare request
        url = f"{self.config.base_url}/{self.config.api_version}/{path.lstrip('/')}"
        
        # Add authentication
        headers = kwargs.pop("headers", {})
        auth_headers = await self._auth.get_headers()
        headers.update(auth_headers)
        
        # Retry logic
        last_exception = None
        for attempt in range(self.config.max_retries + 1):
            try:
                start_time = datetime.utcnow()
                
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs
                ) as response:
                    # Record metrics
                    if self._metrics:
                        duration = (datetime.utcnow() - start_time).total_seconds()
                        await self._metrics.record_request(
                            method=method,
                            path=path,
                            status=response.status,
                            duration=duration
                        )
                    
                    # Handle response
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", self.config.retry_backoff))
                        await asyncio.sleep(retry_after)
                        continue
                    
                    response.raise_for_status()
                    
                    data = await response.json()
                    self._last_activity = datetime.utcnow()
                    
                    return data
                    
            except aiohttp.ClientError as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    backoff = self.config.retry_backoff * (2 ** attempt)
                    self.logger.warning(f"Request failed, retrying in {backoff}s: {e}")
                    await asyncio.sleep(backoff)
                else:
                    self.logger.error(f"Request failed after {self.config.max_retries} retries: {e}")
                    raise
        
        raise last_exception
    
    async def get(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make GET request"""
        return await self.request("GET", path, **kwargs)
    
    async def post(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make POST request"""
        return await self.request("POST", path, **kwargs)
    
    async def put(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make PUT request"""
        return await self.request("PUT", path, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make DELETE request"""
        return await self.request("DELETE", path, **kwargs)
    
    def on(self, event: str, handler: Callable[[Dict[str, Any]], Awaitable[None]]):
        """Register event handler"""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)
    
    def off(self, event: str, handler: Callable):
        """Unregister event handler"""
        if event in self._event_handlers:
            try:
                self._event_handlers[event].remove(handler)
            except ValueError:
                pass
    
    async def _emit_event(self, event: str, data: Dict[str, Any]):
        """Emit event to registered handlers"""
        if event in self._event_handlers:
            tasks = []
            for handler in self._event_handlers[event]:
                tasks.append(handler(data))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _test_connection(self):
        """Test connection to AITBC"""
        try:
            await self.get("/health")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to AITBC: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self._connected
    
    @property
    def last_activity(self) -> Optional[datetime]:
        """Get last activity timestamp"""
        return self._last_activity
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
