"""
Multi-chain configuration management for AITBC CLI
"""

from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from pydantic import BaseModel, Field

class NodeConfig(BaseModel):
    """Configuration for a specific node"""
    id: str = Field(..., description="Node identifier")
    endpoint: str = Field(..., description="Node endpoint URL")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    retry_count: int = Field(default=3, description="Number of retry attempts")
    max_connections: int = Field(default=10, description="Maximum concurrent connections")

class ChainConfig(BaseModel):
    """Default chain configuration"""
    default_gas_limit: int = Field(default=10000000, description="Default gas limit")
    default_gas_price: int = Field(default=20000000000, description="Default gas price in wei")
    max_block_size: int = Field(default=1048576, description="Maximum block size in bytes")
    backup_path: Path = Field(default=Path("./backups"), description="Backup directory path")
    max_concurrent_chains: int = Field(default=100, description="Maximum concurrent chains per node")

class MultiChainConfig(BaseModel):
    """Multi-chain configuration"""
    nodes: Dict[str, NodeConfig] = Field(default_factory=dict, description="Node configurations")
    chains: ChainConfig = Field(default_factory=ChainConfig, description="Chain configuration")
    logging_level: str = Field(default="INFO", description="Logging level")
    enable_caching: bool = Field(default=True, description="Enable response caching")
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")

def load_multichain_config(config_path: Optional[str] = None) -> MultiChainConfig:
    """Load multi-chain configuration from file"""
    if config_path is None:
        config_path = Path.home() / ".aitbc" / "multichain_config.yaml"
    
    config_file = Path(config_path)
    
    if not config_file.exists():
        # Create default configuration
        default_config = MultiChainConfig()
        save_multichain_config(default_config, config_path)
        return default_config
    
    try:
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        return MultiChainConfig(**config_data)
    except Exception as e:
        raise ValueError(f"Failed to load configuration from {config_path}: {e}")

def save_multichain_config(config: MultiChainConfig, config_path: Optional[str] = None) -> None:
    """Save multi-chain configuration to file"""
    if config_path is None:
        config_path = Path.home() / ".aitbc" / "multichain_config.yaml"
    
    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Convert Path objects to strings for YAML serialization
        config_dict = config.dict()
        if 'chains' in config_dict and 'backup_path' in config_dict['chains']:
            config_dict['chains']['backup_path'] = str(config_dict['chains']['backup_path'])
        
        with open(config_file, 'w') as f:
            yaml.dump(config_dict, f, default_flow_style=False, indent=2)
    except Exception as e:
        raise ValueError(f"Failed to save configuration to {config_path}: {e}")

def get_default_node_config() -> NodeConfig:
    """Get default node configuration for local development"""
    return NodeConfig(
        id="default-node",
        endpoint="http://localhost:8545",
        timeout=30,
        retry_count=3,
        max_connections=10
    )

def add_node_config(config: MultiChainConfig, node_config: NodeConfig) -> MultiChainConfig:
    """Add a node configuration"""
    config.nodes[node_config.id] = node_config
    return config

def remove_node_config(config: MultiChainConfig, node_id: str) -> MultiChainConfig:
    """Remove a node configuration"""
    if node_id in config.nodes:
        del config.nodes[node_id]
    return config

def get_node_config(config: MultiChainConfig, node_id: str) -> Optional[NodeConfig]:
    """Get a specific node configuration"""
    return config.nodes.get(node_id)

def list_node_configs(config: MultiChainConfig) -> Dict[str, NodeConfig]:
    """List all node configurations"""
    return config.nodes.copy()
