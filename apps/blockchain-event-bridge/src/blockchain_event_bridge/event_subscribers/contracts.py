"""Contract event subscriber for smart contract event monitoring."""

import asyncio
from typing import TYPE_CHECKING, Any, Dict, Optional

from aitbc.http_client import AsyncAITBCHTTPClient
from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError

from ..config import Settings
from ..metrics import event_queue_size

if TYPE_CHECKING:
    from ..bridge import BlockchainEventBridge


logger = get_logger(__name__)


class ContractEventSubscriber:
    """Subscribes to smart contract events via blockchain RPC."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._running = False
        self._bridge: "BlockchainEventBridge | None" = None
        self._client: Optional[AsyncAITBCHTTPClient] = None

        # Contract addresses from configuration
        self.contract_addresses: Dict[str, str] = {
            "AgentStaking": settings.agent_staking_address or "",
            "PerformanceVerifier": settings.performance_verifier_address or "",
            "AgentServiceMarketplace": settings.marketplace_address or "",
            "BountyIntegration": settings.bounty_address or "",
            "CrossChainBridge": settings.bridge_address or "",
        }

        # Event topics/signatures for each contract
        self.event_topics: Dict[str, list[str]] = {
            "AgentStaking": [
                "StakeCreated",
                "RewardsDistributed",
                "AgentTierUpdated",
            ],
            "PerformanceVerifier": [
                "PerformanceVerified",
                "PenaltyApplied",
                "RewardIssued",
            ],
            "AgentServiceMarketplace": [
                "ServiceListed",
                "ServicePurchased",
            ],
            "BountyIntegration": [
                "BountyCreated",
                "BountyCompleted",
            ],
            "CrossChainBridge": [
                "BridgeInitiated",
                "BridgeCompleted",
            ],
        }

        # Track last processed block for each contract
        self.last_processed_blocks: Dict[str, int] = {}

    def set_bridge(self, bridge: "BlockchainEventBridge") -> None:
        """Set the bridge instance for event handling."""
        self._bridge = bridge

    async def _get_client(self) -> AsyncAITBCHTTPClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = AsyncAITBCHTTPClient(
                base_url=self.settings.blockchain_rpc_url,
                timeout=30
            )
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

        # Initialize last processed blocks from current chain height
        await self._initialize_block_tracking()

        while self._running:
            try:
                await self._poll_contract_events()
                await asyncio.sleep(self.settings.polling_interval_seconds)
            except asyncio.CancelledError:
                logger.info("Contract event subscriber cancelled")
                break
            except Exception as e:
                logger.error(f"Error in contract event subscriber: {e}", exc_info=True)
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
            logger.info(f"Initialized block tracking at height {current_height}")
        except NetworkError as e:
            logger.error(f"Network error initializing block tracking: {e}")
        except Exception as e:
            logger.error(f"Error initializing block tracking: {e}")

    async def _poll_contract_events(self) -> None:
        """Poll for contract events from blockchain."""
        client = await self._get_client()

        for contract_name, contract_address in self.contract_addresses.items():
            if not contract_address:
                continue

            try:
                # Get current chain height
                head_data = await client.async_get("/head")
                current_height = head_data.get("height", 0)
                last_height = self.last_processed_blocks.get(contract_name, current_height - 100)

                # Query events for this contract
                logs_data = await client.async_post(
                    "/eth_getLogs",
                    json={
                        "address": contract_address,
                        "from_block": last_height + 1,
                        "to_block": current_height,
                        "topics": self.event_topics.get(contract_name, []),
                    }
                )

                logs = logs_data.get("logs", [])

                if logs:
                    logger.info(f"Found {len(logs)} events for {contract_name}")

                    # Process each log
                    for log in logs:
                        await self._process_contract_event(contract_name, log)

                # Update last processed block
                self.last_processed_blocks[contract_name] = current_height

            except NetworkError as e:
                logger.error(f"Network error polling events for {contract_name}: {e}")
            except Exception as e:
                logger.error(f"Error polling events for {contract_name}: {e}", exc_info=True)

    async def _process_contract_event(self, contract_name: str, log: Dict[str, Any]) -> None:
        """Process a contract event."""
        event_type = log.get("topics", [""])[0] if log.get("topics") else "Unknown"

        logger.info(f"Processing {contract_name} event: {event_type}")

        if self._bridge:
            # Route event to appropriate handler based on contract type
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

    async def _handle_staking_event(self, log: Dict[str, Any]) -> None:
        """Handle AgentStaking contract event."""
        if self._bridge:
            await self._bridge.handle_staking_event(log)

    async def _handle_performance_event(self, log: Dict[str, Any]) -> None:
        """Handle PerformanceVerifier contract event."""
        if self._bridge:
            await self._bridge.handle_performance_event(log)

    async def _handle_marketplace_event(self, log: Dict[str, Any]) -> None:
        """Handle AgentServiceMarketplace contract event."""
        if self._bridge:
            await self._bridge.handle_marketplace_event(log)

    async def _handle_bounty_event(self, log: Dict[str, Any]) -> None:
        """Handle BountyIntegration contract event."""
        if self._bridge:
            await self._bridge.handle_bounty_event(log)

    async def _handle_bridge_event(self, log: Dict[str, Any]) -> None:
        """Handle CrossChainBridge contract event."""
        if self._bridge:
            await self._bridge.handle_bridge_event(log)

    async def stop(self) -> None:
        """Stop the contract event subscriber."""
        self._running = False
        self._client = None
        logger.info("Contract event subscriber stopped")
