"""Core bridge logic for blockchain event to hermes agent trigger mapping."""
import asyncio
from typing import Any

from aitbc.aitbc_logging import get_logger

from .action_handlers.agent_daemon import AgentDaemonHandler
from .action_handlers.coordinator_api import CoordinatorAPIHandler
from .action_handlers.marketplace import MarketplaceHandler
from .config import Settings
from .event_subscribers.blocks import BlockEventSubscriber
from .event_subscribers.contracts import ContractEventSubscriber
from .event_subscribers.transactions import TransactionEventSubscriber
from .metrics import (
    action_execution_duration_seconds,
    actions_failed_total,
    actions_triggered_total,
    event_processing_duration_seconds,
    events_processed_total,
    events_received_total,
)

logger = get_logger(__name__)

class BlockchainEventBridge:
    """Main bridge service connecting blockchain events to hermes agent actions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._tasks: set[asyncio.Task[Any]] = set()
        self.block_subscriber: BlockEventSubscriber | None = None
        self.transaction_subscriber: TransactionEventSubscriber | None = None
        self.contract_subscriber: ContractEventSubscriber | None = None
        self.coordinator_handler: CoordinatorAPIHandler | None = None
        self.agent_daemon_handler: AgentDaemonHandler | None = None
        self.marketplace_handler: MarketplaceHandler | None = None

    async def start(self) -> None:
        """Start the bridge service."""
        if self._running:
            logger.warning('Bridge already running')
            return
        logger.info('Initializing blockchain event bridge...')
        if self.settings.enable_coordinator_api_trigger:
            self.coordinator_handler = CoordinatorAPIHandler(self.settings.coordinator_api_url, self.settings.coordinator_api_key)
            logger.info('Coordinator API handler initialized')
        if self.settings.enable_agent_daemon_trigger:
            self.agent_daemon_handler = AgentDaemonHandler(self.settings.blockchain_rpc_url)
            logger.info('Agent daemon handler initialized')
        if self.settings.enable_marketplace_trigger:
            self.marketplace_handler = MarketplaceHandler(self.settings.coordinator_api_url, self.settings.coordinator_api_key)
            logger.info('Marketplace handler initialized')
        if self.settings.subscribe_blocks:
            self.block_subscriber = BlockEventSubscriber(self.settings)
            self.block_subscriber.set_bridge(self)
            task = asyncio.create_task(self.block_subscriber.run(), name='block-subscriber')
            self._tasks.add(task)
            logger.info('Block event subscriber started')
        if self.settings.subscribe_transactions:
            self.transaction_subscriber = TransactionEventSubscriber(self.settings)
            self.transaction_subscriber.set_bridge(self)
            task = asyncio.create_task(self.transaction_subscriber.run(), name='transaction-subscriber')
            self._tasks.add(task)
            logger.info('Transaction event subscriber started')
        if self.settings.subscribe_contracts:
            self.contract_subscriber = ContractEventSubscriber(self.settings)
            self.contract_subscriber.set_bridge(self)
            task = asyncio.create_task(self.contract_subscriber.run(), name='contract-subscriber')
            self._tasks.add(task)
            logger.info('Contract event subscriber started')
        self._running = True
        logger.info('Blockchain event bridge started successfully')

    async def stop(self) -> None:
        """Stop the bridge service."""
        if not self._running:
            return
        logger.info('Stopping blockchain event bridge...')
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._running = False
        logger.info('Blockchain event bridge stopped')

    @property
    def is_running(self) -> bool:
        """Check if the bridge is running."""
        return self._running

    async def handle_block_event(self, block_data: dict[str, Any]) -> None:
        """Handle a new block event."""
        event_type = 'block'
        events_received_total.labels(event_type=event_type).inc()
        with event_processing_duration_seconds.labels(event_type=event_type).time():
            try:
                transactions = block_data.get('transactions', [])
                if transactions and self.settings.enable_coordinator_api_trigger:
                    await self._trigger_coordinator_actions(block_data, transactions)
                if transactions and self.settings.enable_marketplace_trigger:
                    await self._trigger_marketplace_actions(block_data, transactions)
                events_processed_total.labels(event_type=event_type, status='success').inc()
                logger.info('Processed block event: height=%s, txs=%s', block_data.get('height'), len(transactions))
            except Exception as e:
                events_processed_total.labels(event_type=event_type, status='error').inc()
                logger.error('Error processing block event: %s', e, exc_info=True)

    async def handle_transaction_event(self, tx_data: dict[str, Any]) -> None:
        """Handle a transaction event."""
        event_type = 'transaction'
        events_received_total.labels(event_type=event_type).inc()
        with event_processing_duration_seconds.labels(event_type=event_type).time():
            try:
                if self.settings.enable_agent_daemon_trigger:
                    await self._trigger_agent_daemon_actions(tx_data)
                if self.settings.enable_coordinator_api_trigger:
                    await self._trigger_coordinator_transaction_actions(tx_data)
                events_processed_total.labels(event_type=event_type, status='success').inc()
                logger.info('Processed transaction event: hash=%s', tx_data.get('hash'))
            except Exception as e:
                events_processed_total.labels(event_type=event_type, status='error').inc()
                logger.error('Error processing transaction event: %s', e, exc_info=True)

    async def _trigger_coordinator_actions(self, block_data: dict[str, Any], transactions: list[Any]) -> None:
        """Trigger coordinator API actions based on block data."""
        if not self.coordinator_handler:
            return
        with action_execution_duration_seconds.labels(action_type='coordinator_api').time():
            try:
                await self.coordinator_handler.handle_block(block_data, transactions)
                actions_triggered_total.labels(action_type='coordinator_api').inc()
            except Exception as e:
                actions_failed_total.labels(action_type='coordinator_api').inc()
                logger.error('Error triggering coordinator API actions: %s', e, exc_info=True)

    async def _trigger_marketplace_actions(self, block_data: dict[str, Any], transactions: list[Any]) -> None:
        """Trigger marketplace actions based on block data."""
        if not self.marketplace_handler:
            return
        with action_execution_duration_seconds.labels(action_type='marketplace').time():
            try:
                await self.marketplace_handler.handle_block(block_data, transactions)
                actions_triggered_total.labels(action_type='marketplace').inc()
            except Exception as e:
                actions_failed_total.labels(action_type='marketplace').inc()
                logger.error('Error triggering marketplace actions: %s', e, exc_info=True)

    async def _trigger_agent_daemon_actions(self, tx_data: dict[str, Any]) -> None:
        """Trigger agent daemon actions based on transaction data."""
        if not self.agent_daemon_handler:
            return
        with action_execution_duration_seconds.labels(action_type='agent_daemon').time():
            try:
                await self.agent_daemon_handler.handle_transaction(tx_data)
                actions_triggered_total.labels(action_type='agent_daemon').inc()
            except Exception as e:
                actions_failed_total.labels(action_type='agent_daemon').inc()
                logger.error('Error triggering agent daemon actions: %s', e, exc_info=True)

    async def _trigger_coordinator_transaction_actions(self, tx_data: dict[str, Any]) -> None:
        """Trigger coordinator API actions based on transaction data."""
        if not self.coordinator_handler:
            return
        with action_execution_duration_seconds.labels(action_type='coordinator_api').time():
            try:
                await self.coordinator_handler.handle_transaction(tx_data)
                actions_triggered_total.labels(action_type='coordinator_api').inc()
            except Exception as e:
                actions_failed_total.labels(action_type='coordinator_api').inc()
                logger.error('Error triggering coordinator API transaction actions: %s', e, exc_info=True)

    async def handle_staking_event(self, event_log: dict[str, Any]) -> None:
        """Handle AgentStaking contract event."""
        event_type = 'staking_event'
        events_received_total.labels(event_type=event_type).inc()
        with event_processing_duration_seconds.labels(event_type=event_type).time():
            try:
                if self.agent_daemon_handler:
                    await self.agent_daemon_handler.handle_staking_event(event_log)
                events_processed_total.labels(event_type=event_type, status='success').inc()
            except Exception as e:
                events_processed_total.labels(event_type=event_type, status='error').inc()
                logger.error('Error processing staking event: %s', e, exc_info=True)

    async def handle_performance_event(self, event_log: dict[str, Any]) -> None:
        """Handle PerformanceVerifier contract event."""
        event_type = 'performance_event'
        events_received_total.labels(event_type=event_type).inc()
        with event_processing_duration_seconds.labels(event_type=event_type).time():
            try:
                if self.agent_daemon_handler:
                    await self.agent_daemon_handler.handle_performance_event(event_log)
                events_processed_total.labels(event_type=event_type, status='success').inc()
            except Exception as e:
                events_processed_total.labels(event_type=event_type, status='error').inc()
                logger.error('Error processing performance event: %s', e, exc_info=True)

    async def handle_marketplace_event(self, event_log: dict[str, Any]) -> None:
        """Handle AgentServiceMarketplace contract event."""
        event_type = 'marketplace_event'
        events_received_total.labels(event_type=event_type).inc()
        with event_processing_duration_seconds.labels(event_type=event_type).time():
            try:
                if self.marketplace_handler:
                    await self.marketplace_handler.handle_contract_event(event_log)
                events_processed_total.labels(event_type=event_type, status='success').inc()
            except Exception as e:
                events_processed_total.labels(event_type=event_type, status='error').inc()
                logger.error('Error processing marketplace event: %s', e, exc_info=True)

    async def handle_bounty_event(self, event_log: dict[str, Any]) -> None:
        """Handle BountyIntegration contract event."""
        event_type = 'bounty_event'
        events_received_total.labels(event_type=event_type).inc()
        with event_processing_duration_seconds.labels(event_type=event_type).time():
            try:
                if self.agent_daemon_handler:
                    await self.agent_daemon_handler.handle_bounty_event(event_log)
                events_processed_total.labels(event_type=event_type, status='success').inc()
            except Exception as e:
                events_processed_total.labels(event_type=event_type, status='error').inc()
                logger.error('Error processing bounty event: %s', e, exc_info=True)

    async def handle_bridge_event(self, event_log: dict[str, Any]) -> None:
        """Handle CrossChainBridge contract event."""
        event_type = 'bridge_event'
        events_received_total.labels(event_type=event_type).inc()
        with event_processing_duration_seconds.labels(event_type=event_type).time():
            try:
                if self.agent_daemon_handler:
                    await self.agent_daemon_handler.handle_bridge_event(event_log)
                events_processed_total.labels(event_type=event_type, status='success').inc()
            except Exception as e:
                events_processed_total.labels(event_type=event_type, status='error').inc()
                logger.error('Error processing bridge event: %s', e, exc_info=True)
