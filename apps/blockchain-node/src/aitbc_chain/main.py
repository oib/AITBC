import asyncio
import functools
import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from aitbc.async_tasks import TaskRegistry
from aitbc.network import IslandRegistry
from aitbc.sync import SyncSourceResolver

from .config import settings
from .consensus import PoAProposer, ProposerConfig
from .consensus.multi_validator_poa import get_consensus
from .database import init_db, session_scope
from .gossip import create_backend, gossip_broker
from .lease_tracker import lease_tracker
from .logger import get_logger
from .mempool import init_mempool
from .observability import register_exporters
from .sync import ChainSync
from .sync_manager import SyncManager
from .sync_manager_http import SyncManagerStatusServer

try:
    from .p2p_network import get_p2p_network
except ImportError:
    get_p2p_network = None  # type: ignore[assignment]

logger = get_logger("aitbc_chain.main")
create_island_manager: Callable[[str, str, str], "IslandManager"] | None
try:
    from .network.island_manager import IslandManager, create_island_manager

    _island_manager_available = True
except ImportError as e:
    logger.warning("Island manager module not available - island operations will be disabled: %s", e)
    _island_manager_available = False
    create_island_manager = None

# Multi-chain manager (v0.6.4)
_multi_chain_manager_available = False
create_multi_chain_manager: Callable[..., "MultiChainManager"] | None
try:
    from .network.multi_chain_manager import MultiChainManager, create_multi_chain_manager

    _multi_chain_manager_available = True
except ImportError as e:
    logger.warning("Multi-chain manager module not available: %s", e)
    _multi_chain_manager_available = False
    create_multi_chain_manager = None


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
    """Load a secp256k1 private key from the keystore.

    If target_address is given, find the keystore file with matching address.
    Otherwise, return the first key found.
    Supports both Ethereum encrypted keystore and simple wallet JSON formats.

    A file is only accepted if the key inside it derives to the address the file
    declares. Matching on the declared ``address`` alone is what let one key be
    labelled as three different identities on the deployed hub: `proposer.json` named
    the treasury while holding the block-signing key, so the node signed 12,353 blocks
    as an address it could not prove, and no follower could import any of them
    (V23-51..55). The file's own claim is the thing that was wrong, so it cannot also
    be the thing that is checked.
    """
    from aitbc.crypto.signature_recovery import canonical_address

    from .proposer_identity import address_of

    if not keystore_dir.exists():
        logger.warning("Keystore directory not found: %s", keystore_dir)
        return None
    for kf in keystore_dir.glob("*.json"):
        try:
            with open(kf) as f:
                data = json.load(f)
            addr = data.get("address")
            if target_address and canonical_address(str(addr or "")) != canonical_address(target_address):
                continue
            private_key_hex = data.get("private_key", "")
            if not private_key_hex:
                continue
            if data.get("encrypted", False):
                try:
                    from aitbc.crypto import decrypt_private_key

                    private_key_hex = decrypt_private_key(private_key_hex, password)
                except Exception as e:
                    logger.warning("Failed to decrypt wallet key in %s: %s", kf.name, e)
                    continue
            if private_key_hex.startswith("0x"):
                private_key_hex = private_key_hex[2:]

            if addr:
                derived = address_of(private_key_hex)
                if canonical_address(derived) != canonical_address(str(addr)):
                    logger.error(
                        "Keystore file %s is mislabelled: it declares %s but its key controls %s. "
                        "Refusing to use it — signing with it would produce blocks no peer can verify.",
                        kf.name,
                        addr,
                        derived,
                    )
                    continue

            return bytes.fromhex(private_key_hex)
        except Exception as e:
            logger.warning("Failed to load keystore file %s: %s: %s", kf.name, type(e).__name__, str(e))
            continue
    return None


if not settings.proposer_key:
    try:
        pwd = _load_keystore_password()
        key_bytes = _load_private_key_from_keystore(settings.keystore_path, pwd, target_address=settings.proposer_id)
        if key_bytes:
            settings.proposer_key = key_bytes.hex()
            logger.info("Loaded proposer private key from keystore", extra={"proposer_id": settings.proposer_id})
        else:
            logger.warning(
                "Proposer private key not found in keystore; block signing disabled",
                extra={"proposer_id": settings.proposer_id},
            )
    except Exception as e:
        logger.warning("Failed to load proposer key from keystore", extra={"error": str(e)})


FORCE_PULL_GAP = 3  # blocks behind the peer before a pull is forced despite push mode


def _pull_trigger(gap: int) -> str | None:
    """Classify our height against a peer's: "behind", "ahead", or None when push is keeping up.

    `gap` is `remote_height - local_height`. Only the positive side used to be examined, so a
    follower sitting 1,458 blocks *ahead* of a peer that had been reset to genesis read as being
    in sync and never pulled again — for 46 hours, across ~5,500 cycles (V23-90). Being ahead of
    the peer we follow is not a healthy state; it is either divergence or a peer that lost its
    history, and both need the pull path to look at hashes.
    """
    if gap >= FORCE_PULL_GAP:
        return "behind"
    if gap < 0:
        return "ahead"
    return None


class BlockchainNode:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._proposers: dict[str, PoAProposer] = {}
        self._task_registry = TaskRegistry()
        self._sync_source_resolver = SyncSourceResolver(
            sync_sources=settings.chain_sync_sources,
            default_url=settings.default_peer_rpc_url,
        )
        self._multi_chain_manager: MultiChainManager | None = None
        self._settlement_coordinators: list[Any] = []
        self._sync: ChainSync | None = None
        self._sync_manager: SyncManager | None = None
        self._sync_http_server: Any | None = None
        self._sync_http_task: asyncio.Task[Any] | None = None

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
        chains_str = getattr(settings, "supported_chains", settings.chain_id)
        chains = [c.strip() for c in chains_str.split(",") if c.strip()]
        if not chains and settings.chain_id:
            chains = [settings.chain_id]
        return chains

    def get_sync_source(self, chain_id: str) -> str | None:
        """Resolve sync source URL for a given chain_id.

        Uses the SyncSourceResolver to check per-chain mapping first,
        then falls back to default_peer_rpc_url.
        """
        return self._sync_source_resolver.get_sync_source(chain_id)

    def _proposer_config(self, chain_id: str) -> ProposerConfig:
        return ProposerConfig(
            chain_id=chain_id,
            proposer_id=settings.proposer_id,
            interval_seconds=settings.block_time_seconds,
            max_block_size_bytes=settings.max_block_size_bytes,
            max_txs_per_block=settings.max_txs_per_block,
            default_peer_rpc_url=settings.default_peer_rpc_url,
        )

    def _create_proposer(self, chain_id: str) -> PoAProposer:
        """Explicitly select and instantiate the block proposer for a chain.

        If multi-validator consensus is enabled and a validator_set is configured,
        the PoAProposer is given a MultiValidatorPoA engine. Otherwise it runs as
        a single proposer. The choice is logged at the top level so it is not
        hidden inside PoAProposer.
        """
        config = self._proposer_config(chain_id)
        consensus = None
        if settings.multi_validator_consensus_enabled and settings.validator_set:
            consensus = get_consensus(chain_id)
            logger.info("Multi-validator consensus selected for chain %s", chain_id)
        elif settings.multi_validator_consensus_enabled:
            logger.warning(
                "multi_validator_consensus_enabled is True but validator_set is empty; "
                "falling back to single proposer for chain %s",
                chain_id,
            )
        else:
            logger.info("Single PoA proposer selected for chain %s", chain_id)
        return PoAProposer(
            config=config,
            session_factory=lambda chain_id=chain_id: session_scope(chain_id),  # type: ignore[misc]
            consensus=consensus,
            sync_manager=self._sync_manager,
        )

    async def _ensure_genesis_for_chains(self) -> None:
        for chain_id in self._supported_chains():
            proposer = self._create_proposer(chain_id)
            await proposer._ensure_genesis_block()

    async def _bootstrap_genesis_for_follower(self) -> None:
        """Build block 0 locally instead of syncing it from the hub (V23-59).

        A follower could not reach height 1 from an empty database. It had no genesis of its
        own, so block 0 had to arrive over sync — and block 0 is unsigned by construction
        (``proposer="genesis"``), which ``sync_validator`` refuses unless ``TRUSTED_PROPOSERS``
        is non-empty. Setting it to admit one unsigned block turns it into an allowlist for
        *every* block thereafter, so the price of bootstrapping was permanently weakened
        validation on the node doing the bootstrapping.

        Nothing is trusted by doing this. ``_ensure_genesis_block`` takes the hash and
        state_root from genesis.json (or the hub's RPC bootstrap) rather than recomputing
        them, so the block written here is the hub's block 0 or it is nothing: a mismatched
        genesis.json produces a different hash, and the first synced block fails its
        parent_hash check immediately rather than silently forking.

        Failure is logged, not raised. Followers that already sync with ``TRUSTED_PROPOSERS``
        set and no local genesis.json keep working exactly as before.
        """
        try:
            await self._ensure_genesis_for_chains()
        except Exception as exc:
            logger.error(
                "Could not bootstrap genesis locally: %s. Falling back to syncing block 0 from the hub, "
                "which requires TRUSTED_PROPOSERS to include 'genesis'. Supply genesis.json to avoid that.",
                exc,
            )

    async def _setup_gossip_subscribers(self) -> None:
        logger.info("Setting up gossip subscribers")
        chains = self._supported_chains()
        # v0.6.2: Subscribe to chain-specific transaction topics for v0.6.3 readiness.
        # Also subscribe to legacy "transactions" topic for backward compatibility.
        tx_subs: list[Any] = []
        try:
            # Legacy global topic (backward compat with v0.6.1 peers)
            if settings.gossip_backward_compat:
                legacy_sub = await gossip_broker.subscribe("transactions")
                tx_subs.append(legacy_sub)
                logger.info("Subscribed to legacy transactions topic (backward compat)")
            # Chain-specific topics (v0.6.3-ready)
            for chain_id in chains:
                chain_topic = f"transactions.{chain_id}"
                try:
                    chain_sub = await gossip_broker.subscribe(chain_topic)
                    tx_subs.append(chain_sub)
                    logger.info("Subscribed to %s topic", chain_topic)
                except Exception as e:
                    logger.warning("Failed to subscribe to %s: %s", chain_topic, e)
            if not tx_subs:
                logger.error("Failed to subscribe to any transaction topic")
                return
        except Exception as e:
            logger.error("Failed to subscribe to transactions: %s", e)
            return

        async def process_txs() -> None:
            from .rpc.utils import normalize_transaction_data

            from .mempool import get_mempool as get_mempool_instance

            mempool = get_mempool_instance()
            while True:
                try:
                    # Round-robin across all transaction subscriptions
                    for tx_sub in tx_subs:
                        try:
                            tx_data = await asyncio.wait_for(tx_sub.queue.get(), timeout=0.01)
                        except TimeoutError:
                            continue
                        if isinstance(tx_data, str):
                            import json

                            tx_data = json.loads(tx_data)
                        if not isinstance(tx_data, dict):
                            continue
                        # Unwrap P2P-style transaction envelopes and drop control
                        # messages (ping/pong) that may be delivered to the
                        # transaction topic by generic websocket gossip clients.
                        msg_type = tx_data.get("type")
                        if msg_type == "new_transaction":
                            tx_data = tx_data.get("tx") or {}
                        elif msg_type in ("ping", "pong"):
                            continue
                        if not isinstance(tx_data, dict) or not tx_data.get("from"):
                            logger.debug(
                                "Ignoring non-transaction gossip message on %s: %s",
                                getattr(tx_sub, "topic", "unknown"),
                                tx_data,
                            )
                            continue
                        chain_id = tx_data.get("chain_id", settings.chain_id)
                        tx_data = normalize_transaction_data(tx_data, chain_id)
                        mempool.add(tx_data, chain_id=chain_id)
                except Exception as exc:
                    logger.error("Error processing transaction from gossip: %s", exc)

        self._task_registry.create_task(process_txs, name="gossip_process_txs")
        # Block subscriptions are now owned by SyncManager.

        # v0.7.7: Subscribe to PBFT gossip topics for each chain that has PBFT enabled.
        for chain_id in chains:
            proposer = self._proposers.get(chain_id)
            if proposer and proposer.pbft_consensus:
                for phase in ("pre_prepare", "prepare", "commit"):
                    pbft_topic = f"pbft.{phase}.{chain_id}"
                    try:
                        pbft_sub = await gossip_broker.subscribe(pbft_topic)
                        logger.info("Successfully subscribed to %s topic", pbft_topic)

                        async def process_pbft(
                            topic_param: str = pbft_topic,
                            sub_param: Any = pbft_sub,
                            pbft: Any = proposer.pbft_consensus,
                        ) -> None:
                            logger.info("PBFT gossip task started for %s", topic_param)
                            while True:
                                try:
                                    msg = await sub_param.queue.get()
                                    if isinstance(msg, str):
                                        import json

                                        msg = json.loads(msg)
                                    await pbft.handle_incoming_message(msg)
                                except Exception as exc:
                                    logger.error("Error processing PBFT message from %s: %s", topic_param, exc)

                        self._task_registry.create_task(
                            functools.partial(process_pbft, pbft_topic, pbft_sub, proposer.pbft_consensus),
                            name=f"gossip_pbft_{phase}_{chain_id}",
                        )
                    except Exception as e:
                        logger.error("Failed to subscribe to %s: %s", pbft_topic, e)

        logger.info("Gossip subscribers setup completed")

    async def start(self) -> None:
        logger.info(
            "Starting blockchain node", extra={"supported_chains": getattr(settings, "supported_chains", settings.chain_id)}
        )
        register_exporters(["prometheus"])
        backend = create_backend(
            settings.gossip_backend,
            broadcast_url=settings.gossip_broadcast_url,
            websocket_url=settings.gossip_websocket_url,
            mesh_peer_urls=settings.mesh_peer_url_list(),
        )
        logger.info(
            "Initializing gossip backend: %s, url: %s, mesh peers: %s",
            settings.gossip_backend,
            settings.gossip_broadcast_url,
            settings.mesh_peer_url_list(),
        )
        await gossip_broker.set_backend(backend)
        logger.info("Gossip backend initialized successfully")
        chains = self._supported_chains()
        logger.info("Initializing databases for chains: %s", chains)
        for chain_id in chains:
            init_db(chain_id)
            logger.info("Initialized database for chain: %s", chain_id)

        if settings.sync_manager_enabled:
            use_gossip = settings.sync_manager_use_gossip
            use_subscription = settings.sync_manager_use_subscription
            if settings.blockchain_mode == "hub" and not settings.multi_validator_consensus_enabled:
                use_gossip = False
                use_subscription = False
            self._sync_manager = SyncManager(
                chains=chains,
                node_id=os.getenv("NODE_ID", settings.p2p_node_id or "unknown-node"),
                proposer_id=settings.proposer_id,
                production_chains=self._block_production_chains(),
                use_gossip=use_gossip,
                use_subscription=use_subscription and settings.subscription_enabled,
                own_gossip=False,
                skip_init_db=True,
            )
            await self._sync_manager.start()

            if settings.sync_manager_http_enabled:
                self._sync_http_server = SyncManagerStatusServer(
                    self._sync_manager,
                    host=settings.sync_manager_http_host,
                    port=settings.sync_manager_http_port,
                )
                self._sync_http_task = asyncio.create_task(
                    self._sync_http_server.start(),
                    name="sync_manager_http_server",
                )
                logger.info(
                    "SyncManager HTTP status server listening on %s:%s",
                    settings.sync_manager_http_host,
                    settings.sync_manager_http_port,
                )
        else:
            logger.info("SyncManager disabled by sync_manager_enabled=false")

        init_mempool(
            backend=settings.mempool_backend,
            db_url=settings.mempool_db_url,
            max_size=settings.mempool_max_size,
            min_fee=settings.min_fee,
        )
        if _island_manager_available and create_island_manager is not None:
            try:
                node_id = os.getenv("NODE_ID", "unknown-node")
                default_island_id = os.getenv("DEFAULT_ISLAND_ID", f"{self._supported_chains()[0]}-island")
                default_chain_id = self._supported_chains()[0]
                logger.info(
                    "Creating island manager with node_id=%s, default_island=%s, default_chain=%s",
                    node_id,
                    default_island_id,
                    default_chain_id,
                )
                island_mgr = create_island_manager(node_id, default_island_id, default_chain_id)
                logger.info("Island manager created successfully")

                # Auto-join islands from bridge_islands config
                if settings.bridge_islands:
                    registry = IslandRegistry(settings.island_registry)
                    bridge_island_ids = [i.strip() for i in settings.bridge_islands.split(",") if i.strip()]
                    for island_id in bridge_island_ids:
                        entry = registry.get_entry(island_id)
                        if entry:
                            island_mgr.join_island(
                                island_id=entry.island_id,
                                island_name=entry.island_name,
                                chain_id=entry.chain_id,
                                is_hub=False,
                            )
                            logger.info("Auto-joined island %s (chain: %s)", entry.island_id, entry.chain_id)
                        else:
                            logger.warning("Island %s in bridge_islands but not in island_registry", island_id)

                # Start background tasks if enabled
                if settings.island_tasks_enabled:
                    self._task_registry.create_task(island_mgr.start, name="island_manager_tasks")
                    logger.info("Island manager background tasks started")
                else:
                    logger.info(
                        "Island manager initialized (background tasks disabled)",
                        extra={"node_id": node_id, "default_island": default_island_id},
                    )
            except Exception as e:
                logger.error("Failed to initialize island manager: %s", e)
        else:
            logger.warning("Island manager not available - island operations will be disabled")
        # v0.6.2: Wire P2P peer capability callback to sync peer tracker.
        # When the P2P service runs in-process, discovered peers are registered
        # with the ChainSync PeerCapabilityTracker, enabling parallel sync.
        if get_p2p_network is not None:
            p2p_service = get_p2p_network()
            if p2p_service is not None:
                try:
                    default_chain = self._supported_chains()[0] if self._supported_chains() else settings.chain_id
                    if self._sync_manager is not None:
                        p2p_service.set_peer_capability_callback(
                            lambda peer_id, rpc_url, block_range, has_state=True, chain_id=None: (
                                self._sync_manager.register_sync_peer(
                                    chain_id or default_chain, peer_id, rpc_url, block_range, has_state
                                )
                            )
                        )
                    else:
                        self._sync = ChainSync(session_factory=lambda: session_scope(default_chain), chain_id=default_chain)
                        p2p_service.set_peer_capability_callback(
                            lambda peer_id, rpc_url, block_range, has_state=True, chain_id=None: self._sync.register_sync_peer(
                                peer_id, rpc_url, block_range, has_state
                            )
                        )
                    logger.info("P2P peer capability callback wired to SyncManager")
                except Exception as e:
                    logger.warning("Failed to wire P2P peer capability callback: %s", e)
            else:
                logger.debug("P2P service not available in-process — peer capability callback not wired")
        # Multi-chain manager: start secondary chains from island_chains config (v0.6.4)
        if _multi_chain_manager_available and create_multi_chain_manager is not None:
            try:
                default_chain_id = self._supported_chains()[0]
                base_db_path = Path(settings.get_db_path(default_chain_id))
                self._multi_chain_manager = create_multi_chain_manager(
                    default_chain_id=default_chain_id,
                    base_db_path=base_db_path,
                    base_rpc_port=int(os.getenv("RPC_PORT", "8202")),
                    base_p2p_port=int(os.getenv("P2P_PORT", "8007")),
                )
                # Start secondary chains (default chain is managed by main proposer logic)
                await self._multi_chain_manager.start_secondary_chains()
                # Start health check background task
                self._task_registry.create_task(self._multi_chain_manager.start, name="multi_chain_manager")
                logger.info("Multi-chain manager initialized and secondary chains started")
            except Exception as e:
                logger.error("Failed to initialize multi-chain manager: %s", e)
        is_validator_node = (
            settings.multi_validator_consensus_enabled
            and settings.validator_set
            and settings.proposer_id
            and settings.proposer_key
        )
        if settings.blockchain_mode == "hub" or is_validator_node:
            logger.info(
                "Running as block producer (blockchain_mode=%s, multi_validator=%s)",
                settings.blockchain_mode,
                settings.multi_validator_consensus_enabled,
            )
            await self._ensure_genesis_for_chains()
            self._start_proposers()
            await lease_tracker.start()
            logger.info("Lease tracker started on producer node")
        elif settings.blockchain_mode == "follower":
            logger.info("Running in FOLLOWER mode (blockchain_mode=%s)", settings.blockchain_mode)
            logger.info("Block production disabled on this node", extra={"proposer_id": settings.proposer_id})
            await self._bootstrap_genesis_for_follower()
        else:
            logger.warning("Unknown blockchain_mode: %s, defaulting to follower behavior", settings.blockchain_mode)
        # Settlement timeout monitor: refunds escrows stuck in non-terminal
        # states (incl. any that timed out while the node was down).
        if settings.escrow_enabled:
            from .cross_chain.settlement_coordinator import AtomicSettlementCoordinator

            for chain_id in self._supported_chains():
                coordinator = AtomicSettlementCoordinator(chain_id=chain_id)
                await coordinator.start_monitor()
                self._settlement_coordinators.append(coordinator)
            logger.info("Settlement timeout monitors started for %d chains", len(self._settlement_coordinators))
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
        # Checked here rather than at import: this is the point where the node commits to
        # appending blocks, and a node that never proposes must not be blocked by it.
        from .proposer_identity import assert_can_sign

        assert_can_sign(settings.proposer_id, settings.proposer_key, settings.keystore_path)

        chains = self._supported_chains()
        production_chains_str = self._env_value(
            "AITBC_FORCE_BLOCK_PRODUCTION_CHAINS", "BLOCK_PRODUCTION_CHAINS", "block_production_chains"
        )
        if not production_chains_str:
            production_chains_str = settings.block_production_chains or ",".join(chains)
        production_chains = [c.strip() for c in production_chains_str.split(",") if c.strip()]
        for chain_id in chains:
            if chain_id not in production_chains:
                logger.info("Skipping block production for chain %s (not in block_production_chains)", chain_id)
                continue
            if chain_id in self._proposers:
                continue

            proposer = self._create_proposer(chain_id)
            self._proposers[chain_id] = proposer
            self._task_registry.create_task(proposer.start, name=f"proposer_{chain_id}")

    def _block_production_chains(self) -> list[str]:
        """Return the list of chains this node is configured to produce blocks for."""
        chains_str = self._env_value(
            "AITBC_FORCE_BLOCK_PRODUCTION_CHAINS", "BLOCK_PRODUCTION_CHAINS", "block_production_chains"
        )
        if chains_str is None:
            chains_str = getattr(settings, "block_production_chains", "")
        return [c.strip() for c in (chains_str or "").split(",") if c.strip()]

    # Sync source resolution and periodic pull logic now live in SyncManager.

    async def _shutdown(self) -> None:
        logger.info("Shutting down blockchain node, cancelling background tasks...")
        if self._sync_http_server is not None:
            try:
                self._sync_http_server.stop()
            except Exception as e:
                logger.error("Error stopping sync manager HTTP server: %s", e)
        if self._sync_http_task is not None:
            try:
                await self._sync_http_task
            except Exception as e:
                logger.error("Error waiting for sync manager HTTP task: %s", e)
        if self._sync_manager is not None:
            try:
                await self._sync_manager.stop()
            except Exception as e:
                logger.error("Error stopping sync manager: %s", e)
        # Stop multi-chain manager (stops all secondary chains gracefully)
        if self._multi_chain_manager is not None:
            try:
                await self._multi_chain_manager.stop()
            except Exception as e:
                logger.error("Error stopping multi-chain manager: %s", e)
        await self._task_registry.cancel_all(timeout=10.0)
        for coordinator in self._settlement_coordinators:
            try:
                await coordinator.stop_monitor()
            except Exception as e:
                logger.error("Error stopping settlement monitor: %s", e)
        self._settlement_coordinators.clear()
        for _chain_id, proposer in list(self._proposers.items()):
            await proposer.stop()
        self._proposers.clear()
        await gossip_broker.shutdown()
        await lease_tracker.stop()


@asynccontextmanager
async def node_app() -> AsyncIterator[BlockchainNode]:
    node: BlockchainNode = BlockchainNode()
    try:
        yield node
    finally:
        await node.stop()


def run() -> None:
    from aitbc.aitbc_logging import configure_logging

    configure_logging(level="INFO")
    asyncio.run(_run())


async def _run() -> None:
    async with node_app() as node:
        await node.start()


if __name__ == "__main__":
    run()
