"""
Base connector class for AITBC Enterprise Connectors
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass
import json

from .core import AITBCClient, ConnectorConfig
from .exceptions import AITBCError, ConnectorError, ValidationError
from .webhooks import WebhookHandler
from .validators import BaseValidator


@dataclass
class OperationResult:
    """Result of a connector operation"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class Transaction:
    """Standard transaction representation"""
    id: str
    amount: float
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata or {}
        }


class BaseConnector(ABC):
    """Base class for all enterprise connectors"""
    
    def __init__(
        self,
        client: AITBCClient,
        config: ConnectorConfig,
        validator: Optional[BaseValidator] = None,
        webhook_handler: Optional[WebhookHandler] = None
    ):
        self.client = client
        self.config = config
        self.logger = logging.getLogger(f"aitbc.{self.__class__.__name__}")
        
        # Injected dependencies
        self.validator = validator
        self.webhook_handler = webhook_handler
        
        # Connector state
        self._initialized = False
        self._last_sync = None
        
        # Event handlers
        self._operation_handlers: Dict[str, List[Callable]] = {}
        
        # Metrics
        self._operation_count = 0
        self._error_count = 0
    
    async def initialize(self) -> None:
        """Initialize the connector"""
        if self._initialized:
            return
        
        try:
            # Perform connector-specific initialization
            await self._initialize()
            
            # Set up webhooks if configured
            if self.config.webhook_endpoint and self.webhook_handler:
                await self._setup_webhooks()
            
            # Register event handlers
            self._register_handlers()
            
            self._initialized = True
            self.logger.info(f"{self.__class__.__name__} initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize {self.__class__.__name__}: {e}")
            raise ConnectorError(f"Initialization failed: {e}")
    
    async def cleanup(self) -> None:
        """Cleanup connector resources"""
        try:
            # Perform connector-specific cleanup
            await self._cleanup()
            
            # Cleanup webhooks
            if self.webhook_handler:
                await self.webhook_handler.cleanup()
            
            self._initialized = False
            self.logger.info(f"{self.__class__.__name__} cleaned up")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    async def execute_operation(
        self,
        operation: str,
        data: Dict[str, Any],
        **kwargs
    ) -> OperationResult:
        """Execute an operation with validation and error handling"""
        if not self._initialized:
            await self.initialize()
        
        start_time = datetime.utcnow()
        
        try:
            # Validate input if validator is configured
            if self.validator:
                await self.validator.validate(operation, data)
            
            # Pre-operation hook
            await self._before_operation(operation, data)
            
            # Execute the operation
            result = await self._execute_operation(operation, data, **kwargs)
            
            # Post-operation hook
            await self._after_operation(operation, data, result)
            
            # Update metrics
            self._operation_count += 1
            
            # Emit operation event
            await self._emit_operation_event(operation, result)
            
            return result
            
        except Exception as e:
            self._error_count += 1
            self.logger.error(f"Operation {operation} failed: {e}")
            
            error_result = OperationResult(
                success=False,
                error=str(e),
                timestamp=datetime.utcnow()
            )
            
            # Emit error event
            await self._emit_operation_event(f"{operation}.error", error_result)
            
            return error_result
        
        finally:
            # Log operation duration
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.logger.debug(f"Operation {operation} completed in {duration:.3f}s")
    
    async def batch_execute(
        self,
        operations: List[Dict[str, Any]],
        max_concurrent: int = 10
    ) -> List[OperationResult]:
        """Execute multiple operations concurrently"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def _execute_with_semaphore(op_data):
            async with semaphore:
                return await self.execute_operation(**op_data)
        
        tasks = [_execute_with_semaphore(op) for op in operations]
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def sync(
        self,
        since: Optional[datetime] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Synchronize data with external system"""
        if not self._initialized:
            await self.initialize()
        
        try:
            # Perform sync
            result = await self._sync(since, filters)
            
            # Update last sync timestamp
            self._last_sync = datetime.utcnow()
            
            return result
            
        except Exception as e:
            self.logger.error(f"Sync failed: {e}")
            raise ConnectorError(f"Sync failed: {e}")
    
    async def validate_webhook(self, payload: Dict[str, Any], signature: str) -> bool:
        """Validate incoming webhook payload"""
        if not self.webhook_handler:
            return False
        
        return await self.webhook_handler.validate(payload, signature)
    
    async def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming webhook"""
        if not self.webhook_handler:
            raise ConnectorError("Webhook handler not configured")
        
        return await self.webhook_handler.handle(payload)
    
    def add_operation_handler(
        self,
        operation: str,
        handler: Callable[[Dict[str, Any]], Awaitable[None]]
    ):
        """Add handler for specific operation"""
        if operation not in self._operation_handlers:
            self._operation_handlers[operation] = []
        self._operation_handlers[operation].append(handler)
    
    def remove_operation_handler(
        self,
        operation: str,
        handler: Callable
    ):
        """Remove handler for specific operation"""
        if operation in self._operation_handlers:
            try:
                self._operation_handlers[operation].remove(handler)
            except ValueError:
                pass
    
    # Abstract methods to be implemented by subclasses
    
    @abstractmethod
    async def _initialize(self) -> None:
        """Connector-specific initialization"""
        pass
    
    @abstractmethod
    async def _cleanup(self) -> None:
        """Connector-specific cleanup"""
        pass
    
    @abstractmethod
    async def _execute_operation(
        self,
        operation: str,
        data: Dict[str, Any],
        **kwargs
    ) -> OperationResult:
        """Execute connector-specific operation"""
        pass
    
    async def _sync(
        self,
        since: Optional[datetime],
        filters: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Default sync implementation"""
        return {
            "synced_at": datetime.utcnow().isoformat(),
            "records": 0,
            "message": "Sync not implemented"
        }
    
    # Hook methods
    
    async def _before_operation(
        self,
        operation: str,
        data: Dict[str, Any]
    ) -> None:
        """Called before operation execution"""
        pass
    
    async def _after_operation(
        self,
        operation: str,
        data: Dict[str, Any],
        result: OperationResult
    ) -> None:
        """Called after operation execution"""
        pass
    
    # Private methods
    
    async def _setup_webhooks(self) -> None:
        """Setup webhook endpoints"""
        if not self.webhook_handler:
            return
        
        await self.webhook_handler.setup(
            endpoint=self.config.webhook_endpoint,
            secret=self.config.webhook_secret
        )
    
    def _register_handlers(self) -> None:
        """Register default event handlers"""
        # Register with client if needed
        pass
    
    async def _emit_operation_event(
        self,
        event: str,
        result: OperationResult
    ) -> None:
        """Emit operation event to handlers"""
        if event in self._operation_handlers:
            tasks = []
            for handler in self._operation_handlers[event]:
                try:
                    tasks.append(handler(result.to_dict() if result.data else {}))
                except Exception as e:
                    self.logger.error(f"Handler error: {e}")
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    # Properties
    
    @property
    def is_initialized(self) -> bool:
        """Check if connector is initialized"""
        return self._initialized
    
    @property
    def last_sync(self) -> Optional[datetime]:
        """Get last sync timestamp"""
        return self._last_sync
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Get connector metrics"""
        return {
            "operation_count": self._operation_count,
            "error_count": self._error_count,
            "error_rate": self._error_count / max(self._operation_count, 1),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None
        }
    
    # Context manager
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()
