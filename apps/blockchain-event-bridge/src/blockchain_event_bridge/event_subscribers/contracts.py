"""Contract event subscriber for smart contract event monitoring."""

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR
from aitbc.exceptions import NetworkError
from aitbc.network import AsyncAITBCHTTPClient

from ..config import Settings

if TYPE_CHECKING:
    from ..bridge import BlockchainEventBridge

logger = get_logger(__name__)

# Number of recent blocks we keep uncommitted to tolerate chain reorganisations.
# Events in blocks closer than this to the head are not marked as processed.
_FINALITY_BLOCKS = 12

_CHECKPOINT_DIR = Path(DATA_DIR) / "data" / "blockchain-event-bridge"
_CHECKPOINT_PATH = _CHECKPOINT_DIR / "contract_checkpoints.json"


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

    def _load_checkpoints(self) -> dict[str, int]:
        """Load persisted contract checkpoints if present."""
        from typing import cast

        try:
            if _CHECKPOINT_PATH.exists():
                with open(_CHECKPOINT_PATH, encoding="utf-8") as f:
                    return cast(dict[str, int], json.load(f))
        except Exception as e:
            logger.warning("Could not load contract checkpoints from %s: %s", _CHECKPOINT_PATH, e)
        return {}

    def _save_checkpoints(self) -> None:
        """Persist last processed block heights."""
        try:
            _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
            with open(_CHECKPOINT_PATH, "w", encoding="utf-8") as f:
                json.dump(self.last_processed_blocks, f)
        except Exception as e:
            logger.warning("Could not save contract checkpoints to %s: %s", _CHECKPOINT_PATH, e)

    async def _initialize_block_tracking(self) -> None:
        """Initialize block tracking from persisted checkpoints.

        ponytail: Previously reset to chain head on every startup, silently
        skipping events that arrived while the bridge was down. If no checkpoint
        exists we start a safe distance behind head; otherwise we resume from the
        last finalized height we processed.
        """
        try:
            client = await self._get_client()
            head_data = await client.get("/head")
            current_height = head_data.get("height", 0)
            safe_height = max(0, current_height - _FINALITY_BLOCKS)

            persisted = self._load_checkpoints()
            for contract in self.contract_addresses:
                if not self.contract_addresses[contract]:
                    continue
                if contract in persisted:
                    # Cap at the safe height so we always re-scan the finality window
                    self.last_processed_blocks[contract] = min(persisted[contract], safe_height)
                    logger.info(
                        "Resumed %s checkpoint at %s (head: %s)",
                        contract,
                        self.last_processed_blocks[contract],
                        current_height,
                    )
                else:
                    # First run: start behind head to avoid skipping recent history.
                    # A missing checkpoint means we cannot recover downtime from before this run.
                    self.last_processed_blocks[contract] = max(0, current_height - 100)
                    logger.warning(
                        "No checkpoint for %s; starting at %s (head: %s). Events before this height may have been missed.",
                        contract,
                        self.last_processed_blocks[contract],
                        current_height,
                    )
        except NetworkError as e:
            logger.error("Network error initializing block tracking: %s", e)
        except Exception as e:
            logger.error("Error initializing block tracking: %s", e)

    async def _poll_contract_events(self) -> None:
        """Poll for contract events from blockchain.

        ponytail: Only scans up to ``current_height - _FINALITY_BLOCKS`` before
        updating the checkpoint, keeping the last N blocks uncommitted so a chain
        reorg in the unprocessed window does not leave us with orphan events.
        """
        client = await self._get_client()
        for contract_name, contract_address in self.contract_addresses.items():
            if not contract_address:
                continue
            try:
                head_data = await client.get("/head")
                current_height = head_data.get("height", 0)
                to_block = max(0, current_height - _FINALITY_BLOCKS)
                last_height = self.last_processed_blocks.get(contract_name, to_block)

                if to_block <= last_height:
                    # Nothing new in the finalized range yet.
                    continue

                logs_data = await client.post(
                    "/eth_getLogs",
                    json={
                        "address": contract_address,
                        "from_block": last_height + 1,
                        "to_block": to_block,
                        "topics": self.event_topics.get(contract_name, []),
                    },
                )
                logs = logs_data.get("logs", [])
                if logs:
                    logger.info("Found %s events for %s", len(logs), contract_name)
                    for log in logs:
                        await self._process_contract_event(contract_name, log)
                self.last_processed_blocks[contract_name] = to_block
                self._save_checkpoints()
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
        self._save_checkpoints()
        logger.info("Contract event subscriber stopped")
