"""
Blockchain-specific cache implementation with intelligent invalidation.
"""

from collections.abc import Callable
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class BlockchainCache:
    """
    Specialized cache for blockchain operations with intelligent invalidation
    """
    
    # Cache key prefixes for different blockchain data types
    PREFIX_ACCOUNT_BALANCE = "account_balance"
    PREFIX_BLOCK = "block"
    PREFIX_TRANSACTION = "transaction"
    PREFIX_CONTRACT_STATE = "contract_state"
    PREFIX_CHAIN_STATE = "chain_state"
    PREFIX_MARKET_DATA = "market_data"
    
    # Default TTL for different data types (in seconds)
    TTL_ACCOUNT_BALANCE = 30  # Account balances change frequently
    TTL_BLOCK = 3600  # Block data is stable for longer
    TTL_TRANSACTION = 86400  # Transaction data is immutable
    TTL_CONTRACT_STATE = 60  # Contract state changes frequently
    TTL_CHAIN_STATE = 10  # Chain state changes very frequently
    TTL_MARKET_DATA = 300  # Market data changes moderately
    
    def __init__(self, redis_cache=None):
        """
        Initialize blockchain cache
        
        Args:
            redis_cache: Optional RedisCache instance for distributed caching
        """
        self.redis_cache = redis_cache
        self.invalidation_subscribers = []
        
    def generate_account_key(self, address: str, chain_id: int) -> str:
        """Generate cache key for account balance"""
        return f"{self.PREFIX_ACCOUNT_BALANCE}:{chain_id}:{address.lower()}"
    
    def generate_block_key(self, block_number: int, chain_id: int) -> str:
        """Generate cache key for block data"""
        return f"{self.PREFIX_BLOCK}:{chain_id}:{block_number}"
    
    def generate_transaction_key(self, tx_hash: str, chain_id: int) -> str:
        """Generate cache key for transaction"""
        return f"{self.PREFIX_TRANSACTION}:{chain_id}:{tx_hash.lower()}"
    
    def generate_contract_state_key(self, contract_address: str, chain_id: int, slot: str = "") -> str:
        """Generate cache key for contract state"""
        slot_suffix = f":{slot}" if slot else ""
        return f"{self.PREFIX_CONTRACT_STATE}:{chain_id}:{contract_address.lower()}{slot_suffix}"
    
    def generate_chain_state_key(self, chain_id: int, state_type: str) -> str:
        """Generate cache key for chain state"""
        return f"{self.PREFIX_CHAIN_STATE}:{chain_id}:{state_type}"
    
    def generate_market_data_key(self, market_type: str, asset_pair: str) -> str:
        """Generate cache key for market data"""
        return f"{self.PREFIX_MARKET_DATA}:{market_type}:{asset_pair}"
    
    def get_account_balance(self, address: str, chain_id: int) -> Any | None:
        """Get cached account balance"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None
    
    def set_account_balance(self, address: str, chain_id: int, balance: Any) -> bool:
        """Cache account balance with short TTL"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, balance, ttl=self.TTL_ACCOUNT_BALANCE)
        return False
    
    def get_block(self, block_number: int, chain_id: int) -> Any | None:
        """Get cached block data"""
        key = self.generate_block_key(block_number, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None
    
    def set_block(self, block_number: int, chain_id: int, block_data: Any) -> bool:
        """Cache block data with long TTL"""
        key = self.generate_block_key(block_number, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, block_data, ttl=self.TTL_BLOCK)
        return False
    
    def get_transaction(self, tx_hash: str, chain_id: int) -> Any | None:
        """Get cached transaction data"""
        key = self.generate_transaction_key(tx_hash, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None
    
    def set_transaction(self, tx_hash: str, chain_id: int, tx_data: Any) -> bool:
        """Cache transaction data with very long TTL"""
        key = self.generate_transaction_key(tx_hash, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, tx_data, ttl=self.TTL_TRANSACTION)
        return False
    
    def invalidate_account(self, address: str, chain_id: int) -> bool:
        """Invalidate cached account balance"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("account", {"address": address, "chain_id": chain_id})
            return success
        return False
    
    def invalidate_block(self, block_number: int, chain_id: int) -> bool:
        """Invalidate cached block data"""
        key = self.generate_block_key(block_number, chain_id)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("block", {"block_number": block_number, "chain_id": chain_id})
            return success
        return False
    
    def invalidate_contract_state(self, contract_address: str, chain_id: int, slot: str = "") -> bool:
        """Invalidate cached contract state"""
        key = self.generate_contract_state_key(contract_address, chain_id, slot)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("contract", {"address": contract_address, "chain_id": chain_id, "slot": slot})
            return success
        return False
    
    def invalidate_chain_state(self, chain_id: int, state_type: str | None = None) -> int:
        """Invalidate chain state cache entries"""
        if state_type:
            # Invalidate specific state type
            key = self.generate_chain_state_key(chain_id, state_type)
            if self.redis_cache:
                success = self.redis_cache.delete(key)
                if success:
                    self._notify_subscribers("chain_state", {"chain_id": chain_id, "state_type": state_type})
                return 1 if success else 0
            return 0
        else:
            # Invalidate all chain state for this chain
            pattern = f"{self.PREFIX_CHAIN_STATE}:{chain_id}:*"
            if self.redis_cache and self.redis_cache._client:
                try:
                    keys = self.redis_cache._client.keys(pattern)
                    if keys:
                        deleted = self.redis_cache._client.delete(*keys)
                        self._notify_subscribers("chain_state", {"chain_id": chain_id, "all": True})
                        return deleted
                except Exception as e:
                    logger.error(f"Error invalidating chain state: {e}")
            return 0
    
    def subscribe_to_invalidation(self, callback: Callable) -> None:
        """Subscribe to cache invalidation events"""
        self.invalidation_subscribers.append(callback)
    
    def _notify_subscribers(self, cache_type: str, data: dict[str, Any]) -> None:
        """Notify subscribers of cache invalidation"""
        for callback in self.invalidation_subscribers:
            try:
                callback(cache_type, data)
            except Exception as e:
                logger.error(f"Error in cache invalidation callback: {e}")
    
    def get_cache_stats(self) -> dict[str, Any]:
        """Get blockchain cache statistics"""
        stats = {
            "redis_available": self.redis_cache is not None and self.redis_cache.is_available(),
            "subscribers": len(self.invalidation_subscribers),
            "prefixes": {
                "account_balance": self.PREFIX_ACCOUNT_BALANCE,
                "block": self.PREFIX_BLOCK,
                "transaction": self.PREFIX_TRANSACTION,
                "contract_state": self.PREFIX_CONTRACT_STATE,
                "chain_state": self.PREFIX_CHAIN_STATE,
                "market_data": self.PREFIX_MARKET_DATA
            },
            "default_ttl": {
                "account_balance": self.TTL_ACCOUNT_BALANCE,
                "block": self.TTL_BLOCK,
                "transaction": self.TTL_TRANSACTION,
                "contract_state": self.TTL_CONTRACT_STATE,
                "chain_state": self.TTL_CHAIN_STATE,
                "market_data": self.TTL_MARKET_DATA
            }
        }
        return stats


def get_blockchain_cache(redis_url: str | None = None) -> BlockchainCache:
    """
    Get or create global blockchain cache instance
    
    Args:
        redis_url: Redis connection URL
        
    Returns:
        BlockchainCache instance
    """
    from aitbc import get_cache
    
    redis_cache = get_cache()
    return BlockchainCache(redis_cache=redis_cache)
