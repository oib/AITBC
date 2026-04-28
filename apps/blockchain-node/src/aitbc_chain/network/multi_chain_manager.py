"""
Multi-Chain Manager
Manages parallel bilateral/micro-chains running alongside the default chain
"""

import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import time

from aitbc import get_logger

logger = get_logger(__name__)


class ChainType(Enum):
    """Chain instance type"""
    DEFAULT = "default"  # Main chain for the island
    BILATERAL = "bilateral"  # Chain between two parties
    MICRO = "micro"  # Small chain for specific use case


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
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None
    error_message: Optional[str] = None


class MultiChainManager:
    """Manages parallel chain instances"""
    
    def __init__(self, default_chain_id: str, base_db_path: Path, base_rpc_port: int = 8006, base_p2p_port: int = 7070):
        self.default_chain_id = default_chain_id
        self.base_db_path = base_db_path
        self.base_rpc_port = base_rpc_port
        self.base_p2p_port = base_p2p_port
        
        # Chain instances
        self.chains: Dict[str, ChainInstance] = {}
        
        # Port allocation
        self.next_rpc_port = base_rpc_port + 1
        self.next_p2p_port = base_p2p_port + 1
        
        self.running = False
        
        # Initialize default chain
        self._initialize_default_chain()
    
    def _initialize_default_chain(self):
        """Initialize the default chain instance"""
        self.chains[self.default_chain_id] = ChainInstance(
            chain_id=self.default_chain_id,
            chain_type=ChainType.DEFAULT,
            status=ChainStatus.RUNNING,
            db_path=self.base_db_path,
            rpc_port=self.base_rpc_port,
            p2p_port=self.base_p2p_port,
            started_at=time.time()
        )
        logger.info(f"Initialized default chain: {self.default_chain_id}")
    
    def _allocate_ports(self) -> tuple[int, int]:
        """Allocate ports for a new chain instance"""
        rpc_port = self.next_rpc_port
        p2p_port = self.next_p2p_port
        
        self.next_rpc_port += 1
        self.next_p2p_port += 1
        
        return rpc_port, p2p_port
    
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
            logger.warning(f"Chain {chain_id} already exists")
            return False
        
        if chain_id == self.default_chain_id:
            logger.warning("Cannot start default chain (already running)")
            return False
        
        # Allocate ports (shared ports - no separate allocation)
        rpc_port = self.base_rpc_port
        p2p_port = self.base_p2p_port
        
        # Create database path with subdirectory structure
        db_path = self.base_db_path.parent / chain_id / "chain.db"
        
        # Create chain instance
        chain = ChainInstance(
            chain_id=chain_id,
            chain_type=chain_type,
            status=ChainStatus.STARTING,
            db_path=db_path,
            rpc_port=rpc_port,
            p2p_port=p2p_port
        )
        
        self.chains[chain_id] = chain
        
        # Start the chain (Ethereum implementation)
        try:
            # Create database directory and file
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Initialize Ethereum chain state
            from aitbc_chain.database import BlockchainDB
            chain_db = BlockchainDB(str(db_path))
            chain_db.initialize()
            
            # Start RPC server on allocated port
            from aitbc_chain.rpc import RPCServer
            rpc_server = RPCServer(rpc_port, chain_db)
            await rpc_server.start()
            
            # Start P2P service on allocated port
            from aitbc_chain.p2p import P2PService
            p2p_service = P2PService(p2p_port, chain_id)
            await p2p_service.start()
            
            # Initialize Ethereum consensus
            from aitbc_chain.consensus import EthereumConsensus
            consensus = EthereumConsensus(chain_db)
            await consensus.initialize()
            
            # Store references in chain instance for later cleanup
            chain._rpc_server = rpc_server
            chain._p2p_service = p2p_service
            chain._consensus = consensus
            chain._chain_db = chain_db
            
            chain.status = ChainStatus.RUNNING
            chain.started_at = time.time()
            
            logger.info(f"Started Ethereum chain {chain_id} (type: {chain_type.value}, rpc: {rpc_port}, p2p: {p2p_port})")
            return True
            
        except Exception as e:
            chain.status = ChainStatus.ERROR
            chain.error_message = str(e)
            logger.error(f"Failed to start chain {chain_id}: {e}")
            return False
    
    async def stop_chain(self, chain_id: str) -> bool:
        """Stop a chain instance"""
        if chain_id not in self.chains:
            logger.warning(f"Chain {chain_id} does not exist")
            return False
        
        if chain_id == self.default_chain_id:
            logger.warning("Cannot stop default chain")
            return False
        
        chain = self.chains[chain_id]
        
        if chain.status == ChainStatus.STOPPED:
            logger.warning(f"Chain {chain_id} already stopped")
            return False
        
        chain.status = ChainStatus.STOPPING
        
        try:
            # Stop RPC server
            if hasattr(chain, '_rpc_server'):
                await chain._rpc_server.stop()
            
            # Stop P2P service
            if hasattr(chain, '_p2p_service'):
                await chain._p2p_service.stop()
            
            # Stop consensus
            if hasattr(chain, '_consensus'):
                await chain._consensus.stop()
            
            # Close database connections
            if hasattr(chain, '_chain_db'):
                chain._chain_db.close()
            
            chain.status = ChainStatus.STOPPED
            chain.stopped_at = time.time()
            
            logger.info(f"Stopped Ethereum chain {chain_id}")
            return True
            
        except Exception as e:
            chain.status = ChainStatus.ERROR
            chain.error_message = str(e)
            logger.error(f"Failed to stop chain {chain_id}: {e}")
            return False
    
    def get_chain_status(self, chain_id: str) -> Optional[ChainInstance]:
        """Get status of a specific chain"""
        return self.chains.get(chain_id)
    
    def get_active_chains(self) -> List[ChainInstance]:
        """Get all active chain instances"""
        return [chain for chain in self.chains.values() if chain.status == ChainStatus.RUNNING]
    
    def get_all_chains(self) -> List[ChainInstance]:
        """Get all chain instances"""
        return list(self.chains.values())
    
    def sync_chain(self, chain_id: str) -> bool:
        """
        Sync a specific chain (Ethereum implementation)
        """
        if chain_id not in self.chains:
            logger.warning(f"Chain {chain_id} does not exist")
            return False
        
        chain = self.chains[chain_id]
        
        if chain.status != ChainStatus.RUNNING:
            logger.warning(f"Chain {chain_id} is not running")
            return False
        
        try:
            # Get chain states from all chains
            chain_states = {}
            for cid, ch in self.chains.items():
                if ch.status == ChainStatus.RUNNING and hasattr(ch, '_chain_db'):
                    chain_states[cid] = ch._chain_db.get_latest_block_number()
            
            # Resolve conflicts using longest-chain rule (Ethereum consensus)
            if chain_states:
                max_block_chain = max(chain_states, key=chain_states.get)
                target_block = chain_states[max_block_chain]
                
                # Sync target chain to the highest block
                if chain_id != max_block_chain:
                    if hasattr(chain, '_chain_db'):
                        chain._chain_db.sync_to_block(target_block)
                        logger.info(f"Synced chain {chain_id} to block {target_block}")
            
            # Broadcast sync status to network
            if hasattr(chain, '_p2p_service'):
                chain._p2p_service.broadcast_sync_status(chain_id, chain_states.get(chain_id, 0))
            
            logger.info(f"Sync completed for chain {chain_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync chain {chain_id}: {e}")
            return False
    
    async def start(self):
        """Start multi-chain manager"""
        self.running = True
        logger.info("Starting multi-chain manager")
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self._chain_health_check())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Multi-chain manager error: {e}")
        finally:
            self.running = False
    
    async def stop(self):
        """Stop multi-chain manager"""
        self.running = False
        logger.info("Stopping multi-chain manager")
    
    async def _chain_health_check(self):
        """Check health of chain instances"""
        while self.running:
            try:
                # Check for chains in error state
                for chain_id, chain in list(self.chains.items()):
                    if chain.status == ChainStatus.ERROR:
                        logger.warning(f"Chain {chain_id} in error state: {chain.error_message}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Chain health check error: {e}")
                await asyncio.sleep(10)


# Global multi-chain manager instance
multi_chain_manager_instance: Optional[MultiChainManager] = None


def get_multi_chain_manager() -> Optional[MultiChainManager]:
    """Get global multi-chain manager instance"""
    return multi_chain_manager_instance


def create_multi_chain_manager(default_chain_id: str, base_db_path: Path, base_rpc_port: int = 8006, base_p2p_port: int = 7070) -> MultiChainManager:
    """Create and set global multi-chain manager instance"""
    global multi_chain_manager_instance
    multi_chain_manager_instance = MultiChainManager(default_chain_id, base_db_path, base_rpc_port, base_p2p_port)
    return multi_chain_manager_instance
