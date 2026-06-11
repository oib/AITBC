# mypy: ignore-errors
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from .config import settings
from .consensus import PoAProposer, ProposerConfig
from .database import init_db, session_scope
from .gossip import create_backend, gossip_broker
from .lease_tracker import lease_tracker
from .logger import get_logger
from .mempool import init_mempool
from .subscription_client import SubscriptionClient
from .sync import ChainSync

logger = get_logger("aitbc_chain.main")

# Try to import island manager - may fail if module has issues
try:
    from .network.island_manager import create_island_manager
    _island_manager_available = True
except ImportError as e:
    logger.warning(f"Island manager module not available - island operations will be disabled: {e}")
    _island_manager_available = False
    create_island_manager = None

def _load_keystore_password() -> str:
    """Load keystore password from file or environment."""
    pwd_file = settings.keystore_password_file
    if pwd_file.exists():
        return pwd_file.read_text().strip()
    env_pwd = os.getenv("KEYSTORE_PASSWORD")
    if env_pwd:
        return env_pwd
    raise RuntimeError(f"Keystore password not found. Set in {pwd_file} or KEYSTORE_PASSWORD env.")

def _load_private_key_from_keystore(keystore_dir: Path, password: str, target_address: str | None = None) -> bytes | None:
    """Load an ed25519 private key from the keystore.
    If target_address is given, find the keystore file with matching address.
    Otherwise, return the first key found.
    Supports both Ethereum encrypted keystore and simple wallet JSON formats.
    """
    if not keystore_dir.exists():
        logger.warning(f"Keystore directory not found: {keystore_dir}")
        return None
    for kf in keystore_dir.glob("*.json"):
        try:
            with open(kf) as f:
                data = json.load(f)
            addr = data.get("address")
            if target_address and addr != target_address:
                continue
            private_key_hex = data.get("private_key", "")
            if not private_key_hex:
                continue
            # Handle encrypted private keys (from wallet daemon)
            if data.get("encrypted", False):
                try:
                    from aitbc.crypto import decrypt_private_key
                    private_key_hex = decrypt_private_key(private_key_hex, password)
                except Exception as e:
                    logger.warning(f"Failed to decrypt wallet key in {kf.name}: {e}")
                    continue
            # Convert hex string to bytes
            if private_key_hex.startswith("0x"):
                private_key_hex = private_key_hex[2:]
            return bytes.fromhex(private_key_hex)
        except Exception as e:
            logger.warning(f"Failed to load keystore file {kf.name}: {type(e).__name__}: {str(e)}")
            continue
    return None

# Attempt to load proposer private key from keystore if not set
if not settings.proposer_key:
    try:
        pwd = _load_keystore_password()
        key_bytes = _load_private_key_from_keystore(settings.keystore_path, pwd, target_address=settings.proposer_id)
        if key_bytes:
            # Encode as hex for easy storage; not yet used for signing
            settings.proposer_key = key_bytes.hex()
            logger.info("Loaded proposer private key from keystore", extra={"proposer_id": settings.proposer_id})
        else:
            logger.warning("Proposer private key not found in keystore; block signing disabled", extra={"proposer_id": settings.proposer_id})
    except Exception as e:
        logger.warning("Failed to load proposer key from keystore", extra={"error": str(e)})


class BlockchainNode:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._proposers: dict[str, PoAProposer] = {}

    @staticmethod
    def _env_value(*names: str) -> str | None:
        for name in names:
            value = os.getenv(name)
            if value is not None:
                return value
        return None

    def _block_production_enabled(self) -> bool:
        override = self._env_value("AITBC_FORCE_ENABLE_BLOCK_PRODUCTION", "ENABLE_BLOCK_PRODUCTION", "enable_block_production")
        if override is not None:
            return override.strip().lower() in {"1", "true", "yes", "on"}
        return bool(getattr(settings, "enable_block_production", True))

    def _supported_chains(self) -> list[str]:
        chains_str = getattr(settings, 'supported_chains', settings.chain_id)
        chains = [c.strip() for c in chains_str.split(",") if c.strip()]
        if not chains and settings.chain_id:
            chains = [settings.chain_id]
        return chains

    def _proposer_config(self, chain_id: str) -> ProposerConfig:
        return ProposerConfig(
            chain_id=chain_id,
            proposer_id=settings.proposer_id,
            interval_seconds=settings.block_time_seconds,
            max_block_size_bytes=settings.max_block_size_bytes,
            max_txs_per_block=settings.max_txs_per_block,
            default_peer_rpc_url=settings.default_peer_rpc_url,
        )

    async def _ensure_genesis_for_chains(self) -> None:
        for chain_id in self._supported_chains():
            proposer = PoAProposer(config=self._proposer_config(chain_id), session_factory=lambda cid=chain_id: session_scope(cid))
            await proposer._ensure_genesis_block()

    async def _setup_gossip_subscribers(self) -> None:
        logger.info("Setting up gossip subscribers")

        # Parse supported chains
        chains = self._supported_chains()

        # Transactions (single topic for all chains)
        try:
            tx_sub = await gossip_broker.subscribe("transactions")
            logger.info("Successfully subscribed to transactions topic")
        except Exception as e:
            logger.error(f"Failed to subscribe to transactions: {e}")
            return

        async def process_txs():
            from .mempool import get_mempool
            from .rpc.utils import normalize_transaction_data
            mempool = get_mempool()
            while True:
                try:
                    tx_data = await tx_sub.queue.get()
                    if isinstance(tx_data, str):
                        import json
                        tx_data = json.loads(tx_data)
                    chain_id = tx_data.get("chain_id", settings.chain_id)
                    # Normalize transaction data to ensure type field is preserved
                    tx_data = normalize_transaction_data(tx_data, chain_id)
                    mempool.add(tx_data, chain_id=chain_id)
                except Exception as exc:
                    logger.error(f"Error processing transaction from gossip: {exc}")

        asyncio.create_task(process_txs())

        # Blocks (chain-specific topics for each chain)
        for chain_id in chains:
            try:
                block_topic = f"blocks.{chain_id}"
                block_sub = await gossip_broker.subscribe(block_topic)
                logger.info(f"Successfully subscribed to {block_topic} topic")

                async def process_blocks_for_chain(chain_id_param=chain_id, block_sub_param=block_sub):
                    last_bulk_sync_time = 0
                    logger.info(f"Block processing task started for chain {chain_id_param}")
                    while True:
                        try:
                            block_data = await block_sub_param.queue.get()
                            if isinstance(block_data, str):
                                import json
                                block_data = json.loads(block_data)

                            # Skip self-proposed blocks (hub node doesn't need to import its own blocks)
                            block_proposer = block_data.get("proposer", "")
                            if block_proposer and block_proposer == settings.proposer_id:
                                logger.debug(f"Skipping self-proposed block {block_data.get('height')} from gossip")
                                continue

                            logger.info(f"Received block from gossip for chain {chain_id_param}")
                            logger.info(f"Importing block for chain {chain_id_param}: {block_data.get('height')}")
                            sync = ChainSync(session_factory=lambda cid=chain_id_param: session_scope(cid), chain_id=chain_id_param)
                            res = sync.import_block(block_data, transactions=block_data.get("transactions"))
                            logger.info(f"Import result: accepted={res.accepted}, reason={res.reason}")

                            # Automatic bulk sync on gap detection
                            if not res.accepted and "Gap detected" in res.reason and settings.auto_sync_enabled:
                                # Parse gap size from reason string
                                try:
                                    reason_parts = res.reason.split(":")
                                    our_height = int(reason_parts[1].strip().split(",")[0].replace("our height: ", ""))
                                    received_height = int(reason_parts[2].strip().replace("received: ", "").replace(")", ""))
                                    gap_size = received_height - our_height

                                    if gap_size > settings.auto_sync_threshold:
                                        current_time = asyncio.get_event_loop().time()
                                        time_since_last_sync = current_time - last_bulk_sync_time

                                        if time_since_last_sync >= settings.min_bulk_sync_interval:
                                            logger.warning(f"Gap detected: {gap_size} blocks, triggering automatic bulk sync (chain={chain_id_param})")

                                            # Get source URL from block metadata if available
                                            source_url = block_data.get("source_url")
                                            if not source_url:
                                                # Fallback to default peer RPC URL
                                                source_url = settings.default_peer_rpc_url

                                            if source_url:
                                                try:
                                                    imported = await sync.bulk_import_from(source_url)
                                                    logger.info(f"Bulk sync completed: {imported} blocks imported (chain={chain_id_param})")
                                                    last_bulk_sync_time = current_time

                                                    # Retry block import after bulk sync
                                                    res = sync.import_block(block_data, transactions=block_data.get("transactions"))
                                                    logger.info(f"Retry import result: accepted={res.accepted}, reason={res.reason}")
                                                except Exception as sync_exc:
                                                    logger.error(f"Automatic bulk sync failed: {sync_exc}")
                                            else:
                                                logger.warning("No source URL available for bulk sync")
                                        else:
                                            logger.info(f"Skipping bulk sync, too recent ({time_since_last_sync:.0f}s ago)")
                                except (ValueError, IndexError) as parse_exc:
                                    logger.error(f"Failed to parse gap size from reason: {res.reason}, error: {parse_exc}")
                        except Exception as exc:
                            logger.error(f"Error processing block from gossip for chain {chain_id}: {exc}")

                asyncio.create_task(process_blocks_for_chain(chain_id_param=chain_id, block_sub_param=block_sub))
            except Exception as e:
                logger.error(f"Failed to subscribe to blocks.{chain_id}: {e}")

        logger.info("Gossip subscribers setup completed")

    async def start(self) -> None:
        logger.info("Starting blockchain node", extra={"supported_chains": getattr(settings, 'supported_chains', settings.chain_id)})

        # Initialize Gossip Backend
        backend = create_backend(
            settings.gossip_backend,
            broadcast_url=settings.gossip_broadcast_url,
        )
        logger.info(f"Initializing gossip backend: {settings.gossip_backend}, url: {settings.gossip_broadcast_url}")
        await gossip_broker.set_backend(backend)
        logger.info("Gossip backend initialized successfully")

        # Parse supported chains
        chains = self._supported_chains()
        logger.info(f"Initializing databases for chains: {chains}")

        # Initialize database for each supported chain
        for chain_id in chains:
            init_db(chain_id)
            logger.info(f"Initialized database for chain: {chain_id}")

        init_mempool(
            backend=settings.mempool_backend,
            db_url=settings.mempool_db_url,
            max_size=settings.mempool_max_size,
            min_fee=settings.min_fee,
        )

        # Initialize island manager for edge API support
        if _island_manager_available and create_island_manager:
            try:
                node_id = os.getenv("NODE_ID", "unknown-node")
                default_island_id = os.getenv("DEFAULT_ISLAND_ID", f"{self._supported_chains()[0]}-island")
                default_chain_id = self._supported_chains()[0]
                logger.info(f"Creating island manager with node_id={node_id}, default_island={default_island_id}, default_chain={default_chain_id}")
                island_manager = create_island_manager(node_id, default_island_id, default_chain_id)
                logger.info("Island manager created successfully")
                logger.info("Island manager initialized (background tasks disabled)", extra={"node_id": node_id, "default_island": default_island_id})
            except Exception as e:
                logger.error(f"Failed to initialize island manager: {e}", exc_info=True)
        else:
            logger.warning("Island manager not available - island operations will be disabled")

        # Start services based on blockchain_mode profile
        if settings.blockchain_mode == "hub":
            # Hub mode: enable block production and lease tracker
            logger.info(f"Running in HUB mode (blockchain_mode={settings.blockchain_mode})")
            await self._ensure_genesis_for_chains()
            self._start_proposers()
            await lease_tracker.start()
            logger.info("Lease tracker started on hub node")
        elif settings.blockchain_mode == "follower":
            # Follower mode: enable periodic sync and subscription client
            logger.info(f"Running in FOLLOWER mode (blockchain_mode={settings.blockchain_mode})")
            logger.info("Block production disabled on this node", extra={"proposer_id": settings.proposer_id})

            # Start subscription client for followers
            subscription_client = None
            if settings.subscription_enabled:
                node_id = os.getenv("NODE_ID", settings.p2p_node_id or "unknown-node")
                hub_url = settings.default_peer_rpc_url or settings.genesis_node
                chain_id = self._supported_chains()[0]

                if hub_url:
                    subscription_client = SubscriptionClient(hub_url, node_id, chain_id)
                    asyncio.create_task(subscription_client.start())
                    logger.info(f"Subscription client started for node {node_id}")
                else:
                    logger.warning("Subscription client not started: no hub URL configured")

            # Start periodic pull sync for followers (fallback when WebSocket push is unavailable)
            if settings.periodic_sync_enabled:
                asyncio.create_task(self._periodic_sync_task(subscription_client))
        else:
            logger.warning(f"Unknown blockchain_mode: {settings.blockchain_mode}, defaulting to follower behavior")

        await self._setup_gossip_subscribers()
        try:
            await self._stop_event.wait()
        finally:
            await self._shutdown()

    async def stop(self) -> None:
        logger.info("Stopping blockchain node")
        self._stop_event.set()
        await self._shutdown()

    def _start_proposers(self) -> None:
        chains = self._supported_chains()

        # Get chains that should produce blocks (if specified, otherwise all supported chains)
        production_chains_str = self._env_value("AITBC_FORCE_BLOCK_PRODUCTION_CHAINS", "BLOCK_PRODUCTION_CHAINS", "block_production_chains")
        if production_chains_str is None:
            production_chains_str = getattr(settings, 'block_production_chains', ",".join(chains))
        production_chains = [c.strip() for c in production_chains_str.split(",") if c.strip()]

        for chain_id in chains:
            # Only start proposer if chain is in production chains
            if chain_id not in production_chains:
                logger.info(f"Skipping block production for chain {chain_id} (not in block_production_chains)")
                continue

            if chain_id in self._proposers:
                continue

            proposer = PoAProposer(config=self._proposer_config(chain_id), session_factory=lambda cid=chain_id: session_scope(cid))
            self._proposers[chain_id] = proposer
            asyncio.create_task(proposer.start())

    async def _periodic_sync_task(self, subscription_client=None) -> None:
        """Periodic pull sync task for follower nodes. Skips pull when WebSocket push is active."""
        chains = self._supported_chains()
        sync_interval = settings.periodic_sync_interval
        source_url = settings.default_peer_rpc_url or settings.genesis_node

        if not source_url:
            logger.warning("Periodic sync disabled: no default_peer_rpc_url or genesis_node configured")
            return

        logger.info(f"Starting periodic sync task (interval={sync_interval}s, source={source_url})")

        while not self._stop_event.is_set():
            try:
                # Skip pull sync when WebSocket push is active
                if subscription_client and subscription_client.get_sync_mode() == "push":
                    logger.debug("Skipping periodic pull: WebSocket push is active")
                else:
                    logger.info("Sync mode: pull (periodic, WebSocket push unavailable)")
                    for chain_id in chains:
                        try:
                            sync = ChainSync(session_factory=lambda cid=chain_id: session_scope(cid), chain_id=chain_id)
                            imported = await sync.bulk_import_from(source_url)
                            if imported > 0:
                                logger.info(f"Periodic sync imported {imported} blocks for chain {chain_id}")
                        except Exception as e:
                            logger.error(f"Periodic sync failed for chain {chain_id}: {e}")
            except Exception as e:
                logger.error(f"Periodic sync task error: {e}")

            # Wait for interval or stop event
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sync_interval)
                break
            except asyncio.TimeoutError:
                continue

    async def _shutdown(self) -> None:
        for chain_id, proposer in list(self._proposers.items()):
            await proposer.stop()
        self._proposers.clear()
        await gossip_broker.shutdown()
        await lease_tracker.stop()


@asynccontextmanager
async def node_app() -> asyncio.AbstractAsyncContextManager[BlockchainNode]:  # type: ignore[override]
    node = BlockchainNode()
    try:
        yield node
    finally:
        await node.stop()


def run() -> None:
    asyncio.run(_run())


async def _run() -> None:
    async with node_app() as node:
        await node.start()


if __name__ == "__main__":  # pragma: no cover
    run()
