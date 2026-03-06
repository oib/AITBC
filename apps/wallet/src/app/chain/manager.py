"""
Multi-Chain Manager for Wallet Daemon

Central management for multiple blockchain networks, providing
chain context, routing, and isolation for wallet operations.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ChainStatus(Enum):
    """Chain operational status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    ERROR = "error"


@dataclass
class ChainConfig:
    """Configuration for a specific blockchain network"""
    chain_id: str
    name: str
    coordinator_url: str
    coordinator_api_key: str
    status: ChainStatus = ChainStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Chain-specific settings
    default_gas_limit: int = 10000000
    default_gas_price: int = 20000000000
    transaction_timeout: int = 300
    max_retries: int = 3
    
    # Storage configuration
    ledger_db_path: Optional[str] = None
    keystore_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "chain_id": self.chain_id,
            "name": self.name,
            "coordinator_url": self.coordinator_url,
            "coordinator_api_key": self.coordinator_api_key,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "default_gas_limit": self.default_gas_limit,
            "default_gas_price": self.default_gas_price,
            "transaction_timeout": self.transaction_timeout,
            "max_retries": self.max_retries,
            "ledger_db_path": self.ledger_db_path,
            "keystore_path": self.keystore_path
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChainConfig":
        """Create from dictionary"""
        # Ensure data is a dict and make a copy
        if not isinstance(data, dict):
            raise ValueError(f"Expected dict, got {type(data)}")
        
        data = data.copy()
        data["status"] = ChainStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


class ChainManager:
    """Central manager for multi-chain operations"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("./data/chains.json")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.chains: Dict[str, ChainConfig] = {}
        self.default_chain_id: Optional[str] = None
        self._load_chains()
    
    def _load_chains(self):
        """Load chain configurations from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                
                for chain_data in data.get("chains", []):
                    chain = ChainConfig.from_dict(chain_data)
                    self.chains[chain.chain_id] = chain
                
                self.default_chain_id = data.get("default_chain_id")
                logger.info(f"Loaded {len(self.chains)} chain configurations")
            else:
                # Create default chain configuration
                self._create_default_chain()
        except Exception as e:
            logger.error(f"Failed to load chain configurations: {e}")
            self._create_default_chain()
    
    def _create_default_chain(self):
        """Create default chain configuration"""
        default_chain = ChainConfig(
            chain_id="ait-devnet",
            name="AITBC Development Network",
            coordinator_url="http://localhost:8011",
            coordinator_api_key="dev-coordinator-key",
            ledger_db_path="./data/wallet_ledger_devnet.db",
            keystore_path="./data/keystore_devnet"
        )
        
        self.chains[default_chain.chain_id] = default_chain
        self.default_chain_id = default_chain.chain_id
        self._save_chains()
        logger.info(f"Created default chain: {default_chain.chain_id}")
    
    def _save_chains(self):
        """Save chain configurations to file"""
        try:
            data = {
                "chains": [chain.to_dict() for chain in self.chains.values()],
                "default_chain_id": self.default_chain_id,
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved {len(self.chains)} chain configurations")
        except Exception as e:
            logger.error(f"Failed to save chain configurations: {e}")
    
    def add_chain(self, chain_config: ChainConfig) -> bool:
        """Add a new chain configuration"""
        try:
            if chain_config.chain_id in self.chains:
                logger.warning(f"Chain {chain_config.chain_id} already exists")
                return False
            
            self.chains[chain_config.chain_id] = chain_config
            
            # Set as default if no default exists
            if self.default_chain_id is None:
                self.default_chain_id = chain_config.chain_id
            
            self._save_chains()
            logger.info(f"Added chain: {chain_config.chain_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add chain {chain_config.chain_id}: {e}")
            return False
    
    def remove_chain(self, chain_id: str) -> bool:
        """Remove a chain configuration"""
        try:
            if chain_id not in self.chains:
                logger.warning(f"Chain {chain_id} not found")
                return False
            
            if chain_id == self.default_chain_id:
                logger.error(f"Cannot remove default chain {chain_id}")
                return False
            
            del self.chains[chain_id]
            self._save_chains()
            logger.info(f"Removed chain: {chain_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove chain {chain_id}: {e}")
            return False
    
    def get_chain(self, chain_id: str) -> Optional[ChainConfig]:
        """Get chain configuration by ID"""
        return self.chains.get(chain_id)
    
    def get_default_chain(self) -> Optional[ChainConfig]:
        """Get default chain configuration"""
        if self.default_chain_id:
            return self.chains.get(self.default_chain_id)
        return None
    
    def set_default_chain(self, chain_id: str) -> bool:
        """Set default chain"""
        try:
            if chain_id not in self.chains:
                logger.error(f"Chain {chain_id} not found")
                return False
            
            self.default_chain_id = chain_id
            self._save_chains()
            logger.info(f"Set default chain: {chain_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set default chain {chain_id}: {e}")
            return False
    
    def list_chains(self) -> List[ChainConfig]:
        """List all chain configurations"""
        return list(self.chains.values())
    
    def get_active_chains(self) -> List[ChainConfig]:
        """Get only active chains"""
        return [chain for chain in self.chains.values() if chain.status == ChainStatus.ACTIVE]
    
    def update_chain_status(self, chain_id: str, status: ChainStatus) -> bool:
        """Update chain status"""
        try:
            if chain_id not in self.chains:
                logger.error(f"Chain {chain_id} not found")
                return False
            
            self.chains[chain_id].status = status
            self.chains[chain_id].updated_at = datetime.now()
            self._save_chains()
            logger.info(f"Updated chain {chain_id} status to {status.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to update chain status {chain_id}: {e}")
            return False
    
    def validate_chain_id(self, chain_id: str) -> bool:
        """Validate that a chain ID exists and is active"""
        chain = self.chains.get(chain_id)
        return chain is not None and chain.status == ChainStatus.ACTIVE
    
    def get_chain_config_for_wallet(self, chain_id: str, wallet_id: str) -> Optional[ChainConfig]:
        """Get chain configuration for a specific wallet operation"""
        if not self.validate_chain_id(chain_id):
            logger.error(f"Invalid or inactive chain: {chain_id}")
            return None
        
        chain = self.chains[chain_id]
        
        # Add wallet-specific context to metadata
        chain.metadata["last_wallet_access"] = wallet_id
        chain.metadata["last_access_time"] = datetime.now().isoformat()
        
        return chain
    
    def get_chain_stats(self) -> Dict[str, Any]:
        """Get statistics about chains"""
        active_chains = self.get_active_chains()
        
        return {
            "total_chains": len(self.chains),
            "active_chains": len(active_chains),
            "inactive_chains": len(self.chains) - len(active_chains),
            "default_chain": self.default_chain_id,
            "chain_list": [
                {
                    "chain_id": chain.chain_id,
                    "name": chain.name,
                    "status": chain.status.value,
                    "coordinator_url": chain.coordinator_url
                }
                for chain in self.chains.values()
            ]
        }


# Global chain manager instance
chain_manager = ChainManager()
