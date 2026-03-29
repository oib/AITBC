"""
Enterprise Client SDK - Phase 6.1 Implementation
Python SDK for enterprise clients to integrate with AITBC platform
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4
from dataclasses import dataclass, field
from enum import Enum
import jwt
import hashlib
import secrets
from pydantic import BaseModel, Field, validator
import logging
logger = logging.getLogger(__name__)



class SDKVersion(str, Enum):
    """SDK version"""
    V1_0 = "1.0.0"
    CURRENT = V1_0

class AuthenticationMethod(str, Enum):
    """Authentication methods"""
    CLIENT_CREDENTIALS = "client_credentials"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"

class IntegrationType(str, Enum):
    """Integration types"""
    ERP = "erp"
    CRM = "crm"
    BI = "bi"
    CUSTOM = "custom"

@dataclass
class EnterpriseConfig:
    """Enterprise SDK configuration"""
    tenant_id: str
    client_id: str
    client_secret: str
    base_url: str = "https://api.aitbc.dev/enterprise"
    api_version: str = "v1"
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0
    auth_method: AuthenticationMethod = AuthenticationMethod.CLIENT_CREDENTIALS
    
class AuthenticationResponse(BaseModel):
    """Authentication response"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scopes: List[str]
    tenant_info: Dict[str, Any]

class APIResponse(BaseModel):
    """API response wrapper"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class IntegrationConfig(BaseModel):
    """Integration configuration"""
    integration_type: IntegrationType
    provider: str
    configuration: Dict[str, Any]
    webhook_url: Optional[str] = None
    webhook_events: Optional[List[str]] = None

class EnterpriseClient:
    """Main enterprise client SDK"""
    
    def __init__(self, config: EnterpriseConfig):
        self.config = config
        self.session = None
        self.access_token = None
        self.token_expires_at = None
        self.refresh_token = None
        self.logger = get_logger(f"enterprise.{config.tenant_id}")
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def initialize(self):
        """Initialize the SDK client"""
        
        try:
            # Create HTTP session
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                headers={
                    "User-Agent": f"AITBC-Enterprise-SDK/{SDKVersion.CURRENT.value}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
            
            # Authenticate
            await self.authenticate()
            
            self.logger.info(f"Enterprise SDK initialized for tenant {self.config.tenant_id}")
            
        except Exception as e:
            self.logger.error(f"SDK initialization failed: {e}")
            raise
    
    async def authenticate(self) -> AuthenticationResponse:
        """Authenticate with the enterprise API"""
        
        try:
            if self.config.auth_method == AuthenticationMethod.CLIENT_CREDENTIALS:
                return await self._client_credentials_auth()
            else:
                raise ValueError(f"Unsupported auth method: {self.config.auth_method}")
                
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            raise
    
    async def _client_credentials_auth(self) -> AuthenticationResponse:
        """Client credentials authentication"""
        
        url = f"{self.config.base_url}/auth"
        
        data = {
            "tenant_id": self.config.tenant_id,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "auth_method": "client_credentials"
        }
        
        async with self.session.post(url, json=data) as response:
            if response.status == 200:
                auth_data = await response.json()
                
                # Store tokens
                self.access_token = auth_data["access_token"]
                self.refresh_token = auth_data.get("refresh_token")
                self.token_expires_at = datetime.utcnow() + timedelta(seconds=auth_data["expires_in"])
                
                # Update session headers
                self.session.headers["Authorization"] = f"Bearer {self.access_token}"
                
                return AuthenticationResponse(**auth_data)
            else:
                error_text = await response.text()
                raise Exception(f"Authentication failed: {response.status} - {error_text}")
    
    async def _ensure_valid_token(self):
        """Ensure we have a valid access token"""
        
        if not self.access_token or (self.token_expires_at and datetime.utcnow() >= self.token_expires_at):
            await self.authenticate()
    
    async def create_integration(self, integration_config: IntegrationConfig) -> APIResponse:
        """Create enterprise integration"""
        
        await self._ensure_valid_token()
        
        try:
            url = f"{self.config.base_url}/integrations"
            
            data = {
                "integration_type": integration_config.integration_type.value,
                "provider": integration_config.provider,
                "configuration": integration_config.configuration
            }
            
            if integration_config.webhook_url:
                data["webhook_config"] = {
                    "url": integration_config.webhook_url,
                    "events": integration_config.webhook_events or [],
                    "active": True
                }
            
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return APIResponse(success=True, data=result)
                else:
                    error_text = await response.text()
                    return APIResponse(
                        success=False,
                        error=f"Integration creation failed: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to create integration: {e}")
            return APIResponse(success=False, error=str(e))
    
    async def get_integration_status(self, integration_id: str) -> APIResponse:
        """Get integration status"""
        
        await self._ensure_valid_token()
        
        try:
            url = f"{self.config.base_url}/integrations/{integration_id}/status"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    result = await response.json()
                    return APIResponse(success=True, data=result)
                else:
                    error_text = await response.text()
                    return APIResponse(
                        success=False,
                        error=f"Failed to get integration status: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to get integration status: {e}")
            return APIResponse(success=False, error=str(e))
    
    async def test_integration(self, integration_id: str) -> APIResponse:
        """Test integration connection"""
        
        await self._ensure_valid_token()
        
        try:
            url = f"{self.config.base_url}/integrations/{integration_id}/test"
            
            async with self.session.post(url) as response:
                if response.status == 200:
                    result = await response.json()
                    return APIResponse(success=True, data=result)
                else:
                    error_text = await response.text()
                    return APIResponse(
                        success=False,
                        error=f"Integration test failed: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to test integration: {e}")
            return APIResponse(success=False, error=str(e))
    
    async def sync_data(self, integration_id: str, data_type: str, 
                       filters: Optional[Dict] = None) -> APIResponse:
        """Sync data from integration"""
        
        await self._ensure_valid_token()
        
        try:
            url = f"{self.config.base_url}/integrations/{integration_id}/sync"
            
            data = {
                "operation": "sync_data",
                "parameters": {
                    "data_type": data_type,
                    "filters": filters or {}
                }
            }
            
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return APIResponse(success=True, data=result)
                else:
                    error_text = await response.text()
                    return APIResponse(
                        success=False,
                        error=f"Data sync failed: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to sync data: {e}")
            return APIResponse(success=False, error=str(e))
    
    async def push_data(self, integration_id: str, data_type: str, 
                       data: Dict[str, Any]) -> APIResponse:
        """Push data to integration"""
        
        await self._ensure_valid_token()
        
        try:
            url = f"{self.config.base_url}/integrations/{integration_id}/push"
            
            request_data = {
                "operation": "push_data",
                "data": data,
                "parameters": {
                    "data_type": data_type
                }
            }
            
            async with self.session.post(url, json=request_data) as response:
                if response.status == 200:
                    result = await response.json()
                    return APIResponse(success=True, data=result)
                else:
                    error_text = await response.text()
                    return APIResponse(
                        success=False,
                        error=f"Data push failed: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to push data: {e}")
            return APIResponse(success=False, error=str(e))
    
    async def get_analytics(self) -> APIResponse:
        """Get enterprise analytics"""
        
        await self._ensure_valid_token()
        
        try:
            url = f"{self.config.base_url}/analytics"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    result = await response.json()
                    return APIResponse(success=True, data=result)
                else:
                    error_text = await response.text()
                    return APIResponse(
                        success=False,
                        error=f"Failed to get analytics: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to get analytics: {e}")
            return APIResponse(success=False, error=str(e))
    
    async def get_quota_status(self) -> APIResponse:
        """Get quota status"""
        
        await self._ensure_valid_token()
        
        try:
            url = f"{self.config.base_url}/quota/status"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    result = await response.json()
                    return APIResponse(success=True, data=result)
                else:
                    error_text = await response.text()
                    return APIResponse(
                        success=False,
                        error=f"Failed to get quota status: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Failed to get quota status: {e}")
            return APIResponse(success=False, error=str(e))
    
    async def close(self):
        """Close the SDK client"""
        
        if self.session:
            await self.session.close()
            self.logger.info(f"Enterprise SDK closed for tenant {self.config.tenant_id}")

class ERPIntegration:
    """ERP integration helper class"""
    
    def __init__(self, client: EnterpriseClient):
        self.client = client
        
    async def sync_customers(self, integration_id: str, 
                           filters: Optional[Dict] = None) -> APIResponse:
        """Sync customers from ERP"""
        return await self.client.sync_data(integration_id, "customers", filters)
    
    async def sync_orders(self, integration_id: str, 
                         filters: Optional[Dict] = None) -> APIResponse:
        """Sync orders from ERP"""
        return await self.client.sync_data(integration_id, "orders", filters)
    
    async def sync_products(self, integration_id: str, 
                           filters: Optional[Dict] = None) -> APIResponse:
        """Sync products from ERP"""
        return await self.client.sync_data(integration_id, "products", filters)
    
    async def create_customer(self, integration_id: str, 
                            customer_data: Dict[str, Any]) -> APIResponse:
        """Create customer in ERP"""
        return await self.client.push_data(integration_id, "customers", customer_data)
    
    async def create_order(self, integration_id: str, 
                          order_data: Dict[str, Any]) -> APIResponse:
        """Create order in ERP"""
        return await self.client.push_data(integration_id, "orders", order_data)

class CRMIntegration:
    """CRM integration helper class"""
    
    def __init__(self, client: EnterpriseClient):
        self.client = client
        
    async def sync_contacts(self, integration_id: str, 
                           filters: Optional[Dict] = None) -> APIResponse:
        """Sync contacts from CRM"""
        return await self.client.sync_data(integration_id, "contacts", filters)
    
    async def sync_opportunities(self, integration_id: str, 
                                filters: Optional[Dict] = None) -> APIResponse:
        """Sync opportunities from CRM"""
        return await self.client.sync_data(integration_id, "opportunities", filters)
    
    async def create_lead(self, integration_id: str, 
                         lead_data: Dict[str, Any]) -> APIResponse:
        """Create lead in CRM"""
        return await self.client.push_data(integration_id, "leads", lead_data)
    
    async def update_contact(self, integration_id: str, 
                            contact_id: str, 
                            contact_data: Dict[str, Any]) -> APIResponse:
        """Update contact in CRM"""
        return await self.client.push_data(integration_id, "contacts", {
            "contact_id": contact_id,
            "data": contact_data
        })

class WebhookHandler:
    """Webhook handler for enterprise integrations"""
    
    def __init__(self, secret: Optional[str] = None):
        self.secret = secret
        self.handlers = {}
        
    def register_handler(self, event_type: str, handler_func):
        """Register webhook event handler"""
        self.handlers[event_type] = handler_func
        
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature"""
        if not self.secret:
            return True
        
        expected_signature = hashlib.hmac_sha256(
            self.secret.encode(),
            payload.encode()
        ).hexdigest()
        
        return secrets.compare_digest(expected_signature, signature)
    
    async def handle_webhook(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle webhook event"""
        
        handler = self.handlers.get(event_type)
        if handler:
            try:
                result = await handler(payload)
                return {"status": "success", "result": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        else:
            return {"status": "error", "error": f"No handler for event type: {event_type}"}

# Convenience functions for common operations
async def create_sap_integration(enterprise_client: EnterpriseClient, 
                               system_id: str, sap_client: str, 
                               username: str, password: str,
                               host: str, port: int = 8000) -> APIResponse:
    """Create SAP ERP integration"""
    
    config = IntegrationConfig(
        integration_type=IntegrationType.ERP,
        provider="sap",
        configuration={
            "system_id": system_id,
            "client": sap_client,
            "username": username,
            "password": password,
            "host": host,
            "port": port,
            "endpoint_url": f"http://{host}:{port}/sap"
        }
    )
    
    return await enterprise_client.create_integration(config)

async def create_salesforce_integration(enterprise_client: EnterpriseClient,
                                      client_id: str, client_secret: str,
                                      username: str, password: str,
                                      security_token: str) -> APIResponse:
    """Create Salesforce CRM integration"""
    
    config = IntegrationConfig(
        integration_type=IntegrationType.CRM,
        provider="salesforce",
        configuration={
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": password,
            "security_token": security_token,
            "endpoint_url": "https://login.salesforce.com"
        }
    )
    
    return await enterprise_client.create_integration(config)

# Example usage
async def example_usage():
    """Example usage of the Enterprise SDK"""
    
    # Configure SDK
    config = EnterpriseConfig(
        tenant_id="enterprise_tenant_123",
        client_id="enterprise_client_456",
        client_secret="enterprise_secret_789"
    )
    
    # Use SDK with context manager
    async with EnterpriseClient(config) as client:
        # Create SAP integration
        sap_result = await create_sap_integration(
            client, "DEV", "100", "sap_user", "sap_pass", "sap.example.com"
        )
        
        if sap_result.success:
            integration_id = sap_result.data["integration_id"]
            
            # Test integration
            test_result = await client.test_integration(integration_id)
            if test_result.success:
                print("SAP integration test passed")
                
                # Sync customers
                erp = ERPIntegration(client)
                customers_result = await erp.sync_customers(integration_id)
                
                if customers_result.success:
                    customers = customers_result.data["data"]["customers"]
                    print(f"Synced {len(customers)} customers")
        
        # Get analytics
        analytics = await client.get_analytics()
        if analytics.success:
            print(f"API calls: {analytics.data['api_calls_total']}")

# Export main classes
__all__ = [
    "EnterpriseClient",
    "EnterpriseConfig",
    "ERPIntegration", 
    "CRMIntegration",
    "WebhookHandler",
    "create_sap_integration",
    "create_salesforce_integration",
    "example_usage"
]
