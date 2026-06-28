"""
Blockchain-specific cache with intelligent invalidation
"""

from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class BlockchainCache:
    """
    Specialized cache for blockchain operations with intelligent invalidation
    """

    PREFIX_ACCOUNT_BALANCE = "account_balance"
    PREFIX_BLOCK = "block"
    PREFIX_BLOCK_HASH = "block_hash"
    PREFIX_TRANSACTION = "transaction"
    PREFIX_CONTRACT_STATE = "contract_state"
    PREFIX_CHAIN_STATE = "chain_state"
    PREFIX_MARKET_DATA = "market_data"
    TTL_ACCOUNT_BALANCE = 30
    TTL_BLOCK = 3600
    TTL_TRANSACTION = 86400
    TTL_CONTRACT_STATE = 60
    TTL_CHAIN_STATE = 10
    TTL_MARKET_DATA = 300

    def __init__(self, redis_cache=None):
        """
        Initialize blockchain cache

        Args:
            redis_cache: Optional RedisCache instance for distributed caching
        """
        self.redis_cache = redis_cache
        self.invalidation_subscribers: list[Any] = []

    def generate_account_key(self, address: str, chain_id: str) -> str:
        """Generate cache key for account balance"""
        return f"{self.PREFIX_ACCOUNT_BALANCE}:{chain_id}:{address.lower()}"

    def generate_block_key(self, height: int, chain_id: str) -> str:
        """Generate cache key for block data by height"""
        return f"{self.PREFIX_BLOCK}:{chain_id}:{height}"

    def generate_block_hash_key(self, hash: str, chain_id: str) -> str:
        """Generate cache key for block data by hash"""
        return f"{self.PREFIX_BLOCK_HASH}:{chain_id}:{hash.lower()}"

    def generate_transaction_key(self, tx_hash: str, chain_id: str) -> str:
        """Generate cache key for transaction"""
        return f"{self.PREFIX_TRANSACTION}:{chain_id}:{tx_hash.lower()}"

    def generate_contract_state_key(self, contract_address: str, chain_id: str, slot: str = "") -> str:
        """Generate cache key for contract state"""
        slot_suffix = f":{slot}" if slot else ""
        return f"{self.PREFIX_CONTRACT_STATE}:{chain_id}:{contract_address.lower()}{slot_suffix}"

    def generate_chain_state_key(self, chain_id: str, state_type: str) -> str:
        """Generate cache key for chain state"""
        return f"{self.PREFIX_CHAIN_STATE}:{chain_id}:{state_type}"

    def generate_market_data_key(self, market_type: str, asset_pair: str) -> str:
        """Generate cache key for market data"""
        return f"{self.PREFIX_MARKET_DATA}:{market_type}:{asset_pair}"

    def get_account_balance(self, address: str, chain_id: str) -> Any | None:
        """Get cached account balance"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None

    def set_account_balance(self, address: str, chain_id: str, balance: Any) -> bool:
        """Cache account balance with short TTL"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, balance, ttl=self.TTL_ACCOUNT_BALANCE)  # type: ignore[no-any-return]
        return False

    def get_block(self, height: int, chain_id: str) -> Any | None:
        """Get cached block data by height"""
        key = self.generate_block_key(height, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None

    def set_block(self, height: int, chain_id: str, block_data: Any) -> bool:
        """Cache block data with long TTL"""
        key = self.generate_block_key(height, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, block_data, ttl=self.TTL_BLOCK)  # type: ignore[no-any-return]
        return False

    def get_block_by_hash(self, hash: str, chain_id: str) -> Any | None:
        """Get cached block data by hash"""
        key = self.generate_block_hash_key(hash, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None

    def set_block_by_hash(self, hash: str, chain_id: str, block_data: Any) -> bool:
        """Cache block data by hash with long TTL"""
        key = self.generate_block_hash_key(hash, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, block_data, ttl=self.TTL_BLOCK)  # type: ignore[no-any-return]
        return False

    def get_transaction(self, tx_hash: str, chain_id: str) -> Any | None:
        """Get cached transaction data"""
        key = self.generate_transaction_key(tx_hash, chain_id)
        if self.redis_cache:
            return self.redis_cache.get(key)
        return None

    def set_transaction(self, tx_hash: str, chain_id: str, tx_data: Any) -> bool:
        """Cache transaction data with very long TTL"""
        key = self.generate_transaction_key(tx_hash, chain_id)
        if self.redis_cache:
            return self.redis_cache.set(key, tx_data, ttl=self.TTL_TRANSACTION)  # type: ignore[no-any-return]
        return False

    def invalidate_account(self, address: str, chain_id: str) -> bool:
        """Invalidate cached account balance"""
        key = self.generate_account_key(address, chain_id)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("account", {"address": address, "chain_id": chain_id})
            return success  # type: ignore[no-any-return]
        return False

    def invalidate_block(self, height: int, chain_id: str) -> bool:
        """Invalidate cached block data by height"""
        key = self.generate_block_key(height, chain_id)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("block", {"height": height, "chain_id": chain_id})
            return success  # type: ignore[no-any-return]
        return False

    def invalidate_block_by_hash(self, hash: str, chain_id: str) -> bool:
        """Invalidate cached block data by hash"""
        key = self.generate_block_hash_key(hash, chain_id)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("block", {"hash": hash, "chain_id": chain_id})
            return success  # type: ignore[no-any-return]
        return False

    def invalidate_contract_state(self, contract_address: str, chain_id: str, slot: str = "") -> bool:
        """Invalidate cached contract state"""
        key = self.generate_contract_state_key(contract_address, chain_id, slot)
        if self.redis_cache:
            success = self.redis_cache.delete(key)
            if success:
                self._notify_subscribers("contract", {"address": contract_address, "chain_id": chain_id, "slot": slot})
            return success  # type: ignore[no-any-return]
        return False

    def invalidate_chain_state(self, chain_id: str, state_type: str | None = None) -> int:
        """Invalidate chain state cache entries"""
        if state_type:
            key = self.generate_chain_state_key(chain_id, state_type)
            if self.redis_cache:
                success = self.redis_cache.delete(key)
                if success:
                    self._notify_subscribers("chain_state", {"chain_id": chain_id, "state_type": state_type})
                return 1 if success else 0
            return 0
        else:
            pattern = f"{self.PREFIX_CHAIN_STATE}:{chain_id}:*"
            if self.redis_cache and self.redis_cache._client:
                try:
                    keys = self.redis_cache._client.keys(pattern)
                    if keys:
                        deleted = self.redis_cache._client.delete(*keys)
                        self._notify_subscribers("chain_state", {"chain_id": chain_id, "all": True})
                        return deleted  # type: ignore[no-any-return]
                except Exception as e:
                    logger.error("Error invalidating chain state: %s", e)
            return 0

    def subscribe_to_invalidation(self, callback) -> None:
        """Subscribe to cache invalidation events"""
        self.invalidation_subscribers.append(callback)

    def _notify_subscribers(self, cache_type: str, data: dict[str, Any]) -> None:
        """Notify subscribers of cache invalidation"""
        for callback in self.invalidation_subscribers:
            try:
                callback(cache_type, data)
            except Exception as e:
                logger.error("Error in cache invalidation callback: %s", e)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get blockchain cache statistics"""
        stats: dict[str, Any] = {
            "redis_available": self.redis_cache is not None and self.redis_cache.is_available(),
            "subscribers": len(self.invalidation_subscribers),
            "prefixes": {
                "account_balance": self.PREFIX_ACCOUNT_BALANCE,
                "block": self.PREFIX_BLOCK,
                "block_hash": self.PREFIX_BLOCK_HASH,
                "transaction": self.PREFIX_TRANSACTION,
                "contract_state": self.PREFIX_CONTRACT_STATE,
                "chain_state": self.PREFIX_CHAIN_STATE,
                "market_data": self.PREFIX_MARKET_DATA,
            },
            "default_ttl": {
                "account_balance": self.TTL_ACCOUNT_BALANCE,
                "block": self.TTL_BLOCK,
                "transaction": self.TTL_TRANSACTION,
                "contract_state": self.TTL_CONTRACT_STATE,
                "chain_state": self.TTL_CHAIN_STATE,
                "market_data": self.TTL_MARKET_DATA,
            },
        }
        return stats
