"""
Automatic cache invalidation based on blockchain events
"""

from typing import Any

from aitbc.aitbc_logging import get_logger

from .blockchain_cache import BlockchainCache

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
            "account_balance_changed": self._on_account_balance_changed,
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
                logger.error("Error in cache invalidation handler for %s: %s", event_type, e)
                return 0
        return 0

    def _on_new_block(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when a new block is mined"""
        chain_id = event_data.get("chain_id")
        block_number = event_data.get("block_number")
        invalidated = 0
        if chain_id and block_number and self.blockchain_cache.invalidate_block(block_number, chain_id):
            invalidated += 1
        if chain_id:
            invalidated += self.blockchain_cache.invalidate_chain_state(chain_id)
        if chain_id:
            invalidated += self._invalidate_all_account_balances(chain_id)
        logger.info("Invalidated %s cache entries for new block %s on chain %s", invalidated, block_number, chain_id)
        return invalidated

    def _on_new_transaction(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when a new transaction is processed"""
        chain_id = event_data.get("chain_id")
        from_address = event_data.get("from_address")
        to_address = event_data.get("to_address")
        contract_address = event_data.get("contract_address")
        invalidated = 0
        if chain_id and from_address and self.blockchain_cache.invalidate_account(from_address, chain_id):
            invalidated += 1
        if chain_id and to_address and self.blockchain_cache.invalidate_account(to_address, chain_id):
            invalidated += 1
        if chain_id and contract_address and self.blockchain_cache.invalidate_contract_state(contract_address, chain_id):
            invalidated += 1
        logger.info("Invalidated %s cache entries for new transaction on chain %s", invalidated, chain_id)
        return invalidated

    def _on_contract_state_changed(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when contract state changes"""
        chain_id = event_data.get("chain_id")
        contract_address = event_data.get("contract_address")
        slot = event_data.get("slot")
        if chain_id and contract_address:
            invalidated = 0
            if slot:
                if self.blockchain_cache.invalidate_contract_state(contract_address, chain_id, slot):
                    invalidated += 1
            elif self.blockchain_cache.invalidate_contract_state(contract_address, chain_id):
                invalidated += 1
            logger.info("Invalidated %s contract cache entries for %s", invalidated, contract_address)
            return invalidated
        return 0

    def _on_account_balance_changed(self, event_data: dict[str, Any]) -> int:
        """Invalidate cache entries when account balance changes"""
        chain_id = event_data.get("chain_id")
        address = event_data.get("address")
        if chain_id and address and self.blockchain_cache.invalidate_account(address, chain_id):
            logger.info("Invalidated account cache for %s on chain %s", address, chain_id)
            return 1
        return 0

    def _invalidate_all_account_balances(self, chain_id: int) -> int:
        """Invalidate all account balances for a chain (conservative approach)"""
        if self.blockchain_cache.redis_cache and self.blockchain_cache.redis_cache._client:
            try:
                pattern = f"{BlockchainCache.PREFIX_ACCOUNT_BALANCE}:{chain_id}:*"
                keys = self.blockchain_cache.redis_cache._client.keys(pattern)
                if keys:
                    deleted = self.blockchain_cache.redis_cache._client.delete(*keys)
                    return deleted  # type: ignore[no-any-return]
            except Exception as e:
                logger.error("Error invalidating all account balances: %s", e)
        return 0
