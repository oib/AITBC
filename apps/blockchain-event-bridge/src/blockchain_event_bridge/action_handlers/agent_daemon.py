"""Agent daemon action handler for triggering autonomous agent responses."""
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.network.http_client import AsyncAITBCHTTPClient

logger = get_logger(__name__)

class AgentDaemonHandler:
    """Handles actions that trigger the agent daemon to process transactions."""

    def __init__(self, blockchain_rpc_url: str) -> None:
        self.blockchain_rpc_url = blockchain_rpc_url.rstrip('/')
        self._client: AsyncAITBCHTTPClient | None = None

    async def _get_client(self) -> AsyncAITBCHTTPClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = AsyncAITBCHTTPClient(base_url=self.blockchain_rpc_url, timeout=30)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        self._client = None

    async def handle_transaction(self, tx_data: dict[str, Any]) -> None:
        """Handle a transaction that may require agent daemon response."""
        tx_hash = tx_data.get('hash', 'unknown')
        tx_type = tx_data.get('type', 'unknown')
        recipient = tx_data.get('to')
        logger.info('Checking transaction %s for agent daemon trigger', tx_hash)
        if self._is_agent_transaction(tx_data):
            await self._notify_agent_daemon(tx_data)

    def _is_agent_transaction(self, tx_data: dict[str, Any]) -> bool:
        """Check if transaction is addressed to an agent wallet."""
        payload = tx_data.get('payload', {})
        if isinstance(payload, dict):
            if 'trigger' in payload or 'agent' in payload or 'command' in payload:
                return True
        return False

    async def _notify_agent_daemon(self, tx_data: dict[str, Any]) -> None:
        """Notify agent daemon about a transaction requiring processing."""
        try:
            tx_hash = tx_data.get('hash', 'unknown')
            recipient = tx_data.get('to')
            logger.info('Agent daemon should process transaction %s to %s', tx_hash, recipient)
        except Exception as e:
            logger.error('Error notifying agent daemon: %s', e, exc_info=True)

    async def handle_staking_event(self, event_log: dict[str, Any]) -> None:
        """Handle AgentStaking contract event."""
        event_type = event_log.get('topics', [''])[0] if event_log.get('topics') else 'Unknown'
        logger.info('Handling staking event: %s', event_type)
        if 'StakeCreated' in event_type:
            await self._handle_stake_created(event_log)
        elif 'RewardsDistributed' in event_type:
            await self._handle_rewards_distributed(event_log)
        elif 'AgentTierUpdated' in event_type:
            await self._handle_agent_tier_updated(event_log)

    async def _handle_stake_created(self, event_log: dict[str, Any]) -> None:
        """Handle StakeCreated event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('StakeCreated event: %s', data)
            logger.info('Would call coordinator API reputation service to update agent stake')
        except Exception as e:
            logger.error('Error handling StakeCreated event: %s', e, exc_info=True)

    async def _handle_rewards_distributed(self, event_log: dict[str, Any]) -> None:
        """Handle RewardsDistributed event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('RewardsDistributed event: %s', data)
            logger.info('Would call coordinator API to update agent rewards')
        except Exception as e:
            logger.error('Error handling RewardsDistributed event: %s', e, exc_info=True)

    async def _handle_agent_tier_updated(self, event_log: dict[str, Any]) -> None:
        """Handle AgentTierUpdated event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('AgentTierUpdated event: %s', data)
            logger.info('Would call coordinator API reputation service to update agent tier')
        except Exception as e:
            logger.error('Error handling AgentTierUpdated event: %s', e, exc_info=True)

    async def handle_performance_event(self, event_log: dict[str, Any]) -> None:
        """Handle PerformanceVerifier contract event."""
        event_type = event_log.get('topics', [''])[0] if event_log.get('topics') else 'Unknown'
        logger.info('Handling performance event: %s', event_type)
        if 'PerformanceVerified' in event_type:
            await self._handle_performance_verified(event_log)
        elif 'PenaltyApplied' in event_type:
            await self._handle_penalty_applied(event_log)
        elif 'RewardIssued' in event_type:
            await self._handle_reward_issued(event_log)

    async def _handle_performance_verified(self, event_log: dict[str, Any]) -> None:
        """Handle PerformanceVerified event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('PerformanceVerified event: %s', data)
            logger.info('Would call coordinator API performance service to update metrics')
        except Exception as e:
            logger.error('Error handling PerformanceVerified event: %s', e, exc_info=True)

    async def _handle_penalty_applied(self, event_log: dict[str, Any]) -> None:
        """Handle PenaltyApplied event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('PenaltyApplied event: %s', data)
            logger.info('Would call coordinator API performance service to apply penalty')
        except Exception as e:
            logger.error('Error handling PenaltyApplied event: %s', e, exc_info=True)

    async def _handle_reward_issued(self, event_log: dict[str, Any]) -> None:
        """Handle RewardIssued event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('RewardIssued event: %s', data)
            logger.info('Would call coordinator API performance service to issue reward')
        except Exception as e:
            logger.error('Error handling RewardIssued event: %s', e, exc_info=True)

    async def handle_bounty_event(self, event_log: dict[str, Any]) -> None:
        """Handle BountyIntegration contract event."""
        event_type = event_log.get('topics', [''])[0] if event_log.get('topics') else 'Unknown'
        logger.info('Handling bounty event: %s', event_type)
        if 'BountyCreated' in event_type:
            await self._handle_bounty_created(event_log)
        elif 'BountyCompleted' in event_type:
            await self._handle_bounty_completed(event_log)

    async def _handle_bounty_created(self, event_log: dict[str, Any]) -> None:
        """Handle BountyCreated event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('BountyCreated event: %s', data)
            logger.info('Would call coordinator API bounty service to sync bounty')
        except Exception as e:
            logger.error('Error handling BountyCreated event: %s', e, exc_info=True)

    async def _handle_bounty_completed(self, event_log: dict[str, Any]) -> None:
        """Handle BountyCompleted event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('BountyCompleted event: %s', data)
            logger.info('Would call coordinator API bounty service to complete bounty')
        except Exception as e:
            logger.error('Error handling BountyCompleted event: %s', e, exc_info=True)

    async def handle_bridge_event(self, event_log: dict[str, Any]) -> None:
        """Handle CrossChainBridge contract event."""
        event_type = event_log.get('topics', [''])[0] if event_log.get('topics') else 'Unknown'
        logger.info('Handling bridge event: %s', event_type)
        if 'BridgeInitiated' in event_type:
            await self._handle_bridge_initiated(event_log)
        elif 'BridgeCompleted' in event_type:
            await self._handle_bridge_completed(event_log)

    async def _handle_bridge_initiated(self, event_log: dict[str, Any]) -> None:
        """Handle BridgeInitiated event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('BridgeInitiated event: %s', data)
            logger.info('Would call coordinator API cross-chain service to track bridge')
        except Exception as e:
            logger.error('Error handling BridgeInitiated event: %s', e, exc_info=True)

    async def _handle_bridge_completed(self, event_log: dict[str, Any]) -> None:
        """Handle BridgeCompleted event."""
        try:
            data = event_log.get('data', '{}')
            logger.info('BridgeCompleted event: %s', data)
            logger.info('Would call coordinator API cross-chain service to complete bridge')
        except Exception as e:
            logger.error('Error handling BridgeCompleted event: %s', e, exc_info=True)
