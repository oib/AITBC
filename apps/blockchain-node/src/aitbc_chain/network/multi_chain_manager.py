# mypy: ignore-errors
"""
Multi-Chain Manager
Manages parallel bilateral/micro-chains running alongside the default chain
"""
import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from aitbc import get_logger
logger = get_logger(__name__)

class ChainType(Enum):
    """Chain instance type"""
    DEFAULT = 'default'
    BILATERAL = 'bilateral'
    MICRO = 'micro'

class ChainStatus(Enum):
    """Chain instance status"""
    STOPPED = 'stopped'
    STARTING = 'starting'
    RUNNING = 'running'
    STOPPING = 'stopping'
    ERROR = 'error'

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

class MultiChainManager:
    """Manages parallel chain instances"""

    def __init__(self, default_chain_id: str, base_db_path: Path, base_rpc_port: int=8006, base_p2p_port: int=7070):
        self.default_chain_id = default_chain_id
        self.base_db_path = base_db_path
        self.base_rpc_port = base_rpc_port
        self.base_p2p_port = base_p2p_port
        self.chains: dict[str, ChainInstance] = {}
        self.next_rpc_port = base_rpc_port + 1
        self.next_p2p_port = base_p2p_port + 1
        self.running = False
        self._initialize_default_chain()

    def _initialize_default_chain(self):
        """Initialize the default chain instance"""
        self.chains[self.default_chain_id] = ChainInstance(chain_id=self.default_chain_id, chain_type=ChainType.DEFAULT, status=ChainStatus.RUNNING, db_path=self.base_db_path, rpc_port=self.base_rpc_port, p2p_port=self.base_p2p_port, started_at=time.time())
        logger.info('Initialized default chain: %s', self.default_chain_id)

    def _allocate_ports(self) -> tuple[int, int]:
        """Allocate ports for a new chain instance"""
        rpc_port = self.next_rpc_port
        p2p_port = self.next_p2p_port
        self.next_rpc_port += 1
        self.next_p2p_port += 1
        return (rpc_port, p2p_port)

    async def start_chain(self, chain_id: str, chain_type: ChainType=ChainType.MICRO) -> bool:
        """
        Start a new chain instance
        
        Args:
            chain_id: Unique identifier for the chain
            chain_type: Type of chain (BILATERAL or MICRO)
            
        Returns:
            True if successful, False otherwise
        """
        if chain_id in self.chains:
            logger.warning('Chain %s already exists', chain_id)
            return False
        if chain_id == self.default_chain_id:
            logger.warning('Cannot start default chain (already running)')
            return False
        rpc_port = self.base_rpc_port
        p2p_port = self.base_p2p_port
        db_path = self.base_db_path.parent / chain_id / 'chain.db'
        chain = ChainInstance(chain_id=chain_id, chain_type=chain_type, status=ChainStatus.STARTING, db_path=db_path, rpc_port=rpc_port, p2p_port=p2p_port)
        self.chains[chain_id] = chain
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            from aitbc_chain.database import BlockchainDB
            chain_db = BlockchainDB(str(db_path))
            chain_db.initialize()
            from aitbc_chain.rpc import RPCServer
            rpc_server = RPCServer(rpc_port, chain_db)
            await rpc_server.start()
            from aitbc_chain.p2p import P2PService
            p2p_service = P2PService(p2p_port, chain_id)
            await p2p_service.start()
            from aitbc_chain.consensus import EthereumConsensus
            consensus = EthereumConsensus(chain_db)
            await consensus.initialize()
            chain._rpc_server = rpc_server
            chain._p2p_service = p2p_service
            chain._consensus = consensus
            chain._chain_db = chain_db
            chain.status = ChainStatus.RUNNING
            chain.started_at = time.time()
            logger.info('Started Ethereum chain %s (type: %s, rpc: %s, p2p: %s)', chain_id, chain_type.value, rpc_port, p2p_port)
            return True
        except Exception as e:
            chain.status = ChainStatus.ERROR
            chain.error_message = str(e)
            logger.error('Failed to start chain %s: %s', chain_id, e)
            return False

    async def stop_chain(self, chain_id: str) -> bool:
        """Stop a chain instance"""
        if chain_id not in self.chains:
            logger.warning('Chain %s does not exist', chain_id)
            return False
        if chain_id == self.default_chain_id:
            logger.warning('Cannot stop default chain')
            return False
        chain = self.chains[chain_id]
        if chain.status == ChainStatus.STOPPED:
            logger.warning('Chain %s already stopped', chain_id)
            return False
        chain.status = ChainStatus.STOPPING
        try:
            if hasattr(chain, '_rpc_server'):
                await chain._rpc_server.stop()
            if hasattr(chain, '_p2p_service'):
                await chain._p2p_service.stop()
            if hasattr(chain, '_consensus'):
                await chain._consensus.stop()
            if hasattr(chain, '_chain_db'):
                chain._chain_db.close()
            chain.status = ChainStatus.STOPPED
            chain.stopped_at = time.time()
            logger.info('Stopped Ethereum chain %s', chain_id)
            return True
        except Exception as e:
            chain.status = ChainStatus.ERROR
            chain.error_message = str(e)
            logger.error('Failed to stop chain %s: %s', chain_id, e)
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

    def sync_chain(self, chain_id: str) -> bool:
        """
        Sync a specific chain (Ethereum implementation)
        """
        if chain_id not in self.chains:
            logger.warning('Chain %s does not exist', chain_id)
            return False
        chain = self.chains[chain_id]
        if chain.status != ChainStatus.RUNNING:
            logger.warning('Chain %s is not running', chain_id)
            return False
        try:
            chain_states = {}
            for cid, ch in self.chains.items():
                if ch.status == ChainStatus.RUNNING and hasattr(ch, '_chain_db'):
                    chain_states[cid] = ch._chain_db.get_latest_block_number()
            if chain_states:
                max_block_chain = max(chain_states, key=chain_states.get)
                target_block = chain_states[max_block_chain]
                if chain_id != max_block_chain:
                    if hasattr(chain, '_chain_db'):
                        chain._chain_db.sync_to_block(target_block)
                        logger.info('Synced chain %s to block %s', chain_id, target_block)
            if hasattr(chain, '_p2p_service'):
                chain._p2p_service.broadcast_sync_status(chain_id, chain_states.get(chain_id, 0))
            logger.info('Sync completed for chain %s', chain_id)
            return True
        except Exception as e:
            logger.error('Failed to sync chain %s: %s', chain_id, e)
            return False

    async def start(self):
        """Start multi-chain manager"""
        self.running = True
        logger.info('Starting multi-chain manager')
        tasks = [asyncio.create_task(self._chain_health_check())]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error('Multi-chain manager error: %s', e)
        finally:
            self.running = False

    async def stop(self):
        """Stop multi-chain manager"""
        self.running = False
        logger.info('Stopping multi-chain manager')

    async def _chain_health_check(self):
        """Check health of chain instances"""
        while self.running:
            try:
                for chain_id, chain in list(self.chains.items()):
                    if chain.status == ChainStatus.ERROR:
                        logger.warning('Chain %s in error state: %s', chain_id, chain.error_message)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error('Chain health check error: %s', e)
                await asyncio.sleep(10)
multi_chain_manager_instance: MultiChainManager | None = None

def get_multi_chain_manager() -> MultiChainManager | None:
    """Get global multi-chain manager instance"""
    return multi_chain_manager_instance

def create_multi_chain_manager(default_chain_id: str, base_db_path: Path, base_rpc_port: int=8006, base_p2p_port: int=7070) -> MultiChainManager:
    """Create and set global multi-chain manager instance"""
    global multi_chain_manager_instance
    multi_chain_manager_instance = MultiChainManager(default_chain_id, base_db_path, base_rpc_port, base_p2p_port)
    return multi_chain_manager_instance