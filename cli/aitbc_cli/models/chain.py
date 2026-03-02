"""
Data models for multi-chain functionality
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class ChainType(str, Enum):
    """Chain type enumeration"""
    MAIN = "main"
    TOPIC = "topic"
    PRIVATE = "private"
    TEMPORARY = "temporary"

class ChainStatus(str, Enum):
    """Chain status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SYNCING = "syncing"
    ERROR = "error"
    MAINTENANCE = "maintenance"

class ConsensusAlgorithm(str, Enum):
    """Consensus algorithm enumeration"""
    POW = "pow"  # Proof of Work
    POS = "pos"  # Proof of Stake
    POA = "poa"  # Proof of Authority
    HYBRID = "hybrid"

class GenesisAccount(BaseModel):
    """Genesis account configuration"""
    address: str = Field(..., description="Account address")
    balance: str = Field(..., description="Account balance in wei")
    type: str = Field(default="regular", description="Account type")

class GenesisContract(BaseModel):
    """Genesis contract configuration"""
    name: str = Field(..., description="Contract name")
    address: str = Field(..., description="Contract address")
    bytecode: str = Field(..., description="Contract bytecode")
    abi: Dict[str, Any] = Field(..., description="Contract ABI")

class PrivacyConfig(BaseModel):
    """Privacy configuration for chains"""
    visibility: str = Field(default="public", description="Chain visibility")
    access_control: str = Field(default="open", description="Access control type")
    require_invitation: bool = Field(default=False, description="Require invitation to join")
    encryption_enabled: bool = Field(default=False, description="Enable transaction encryption")

class ConsensusConfig(BaseModel):
    """Consensus configuration"""
    algorithm: ConsensusAlgorithm = Field(..., description="Consensus algorithm")
    block_time: int = Field(default=5, description="Block time in seconds")
    max_validators: int = Field(default=100, description="Maximum number of validators")
    min_stake: int = Field(default=1000000000000000000, description="Minimum stake in wei")
    authorities: List[str] = Field(default_factory=list, description="List of authority addresses")

class ChainParameters(BaseModel):
    """Chain parameters"""
    max_block_size: int = Field(default=1048576, description="Maximum block size in bytes")
    max_gas_per_block: int = Field(default=10000000, description="Maximum gas per block")
    min_gas_price: int = Field(default=1000000000, description="Minimum gas price in wei")
    block_reward: str = Field(default="2000000000000000000", description="Block reward in wei")
    difficulty: int = Field(default=1000000, description="Initial difficulty")

class ChainLimits(BaseModel):
    """Chain limits"""
    max_participants: int = Field(default=1000, description="Maximum participants")
    max_contracts: int = Field(default=100, description="Maximum smart contracts")
    max_transactions_per_block: int = Field(default=500, description="Max transactions per block")
    max_storage_size: int = Field(default=1073741824, description="Max storage size in bytes")

class GenesisConfig(BaseModel):
    """Genesis block configuration"""
    chain_id: Optional[str] = Field(None, description="Chain ID")
    chain_type: ChainType = Field(..., description="Chain type")
    purpose: str = Field(..., description="Chain purpose")
    name: str = Field(..., description="Chain name")
    description: Optional[str] = Field(None, description="Chain description")
    timestamp: Optional[datetime] = Field(None, description="Genesis timestamp")
    parent_hash: str = Field(default="0x0000000000000000000000000000000000000000000000000000000000000000", description="Parent hash")
    gas_limit: int = Field(default=10000000, description="Gas limit")
    gas_price: int = Field(default=20000000000, description="Gas price")
    difficulty: int = Field(default=1000000, description="Initial difficulty")
    block_time: int = Field(default=5, description="Block time")
    accounts: List[GenesisAccount] = Field(default_factory=list, description="Genesis accounts")
    contracts: List[GenesisContract] = Field(default_factory=list, description="Genesis contracts")
    consensus: ConsensusConfig = Field(..., description="Consensus configuration")
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig, description="Privacy settings")
    parameters: ChainParameters = Field(default_factory=ChainParameters, description="Chain parameters")

class ChainConfig(BaseModel):
    """Chain configuration"""
    type: ChainType = Field(..., description="Chain type")
    purpose: str = Field(..., description="Chain purpose")
    name: str = Field(..., description="Chain name")
    description: Optional[str] = Field(None, description="Chain description")
    consensus: ConsensusConfig = Field(..., description="Consensus configuration")
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig, description="Privacy settings")
    parameters: ChainParameters = Field(default_factory=ChainParameters, description="Chain parameters")
    limits: ChainLimits = Field(default_factory=ChainLimits, description="Chain limits")

class ChainInfo(BaseModel):
    """Chain information"""
    id: str = Field(..., description="Chain ID")
    type: ChainType = Field(..., description="Chain type")
    purpose: str = Field(..., description="Chain purpose")
    name: str = Field(..., description="Chain name")
    description: Optional[str] = Field(None, description="Chain description")
    status: ChainStatus = Field(..., description="Chain status")
    created_at: datetime = Field(..., description="Creation timestamp")
    block_height: int = Field(default=0, description="Current block height")
    size_mb: float = Field(default=0.0, description="Chain size in MB")
    node_count: int = Field(default=0, description="Number of nodes")
    active_nodes: int = Field(default=0, description="Number of active nodes")
    contract_count: int = Field(default=0, description="Number of contracts")
    client_count: int = Field(default=0, description="Number of clients")
    miner_count: int = Field(default=0, description="Number of miners")
    agent_count: int = Field(default=0, description="Number of agents")
    consensus_algorithm: ConsensusAlgorithm = Field(..., description="Consensus algorithm")
    block_time: int = Field(default=5, description="Block time in seconds")
    tps: float = Field(default=0.0, description="Transactions per second")
    avg_block_time: float = Field(default=0.0, description="Average block time")
    avg_gas_used: int = Field(default=0, description="Average gas used per block")
    growth_rate_mb_per_day: float = Field(default=0.0, description="Growth rate MB per day")
    gas_price: int = Field(default=20000000000, description="Current gas price")
    memory_usage_mb: float = Field(default=0.0, description="Memory usage in MB")
    disk_usage_mb: float = Field(default=0.0, description="Disk usage in MB")
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig, description="Privacy settings")

class NodeInfo(BaseModel):
    """Node information"""
    id: str = Field(..., description="Node ID")
    type: str = Field(default="full", description="Node type")
    status: str = Field(..., description="Node status")
    version: str = Field(..., description="Node version")
    uptime_days: int = Field(default=0, description="Uptime in days")
    uptime_hours: int = Field(default=0, description="Uptime hours")
    hosted_chains: Dict[str, ChainInfo] = Field(default_factory=dict, description="Hosted chains")
    cpu_usage: float = Field(default=0.0, description="CPU usage percentage")
    memory_usage_mb: float = Field(default=0.0, description="Memory usage in MB")
    disk_usage_mb: float = Field(default=0.0, description="Disk usage in MB")
    network_in_mb: float = Field(default=0.0, description="Network in MB/s")
    network_out_mb: float = Field(default=0.0, description="Network out MB/s")

class GenesisAccount(BaseModel):
    """Genesis account configuration"""
    address: str = Field(..., description="Account address")
    balance: str = Field(..., description="Account balance in wei")
    type: str = Field(default="regular", description="Account type")

class GenesisContract(BaseModel):
    """Genesis contract configuration"""
    name: str = Field(..., description="Contract name")
    address: str = Field(..., description="Contract address")
    bytecode: str = Field(..., description="Contract bytecode")
    abi: Dict[str, Any] = Field(..., description="Contract ABI")

class GenesisBlock(BaseModel):
    """Genesis block configuration"""
    chain_id: str = Field(..., description="Chain ID")
    chain_type: ChainType = Field(..., description="Chain type")
    purpose: str = Field(..., description="Chain purpose")
    name: str = Field(..., description="Chain name")
    description: Optional[str] = Field(None, description="Chain description")
    timestamp: datetime = Field(..., description="Genesis timestamp")
    parent_hash: str = Field(default="0x0000000000000000000000000000000000000000000000000000000000000000", description="Parent hash")
    gas_limit: int = Field(default=10000000, description="Gas limit")
    gas_price: int = Field(default=20000000000, description="Gas price")
    difficulty: int = Field(default=1000000, description="Initial difficulty")
    block_time: int = Field(default=5, description="Block time")
    accounts: List[GenesisAccount] = Field(default_factory=list, description="Genesis accounts")
    contracts: List[GenesisContract] = Field(default_factory=list, description="Genesis contracts")
    consensus: ConsensusConfig = Field(..., description="Consensus configuration")
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig, description="Privacy settings")
    parameters: ChainParameters = Field(default_factory=ChainParameters, description="Chain parameters")
    state_root: str = Field(..., description="State root hash")
    hash: str = Field(..., description="Genesis block hash")

class ChainMigrationPlan(BaseModel):
    """Chain migration plan"""
    chain_id: str = Field(..., description="Chain ID to migrate")
    source_node: str = Field(..., description="Source node ID")
    target_node: str = Field(..., description="Target node ID")
    size_mb: float = Field(..., description="Chain size in MB")
    estimated_minutes: int = Field(..., description="Estimated migration time in minutes")
    required_space_mb: float = Field(..., description="Required space in MB")
    available_space_mb: float = Field(..., description="Available space in MB")
    feasible: bool = Field(..., description="Migration feasibility")
    issues: List[str] = Field(default_factory=list, description="Migration issues")

class ChainMigrationResult(BaseModel):
    """Chain migration result"""
    chain_id: str = Field(..., description="Chain ID")
    source_node: str = Field(..., description="Source node ID")
    target_node: str = Field(..., description="Target node ID")
    success: bool = Field(..., description="Migration success")
    blocks_transferred: int = Field(default=0, description="Number of blocks transferred")
    transfer_time_seconds: int = Field(default=0, description="Transfer time in seconds")
    verification_passed: bool = Field(default=False, description="Verification passed")
    error: Optional[str] = Field(None, description="Error message if failed")

class ChainBackupResult(BaseModel):
    """Chain backup result"""
    chain_id: str = Field(..., description="Chain ID")
    backup_file: str = Field(..., description="Backup file path")
    original_size_mb: float = Field(..., description="Original size in MB")
    backup_size_mb: float = Field(..., description="Backup size in MB")
    compression_ratio: float = Field(default=1.0, description="Compression ratio")
    checksum: str = Field(..., description="Backup file checksum")
    verification_passed: bool = Field(default=False, description="Verification passed")

class ChainRestoreResult(BaseModel):
    """Chain restore result"""
    chain_id: str = Field(..., description="Chain ID")
    node_id: str = Field(..., description="Target node ID")
    blocks_restored: int = Field(default=0, description="Number of blocks restored")
    verification_passed: bool = Field(default=False, description="Verification passed")
    error: Optional[str] = Field(None, description="Error message if failed")
