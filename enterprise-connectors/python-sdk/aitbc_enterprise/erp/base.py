"""
Base classes for ERP connectors with plugin architecture
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type, Union, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import importlib

from ..base import BaseConnector, OperationResult
from ..core import ConnectorConfig
from ..exceptions import ERPError, ValidationError


class ERPSystem(Enum):
    """Supported ERP systems"""
    SAP = "sap"
    ORACLE = "oracle"
    NETSUITE = "netsuite"
    MICROSOFT_DYNAMICS = "dynamics"
    SALESFORCE = "salesforce"


class Protocol(Enum):
    """Supported protocols"""
    REST = "rest"
    SOAP = "soap"
    ODATA = "odata"
    IDOC = "idoc"
    BAPI = "bapi"
    SUITE_TALK = "suite_talk"


@dataclass
class ERPDataModel:
    """ERP data model definition"""
    entity_type: str
    fields: Dict[str, Any]
    relationships: Dict[str, str] = field(default_factory=dict)
    validations: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "fields": self.fields,
            "relationships": self.relationships,
            "validations": self.validations
        }


@dataclass
class SyncResult:
    """Synchronization result"""
    entity_type: str
    synced_count: int
    failed_count: int
    errors: List[str] = field(default_factory=list)
    last_sync: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "synced_count": self.synced_count,
            "failed_count": self.failed_count,
            "errors": self.errors,
            "last_sync": self.last_sync.isoformat()
        }


class ProtocolHandler(ABC):
    """Abstract base class for protocol handlers"""
    
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish protocol connection"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Close protocol connection"""
        pass
    
    @abstractmethod
    async def send_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send request via protocol"""
        pass
    
    @abstractmethod
    async def batch_request(self, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Send batch requests"""
        pass


class DataMapper:
    """Maps data between AITBC and ERP formats"""
    
    def __init__(self, mappings: Dict[str, Dict[str, str]]):
        self.mappings = mappings
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    def to_erp(self, entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Map AITBC format to ERP format"""
        if entity_type not in self.mappings:
            raise ValidationError(f"No mapping for entity type: {entity_type}")
        
        mapping = self.mappings[entity_type]
        erp_data = {}
        
        for aitbc_field, erp_field in mapping.items():
            if aitbc_field in data:
                erp_data[erp_field] = data[aitbc_field]
        
        return erp_data
    
    def from_erp(self, entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Map ERP format to AITBC format"""
        if entity_type not in self.mappings:
            raise ValidationError(f"No mapping for entity type: {entity_type}")
        
        mapping = self.mappings[entity_type]
        aitbc_data = {}
        
        # Reverse mapping
        reverse_mapping = {v: k for k, v in mapping.items()}
        
        for erp_field, value in data.items():
            if erp_field in reverse_mapping:
                aitbc_data[reverse_mapping[erp_field]] = value
        
        return aitbc_data


class BatchProcessor:
    """Handles batch operations for ERP connectors"""
    
    def __init__(self, batch_size: int = 100, max_concurrent: int = 5):
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.logger = __import__('logging').getLogger(f"aitbc.{self.__class__.__name__}")
    
    async def process_batches(
        self,
        items: List[Dict[str, Any]],
        processor: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Process items in batches"""
        results = []
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def process_batch(batch):
            async with semaphore:
                try:
                    return await processor(batch)
                except Exception as e:
                    self.logger.error(f"Batch processing failed: {e}")
                    return [{"error": str(e)} for _ in batch]
        
        # Create batches
        batches = [
            items[i:i + self.batch_size]
            for i in range(0, len(items), self.batch_size)
        ]
        
        # Process batches concurrently
        tasks = [process_batch(batch) for batch in batches]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results
        for result in batch_results:
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append({"error": str(result)})
        
        return results


class ChangeTracker:
    """Tracks changes for delta synchronization"""
    
    def __init__(self):
        self.last_syncs: Dict[str, datetime] = {}
        self.change_logs: Dict[str, List[Dict[str, Any]]] = {}
    
    def update_last_sync(self, entity_type: str, timestamp: datetime):
        """Update last sync timestamp"""
        self.last_syncs[entity_type] = timestamp
    
    def get_last_sync(self, entity_type: str) -> Optional[datetime]:
        """Get last sync timestamp"""
        return self.last_syncs.get(entity_type)
    
    def log_change(self, entity_type: str, change: Dict[str, Any]):
        """Log a change"""
        if entity_type not in self.change_logs:
            self.change_logs[entity_type] = []
        
        self.change_logs[entity_type].append({
            **change,
            "timestamp": datetime.utcnow()
        })
    
    def get_changes_since(
        self,
        entity_type: str,
        since: datetime
    ) -> List[Dict[str, Any]]:
        """Get changes since timestamp"""
        changes = self.change_logs.get(entity_type, [])
        return [
            c for c in changes
            if c["timestamp"] > since
        ]


class ERPConnector(BaseConnector):
    """Base class for ERP connectors with plugin architecture"""
    
    # Registry for protocol handlers
    _protocol_registry: Dict[Protocol, Type[ProtocolHandler]] = {}
    
    def __init__(
        self,
        client: 'AITBCClient',
        config: ConnectorConfig,
        erp_system: ERPSystem,
        protocol: Protocol,
        data_mapper: Optional[DataMapper] = None
    ):
        super().__init__(client, config)
        
        self.erp_system = erp_system
        self.protocol = protocol
        
        # Initialize components
        self.protocol_handler = self._create_protocol_handler()
        self.data_mapper = data_mapper or DataMapper({})
        self.batch_processor = BatchProcessor()
        self.change_tracker = ChangeTracker()
        
        # ERP-specific configuration
        self.erp_config = config.auth_config.get("erp", {})
        
        # Data models
        self.data_models: Dict[str, ERPDataModel] = {}
    
    @classmethod
    def register_protocol(
        cls,
        protocol: Protocol,
        handler_class: Type[ProtocolHandler]
    ):
        """Register a protocol handler"""
        cls._protocol_registry[protocol] = handler_class
    
    def _create_protocol_handler(self) -> ProtocolHandler:
        """Create protocol handler from registry"""
        if self.protocol not in self._protocol_registry:
            raise ERPError(f"No handler registered for protocol: {self.protocol}")
        
        handler_class = self._protocol_registry[self.protocol]
        return handler_class(self.config)
    
    async def _initialize(self) -> None:
        """Initialize ERP connector"""
        # Connect via protocol
        if not await self.protocol_handler.connect():
            raise ERPError(f"Failed to connect via {self.protocol}")
        
        # Load data models
        await self._load_data_models()
        
        self.logger.info(f"{self.erp_system.value} connector initialized")
    
    async def _cleanup(self) -> None:
        """Cleanup ERP connector"""
        await self.protocol_handler.disconnect()
    
    async def _execute_operation(
        self,
        operation: str,
        data: Dict[str, Any],
        **kwargs
    ) -> OperationResult:
        """Execute ERP-specific operations"""
        try:
            if operation.startswith("create_"):
                entity_type = operation[7:]  # Remove "create_" prefix
                return await self._create_entity(entity_type, data)
            elif operation.startswith("update_"):
                entity_type = operation[7:]  # Remove "update_" prefix
                return await self._update_entity(entity_type, data)
            elif operation.startswith("delete_"):
                entity_type = operation[7:]  # Remove "delete_" prefix
                return await self._delete_entity(entity_type, data)
            elif operation == "sync":
                return await self._sync_data(data)
            elif operation == "batch_sync":
                return await self._batch_sync(data)
            else:
                raise ValidationError(f"Unknown operation: {operation}")
                
        except Exception as e:
            self.logger.error(f"ERP operation failed: {e}")
            raise ERPError(f"Operation failed: {e}")
    
    async def _create_entity(self, entity_type: str, data: Dict[str, Any]) -> OperationResult:
        """Create entity in ERP"""
        # Map data to ERP format
        erp_data = self.data_mapper.to_erp(entity_type, data)
        
        # Send to ERP
        endpoint = f"/{entity_type}"
        result = await self.protocol_handler.send_request(endpoint, erp_data)
        
        # Track change
        self.change_tracker.log_change(entity_type, {
            "action": "create",
            "data": result
        })
        
        return OperationResult(
            success=True,
            data=result,
            metadata={"entity_type": entity_type, "action": "create"}
        )
    
    async def _update_entity(self, entity_type: str, data: Dict[str, Any]) -> OperationResult:
        """Update entity in ERP"""
        entity_id = data.get("id")
        if not entity_id:
            raise ValidationError("Entity ID required for update")
        
        # Map data to ERP format
        erp_data = self.data_mapper.to_erp(entity_type, data)
        
        # Send to ERP
        endpoint = f"/{entity_type}/{entity_id}"
        result = await self.protocol_handler.send_request(endpoint, erp_data, method="PUT")
        
        # Track change
        self.change_tracker.log_change(entity_type, {
            "action": "update",
            "entity_id": entity_id,
            "data": result
        })
        
        return OperationResult(
            success=True,
            data=result,
            metadata={"entity_type": entity_type, "action": "update"}
        )
    
    async def _delete_entity(self, entity_type: str, data: Dict[str, Any]) -> OperationResult:
        """Delete entity from ERP"""
        entity_id = data.get("id")
        if not entity_id:
            raise ValidationError("Entity ID required for delete")
        
        # Send to ERP
        endpoint = f"/{entity_type}/{entity_id}"
        await self.protocol_handler.send_request(endpoint, {}, method="DELETE")
        
        # Track change
        self.change_tracker.log_change(entity_type, {
            "action": "delete",
            "entity_id": entity_id
        })
        
        return OperationResult(
            success=True,
            metadata={"entity_type": entity_type, "action": "delete"}
        )
    
    async def _sync_data(self, data: Dict[str, Any]) -> OperationResult:
        """Synchronize data from ERP"""
        entity_type = data.get("entity_type")
        since = data.get("since")
        
        if not entity_type:
            raise ValidationError("entity_type required")
        
        # Get last sync if not provided
        if not since:
            since = self.change_tracker.get_last_sync(entity_type)
        
        # Query ERP for changes
        endpoint = f"/{entity_type}"
        params = {"since": since.isoformat()} if since else {}
        
        result = await self.protocol_handler.send_request(endpoint, params)
        
        # Map data to AITBC format
        items = result.get("items", [])
        mapped_items = [
            self.data_mapper.from_erp(entity_type, item)
            for item in items
        ]
        
        # Update last sync
        self.change_tracker.update_last_sync(entity_type, datetime.utcnow())
        
        return OperationResult(
            success=True,
            data={"items": mapped_items, "count": len(mapped_items)},
            metadata={"entity_type": entity_type, "since": since}
        )
    
    async def _batch_sync(self, data: Dict[str, Any]) -> OperationResult:
        """Batch synchronize data"""
        entity_type = data.get("entity_type")
        items = data.get("items", [])
        
        if not entity_type or not items:
            raise ValidationError("entity_type and items required")
        
        # Process in batches
        batch_data = [{"entity_type": entity_type, "item": item} for item in items]
        
        results = await self.batch_processor.process_batches(
            batch_data,
            self._process_sync_batch
        )
        
        # Count successes and failures
        successful = sum(1 for r in results if "error" not in r)
        failed = len(results) - successful
        
        return OperationResult(
            success=failed == 0,
            data={"results": results},
            metadata={
                "entity_type": entity_type,
                "total": len(items),
                "successful": successful,
                "failed": failed
            }
        )
    
    async def _process_sync_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process a sync batch"""
        entity_type = batch[0]["entity_type"]
        items = [b["item"] for b in batch]
        
        # Map to ERP format
        erp_items = [
            self.data_mapper.to_erp(entity_type, item)
            for item in items
        ]
        
        # Send batch request
        endpoint = f"/{entity_type}/batch"
        results = await self.protocol_handler.batch_request([
            {"method": "POST", "endpoint": endpoint, "data": item}
            for item in erp_items
        ])
        
        return results
    
    async def _load_data_models(self):
        """Load ERP data models"""
        # Default models - override in subclasses
        self.data_models = {
            "customer": ERPDataModel(
                entity_type="customer",
                fields={"id": str, "name": str, "email": str, "phone": str}
            ),
            "order": ERPDataModel(
                entity_type="order",
                fields={"id": str, "customer_id": str, "items": list, "total": float}
            ),
            "invoice": ERPDataModel(
                entity_type="invoice",
                fields={"id": str, "order_id": str, "amount": float, "status": str}
            )
        }
    
    def register_data_model(self, model: ERPDataModel):
        """Register a data model"""
        self.data_models[model.entity_type] = model
    
    def get_data_model(self, entity_type: str) -> Optional[ERPDataModel]:
        """Get data model by type"""
        return self.data_models.get(entity_type)


# Protocol handler registry decorator
def register_protocol(protocol: Protocol):
    """Decorator to register protocol handlers"""
    def decorator(handler_class: Type[ProtocolHandler]):
        ERPConnector.register_protocol(protocol, handler_class)
        return handler_class
    return decorator
