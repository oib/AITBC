"""Contract event subscriber for smart contract event monitoring."""

import asyncio
from typing import TYPE_CHECKING, Any

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError
from aitbc.network.http_client import AsyncAITBCHTTPClient

from ..config import Settings

if TYPE_CHECKING:
    from ..bridge import BlockchainEventBridge
logger = get_logger(__name__)


class ContractEventSubscriber:
    """Subscribes to smart contract events via blockchain RPC."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._bridge: BlockchainEventBridge | None = None
        self._client: AsyncAITBCHTTPClient | None = None
        self.contract_addresses: dict[str, str] = {
            "AgentStaking": settings.agent_staking_address or "",
            "PerformanceVerifier": settings.performance_verifier_address or "",
            "AgentServiceMarketplace": settings.marketplace_address or "",
            "BountyIntegration": settings.bounty_address or "",
            "CrossChainBridge": settings.bridge_address or "",
        }
        self.event_topics: dict[str, list[str]] = {
            "AgentStaking": ["StakeCreated", "RewardsDistributed", "AgentTierUpdated"],
            "PerformanceVerifier": ["PerformanceVerified", "PenaltyApplied", "RewardIssued"],
            "AgentServiceMarketplace": ["ServiceListed", "ServicePurchased"],
            "BountyIntegration": ["BountyCreated", "BountyCompleted"],
            "CrossChainBridge": ["BridgeInitiated", "BridgeCompleted"],
        }
        self.last_processed_blocks: dict[str, int] = {}

    def set_bridge(self, bridge: "BlockchainEventBridge") -> None:
        """Set the bridge instance for event handling."""
        self._bridge = bridge

    async def _get_client(self) -> AsyncAITBCHTTPClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = AsyncAITBCHTTPClient(base_url=self.settings.blockchain_rpc_url, timeout=30)
        return self._client

    async def run(self) -> None:
        """Run the contract event subscriber."""
        if not self.settings.subscribe_contracts:
            logger.info("Contract event subscription disabled")
            return
        if self._running:
            logger.warning("Contract event subscriber already running")
            return
        self._running = True
        logger.info("Starting contract event subscriber...")
        await self._initialize_block_tracking()
        while self._running:
            try:
                await self._poll_contract_events()
                await asyncio.sleep(self.settings.polling_interval_seconds)
            except asyncio.CancelledError:
                logger.info("Contract event subscriber cancelled")
                break
            except Exception as e:
                logger.error("Error in contract event subscriber: %s", e, exc_info=True)
                await asyncio.sleep(5)

    async def _initialize_block_tracking(self) -> None:
        """Initialize block tracking from current chain height."""
        try:
            client = await self._get_client()
            head_data = await client.async_get("/head")
            current_height = head_data.get("height", 0)
            for contract in self.contract_addresses:
                if self.contract_addresses[contract]:
                    self.last_processed_blocks[contract] = current_height
            logger.info("Initialized block tracking at height %s", current_height)
        except NetworkError as e:
            logger.error("Network error initializing block tracking: %s", e)
        except Exception as e:
            logger.error("Error initializing block tracking: %s", e)

    async def _poll_contract_events(self) -> None:
        """Poll for contract events from blockchain."""
        client = await self._get_client()
        for contract_name, contract_address in self.contract_addresses.items():
            if not contract_address:
                continue
            try:
                head_data = await client.async_get("/head")
                current_height = head_data.get("height", 0)
                last_height = self.last_processed_blocks.get(contract_name, current_height - 100)
                logs_data = await client.async_post(
                    "/eth_getLogs",
                    json={
                        "address": contract_address,
                        "from_block": last_height + 1,
                        "to_block": current_height,
                        "topics": self.event_topics.get(contract_name, []),
                    },
                )
                logs = logs_data.get("logs", [])
                if logs:
                    logger.info("Found %s events for %s", len(logs), contract_name)
                    for log in logs:
                        await self._process_contract_event(contract_name, log)
                self.last_processed_blocks[contract_name] = current_height
            except NetworkError as e:
                logger.error("Network error polling events for %s: %s", contract_name, e)
            except Exception as e:
                logger.error("Error polling events for %s: %s", contract_name, e, exc_info=True)

    async def _process_contract_event(self, contract_name: str, log: dict[str, Any]) -> None:
        """Process a contract event."""
        event_type = log.get("topics", [""])[0] if log.get("topics") else "Unknown"
        logger.info("Processing %s event: %s", contract_name, event_type)
        if self._bridge:
            if contract_name == "AgentStaking":
                await self._handle_staking_event(log)
            elif contract_name == "PerformanceVerifier":
                await self._handle_performance_event(log)
            elif contract_name == "AgentServiceMarketplace":
                await self._handle_marketplace_event(log)
            elif contract_name == "BountyIntegration":
                await self._handle_bounty_event(log)
            elif contract_name == "CrossChainBridge":
                await self._handle_bridge_event(log)

    async def _handle_staking_event(self, log: dict[str, Any]) -> None:
        """Handle AgentStaking contract event."""
        if self._bridge:
            await self._bridge.handle_staking_event(log)

    async def _handle_performance_event(self, log: dict[str, Any]) -> None:
        """Handle PerformanceVerifier contract event."""
        if self._bridge:
            await self._bridge.handle_performance_event(log)

    async def _handle_marketplace_event(self, log: dict[str, Any]) -> None:
        """Handle AgentServiceMarketplace contract event."""
        if self._bridge:
            await self._bridge.handle_marketplace_event(log)

    async def _handle_bounty_event(self, log: dict[str, Any]) -> None:
        """Handle BountyIntegration contract event."""
        if self._bridge:
            await self._bridge.handle_bounty_event(log)

    async def _handle_bridge_event(self, log: dict[str, Any]) -> None:
        """Handle CrossChainBridge contract event."""
        if self._bridge:
            await self._bridge.handle_bridge_event(log)

    async def stop(self) -> None:
        """Stop the contract event subscriber."""
        self._running = False
        self._client = None
        logger.info("Contract event subscriber stopped")
