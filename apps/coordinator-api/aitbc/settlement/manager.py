"""
Bridge manager for cross-chain settlements
"""

from typing import Dict, Any, List, Optional, Type
import asyncio
import json
from datetime import datetime, timedelta
from dataclasses import asdict

from .bridges.base import (
    BridgeAdapter,
    BridgeConfig,
    SettlementMessage,
    SettlementResult,
    BridgeStatus,
    BridgeError
)
from .bridges.layerzero import LayerZeroAdapter
from .storage import SettlementStorage


class BridgeManager:
    """Manages multiple bridge adapters for cross-chain settlements"""
    
    def __init__(self, storage: SettlementStorage):
        self.adapters: Dict[str, BridgeAdapter] = {}
        self.default_adapter: Optional[str] = None
        self.storage = storage
        self._initialized = False
    
    async def initialize(self, configs: Dict[str, BridgeConfig]) -> None:
        """Initialize all bridge adapters"""
        for name, config in configs.items():
            if config.enabled:
                adapter = await self._create_adapter(config)
                await adapter.initialize()
                self.adapters[name] = adapter
                
                # Set first enabled adapter as default
                if self.default_adapter is None:
                    self.default_adapter = name
        
        self._initialized = True
    
    async def register_adapter(self, name: str, adapter: BridgeAdapter) -> None:
        """Register a bridge adapter"""
        await adapter.initialize()
        self.adapters[name] = adapter
        
        if self.default_adapter is None:
            self.default_adapter = name
    
    async def settle_cross_chain(
        self,
        message: SettlementMessage,
        bridge_name: Optional[str] = None,
        retry_on_failure: bool = True
    ) -> SettlementResult:
        """Settle message across chains"""
        if not self._initialized:
            raise BridgeError("Bridge manager not initialized")
        
        # Get adapter
        adapter = self._get_adapter(bridge_name)
        
        # Validate message
        await adapter.validate_message(message)
        
        # Store initial settlement record
        await self.storage.store_settlement(
            message_id="pending",
            message=message,
            bridge_name=adapter.name,
            status=BridgeStatus.PENDING
        )
        
        # Attempt settlement with retries
        max_retries = 3 if retry_on_failure else 1
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Send message
                result = await adapter.send_message(message)
                
                # Update storage with result
                await self.storage.update_settlement(
                    message_id=result.message_id,
                    status=result.status,
                    transaction_hash=result.transaction_hash,
                    error_message=result.error_message
                )
                
                # Start monitoring for completion
                asyncio.create_task(self._monitor_settlement(result.message_id))
                
                return result
                
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    # Wait before retry
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    # Final attempt failed
                    result = SettlementResult(
                        message_id="",
                        status=BridgeStatus.FAILED,
                        error_message=str(e)
                    )
                    
                    await self.storage.update_settlement(
                        message_id="",
                        status=BridgeStatus.FAILED,
                        error_message=str(e)
                    )
                    
                    return result
    
    async def get_settlement_status(self, message_id: str) -> SettlementResult:
        """Get current status of settlement"""
        # Get from storage first
        stored = await self.storage.get_settlement(message_id)
        
        if not stored:
            raise ValueError(f"Settlement {message_id} not found")
        
        # If completed or failed, return stored result
        if stored['status'] in [BridgeStatus.COMPLETED, BridgeStatus.FAILED]:
            return SettlementResult(**stored)
        
        # Otherwise check with bridge
        adapter = self.adapters.get(stored['bridge_name'])
        if not adapter:
            raise BridgeError(f"Bridge {stored['bridge_name']} not found")
        
        # Get current status from bridge
        result = await adapter.get_message_status(message_id)
        
        # Update storage if status changed
        if result.status != stored['status']:
            await self.storage.update_settlement(
                message_id=message_id,
                status=result.status,
                completed_at=result.completed_at
            )
        
        return result
    
    async def estimate_settlement_cost(
        self,
        message: SettlementMessage,
        bridge_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Estimate cost for settlement across different bridges"""
        results = {}
        
        if bridge_name:
            # Estimate for specific bridge
            adapter = self._get_adapter(bridge_name)
            results[bridge_name] = await adapter.estimate_cost(message)
        else:
            # Estimate for all bridges
            for name, adapter in self.adapters.items():
                try:
                    await adapter.validate_message(message)
                    results[name] = await adapter.estimate_cost(message)
                except Exception as e:
                    results[name] = {'error': str(e)}
        
        return results
    
    async def get_optimal_bridge(
        self,
        message: SettlementMessage,
        priority: str = 'cost'  # 'cost' or 'speed'
    ) -> str:
        """Get optimal bridge for settlement"""
        if len(self.adapters) == 1:
            return list(self.adapters.keys())[0]
        
        # Get estimates for all bridges
        estimates = await self.estimate_settlement_cost(message)
        
        # Filter out failed estimates
        valid_estimates = {
            name: est for name, est in estimates.items()
            if 'error' not in est
        }
        
        if not valid_estimates:
            raise BridgeError("No bridges available for settlement")
        
        # Select based on priority
        if priority == 'cost':
            # Select cheapest
            optimal = min(valid_estimates.items(), key=lambda x: x[1]['total'])
        else:
            # Select fastest (based on historical data)
            # For now, return default
            optimal = (self.default_adapter, valid_estimates[self.default_adapter])
        
        return optimal[0]
    
    async def batch_settle(
        self,
        messages: List[SettlementMessage],
        bridge_name: Optional[str] = None
    ) -> List[SettlementResult]:
        """Settle multiple messages"""
        results = []
        
        # Process in parallel with rate limiting
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent settlements
        
        async def settle_single(message):
            async with semaphore:
                return await self.settle_cross_chain(message, bridge_name)
        
        tasks = [settle_single(msg) for msg in messages]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed results
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append(SettlementResult(
                    message_id="",
                    status=BridgeStatus.FAILED,
                    error_message=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def refund_failed_settlement(self, message_id: str) -> SettlementResult:
        """Attempt to refund a failed settlement"""
        # Get settlement details
        stored = await self.storage.get_settlement(message_id)
        
        if not stored:
            raise ValueError(f"Settlement {message_id} not found")
        
        # Check if it's actually failed
        if stored['status'] != BridgeStatus.FAILED:
            raise ValueError(f"Settlement {message_id} is not in failed state")
        
        # Get adapter
        adapter = self.adapters.get(stored['bridge_name'])
        if not adapter:
            raise BridgeError(f"Bridge {stored['bridge_name']} not found")
        
        # Attempt refund
        result = await adapter.refund_failed_message(message_id)
        
        # Update storage
        await self.storage.update_settlement(
            message_id=message_id,
            status=result.status,
            error_message=result.error_message
        )
        
        return result
    
    def get_supported_chains(self) -> Dict[str, List[int]]:
        """Get all supported chains by bridge"""
        chains = {}
        for name, adapter in self.adapters.items():
            chains[name] = adapter.get_supported_chains()
        return chains
    
    def get_bridge_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all bridges"""
        info = {}
        for name, adapter in self.adapters.items():
            info[name] = {
                'name': adapter.name,
                'supported_chains': adapter.get_supported_chains(),
                'max_message_size': adapter.get_max_message_size(),
                'config': asdict(adapter.config)
            }
        return info
    
    async def _monitor_settlement(self, message_id: str) -> None:
        """Monitor settlement until completion"""
        max_wait_time = timedelta(hours=1)
        start_time = datetime.utcnow()
        
        while datetime.utcnow() - start_time < max_wait_time:
            # Check status
            result = await self.get_settlement_status(message_id)
            
            # If completed or failed, stop monitoring
            if result.status in [BridgeStatus.COMPLETED, BridgeStatus.FAILED]:
                break
            
            # Wait before checking again
            await asyncio.sleep(30)  # Check every 30 seconds
        
        # If still pending after timeout, mark as failed
        if result.status == BridgeStatus.IN_PROGRESS:
            await self.storage.update_settlement(
                message_id=message_id,
                status=BridgeStatus.FAILED,
                error_message="Settlement timed out"
            )
    
    def _get_adapter(self, bridge_name: Optional[str] = None) -> BridgeAdapter:
        """Get bridge adapter"""
        if bridge_name:
            if bridge_name not in self.adapters:
                raise BridgeError(f"Bridge {bridge_name} not found")
            return self.adapters[bridge_name]
        
        if self.default_adapter is None:
            raise BridgeError("No default bridge configured")
        
        return self.adapters[self.default_adapter]
    
    async def _create_adapter(self, config: BridgeConfig) -> BridgeAdapter:
        """Create adapter instance based on config"""
        # Import web3 here to avoid circular imports
        from web3 import Web3
        
        # Get web3 instance (this would be injected or configured)
        web3 = Web3()  # Placeholder
        
        if config.name == "layerzero":
            return LayerZeroAdapter(config, web3)
        # Add other adapters as they're implemented
        # elif config.name == "chainlink_ccip":
        #     return ChainlinkCCIPAdapter(config, web3)
        else:
            raise BridgeError(f"Unknown bridge type: {config.name}")
