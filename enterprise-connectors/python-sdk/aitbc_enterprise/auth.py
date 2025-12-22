"""
Authentication handlers for AITBC Enterprise Connectors
"""

import base64
import hashlib
import hmac
import json
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from .core import ConnectorConfig
from .exceptions import AuthenticationError


class AuthHandler(ABC):
    """Abstract base class for authentication handlers"""
    
    @abstractmethod
    async def get_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        pass


class BearerAuthHandler(AuthHandler):
    """Bearer token authentication"""
    
    def __init__(self, config: ConnectorConfig):
        self.api_key = config.api_key
    
    async def get_headers(self) -> Dict[str, str]:
        """Get Bearer token headers"""
        return {
            "Authorization": f"Bearer {self.api_key}"
        }


class BasicAuthHandler(AuthHandler):
    """Basic authentication"""
    
    def __init__(self, config: ConnectorConfig):
        self.username = config.auth_config.get("username")
        self.password = config.auth_config.get("password")
    
    async def get_headers(self) -> Dict[str, str]:
        """Get Basic auth headers"""
        if not self.username or not self.password:
            raise AuthenticationError("Username and password required for Basic auth")
        
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        
        return {
            "Authorization": f"Basic {encoded}"
        }


class APIKeyAuthHandler(AuthHandler):
    """API key authentication (custom header)"""
    
    def __init__(self, config: ConnectorConfig):
        self.api_key = config.api_key
        self.header_name = config.auth_config.get("header_name", "X-API-Key")
    
    async def get_headers(self) -> Dict[str, str]:
        """Get API key headers"""
        return {
            self.header_name: self.api_key
        }


class HMACAuthHandler(AuthHandler):
    """HMAC signature authentication"""
    
    def __init__(self, config: ConnectorConfig):
        self.api_key = config.api_key
        self.secret = config.auth_config.get("secret")
        self.algorithm = config.auth_config.get("algorithm", "sha256")
    
    async def get_headers(self) -> Dict[str, str]:
        """Get HMAC signature headers"""
        if not self.secret:
            raise AuthenticationError("Secret required for HMAC auth")
        
        timestamp = str(int(time.time()))
        message = f"{timestamp}:{self.api_key}"
        
        signature = hmac.new(
            self.secret.encode(),
            message.encode(),
            getattr(hashlib, self.algorithm)
        ).hexdigest()
        
        return {
            "X-API-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature
        }


class OAuth2Handler(AuthHandler):
    """OAuth 2.0 authentication"""
    
    def __init__(self, config: ConnectorConfig):
        self.client_id = config.auth_config.get("client_id")
        self.client_secret = config.auth_config.get("client_secret")
        self.token_url = config.auth_config.get("token_url")
        self.scope = config.auth_config.get("scope", "")
        
        self._access_token = None
        self._refresh_token = None
        self._expires_at = None
    
    async def get_headers(self) -> Dict[str, str]:
        """Get OAuth 2.0 headers"""
        if not self._is_token_valid():
            await self._refresh_access_token()
        
        return {
            "Authorization": f"Bearer {self._access_token}"
        }
    
    def _is_token_valid(self) -> bool:
        """Check if access token is valid"""
        if not self._access_token or not self._expires_at:
            return False
        
        # Refresh 5 minutes before expiry
        return datetime.utcnow() < (self._expires_at - timedelta(minutes=5))
    
    async def _refresh_access_token(self):
        """Refresh OAuth 2.0 access token"""
        import aiohttp
        
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, data=data) as response:
                if response.status != 200:
                    raise AuthenticationError(f"OAuth token request failed: {response.status}")
                
                token_data = await response.json()
                
                self._access_token = token_data["access_token"]
                self._refresh_token = token_data.get("refresh_token")
                
                expires_in = token_data.get("expires_in", 3600)
                self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in)


class CertificateAuthHandler(AuthHandler):
    """Certificate-based authentication"""
    
    def __init__(self, config: ConnectorConfig):
        self.cert_path = config.auth_config.get("cert_path")
        self.key_path = config.auth_config.get("key_path")
        self.passphrase = config.auth_config.get("passphrase")
    
    async def get_headers(self) -> Dict[str, str]:
        """Certificate auth uses client cert, not headers"""
        return {}
    
    def get_ssl_context(self):
        """Get SSL context for certificate authentication"""
        import ssl
        
        context = ssl.create_default_context()
        
        if self.cert_path and self.key_path:
            context.load_cert_chain(
                self.cert_path,
                self.key_path,
                password=self.passphrase
            )
        
        return context


class AuthHandlerFactory:
    """Factory for creating authentication handlers"""
    
    @staticmethod
    def create(config: ConnectorConfig) -> AuthHandler:
        """Create appropriate auth handler based on config"""
        auth_type = config.auth_type.lower()
        
        if auth_type == "bearer":
            return BearerAuthHandler(config)
        elif auth_type == "basic":
            return BasicAuthHandler(config)
        elif auth_type == "api_key":
            return APIKeyAuthHandler(config)
        elif auth_type == "hmac":
            return HMACAuthHandler(config)
        elif auth_type == "oauth2":
            return OAuth2Handler(config)
        elif auth_type == "certificate":
            return CertificateAuthHandler(config)
        else:
            raise AuthenticationError(f"Unsupported auth type: {auth_type}")
