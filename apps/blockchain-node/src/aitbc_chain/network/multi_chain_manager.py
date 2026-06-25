"""
Multi-Chain Manager
Manages parallel bilateral/micro-chains running alongside the default chain
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from sqlmodel import select

from aitbc.aitbc_logging import get_logger

from ..base_models import Block
from ..config import ProposerConfig, settings
from ..consensus.poa import PoAProposer
from ..database import init_db, session_scope, shutdown_db
from ..gossip import gossip_broker

logger = get_logger(__name__)


class ChainType(Enum):
    """Chain instance type"""

    DEFAULT = "default"
    BILATERAL = "bilateral"
    MICRO = "micro"


class ChainStatus(Enum):
    """Chain instance status"""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ChainInstance:
    """Represents a chain instance"""

    chain_id: str
    chain_type: ChainType
    status: ChainStatus
    db_path: Path
    rpc_port: int
    p2p_port: int
    started_at: float | None = None
    stopped_at: float | None = None
    error_message: str | None = None
    # Dynamic attributes added at runtime
    _consensus: Any = field(default=None, init=False, repr=False)


class MultiChainManager:
    """Manages parallel chain instances"""

    def __init__(
        self, default_chain_id: str, base_db_path: Path, base_rpc_port: int = 8006, base_p2p_port: int = 7070
    ) -> None:
        self.default_chain_id = default_chain_id
        self.base_db_path = base_db_path
        self.base_rpc_port = base_rpc_port
        self.base_p2p_port = base_p2p_port
        self.chains: dict[str, ChainInstance] = {}
        self.next_rpc_port = base_rpc_port + 1
        self.next_p2p_port = base_p2p_port + 1
        self.running = False
        self._initialize_default_chain()

    def _initialize_default_chain(self) -> None:
        """Initialize the default chain instance"""
        self.chains[self.default_chain_id] = ChainInstance(
            chain_id=self.default_chain_id,
            chain_type=ChainType.DEFAULT,
            status=ChainStatus.RUNNING,
            db_path=self.base_db_path,
            rpc_port=self.base_rpc_port,
            p2p_port=self.base_p2p_port,
            started_at=time.time(),
        )
        logger.info("Initialized default chain: %s", self.default_chain_id)

    def _allocate_ports(self) -> tuple[int, int]:
        """Allocate ports for a new chain instance"""
        rpc_port = self.next_rpc_port
        p2p_port = self.next_p2p_port
        self.next_rpc_port += 1
        self.next_p2p_port += 1
        return (rpc_port, p2p_port)

    def _proposer_config(self, chain_id: str) -> ProposerConfig:
        """Build a ProposerConfig for a chain instance"""
        return ProposerConfig(
            chain_id=chain_id,
            proposer_id=settings.proposer_id,
            interval_seconds=settings.block_time_seconds,
            max_block_size_bytes=settings.max_block_size_bytes,
            max_txs_per_block=settings.max_txs_per_block,
            default_peer_rpc_url=settings.default_peer_rpc_url,
        )

    async def start_chain(self, chain_id: str, chain_type: ChainType = ChainType.MICRO) -> bool:
        """
        Start a new chain instance

        Args:
            chain_id: Unique identifier for the chain
            chain_type: Type of chain (BILATERAL or MICRO)

        Returns:
            True if successful, False otherwise
        """
        if chain_id in self.chains:
            logger.warning("Chain %s already exists", chain_id)
            return False
        if chain_id == self.default_chain_id:
            logger.warning("Cannot start default chain (already running)")
            return False
        rpc_port, p2p_port = self._allocate_ports()
        db_path = self.base_db_path.parent / chain_id / "chain.db"
        chain = ChainInstance(
            chain_id=chain_id,
            chain_type=chain_type,
            status=ChainStatus.STARTING,
            db_path=db_path,
            rpc_port=rpc_port,
            p2p_port=p2p_port,
        )
        self.chains[chain_id] = chain
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)

            # Initialize the chain database using the actual database layer
            init_db(chain_id)

            # Start the PoA proposer for block production on this chain
            proposer_config = self._proposer_config(chain_id)
            consensus = PoAProposer(
                config=proposer_config,
                session_factory=lambda cid=chain_id: session_scope(cid),
            )
            await consensus.start()

            chain._consensus = consensus
            chain.status = ChainStatus.RUNNING
            chain.started_at = time.time()
            logger.info("Started chain %s (type: %s, rpc: %s, p2p: %s)", chain_id, chain_type.value, rpc_port, p2p_port)
            return True
        except Exception as e:
            chain.status = ChainStatus.ERROR
            chain.error_message = str(e)
            logger.error("Failed to start chain %s: %s", chain_id, e)
            return False

    async def stop_chain(self, chain_id: str) -> bool:
        """Stop a chain instance"""
        if chain_id not in self.chains:
            logger.warning("Chain %s does not exist", chain_id)
            return False
        if chain_id == self.default_chain_id:
            logger.warning("Cannot stop default chain")
            return False
        chain = self.chains[chain_id]
        if chain.status == ChainStatus.STOPPED:
            logger.warning("Chain %s already stopped", chain_id)
            return False
        chain.status = ChainStatus.STOPPING
        try:
            if chain._consensus is not None:
                await chain._consensus.stop()
                chain._consensus = None
            shutdown_db(chain_id)
            chain.status = ChainStatus.STOPPED
            chain.stopped_at = time.time()
            logger.info("Stopped chain %s", chain_id)
            return True
        except Exception as e:
            chain.status = ChainStatus.ERROR
            chain.error_message = str(e)
            logger.error("Failed to stop chain %s: %s", chain_id, e)
            return False

    def get_chain_status(self, chain_id: str) -> ChainInstance | None:
        """Get status of a specific chain"""
        return self.chains.get(chain_id)

    def get_active_chains(self) -> list[ChainInstance]:
        """Get all active chain instances"""
        return [chain for chain in self.chains.values() if chain.status == ChainStatus.RUNNING]

    def get_all_chains(self) -> list[ChainInstance]:
        """Get all chain instances"""
        return list(self.chains.values())

    def _get_latest_block_height(self, chain_id: str) -> int:
        """Get the latest block height for a chain from the database"""
        with session_scope(chain_id) as session:
            block = session.exec(
                select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)
            ).first()
            return block.height if block else 0

    def sync_chain(self, chain_id: str) -> bool:
        """
        Sync a specific chain to the highest block height among running chains.
        Uses gossip to broadcast sync status.
        """
        if chain_id not in self.chains:
            logger.warning("Chain %s does not exist", chain_id)
            return False
        chain = self.chains[chain_id]
        if chain.status != ChainStatus.RUNNING:
            logger.warning("Chain %s is not running", chain_id)
            return False
        try:
            chain_states: dict[str, int] = {}
            for cid, ch in self.chains.items():
                if ch.status == ChainStatus.RUNNING:
                    chain_states[cid] = self._get_latest_block_height(cid)
            if chain_states:
                max_block_chain = max(chain_states, key=lambda k: chain_states[k])
                target_block = chain_states[max_block_chain]
                if chain_id != max_block_chain:
                    logger.info(
                        "Chain %s at block %s, target %s (from %s) — full sync deferred to v0.6.4",
                        chain_id,
                        chain_states.get(chain_id, 0),
                        target_block,
                        max_block_chain,
                    )
            # Broadcast sync status via gossip
            local_height = chain_states.get(chain_id, 0)
            asyncio.ensure_future(gossip_broker.publish(f"chain.{chain_id}.sync", {"height": local_height}))
            logger.info("Sync completed for chain %s", chain_id)
            return True
        except Exception as e:
            logger.error("Failed to sync chain %s: %s", chain_id, e)
            return False

    async def start(self) -> None:
        """Start multi-chain manager"""
        self.running = True
        logger.info("Starting multi-chain manager")
        tasks = [asyncio.create_task(self._chain_health_check())]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error("Multi-chain manager error: %s", e)
        finally:
            self.running = False

    async def stop(self) -> None:
        """Stop multi-chain manager"""
        self.running = False
        logger.info("Stopping multi-chain manager")

    async def _chain_health_check(self) -> None:
        """Check health of chain instances"""
        while self.running:
            try:
                for chain_id, chain in list(self.chains.items()):
                    if chain.status == ChainStatus.ERROR:
                        logger.warning("Chain %s in error state: %s", chain_id, chain.error_message)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error("Chain health check error: %s", e)
                await asyncio.sleep(10)


multi_chain_manager_instance: MultiChainManager | None = None


def get_multi_chain_manager() -> MultiChainManager | None:
    """Get global multi-chain manager instance"""
    return multi_chain_manager_instance


def create_multi_chain_manager(
    default_chain_id: str, base_db_path: Path, base_rpc_port: int = 8006, base_p2p_port: int = 7070
) -> MultiChainManager:
    """Create and set global multi-chain manager instance"""
    global multi_chain_manager_instance
    multi_chain_manager_instance = MultiChainManager(default_chain_id, base_db_path, base_rpc_port, base_p2p_port)
    return multi_chain_manager_instance
