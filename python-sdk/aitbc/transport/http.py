"""
HTTP transport implementation for AITBC Python SDK
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, AsyncIterator, Union
from datetime import datetime, timedelta

import aiohttp
from aiohttp import ClientTimeout, ClientError, ClientResponseError

from .base import Transport, TransportError, TransportConnectionError, TransportRequestError

logger = logging.getLogger(__name__)


class HTTPTransport(Transport):
    """HTTP transport for REST API calls"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config['base_url'].rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = ClientTimeout(
            total=config.get('timeout', 30),
            connect=config.get('connect_timeout', 10),
            sock_read=config.get('read_timeout', 30)
        )
        self.default_headers = config.get('default_headers', {})
        self.max_redirects = config.get('max_redirects', 10)
        self.verify_ssl = config.get('verify_ssl', True)
        self._last_request_time: Optional[float] = None
    
    async def connect(self) -> None:
        """Create HTTP session"""
        try:
            # Configure SSL context
            ssl_context = None
            if not self.verify_ssl:
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            # Create connector
            connector = aiohttp.TCPConnector(
                limit=self.config.get('connection_limit', 100),
                limit_per_host=self.config.get('connection_limit_per_host', 30),
                ttl_dns_cache=self.config.get('dns_cache_ttl', 300),
                use_dns_cache=True,
                ssl=ssl_context,
                enable_cleanup_closed=True
            )
            
            # Create session
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout,
                headers=self.default_headers,
                max_redirects=self.max_redirects,
                raise_for_status=False  # We'll handle status codes manually
            )
            
            # Test connection with health check
            await self.health_check()
            self._connected = True
            logger.info(f"HTTP transport connected to {self.base_url}")
            
        except Exception as e:
            logger.error(f"Failed to connect HTTP transport: {e}")
            raise TransportConnectionError(f"Connection failed: {e}")
    
    async def disconnect(self) -> None:
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
        self._connected = False
        logger.info("HTTP transport disconnected")
    
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Make HTTP request"""
        await self.ensure_connected()
        
        if not self.session:
            raise TransportConnectionError("Transport not connected")
        
        # Prepare URL
        url = f"{self.base_url}{path}"
        
        # Prepare headers
        request_headers = {}
        if self.default_headers:
            request_headers.update(self.default_headers)
        if headers:
            request_headers.update(headers)
        
        # Add content-type if data is provided
        if data and 'content-type' not in request_headers:
            request_headers['content-type'] = 'application/json'
        
        # Prepare request timeout
        request_timeout = self.timeout
        if timeout:
            request_timeout = ClientTimeout(total=timeout)
        
        # Log request
        logger.debug(f"HTTP {method} {url}")
        
        try:
            # Make request
            async with self.session.request(
                method=method.upper(),
                url=url,
                json=data if data and request_headers.get('content-type') == 'application/json' else None,
                data=data if data and request_headers.get('content-type') != 'application/json' else None,
                params=params,
                headers=request_headers,
                timeout=request_timeout
            ) as response:
                # Record request time
                self._last_request_time = asyncio.get_event_loop().time()
                
                # Handle response
                await self._handle_response(response)
                
                # Parse response
                if response.content_type == 'application/json':
                    result = await response.json()
                else:
                    result = {'data': await response.text()}
                
                # Add metadata
                result['_metadata'] = {
                    'status_code': response.status,
                    'headers': dict(response.headers),
                    'url': str(response.url)
                }
                
                return result
                
        except ClientResponseError as e:
            raise TransportRequestError(
                f"HTTP {e.status}: {e.message}",
                status_code=e.status,
                response={'error': e.message}
            )
        except ClientError as e:
            raise TransportError(f"HTTP request failed: {e}")
        except asyncio.TimeoutError:
            raise TransportError("Request timed out")
        except Exception as e:
            raise TransportError(f"Unexpected error: {e}")
    
    async def stream(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream responses (not supported for basic HTTP)"""
        raise NotImplementedError("HTTP transport does not support streaming")
    
    async def download(
        self,
        path: str,
        file_path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        chunk_size: int = 8192
    ) -> None:
        """Download file to disk"""
        await self.ensure_connected()
        
        if not self.session:
            raise TransportConnectionError("Transport not connected")
        
        url = f"{self.base_url}{path}"
        
        try:
            async with self.session.get(
                url,
                params=params,
                headers=headers
            ) as response:
                await self._handle_response(response)
                
                # Stream to file
                with open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        f.write(chunk)
                
                logger.info(f"Downloaded {url} to {file_path}")
                
        except Exception as e:
            raise TransportError(f"Download failed: {e}")
    
    async def upload(
        self,
        path: str,
        file_path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        chunk_size: int = 8192
    ) -> Dict[str, Any]:
        """Upload file from disk"""
        await self.ensure_connected()
        
        if not self.session:
            raise TransportConnectionError("Transport not connected")
        
        url = f"{self.base_url}{path}"
        
        try:
            # Prepare multipart form data
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field(
                    'file',
                    f,
                    filename=file_path.split('/')[-1],
                    content_type='application/octet-stream'
                )
                
                # Add additional fields
                if params:
                    for key, value in params.items():
                        data.add_field(key, str(value))
                
                async with self.session.post(
                    url,
                    data=data,
                    headers=headers
                ) as response:
                    await self._handle_response(response)
                    
                    if response.content_type == 'application/json':
                        return await response.json()
                    else:
                        return {'status': 'uploaded'}
                        
        except Exception as e:
            raise TransportError(f"Upload failed: {e}")
    
    async def _handle_response(self, response: aiohttp.ClientResponse) -> None:
        """Handle HTTP response"""
        if response.status >= 400:
            error_data = {}
            
            try:
                if response.content_type == 'application/json':
                    error_data = await response.json()
                else:
                    error_data = {'error': await response.text()}
            except:
                error_data = {'error': f'HTTP {response.status}'}
            
            raise TransportRequestError(
                error_data.get('error', f'HTTP {response.status}'),
                status_code=response.status,
                response=error_data
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get transport statistics"""
        stats = {
            'connected': self._connected,
            'base_url': self.base_url,
            'last_request_time': self._last_request_time
        }
        
        if self.session:
            # Get connector stats
            connector = self.session.connector
            stats.update({
                'total_connections': len(connector._conns),
                'available_connections': sum(len(conns) for conns in connector._conns.values())
            })
        
        return stats


class AuthenticatedHTTPTransport(HTTPTransport):
    """HTTP transport with authentication"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.auth_type = config.get('auth_type', 'api_key')
        self.auth_config = config.get('auth', {})
    
    async def _add_auth_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Add authentication headers"""
        headers = headers.copy()
        
        if self.auth_type == 'api_key':
            api_key = self.auth_config.get('api_key')
            if api_key:
                key_header = self.auth_config.get('key_header', 'X-API-Key')
                headers[key_header] = api_key
        
        elif self.auth_type == 'bearer':
            token = self.auth_config.get('token')
            if token:
                headers['Authorization'] = f'Bearer {token}'
        
        elif self.auth_type == 'basic':
            username = self.auth_config.get('username')
            password = self.auth_config.get('password')
            if username and password:
                import base64
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers['Authorization'] = f'Basic {credentials}'
        
        return headers
    
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Make authenticated HTTP request"""
        # Add auth headers
        auth_headers = await self._add_auth_headers(headers or {})
        
        return await super().request(
            method, path, data, params, auth_headers, timeout
        )


class RetryableHTTPTransport(HTTPTransport):
    """HTTP transport with automatic retry"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 1)
        self.retry_backoff = config.get('retry_backoff', 2)
        self.retry_on = config.get('retry_on', [500, 502, 503, 504])
    
    async def request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic"""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await super().request(
                    method, path, data, params, headers, timeout
                )
            
            except TransportRequestError as e:
                last_error = e
                
                # Check if we should retry
                if attempt < self.max_retries and e.status_code in self.retry_on:
                    delay = self.retry_delay * (self.retry_backoff ** attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                
                # Don't retry on client errors or final attempt
                break
            
            except TransportError as e:
                last_error = e
                
                # Retry on connection errors
                if attempt < self.max_retries:
                    delay = self.retry_delay * (self.retry_backoff ** attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                
                break
        
        # All retries failed
        raise last_error
