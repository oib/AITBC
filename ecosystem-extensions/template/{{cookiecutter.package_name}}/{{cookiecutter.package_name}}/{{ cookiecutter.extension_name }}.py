"""
{{ cookiecutter.extension_display_name }} Connector

{{ cookiecutter.extension_description }}
"""

{% if cookiecutter.use_asyncio %}
import asyncio
from typing import Dict, Any, Optional, List
{% else %}
from typing import Dict, Any, Optional, List
{% endif %}

from aitbc_enterprise.base import BaseConnector
from aitbc_enterprise.core import AITBCClient, ConnectorConfig
from aitbc_enterprise.exceptions import ConnectorError

{% if cookiecutter.extension_type == "payment" %}
from aitbc_enterprise.payments.base import PaymentConnector, Charge, Refund, PaymentMethod
{% elif cookiecutter.extension_type == "erp" %}
from aitbc_enterprise.erp.base import ERPConnector, ERPDataModel, SyncResult
{% endif %}


class {{ cookiecutter.class_name }}({% if cookiecutter.extension_type == "payment" %}PaymentConnector{% elif cookiecutter.extension_type == "erp" %}ERPConnector{% else %}BaseConnector{% endif %}):
    """
    {{ cookiecutter.extension_display_name }} connector for AITBC
    
    This connector provides integration with {{ cookiecutter.extension_name }}.
    """
    
    def __init__(self, client: AITBCClient, config: ConnectorConfig):
        """
        Initialize the {{ cookiecutter.extension_name }} connector
        
        Args:
            client: AITBC client instance
            config: Connector configuration
        """
        super().__init__(client, config)
        
        # Initialize your service client here
        # Example:
        # self.service_client = ServiceClient(
        #     api_key=config.settings.get("api_key"),
        #     base_url=config.settings.get("base_url")
        # )
        
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    {% if cookiecutter.use_asyncio %}
    async def initialize(self):
        """
        Initialize the connector and establish connections
        """
        await super().initialize()
        
        # Initialize your service connection here
        # Example:
        # await self.service_client.authenticate()
        
        self.logger.info("{{ cookiecutter.class_name }} initialized successfully")
    
    async def cleanup(self):
        """
        Cleanup resources and close connections
        """
        # Cleanup your service connection here
        # Example:
        # await self.service_client.close()
        
        await super().cleanup()
        
        self.logger.info("{{ cookiecutter.class_name }} cleaned up successfully")
    {% endif %}
    
    {% if cookiecutter.extension_type == "payment" %}
    {% if cookiecutter.use_asyncio %}
    async def create_charge(
        self,
        amount: int,
        currency: str,
        source: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Charge:
        """
        Create a payment charge
        
        Args:
            amount: Amount in smallest currency unit
            currency: Currency code (e.g., 'USD')
            source: Payment source identifier
            description: Optional description
            metadata: Optional metadata
            
        Returns:
            Charge object representing the payment
        """
        try:
            # Implement charge creation logic here
            # Example:
            # charge_data = await self.service_client.create_charge({
            #     "amount": amount,
            #     "currency": currency,
            #     "source": source,
            #     "description": description,
            #     "metadata": metadata or {}
            # })
            
            # Convert to AITBC Charge format
            charge = Charge(
                id="charge_123",  # From service response
                amount=amount,
                currency=currency,
                status="pending",  # From service response
                created_at=__import__('datetime').datetime.utcnow(),
                metadata=metadata or {}
            )
            
            # Log the operation
            await self._log_operation("create_charge", {
                "amount": amount,
                "currency": currency,
                "charge_id": charge.id
            })
            
            return charge
            
        except Exception as e:
            self.logger.error(f"Failed to create charge: {e}")
            raise ConnectorError(f"Charge creation failed: {e}")
    
    async def refund_charge(
        self,
        charge_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Refund:
        """
        Refund a charge
        
        Args:
            charge_id: ID of charge to refund
            amount: Optional amount to refund (full if None)
            reason: Optional refund reason
            
        Returns:
            Refund object
        """
        # Implement refund logic here
        pass
    
    async def get_charge(self, charge_id: str) -> Charge:
        """
        Get charge details
        
        Args:
            charge_id: Charge ID
            
        Returns:
            Charge object
        """
        # Implement charge retrieval here
        pass
    {% else %}
    def create_charge(
        self,
        amount: int,
        currency: str,
        source: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Charge:
        """
        Create a payment charge (synchronous version)
        """
        # Synchronous implementation
        pass
    {% endif %}
    
    {% elif cookiecutter.extension_type == "erp" %}
    {% if cookiecutter.use_asyncio %}
    async def sync_data(
        self,
        data_type: str,
        start_date: Optional[__import__('datetime').datetime] = None,
        end_date: Optional[__import__('datetime').datetime] = None
    ) -> SyncResult:
        """
        Sync data from ERP system
        
        Args:
            data_type: Type of data to sync (e.g., 'customers', 'orders')
            start_date: Optional start date for sync
            end_date: Optional end date for sync
            
        Returns:
            SyncResult with sync statistics
        """
        try:
            # Implement sync logic here
            # Example:
            # data = await self.service_client.get_data(
            #     data_type=data_type,
            #     start_date=start_date,
            #     end_date=end_date
            # )
            
            # Process and transform data
            # processed_data = self._transform_data(data)
            
            # Store in AITBC
            # await self._store_data(processed_data)
            
            result = SyncResult(
                records_processed=100,  # From actual sync
                records_created=80,
                records_updated=20,
                errors=[],
                sync_time=__import__('datetime').datetime.utcnow()
            )
            
            # Log the operation
            await self._log_operation("sync_data", {
                "data_type": data_type,
                "records_processed": result.records_processed
            })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to sync {data_type}: {e}")
            raise ConnectorError(f"Data sync failed: {e}")
    
    async def get_data_model(self, data_type: str) -> ERPDataModel:
        """
        Get data model for ERP data type
        
        Args:
            data_type: Type of data
            
        Returns:
            ERPDataModel definition
        """
        # Implement data model retrieval here
        pass
    {% else %}
    def sync_data(
        self,
        data_type: str,
        start_date: Optional[__import__('datetime').datetime] = None,
        end_date: Optional[__import__('datetime').datetime] = None
    ) -> SyncResult:
        """
        Sync data from ERP system (synchronous version)
        """
        # Synchronous implementation
        pass
    {% endif %}
    
    {% else %}
    {% if cookiecutter.use_asyncio %}
    async def execute_operation(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a custom operation
        
        Args:
            operation: Operation name
            parameters: Optional parameters
            
        Returns:
            Operation result
        """
        try:
            # Implement your custom operation here
            result = {
                "operation": operation,
                "parameters": parameters,
                "result": "success",
                "timestamp": __import__('datetime').datetime.utcnow().isoformat()
            }
            
            # Log the operation
            await self._log_operation("execute_operation", {
                "operation": operation,
                "parameters": parameters
            })
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to execute {operation}: {e}")
            raise ConnectorError(f"Operation failed: {e}")
    {% else %}
    def execute_operation(
        self,
        operation: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a custom operation (synchronous version)
        """
        # Synchronous implementation
        pass
    {% endif %}
    {% endif %}
    
    # Helper methods
    
    def _transform_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform data from external format to AITBC format
        
        Args:
            data: Raw data from external service
            
        Returns:
            Transformed data
        """
        # Implement data transformation logic here
        return data
    
    {% if cookiecutter.use_asyncio %}
    async def _store_data(self, data: List[Dict[str, Any]]) -> bool:
        """
        Store data in AITBC
        
        Args:
            data: Data to store
            
        Returns:
            True if successful
        """
        # Implement data storage logic here
        return True
    {% else %}
    def _store_data(self, data: List[Dict[str, Any]]) -> bool:
        """
        Store data in AITBC (synchronous version)
        """
        # Synchronous implementation
        return True
    {% endif %}
    
    def validate_config(self) -> bool:
        """
        Validate connector configuration
        
        Returns:
            True if configuration is valid
        """
        required_settings = []
        
        {% if cookiecutter.extension_type == "payment" %}
        required_settings = ["api_key", "webhook_secret"]
        {% elif cookiecutter.extension_type == "erp" %}
        required_settings = ["host", "username", "password", "database"]
        {% endif %}
        
        for setting in required_settings:
            if setting not in self.config.settings:
                raise ConnectorError(f"Missing required setting: {setting}")
        
        return True
