"""
Enterprise Integration Framework - Phase 6.1 Implementation
ERP, CRM, and business system connectors for enterprise clients
"""

import asyncio
import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import aiohttp
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)



class IntegrationType(str, Enum):
    """Enterprise integration types"""
    ERP = "erp"
    CRM = "crm"
    BI = "bi"
    HR = "hr"
    FINANCE = "finance"
    CUSTOM = "custom"

class IntegrationProvider(str, Enum):
    """Supported integration providers"""
    SAP = "sap"
    ORACLE = "oracle"
    MICROSOFT = "microsoft"
    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"
    TABLEAU = "tableau"
    POWERBI = "powerbi"
    WORKDAY = "workday"

class DataFormat(str, Enum):
    """Data exchange formats"""
    JSON = "json"
    XML = "xml"
    CSV = "csv"
    ODATA = "odata"
    SOAP = "soap"
    REST = "rest"

@dataclass
class IntegrationConfig:
    """Integration configuration"""
    integration_id: str
    tenant_id: str
    integration_type: IntegrationType
    provider: IntegrationProvider
    endpoint_url: str
    authentication: Dict[str, str]
    data_format: DataFormat
    mapping_rules: Dict[str, Any] = field(default_factory=dict)
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    rate_limits: Dict[str, int] = field(default_factory=dict)
    webhook_config: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_sync: Optional[datetime] = None
    status: str = "active"

class IntegrationRequest(BaseModel):
    """Integration request model"""
    integration_id: str = Field(..., description="Integration identifier")
    operation: str = Field(..., description="Operation to perform")
    data: Dict[str, Any] = Field(..., description="Request data")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Additional parameters")

class IntegrationResponse(BaseModel):
    """Integration response model"""
    success: bool = Field(..., description="Operation success status")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")

class ERPIntegration:
    """Base ERP integration class"""
    
    def __init__(self, config: IntegrationConfig):
        self.config = config
        self.session = None
        self.logger = get_logger(f"erp.{config.provider.value}")
        
    async def initialize(self):
        """Initialize ERP connection"""
        raise NotImplementedError
    
    async def test_connection(self) -> bool:
        """Test ERP connection"""
        raise NotImplementedError
    
    async def sync_data(self, data_type: str, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync data from ERP"""
        raise NotImplementedError
    
    async def push_data(self, data_type: str, data: Dict[str, Any]) -> IntegrationResponse:
        """Push data to ERP"""
        raise NotImplementedError
    
    async def close(self):
        """Close ERP connection"""
        if self.session:
            await self.session.close()

class SAPIntegration(ERPIntegration):
    """SAP ERP integration"""
    
    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.system_id = config.authentication.get("system_id")
        self.client = config.authentication.get("client")
        self.username = config.authentication.get("username")
        self.password = config.authentication.get("password")
        self.language = config.authentication.get("language", "EN")
        
    async def initialize(self):
        """Initialize SAP connection"""
        try:
            # Create HTTP session for SAP web services
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                auth=aiohttp.BasicAuth(self.username, self.password)
            )
            
            # Test connection
            if await self.test_connection():
                self.logger.info(f"SAP connection established for {self.config.integration_id}")
                return True
            else:
                raise Exception("SAP connection test failed")
                
        except Exception as e:
            self.logger.error(f"SAP initialization failed: {e}")
            raise
    
    async def test_connection(self) -> bool:
        """Test SAP connection"""
        try:
            # SAP system info endpoint
            url = f"{self.config.endpoint_url}/sap/bc/ping"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    return True
                else:
                    self.logger.error(f"SAP ping failed: {response.status}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"SAP connection test failed: {e}")
            return False
    
    async def sync_data(self, data_type: str, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync data from SAP"""
        
        try:
            if data_type == "customers":
                return await self._sync_customers(filters)
            elif data_type == "orders":
                return await self._sync_orders(filters)
            elif data_type == "products":
                return await self._sync_products(filters)
            else:
                return IntegrationResponse(
                    success=False,
                    error=f"Unsupported data type: {data_type}"
                )
                
        except Exception as e:
            self.logger.error(f"SAP data sync failed: {e}")
            return IntegrationResponse(
                success=False,
                error=str(e)
            )
    
    async def _sync_customers(self, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync customer data from SAP"""
        
        try:
            # SAP BAPI customer list endpoint
            url = f"{self.config.endpoint_url}/sap/bc/sap/rfc/customer_list"
            
            params = {
                "client": self.client,
                "language": self.language
            }
            
            if filters:
                params.update(filters)
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Apply mapping rules
                    mapped_data = self._apply_mapping_rules(data, "customers")
                    
                    return IntegrationResponse(
                        success=True,
                        data=mapped_data,
                        metadata={
                            "records_count": len(mapped_data.get("customers", [])),
                            "sync_time": datetime.utcnow().isoformat()
                        }
                    )
                else:
                    error_text = await response.text()
                    return IntegrationResponse(
                        success=False,
                        error=f"SAP API error: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            return IntegrationResponse(
                success=False,
                error=str(e)
            )
    
    async def _sync_orders(self, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync order data from SAP"""
        
        try:
            # SAP sales order endpoint
            url = f"{self.config.endpoint_url}/sap/bc/sap/rfc/sales_orders"
            
            params = {
                "client": self.client,
                "language": self.language
            }
            
            if filters:
                params.update(filters)
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Apply mapping rules
                    mapped_data = self._apply_mapping_rules(data, "orders")
                    
                    return IntegrationResponse(
                        success=True,
                        data=mapped_data,
                        metadata={
                            "records_count": len(mapped_data.get("orders", [])),
                            "sync_time": datetime.utcnow().isoformat()
                        }
                    )
                else:
                    error_text = await response.text()
                    return IntegrationResponse(
                        success=False,
                        error=f"SAP API error: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            return IntegrationResponse(
                success=False,
                error=str(e)
            )
    
    async def _sync_products(self, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync product data from SAP"""
        
        try:
            # SAP material master endpoint
            url = f"{self.config.endpoint_url}/sap/bc/sap/rfc/material_master"
            
            params = {
                "client": self.client,
                "language": self.language
            }
            
            if filters:
                params.update(filters)
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Apply mapping rules
                    mapped_data = self._apply_mapping_rules(data, "products")
                    
                    return IntegrationResponse(
                        success=True,
                        data=mapped_data,
                        metadata={
                            "records_count": len(mapped_data.get("products", [])),
                            "sync_time": datetime.utcnow().isoformat()
                        }
                    )
                else:
                    error_text = await response.text()
                    return IntegrationResponse(
                        success=False,
                        error=f"SAP API error: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            return IntegrationResponse(
                success=False,
                error=str(e)
            )
    
    def _apply_mapping_rules(self, data: Dict[str, Any], data_type: str) -> Dict[str, Any]:
        """Apply mapping rules to transform data"""
        
        mapping_rules = self.config.mapping_rules.get(data_type, {})
        mapped_data = {}
        
        # Apply field mappings
        for sap_field, aitbc_field in mapping_rules.get("field_mappings", {}).items():
            if sap_field in data:
                mapped_data[aitbc_field] = data[sap_field]
        
        # Apply transformations
        transformations = mapping_rules.get("transformations", {})
        for field, transform in transformations.items():
            if field in mapped_data:
                # Apply transformation logic
                if transform["type"] == "date_format":
                    # Date format transformation
                    mapped_data[field] = self._transform_date(mapped_data[field], transform["format"])
                elif transform["type"] == "numeric":
                    # Numeric transformation
                    mapped_data[field] = self._transform_numeric(mapped_data[field], transform)
        
        return {data_type: mapped_data}
    
    def _transform_date(self, date_value: str, format_str: str) -> str:
        """Transform date format"""
        try:
            # Parse SAP date format and convert to target format
            # SAP typically uses YYYYMMDD format
            if len(date_value) == 8 and date_value.isdigit():
                year = date_value[:4]
                month = date_value[4:6]
                day = date_value[6:8]
                return f"{year}-{month}-{day}"
            return date_value
        except:
            return date_value
    
    def _transform_numeric(self, value: str, transform: Dict[str, Any]) -> Union[str, int, float]:
        """Transform numeric values"""
        try:
            if transform.get("type") == "decimal":
                return float(value) / (10 ** transform.get("scale", 2))
            elif transform.get("type") == "integer":
                return int(float(value))
            return value
        except:
            return value

class OracleIntegration(ERPIntegration):
    """Oracle ERP integration"""
    
    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.service_name = config.authentication.get("service_name")
        self.username = config.authentication.get("username")
        self.password = config.authentication.get("password")
        
    async def initialize(self):
        """Initialize Oracle connection"""
        try:
            # Create HTTP session for Oracle REST APIs
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                auth=aiohttp.BasicAuth(self.username, self.password)
            )
            
            # Test connection
            if await self.test_connection():
                self.logger.info(f"Oracle connection established for {self.config.integration_id}")
                return True
            else:
                raise Exception("Oracle connection test failed")
                
        except Exception as e:
            self.logger.error(f"Oracle initialization failed: {e}")
            raise
    
    async def test_connection(self) -> bool:
        """Test Oracle connection"""
        try:
            # Oracle Fusion Cloud REST API endpoint
            url = f"{self.config.endpoint_url}/fscmRestApi/resources/latest/version"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    return True
                else:
                    self.logger.error(f"Oracle version check failed: {response.status}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Oracle connection test failed: {e}")
            return False
    
    async def sync_data(self, data_type: str, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync data from Oracle"""
        
        try:
            if data_type == "customers":
                return await self._sync_customers(filters)
            elif data_type == "orders":
                return await self._sync_orders(filters)
            elif data_type == "products":
                return await self._sync_products(filters)
            else:
                return IntegrationResponse(
                    success=False,
                    error=f"Unsupported data type: {data_type}"
                )
                
        except Exception as e:
            self.logger.error(f"Oracle data sync failed: {e}")
            return IntegrationResponse(
                success=False,
                error=str(e)
            )
    
    async def _sync_customers(self, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync customer data from Oracle"""
        
        try:
            # Oracle Fusion Cloud Customer endpoint
            url = f"{self.config.endpoint_url}/fscmRestApi/resources/latest/customerAccounts"
            
            params = {}
            if filters:
                params.update(filters)
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Apply mapping rules
                    mapped_data = self._apply_mapping_rules(data, "customers")
                    
                    return IntegrationResponse(
                        success=True,
                        data=mapped_data,
                        metadata={
                            "records_count": len(mapped_data.get("customers", [])),
                            "sync_time": datetime.utcnow().isoformat()
                        }
                    )
                else:
                    error_text = await response.text()
                    return IntegrationResponse(
                        success=False,
                        error=f"Oracle API error: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            return IntegrationResponse(
                success=False,
                error=str(e)
            )
    
    def _apply_mapping_rules(self, data: Dict[str, Any], data_type: str) -> Dict[str, Any]:
        """Apply mapping rules to transform data"""
        
        mapping_rules = self.config.mapping_rules.get(data_type, {})
        mapped_data = {}
        
        # Apply field mappings
        for oracle_field, aitbc_field in mapping_rules.get("field_mappings", {}).items():
            if oracle_field in data:
                mapped_data[aitbc_field] = data[oracle_field]
        
        return {data_type: mapped_data}

class CRMIntegration:
    """Base CRM integration class"""
    
    def __init__(self, config: IntegrationConfig):
        self.config = config
        self.session = None
        self.logger = get_logger(f"crm.{config.provider.value}")
        
    async def initialize(self):
        """Initialize CRM connection"""
        raise NotImplementedError
    
    async def test_connection(self) -> bool:
        """Test CRM connection"""
        raise NotImplementedError
    
    async def sync_contacts(self, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync contacts from CRM"""
        raise NotImplementedError
    
    async def sync_opportunities(self, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync opportunities from CRM"""
        raise NotImplementedError
    
    async def create_lead(self, lead_data: Dict[str, Any]) -> IntegrationResponse:
        """Create lead in CRM"""
        raise NotImplementedError
    
    async def close(self):
        """Close CRM connection"""
        if self.session:
            await self.session.close()

class SalesforceIntegration(CRMIntegration):
    """Salesforce CRM integration"""
    
    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.client_id = config.authentication.get("client_id")
        self.client_secret = config.authentication.get("client_secret")
        self.username = config.authentication.get("username")
        self.password = config.authentication.get("password")
        self.security_token = config.authentication.get("security_token")
        self.access_token = None
        
    async def initialize(self):
        """Initialize Salesforce connection"""
        try:
            # Create HTTP session
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            # Authenticate with Salesforce
            if await self._authenticate():
                self.logger.info(f"Salesforce connection established for {self.config.integration_id}")
                return True
            else:
                raise Exception("Salesforce authentication failed")
                
        except Exception as e:
            self.logger.error(f"Salesforce initialization failed: {e}")
            raise
    
    async def _authenticate(self) -> bool:
        """Authenticate with Salesforce"""
        
        try:
            # Salesforce OAuth2 endpoint
            url = f"{self.config.endpoint_url}/services/oauth2/token"
            
            data = {
                "grant_type": "password",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "username": self.username,
                "password": f"{self.password}{self.security_token}"
            }
            
            async with self.session.post(url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data["access_token"]
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Salesforce authentication failed: {error_text}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Salesforce authentication error: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """Test Salesforce connection"""
        
        try:
            if not self.access_token:
                return False
            
            # Salesforce identity endpoint
            url = f"{self.config.endpoint_url}/services/oauth2/userinfo"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            async with self.session.get(url, headers=headers) as response:
                return response.status == 200
                
        except Exception as e:
            self.logger.error(f"Salesforce connection test failed: {e}")
            return False
    
    async def sync_contacts(self, filters: Optional[Dict] = None) -> IntegrationResponse:
        """Sync contacts from Salesforce"""
        
        try:
            if not self.access_token:
                return IntegrationResponse(
                    success=False,
                    error="Not authenticated"
                )
            
            # Salesforce contacts endpoint
            url = f"{self.config.endpoint_url}/services/data/v52.0/sobjects/Contact"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            params = {}
            if filters:
                params.update(filters)
            
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Apply mapping rules
                    mapped_data = self._apply_mapping_rules(data, "contacts")
                    
                    return IntegrationResponse(
                        success=True,
                        data=mapped_data,
                        metadata={
                            "records_count": len(data.get("records", [])),
                            "sync_time": datetime.utcnow().isoformat()
                        }
                    )
                else:
                    error_text = await response.text()
                    return IntegrationResponse(
                        success=False,
                        error=f"Salesforce API error: {response.status} - {error_text}"
                    )
                    
        except Exception as e:
            self.logger.error(f"Salesforce contacts sync failed: {e}")
            return IntegrationResponse(
                success=False,
                error=str(e)
            )
    
    def _apply_mapping_rules(self, data: Dict[str, Any], data_type: str) -> Dict[str, Any]:
        """Apply mapping rules to transform data"""
        
        mapping_rules = self.config.mapping_rules.get(data_type, {})
        mapped_data = {}
        
        # Apply field mappings
        for salesforce_field, aitbc_field in mapping_rules.get("field_mappings", {}).items():
            if salesforce_field in data:
                mapped_data[aitbc_field] = data[salesforce_field]
        
        return {data_type: mapped_data}

class EnterpriseIntegrationFramework:
    """Enterprise integration framework manager"""
    
    def __init__(self):
        self.integrations = {}  # Active integrations
        self.logger = logger
        
    async def create_integration(self, config: IntegrationConfig) -> bool:
        """Create and initialize enterprise integration"""
        
        try:
            # Create integration instance based on type and provider
            integration = await self._create_integration_instance(config)
            
            # Initialize integration
            await integration.initialize()
            
            # Store integration
            self.integrations[config.integration_id] = integration
            
            self.logger.info(f"Enterprise integration created: {config.integration_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create integration {config.integration_id}: {e}")
            return False
    
    async def _create_integration_instance(self, config: IntegrationConfig):
        """Create integration instance based on configuration"""
        
        if config.integration_type == IntegrationType.ERP:
            if config.provider == IntegrationProvider.SAP:
                return SAPIntegration(config)
            elif config.provider == IntegrationProvider.ORACLE:
                return OracleIntegration(config)
            else:
                raise ValueError(f"Unsupported ERP provider: {config.provider}")
        
        elif config.integration_type == IntegrationType.CRM:
            if config.provider == IntegrationProvider.SALESFORCE:
                return SalesforceIntegration(config)
            else:
                raise ValueError(f"Unsupported CRM provider: {config.provider}")
        
        else:
            raise ValueError(f"Unsupported integration type: {config.integration_type}")
    
    async def execute_integration_request(self, request: IntegrationRequest) -> IntegrationResponse:
        """Execute integration request"""
        
        try:
            integration = self.integrations.get(request.integration_id)
            if not integration:
                return IntegrationResponse(
                    success=False,
                    error=f"Integration not found: {request.integration_id}"
                )
            
            # Execute operation based on integration type
            if isinstance(integration, ERPIntegration):
                if request.operation == "sync_data":
                    data_type = request.parameters.get("data_type", "customers")
                    filters = request.parameters.get("filters")
                    return await integration.sync_data(data_type, filters)
                elif request.operation == "push_data":
                    data_type = request.parameters.get("data_type", "customers")
                    return await integration.push_data(data_type, request.data)
            
            elif isinstance(integration, CRMIntegration):
                if request.operation == "sync_contacts":
                    filters = request.parameters.get("filters")
                    return await integration.sync_contacts(filters)
                elif request.operation == "sync_opportunities":
                    filters = request.parameters.get("filters")
                    return await integration.sync_opportunities(filters)
                elif request.operation == "create_lead":
                    return await integration.create_lead(request.data)
            
            return IntegrationResponse(
                success=False,
                error=f"Unsupported operation: {request.operation}"
            )
            
        except Exception as e:
            self.logger.error(f"Integration request failed: {e}")
            return IntegrationResponse(
                success=False,
                error=str(e)
            )
    
    async def test_integration(self, integration_id: str) -> bool:
        """Test integration connection"""
        
        integration = self.integrations.get(integration_id)
        if not integration:
            return False
        
        return await integration.test_connection()
    
    async def get_integration_status(self, integration_id: str) -> Dict[str, Any]:
        """Get integration status"""
        
        integration = self.integrations.get(integration_id)
        if not integration:
            return {"status": "not_found"}
        
        return {
            "integration_id": integration_id,
            "integration_type": integration.config.integration_type.value,
            "provider": integration.config.provider.value,
            "endpoint_url": integration.config.endpoint_url,
            "status": "active",
            "last_test": datetime.utcnow().isoformat()
        }
    
    async def close_integration(self, integration_id: str):
        """Close integration connection"""
        
        integration = self.integrations.get(integration_id)
        if integration:
            await integration.close()
            del self.integrations[integration_id]
            self.logger.info(f"Integration closed: {integration_id}")
    
    async def close_all_integrations(self):
        """Close all integration connections"""
        
        for integration_id in list(self.integrations.keys()):
            await self.close_integration(integration_id)

# Global integration framework instance
integration_framework = EnterpriseIntegrationFramework()

# CLI Interface Functions
def create_tenant(name: str, domain: str) -> str:
    """Create a new tenant"""
    return api_gateway.create_tenant(name, domain)

def get_tenant_info(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Get tenant information"""
    tenant = api_gateway.get_tenant(tenant_id)
    if tenant:
        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "domain": tenant.domain,
            "status": tenant.status.value,
            "created_at": tenant.created_at.isoformat(),
            "features": tenant.features
        }
    return None

def generate_api_key(tenant_id: str) -> str:
    """Generate API key for tenant"""
    return security_manager.generate_api_key(tenant_id)

def register_integration(tenant_id: str, name: str, integration_type: str, config: Dict[str, Any]) -> str:
    """Register third-party integration"""
    return integration_framework.register_integration(tenant_id, name, IntegrationType(integration_type), config)

def get_system_status() -> Dict[str, Any]:
    """Get enterprise integration system status"""
    return {
        "tenants": len(api_gateway.tenants),
        "endpoints": len(api_gateway.endpoints),
        "integrations": len(api_gateway.integrations),
        "security_events": len(api_gateway.security_events),
        "system_health": "operational"
    }

def list_tenants() -> List[Dict[str, Any]]:
    """List all tenants"""
    return [
        {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "domain": tenant.domain,
            "status": tenant.status.value,
            "features": tenant.features
        }
        for tenant in api_gateway.tenants.values()
    ]

def list_integrations(tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List integrations"""
    integrations = api_gateway.integrations.values()
    if tenant_id:
        integrations = [i for i in integrations if i.tenant_id == tenant_id]

    return [
        {
            "integration_id": i.integration_id,
            "name": i.name,
            "type": i.type.value,
            "tenant_id": i.tenant_id,
            "status": i.status,
            "created_at": i.created_at.isoformat()
        }
        for i in integrations
    ]
