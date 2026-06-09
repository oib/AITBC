"""
Cache invalidation based on blockchain events.
"""

from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.caching.blockchain import BlockchainCache

logger = get_logger(__name__)


class CacheInvalidator:
    """
    Automatic cache invalidation based on blockchain events
    """
    
    def __init__(self, blockchain_cache: BlockchainCache):
        """
        Initialize cache invalidator
        
        Args:
            blockchain_cache: BlockchainCache instance to manage invalidation
        """
        self.blockchain_cache = blockchain_cache
        self.invalidation_rules = {
            "new_block": self._on_new_block,
            "new_transaction": self._on_new_transaction,
            "contract_state_changed": self._on_contract_state_changed,
            "account_balance_changed": self._on_account_balance_changed
        }
    
    def handle_event(self, event_type: str, event_data: dict[str, Any]) -> int:
        """
        Handle blockchain event and invalidate appropriate cache entries
        
        Args:
            event_type: Type of blockchain event
            event_data: Event data with relevant information
            
        Returns:
            Number of cache entries invalidated
        """
        handler = self.invalidation_rules.get(event_type)
        if handler:
            try:
                return handler(event_data)
            except Exception as e:
                logger.error(f"Error in cache invalidation handler for {event_type}: {e}")
                return 0
        return 0
    
    def _on_new_block(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when a new block is mined"""
        chain_id = event_data.get("chain_id")
        block_number = event_data.get("block_number")
        
        invalidated = 0
        
        # Invalidate the new block itself (will be cached with fresh data)
        if chain_id and block_number:
            if self.blockchain_cache.invalidate_block(block_number, chain_id):
                invalidated += 1
        
        # Invalidate chain state (block number, gas price, etc.)
        if chain_id:
            invalidated += self.blockchain_cache.invalidate_chain_state(chain_id)
        
        # Invalidate account balances that might have changed
        # This is a conservative approach - in production, you might be more selective
        if chain_id:
            invalidated += self._invalidate_all_account_balances(chain_id)
        
        logger.info(f"Invalidated {invalidated} cache entries for new block {block_number} on chain {chain_id}")
        return invalidated
    
    def _on_new_transaction(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when a new transaction is processed"""
        chain_id = event_data.get("chain_id")
        from_address = event_data.get("from_address")
        to_address = event_data.get("to_address")
        contract_address = event_data.get("contract_address")
        
        invalidated = 0
        
        # Invalidate account balances for sender and receiver
        if chain_id and from_address:
            if self.blockchain_cache.invalidate_account(from_address, chain_id):
                invalidated += 1
        
        if chain_id and to_address:
            if self.blockchain_cache.invalidate_account(to_address, chain_id):
                invalidated += 1
        
        # Invalidate contract state if relevant
        if chain_id and contract_address:
            if self.blockchain_cache.invalidate_contract_state(contract_address, chain_id):
                invalidated += 1
        
        logger.info(f"Invalidated {invalidated} cache entries for new transaction on chain {chain_id}")
        return invalidated
    
    def _on_contract_state_changed(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when contract state changes"""
        chain_id = event_data.get("chain_id")
        contract_address = event_data.get("contract_address")
        slot = event_data.get("slot")
        
        if chain_id and contract_address:
            # Invalidate specific contract state
            invalidated = self.blockchain_cache.invalidate_contract_state(
                contract_address, chain_id, slot
            )
            
            # Also invalidate all contract state for this contract if this is a major change
            if not slot:  # No specific slot means broad state change
                invalidated += self.blockchain_cache.invalidate_contract_state(
                    contract_address, chain_id
                )
            
            logger.info(f"Invalidated {invalidated} contract cache entries for {contract_address}")
            return invalidated
        
        return 0
    
    def _on_account_balance_changed(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when account balance changes"""
        chain_id = event_data.get("chain_id")
        address = event_data.get("address")
        
        if chain_id and address:
            if self.blockchain_cache.invalidate_account(address, chain_id):
                logger.info(f"Invalidated account cache for {address} on chain {chain_id}")
                return 1
        
        return 0
    
    def _invalidate_all_account_balances(self, chain_id: int) -> int:
        """Invalidate all account balances for a chain (conservative approach)"""
        # In a real implementation, you might track which accounts are affected
        # For now, this is a placeholder that would need Redis pattern matching
        if self.blockchain_cache.redis_cache and self.blockchain_cache.redis_cache._client:
            try:
                pattern = f"{BlockchainCache.PREFIX_ACCOUNT_BALANCE}:{chain_id}:*"
                keys = self.blockchain_cache.redis_cache._client.keys(pattern)
                if keys:
                    deleted = self.blockchain_cache.redis_cache._client.delete(*keys)
                    return deleted
            except Exception as e:
                logger.error(f"Error invalidating all account balances: {e}")
        return 0
