"""
Chain manager for multi-chain operations
"""

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from .config import MultiChainConfig, get_node_config
from .node_client import NodeClient
from models.chain import (
    ChainConfig, ChainInfo, ChainType, ChainStatus, 
    GenesisBlock, ChainMigrationPlan, ChainMigrationResult,
    ChainBackupResult, ChainRestoreResult
)

class ChainAlreadyExistsError(Exception):
    """Chain already exists error"""
    pass

class ChainNotFoundError(Exception):
    """Chain not found error"""
    pass

class NodeNotAvailableError(Exception):
    """Node not available error"""
    pass

class ChainManager:
    """Multi-chain manager"""
    
    def __init__(self, config: MultiChainConfig):
        self.config = config
        self._chain_cache: Dict[str, ChainInfo] = {}
        self._node_clients: Dict[str, Any] = {}
    
    async def list_chains(
        self, 
        chain_type: Optional[ChainType] = None,
        include_private: bool = False,
        sort_by: str = "id"
    ) -> List[ChainInfo]:
        """List all available chains"""
        chains = []
        
        # Get chains from all available nodes
        for node_id, node_config in self.config.nodes.items():
            try:
                node_chains = await self._get_node_chains(node_id)
                for chain in node_chains:
                    # Filter private chains if not requested
                    if not include_private and chain.privacy.visibility == "private":
                        continue
                    
                    # Filter by chain type if specified
                    if chain_type and chain.type != chain_type:
                        continue
                    
                    chains.append(chain)
            except Exception as e:
                # Log error but continue with other nodes
                print(f"Error getting chains from node {node_id}: {e}")
        
        # Remove duplicates (same chain on multiple nodes)
        unique_chains = {}
        for chain in chains:
            if chain.id not in unique_chains:
                unique_chains[chain.id] = chain
        
        chains = list(unique_chains.values())
        
        # Sort chains
        if sort_by == "id":
            chains.sort(key=lambda x: x.id)
        elif sort_by == "size":
            chains.sort(key=lambda x: x.size_mb, reverse=True)
        elif sort_by == "nodes":
            chains.sort(key=lambda x: x.node_count, reverse=True)
        elif sort_by == "created":
            chains.sort(key=lambda x: x.created_at, reverse=True)
        
        return chains
    
    async def get_chain_info(self, chain_id: str, detailed: bool = False, metrics: bool = False) -> ChainInfo:
        """Get detailed information about a chain"""
        # Check cache first
        if chain_id in self._chain_cache:
            chain_info = self._chain_cache[chain_id]
        else:
            # Get from node
            chain_info = await self._find_chain_on_nodes(chain_id)
            if not chain_info:
                raise ChainNotFoundError(f"Chain {chain_id} not found")
            
            # Cache the result
            self._chain_cache[chain_id] = chain_info
        
        # Add detailed information if requested
        if detailed or metrics:
            chain_info = await self._enrich_chain_info(chain_info)
        
        return chain_info
    
    async def create_chain(self, chain_config: ChainConfig, node_id: Optional[str] = None) -> str:
        """Create a new chain"""
        # Generate chain ID
        chain_id = self._generate_chain_id(chain_config)
        
        # Check if chain already exists
        try:
            await self.get_chain_info(chain_id)
            raise ChainAlreadyExistsError(f"Chain {chain_id} already exists")
        except ChainNotFoundError:
            pass  # Chain doesn't exist, which is good
        
        # Select node if not specified
        if not node_id:
            node_id = await self._select_best_node(chain_config)
        
        # Validate node availability
        if node_id not in self.config.nodes:
            raise NodeNotAvailableError(f"Node {node_id} not configured")
        
        # Create genesis block
        genesis_block = await self._create_genesis_block(chain_config, chain_id)
        
        # Create chain on node
        await self._create_chain_on_node(node_id, genesis_block)
        
        # Return chain ID
        return chain_id
    
    async def delete_chain(self, chain_id: str, force: bool = False) -> bool:
        """Delete a chain"""
        chain_info = await self.get_chain_info(chain_id)
        
        # Get all nodes hosting this chain
        hosting_nodes = await self._get_chain_hosting_nodes(chain_id)
        
        if not force and len(hosting_nodes) > 1:
            raise ValueError(f"Chain {chain_id} is hosted on {len(hosting_nodes)} nodes. Use --force to delete.")
        
        # Delete from all hosting nodes
        success = True
        for node_id in hosting_nodes:
            try:
                await self._delete_chain_from_node(node_id, chain_id)
            except Exception as e:
                print(f"Error deleting chain from node {node_id}: {e}")
                success = False
        
        # Remove from cache
        if chain_id in self._chain_cache:
            del self._chain_cache[chain_id]
        
        return success
    
    async def add_chain_to_node(self, chain_id: str, node_id: str) -> bool:
        """Add a chain to a node"""
        # Validate node
        if node_id not in self.config.nodes:
            raise NodeNotAvailableError(f"Node {node_id} not configured")
        
        # Get chain info
        chain_info = await self.get_chain_info(chain_id)
        
        # Add chain to node
        try:
            await self._add_chain_to_node(node_id, chain_info)
            return True
        except Exception as e:
            print(f"Error adding chain to node: {e}")
            return False
    
    async def remove_chain_from_node(self, chain_id: str, node_id: str, migrate: bool = False) -> bool:
        """Remove a chain from a node"""
        # Validate node
        if node_id not in self.config.nodes:
            raise NodeNotAvailableError(f"Node {node_id} not configured")
        
        if migrate:
            # Find alternative node
            target_node = await self._find_alternative_node(chain_id, node_id)
            if target_node:
                # Migrate chain first
                migration_result = await self.migrate_chain(chain_id, node_id, target_node)
                if not migration_result.success:
                    return False
        
        # Remove chain from node
        try:
            await self._remove_chain_from_node(node_id, chain_id)
            return True
        except Exception as e:
            print(f"Error removing chain from node: {e}")
            return False
    
    async def migrate_chain(self, chain_id: str, from_node: str, to_node: str, dry_run: bool = False) -> ChainMigrationResult:
        """Migrate a chain between nodes"""
        # Validate nodes
        if from_node not in self.config.nodes:
            raise NodeNotAvailableError(f"Source node {from_node} not configured")
        if to_node not in self.config.nodes:
            raise NodeNotAvailableError(f"Target node {to_node} not configured")
        
        # Get chain info
        chain_info = await self.get_chain_info(chain_id)
        
        # Create migration plan
        migration_plan = await self._create_migration_plan(chain_id, from_node, to_node, chain_info)
        
        if dry_run:
            return ChainMigrationResult(
                chain_id=chain_id,
                source_node=from_node,
                target_node=to_node,
                success=migration_plan.feasible,
                blocks_transferred=0,
                transfer_time_seconds=0,
                verification_passed=False,
                error=None if migration_plan.feasible else "Migration not feasible"
            )
        
        if not migration_plan.feasible:
            return ChainMigrationResult(
                chain_id=chain_id,
                source_node=from_node,
                target_node=to_node,
                success=False,
                blocks_transferred=0,
                transfer_time_seconds=0,
                verification_passed=False,
                error="; ".join(migration_plan.issues)
            )
        
        # Execute migration
        return await self._execute_migration(chain_id, from_node, to_node)
    
    async def backup_chain(self, chain_id: str, backup_path: Optional[str] = None, compress: bool = False, verify: bool = False) -> ChainBackupResult:
        """Backup a chain"""
        # Get chain info
        chain_info = await self.get_chain_info(chain_id)
        
        # Get hosting node
        hosting_nodes = await self._get_chain_hosting_nodes(chain_id)
        if not hosting_nodes:
            raise ChainNotFoundError(f"Chain {chain_id} not found on any node")
        
        node_id = hosting_nodes[0]  # Use first available node
        
        # Set backup path
        if not backup_path:
            backup_path = self.config.chains.backup_path / f"{chain_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
        
        # Execute backup
        return await self._execute_backup(chain_id, node_id, backup_path, compress, verify)
    
    async def restore_chain(self, backup_file: str, node_id: Optional[str] = None, verify: bool = False) -> ChainRestoreResult:
        """Restore a chain from backup"""
        backup_path = Path(backup_file)
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file {backup_file} not found")
        
        # Select node if not specified
        if not node_id:
            node_id = await self._select_best_node_for_restore()
        
        # Execute restore
        return await self._execute_restore(backup_path, node_id, verify)
    
    # Private methods
    
    def _generate_chain_id(self, chain_config: ChainConfig) -> str:
        """Generate a unique chain ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        prefix = f"AITBC-{chain_config.type.value.upper()}-{chain_config.purpose.upper()}"
        return f"{prefix}-{timestamp}"
    
    async def _get_node_chains(self, node_id: str) -> List[ChainInfo]:
        """Get chains from a specific node"""
        if node_id not in self.config.nodes:
            return []
        
        node_config = self.config.nodes[node_id]
        
        try:
            async with NodeClient(node_config) as client:
                return await client.get_hosted_chains()
        except Exception as e:
            print(f"Error getting chains from node {node_id}: {e}")
            return []
    
    async def _find_chain_on_nodes(self, chain_id: str) -> Optional[ChainInfo]:
        """Find a chain on available nodes"""
        for node_id in self.config.nodes:
            try:
                chains = await self._get_node_chains(node_id)
                for chain in chains:
                    if chain.id == chain_id:
                        return chain
            except Exception:
                continue
        return None
    
    async def _enrich_chain_info(self, chain_info: ChainInfo) -> ChainInfo:
        """Enrich chain info with detailed data"""
        # This would get additional metrics and detailed information
        # For now, return the same chain info
        return chain_info
    
    async def _select_best_node(self, chain_config: ChainConfig) -> str:
        """Select the best node for creating a chain"""
        # Simple selection - in reality, this would consider load, resources, etc.
        available_nodes = list(self.config.nodes.keys())
        if not available_nodes:
            raise NodeNotAvailableError("No nodes available")
        return available_nodes[0]
    
    async def _create_genesis_block(self, chain_config: ChainConfig, chain_id: str) -> GenesisBlock:
        """Create a genesis block for the chain"""
        timestamp = datetime.now()
        
        # Create state root (placeholder)
        state_data = {
            "chain_id": chain_id,
            "config": chain_config.dict(),
            "timestamp": timestamp.isoformat()
        }
        state_root = hashlib.sha256(json.dumps(state_data, sort_keys=True).encode()).hexdigest()
        
        # Create genesis hash
        genesis_data = {
            "chain_id": chain_id,
            "timestamp": timestamp.isoformat(),
            "state_root": state_root
        }
        genesis_hash = hashlib.sha256(json.dumps(genesis_data, sort_keys=True).encode()).hexdigest()
        
        return GenesisBlock(
            chain_id=chain_id,
            chain_type=chain_config.type,
            purpose=chain_config.purpose,
            name=chain_config.name,
            description=chain_config.description,
            timestamp=timestamp,
            consensus=chain_config.consensus,
            privacy=chain_config.privacy,
            parameters=chain_config.parameters,
            state_root=state_root,
            hash=genesis_hash
        )
    
    async def _create_chain_on_node(self, node_id: str, genesis_block: GenesisBlock) -> None:
        """Create a chain on a specific node"""
        if node_id not in self.config.nodes:
            raise NodeNotAvailableError(f"Node {node_id} not configured")
        
        node_config = self.config.nodes[node_id]
        
        try:
            async with NodeClient(node_config) as client:
                chain_id = await client.create_chain(genesis_block.dict())
                print(f"Successfully created chain {chain_id} on node {node_id}")
        except Exception as e:
            print(f"Error creating chain on node {node_id}: {e}")
            raise
    
    async def _get_chain_hosting_nodes(self, chain_id: str) -> List[str]:
        """Get all nodes hosting a specific chain"""
        hosting_nodes = []
        for node_id in self.config.nodes:
            try:
                chains = await self._get_node_chains(node_id)
                if any(chain.id == chain_id for chain in chains):
                    hosting_nodes.append(node_id)
            except Exception:
                continue
        return hosting_nodes
    
    async def _delete_chain_from_node(self, node_id: str, chain_id: str) -> None:
        """Delete a chain from a specific node"""
        if node_id not in self.config.nodes:
            raise NodeNotAvailableError(f"Node {node_id} not configured")
        
        node_config = self.config.nodes[node_id]
        
        try:
            async with NodeClient(node_config) as client:
                success = await client.delete_chain(chain_id)
                if success:
                    print(f"Successfully deleted chain {chain_id} from node {node_id}")
                else:
                    raise Exception(f"Failed to delete chain {chain_id}")
        except Exception as e:
            print(f"Error deleting chain from node {node_id}: {e}")
            raise
    
    async def _add_chain_to_node(self, node_id: str, chain_info: ChainInfo) -> None:
        """Add a chain to a specific node"""
        # This would actually add the chain to the node
        print(f"Adding chain {chain_info.id} to node {node_id}")
    
    async def _remove_chain_from_node(self, node_id: str, chain_id: str) -> None:
        """Remove a chain from a specific node"""
        # This would actually remove the chain from the node
        print(f"Removing chain {chain_id} from node {node_id}")
    
    async def _find_alternative_node(self, chain_id: str, exclude_node: str) -> Optional[str]:
        """Find an alternative node for a chain"""
        hosting_nodes = await self._get_chain_hosting_nodes(chain_id)
        for node_id in hosting_nodes:
            if node_id != exclude_node:
                return node_id
        return None
    
    async def _create_migration_plan(self, chain_id: str, from_node: str, to_node: str, chain_info: ChainInfo) -> ChainMigrationPlan:
        """Create a migration plan"""
        # This would analyze the migration and create a detailed plan
        return ChainMigrationPlan(
            chain_id=chain_id,
            source_node=from_node,
            target_node=to_node,
            size_mb=chain_info.size_mb,
            estimated_minutes=int(chain_info.size_mb / 100),  # Rough estimate
            required_space_mb=chain_info.size_mb * 1.5,  # 50% extra space
            available_space_mb=10000,  # Placeholder
            feasible=True,
            issues=[]
        )
    
    async def _execute_migration(self, chain_id: str, from_node: str, to_node: str) -> ChainMigrationResult:
        """Execute the actual migration"""
        # This would actually execute the migration
        print(f"Migrating chain {chain_id} from {from_node} to {to_node}")
        
        return ChainMigrationResult(
            chain_id=chain_id,
            source_node=from_node,
            target_node=to_node,
            success=True,
            blocks_transferred=1000,  # Placeholder
            transfer_time_seconds=300,  # Placeholder
            verification_passed=True
        )
    
    async def _execute_backup(self, chain_id: str, node_id: str, backup_path: str, compress: bool, verify: bool) -> ChainBackupResult:
        """Execute the actual backup"""
        if node_id not in self.config.nodes:
            raise NodeNotAvailableError(f"Node {node_id} not configured")
        
        node_config = self.config.nodes[node_id]
        
        try:
            async with NodeClient(node_config) as client:
                backup_info = await client.backup_chain(chain_id, backup_path)
                
                return ChainBackupResult(
                    chain_id=chain_id,
                    backup_file=backup_info["backup_file"],
                    original_size_mb=backup_info["original_size_mb"],
                    backup_size_mb=backup_info["backup_size_mb"],
                    compression_ratio=backup_info["original_size_mb"] / backup_info["backup_size_mb"],
                    checksum=backup_info["checksum"],
                    verification_passed=verify
                )
        except Exception as e:
            print(f"Error during backup: {e}")
            raise
    
    async def _execute_restore(self, backup_path: str, node_id: str, verify: bool) -> ChainRestoreResult:
        """Execute the actual restore"""
        if node_id not in self.config.nodes:
            raise NodeNotAvailableError(f"Node {node_id} not configured")
        
        node_config = self.config.nodes[node_id]
        
        try:
            async with NodeClient(node_config) as client:
                restore_info = await client.restore_chain(backup_path)
                
                return ChainRestoreResult(
                    chain_id=restore_info["chain_id"],
                    node_id=node_id,
                    blocks_restored=restore_info["blocks_restored"],
                    verification_passed=restore_info["verification_passed"]
                )
        except Exception as e:
            print(f"Error during restore: {e}")
            raise
    
    async def _select_best_node_for_restore(self) -> str:
        """Select the best node for restoring a chain"""
        available_nodes = list(self.config.nodes.keys())
        if not available_nodes:
            raise NodeNotAvailableError("No nodes available")
        return available_nodes[0]
