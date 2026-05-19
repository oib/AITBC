"""
Chain registry configuration for AITBC CLI
Manages available blockchain networks and their configurations
"""

from typing import Dict, Optional
from dataclasses import dataclass
import os


@dataclass
class ChainConfig:
    """Configuration for a blockchain network"""
    chain_id: str
    name: str
    rpc_url: str
    explorer_url: Optional[str] = None
    is_testnet: bool = False
    native_currency: str = "AITBC"


class ChainRegistry:
    """Registry for managing blockchain network configurations"""
    
    def __init__(self):
        """Initialize chain registry with default chains"""
        self.chains: Dict[str, ChainConfig] = {}
        self._load_default_chains()
    
    def _load_default_chains(self) -> None:
        """Load default chain configurations"""
        # AITBC Devnet
        self.chains["ait-devnet"] = ChainConfig(
            chain_id="ait-devnet",
            name="AITBC Development Network",
            rpc_url="http://localhost:8025",
            explorer_url="http://localhost:8026",
            is_testnet=True,
            native_currency="AITBC"
        )
        
        # AITBC Testnet
        self.chains["ait-testnet"] = ChainConfig(
            chain_id="ait-testnet",
            name="AITBC Test Network",
            rpc_url="http://localhost:8027",
            explorer_url="http://localhost:8028",
            is_testnet=True,
            native_currency="AITBC"
        )
    
    def get_chain(self, chain_id: str) -> Optional[ChainConfig]:
        """Get chain configuration by ID"""
        return self.chains.get(chain_id)
    
    def get_all_chains(self) -> Dict[str, ChainConfig]:
        """Get all registered chains"""
        return self.chains.copy()
    
    def get_chain_ids(self) -> list[str]:
        """Get list of all chain IDs"""
        return list(self.chains.keys())
    
    def get_testnet_chains(self) -> Dict[str, ChainConfig]:
        """Get all testnet chains"""
        return {
            chain_id: config 
            for chain_id, config in self.chains.items() 
            if config.is_testnet
        }
    
    def get_mainnet_chains(self) -> Dict[str, ChainConfig]:
        """Get all mainnet chains"""
        return {
            chain_id: config 
            for chain_id, config in self.chains.items() 
            if not config.is_testnet
        }
    
    def register_chain(self, chain_id: str, config: ChainConfig) -> None:
        """Register a new chain configuration"""
        self.chains[chain_id] = config
    
    def unregister_chain(self, chain_id: str) -> bool:
        """Unregister a chain configuration"""
        if chain_id in self.chains:
            del self.chains[chain_id]
            return True
        return False
    
    def load_from_env(self) -> None:
        """Load additional chains from environment variables"""
        # Format: AITBC_CHAIN_<CHAIN_ID>_NAME, AITBC_CHAIN_<CHAIN_ID>_RPC_URL, etc.
        for key, value in os.environ.items():
            if key.startswith("AITBC_CHAIN_") and key.endswith("_RPC_URL"):
                chain_id = key.replace("AITBC_CHAIN_", "").replace("_RPC_URL", "").lower()
                
                name = os.environ.get(f"AITBC_CHAIN_{chain_id.upper()}_NAME", chain_id)
                explorer_url = os.environ.get(f"AITBC_CHAIN_{chain_id.upper()}_EXPLORER_URL")
                is_testnet = os.environ.get(f"AITBC_CHAIN_{chain_id.upper()}_IS_TESTNET", "false").lower() == "true"
                native_currency = os.environ.get(f"AITBC_CHAIN_{chain_id.upper()}_NATIVE_CURRENCY", "AITBC")
                
                self.register_chain(
                    chain_id,
                    ChainConfig(
                        chain_id=chain_id,
                        name=name,
                        rpc_url=value,
                        explorer_url=explorer_url,
                        is_testnet=is_testnet,
                        native_currency=native_currency
                    )
                )


# Global chain registry instance
_chain_registry: Optional[ChainRegistry] = None


def get_chain_registry() -> ChainRegistry:
    """Get or create global chain registry instance"""
    global _chain_registry
    if _chain_registry is None:
        _chain_registry = ChainRegistry()
        _chain_registry.load_from_env()
    return _chain_registry
