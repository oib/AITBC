"""
Genesis block generator for multi-chain functionality
"""

import hashlib
import json
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from core.config import MultiChainConfig
from models.chain import GenesisBlock, GenesisConfig, ChainType, ConsensusAlgorithm

class GenesisValidationError(Exception):
    """Genesis validation error"""
    pass

class GenesisGenerator:
    """Genesis block generator"""
    
    def __init__(self, config: MultiChainConfig):
        self.config = config
        self.templates_dir = Path(__file__).parent.parent.parent / "templates" / "genesis"
    
    def create_genesis(self, genesis_config: GenesisConfig) -> GenesisBlock:
        """Create a genesis block from configuration"""
        # Validate configuration
        self._validate_genesis_config(genesis_config)
        
        # Generate chain ID if not provided
        if not genesis_config.chain_id:
            genesis_config.chain_id = self._generate_chain_id(genesis_config)
        
        # Set timestamp if not provided
        if not genesis_config.timestamp:
            genesis_config.timestamp = datetime.now()
        
        # Calculate state root
        state_root = self._calculate_state_root(genesis_config)
        
        # Calculate genesis hash
        genesis_hash = self._calculate_genesis_hash(genesis_config, state_root)
        
        # Create genesis block
        genesis_block = GenesisBlock(
            chain_id=genesis_config.chain_id,
            chain_type=genesis_config.chain_type,
            purpose=genesis_config.purpose,
            name=genesis_config.name,
            description=genesis_config.description,
            timestamp=genesis_config.timestamp,
            parent_hash=genesis_config.parent_hash,
            gas_limit=genesis_config.gas_limit,
            gas_price=genesis_config.gas_price,
            difficulty=genesis_config.difficulty,
            block_time=genesis_config.block_time,
            accounts=genesis_config.accounts,
            contracts=genesis_config.contracts,
            consensus=genesis_config.consensus,
            privacy=genesis_config.privacy,
            parameters=genesis_config.parameters,
            state_root=state_root,
            hash=genesis_hash
        )
        
        return genesis_block
    
    def create_from_template(self, template_name: str, custom_config_file: str) -> GenesisBlock:
        """Create genesis block from template"""
        # Load template
        template_path = self.templates_dir / f"{template_name}.yaml"
        if not template_path.exists():
            raise ValueError(f"Template {template_name} not found at {template_path}")
        
        with open(template_path, 'r') as f:
            template_data = yaml.safe_load(f)
        
        # Load custom configuration
        with open(custom_config_file, 'r') as f:
            custom_data = yaml.safe_load(f)
        
        # Merge template with custom config
        merged_config = self._merge_configs(template_data, custom_data)
        
        # Create genesis config
        genesis_config = GenesisConfig(**merged_config['genesis'])
        
        # Create genesis block
        return self.create_genesis(genesis_config)
    
    def validate_genesis(self, genesis_block: GenesisBlock) -> 'ValidationResult':
        """Validate a genesis block"""
        errors = []
        checks = {}
        
        # Check required fields
        checks['chain_id'] = bool(genesis_block.chain_id)
        if not genesis_block.chain_id:
            errors.append("Chain ID is required")
        
        checks['chain_type'] = genesis_block.chain_type in ChainType
        if genesis_block.chain_type not in ChainType:
            errors.append(f"Invalid chain type: {genesis_block.chain_type}")
        
        checks['purpose'] = bool(genesis_block.purpose)
        if not genesis_block.purpose:
            errors.append("Purpose is required")
        
        checks['name'] = bool(genesis_block.name)
        if not genesis_block.name:
            errors.append("Name is required")
        
        checks['timestamp'] = isinstance(genesis_block.timestamp, datetime)
        if not isinstance(genesis_block.timestamp, datetime):
            errors.append("Invalid timestamp format")
        
        checks['consensus'] = bool(genesis_block.consensus)
        if not genesis_block.consensus:
            errors.append("Consensus configuration is required")
        
        checks['hash'] = bool(genesis_block.hash)
        if not genesis_block.hash:
            errors.append("Genesis hash is required")
        
        # Validate hash
        if genesis_block.hash:
            calculated_hash = self._calculate_genesis_hash(genesis_block, genesis_block.state_root)
            checks['hash_valid'] = genesis_block.hash == calculated_hash
            if genesis_block.hash != calculated_hash:
                errors.append("Genesis hash does not match calculated hash")
        
        # Validate state root
        if genesis_block.state_root:
            calculated_state_root = self._calculate_state_root_from_block(genesis_block)
            checks['state_root_valid'] = genesis_block.state_root == calculated_state_root
            if genesis_block.state_root != calculated_state_root:
                errors.append("State root does not match calculated state root")
        
        # Validate accounts
        checks['accounts_valid'] = all(
            bool(account.address) and bool(account.balance) 
            for account in genesis_block.accounts
        )
        if not checks['accounts_valid']:
            errors.append("All accounts must have address and balance")
        
        # Validate contracts
        checks['contracts_valid'] = all(
            bool(contract.name) and bool(contract.address) and bool(contract.bytecode)
            for contract in genesis_block.contracts
        )
        if not checks['contracts_valid']:
            errors.append("All contracts must have name, address, and bytecode")
        
        # Validate consensus
        if genesis_block.consensus:
            checks['consensus_algorithm'] = genesis_block.consensus.algorithm in ConsensusAlgorithm
            if genesis_block.consensus.algorithm not in ConsensusAlgorithm:
                errors.append(f"Invalid consensus algorithm: {genesis_block.consensus.algorithm}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            checks=checks
        )
    
    def get_genesis_info(self, genesis_file: str) -> Dict[str, Any]:
        """Get information about a genesis block file"""
        genesis_path = Path(genesis_file)
        if not genesis_path.exists():
            raise FileNotFoundError(f"Genesis file {genesis_file} not found")
        
        # Load genesis block
        if genesis_path.suffix.lower() in ['.yaml', '.yml']:
            with open(genesis_path, 'r') as f:
                genesis_data = yaml.safe_load(f)
        else:
            with open(genesis_path, 'r') as f:
                genesis_data = json.load(f)
        
        genesis_block = GenesisBlock(**genesis_data)
        
        return {
            "chain_id": genesis_block.chain_id,
            "chain_type": genesis_block.chain_type.value,
            "purpose": genesis_block.purpose,
            "name": genesis_block.name,
            "description": genesis_block.description,
            "created": genesis_block.timestamp.isoformat(),
            "genesis_hash": genesis_block.hash,
            "state_root": genesis_block.state_root,
            "consensus_algorithm": genesis_block.consensus.algorithm.value,
            "block_time": genesis_block.block_time,
            "gas_limit": genesis_block.gas_limit,
            "gas_price": genesis_block.gas_price,
            "accounts_count": len(genesis_block.accounts),
            "contracts_count": len(genesis_block.contracts),
            "privacy_visibility": genesis_block.privacy.visibility,
            "access_control": genesis_block.privacy.access_control,
            "file_size": genesis_path.stat().st_size,
            "file_format": genesis_path.suffix.lower().replace('.', '')
        }
    
    def export_genesis(self, chain_id: str, format: str = "json") -> str:
        """Export genesis block in specified format"""
        # This would get the genesis block from storage
        # For now, return placeholder
        return f"Genesis block for {chain_id} in {format} format"
    
    def calculate_genesis_hash(self, genesis_file: str) -> str:
        """Calculate genesis hash from file"""
        genesis_path = Path(genesis_file)
        if not genesis_path.exists():
            raise FileNotFoundError(f"Genesis file {genesis_file} not found")
        
        # Load genesis block
        if genesis_path.suffix.lower() in ['.yaml', '.yml']:
            with open(genesis_path, 'r') as f:
                genesis_data = yaml.safe_load(f)
        else:
            with open(genesis_path, 'r') as f:
                genesis_data = json.load(f)
        
        genesis_block = GenesisBlock(**genesis_data)
        
        return self._calculate_genesis_hash(genesis_block, genesis_block.state_root)
    
    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        """List available genesis templates"""
        templates = {}
        
        if not self.templates_dir.exists():
            return templates
        
        for template_file in self.templates_dir.glob("*.yaml"):
            template_name = template_file.stem
            
            try:
                with open(template_file, 'r') as f:
                    template_data = yaml.safe_load(f)
                
                templates[template_name] = {
                    "name": template_name,
                    "description": template_data.get('description', ''),
                    "chain_type": template_data.get('genesis', {}).get('chain_type', 'unknown'),
                    "purpose": template_data.get('genesis', {}).get('purpose', 'unknown'),
                    "file_path": str(template_file)
                }
            except Exception as e:
                templates[template_name] = {
                    "name": template_name,
                    "description": f"Error loading template: {e}",
                    "chain_type": "error",
                    "purpose": "error",
                    "file_path": str(template_file)
                }
        
        return templates
    
    # Private methods
    
    def _validate_genesis_config(self, genesis_config: GenesisConfig) -> None:
        """Validate genesis configuration"""
        if not genesis_config.chain_type:
            raise GenesisValidationError("Chain type is required")
        
        if not genesis_config.purpose:
            raise GenesisValidationError("Purpose is required")
        
        if not genesis_config.name:
            raise GenesisValidationError("Name is required")
        
        if not genesis_config.consensus:
            raise GenesisValidationError("Consensus configuration is required")
        
        if genesis_config.consensus.algorithm not in ConsensusAlgorithm:
            raise GenesisValidationError(f"Invalid consensus algorithm: {genesis_config.consensus.algorithm}")
    
    def _generate_chain_id(self, genesis_config: GenesisConfig) -> str:
        """Generate a unique chain ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        prefix = f"AITBC-{genesis_config.chain_type.value.upper()}-{genesis_config.purpose.upper()}"
        return f"{prefix}-{timestamp}"
    
    def _calculate_state_root(self, genesis_config: GenesisConfig) -> str:
        """Calculate state root hash"""
        state_data = {
            "chain_id": genesis_config.chain_id,
            "chain_type": genesis_config.chain_type.value,
            "purpose": genesis_config.purpose,
            "name": genesis_config.name,
            "timestamp": genesis_config.timestamp.isoformat() if genesis_config.timestamp else datetime.now().isoformat(),
            "accounts": [account.dict() for account in genesis_config.accounts],
            "contracts": [contract.dict() for contract in genesis_config.contracts],
            "parameters": genesis_config.parameters.dict()
        }
        
        state_json = json.dumps(state_data, sort_keys=True)
        return hashlib.sha256(state_json.encode()).hexdigest()
    
    def _calculate_genesis_hash(self, genesis_config: GenesisConfig, state_root: str) -> str:
        """Calculate genesis block hash"""
        genesis_data = {
            "chain_id": genesis_config.chain_id,
            "chain_type": genesis_config.chain_type.value,
            "purpose": genesis_config.purpose,
            "name": genesis_config.name,
            "timestamp": genesis_config.timestamp.isoformat() if genesis_config.timestamp else datetime.now().isoformat(),
            "parent_hash": genesis_config.parent_hash,
            "gas_limit": genesis_config.gas_limit,
            "gas_price": genesis_config.gas_price,
            "difficulty": genesis_config.difficulty,
            "block_time": genesis_config.block_time,
            "consensus": genesis_config.consensus.dict(),
            "privacy": genesis_config.privacy.dict(),
            "parameters": genesis_config.parameters.dict(),
            "state_root": state_root
        }
        
        genesis_json = json.dumps(genesis_data, sort_keys=True)
        return hashlib.sha256(genesis_json.encode()).hexdigest()
    
    def _calculate_state_root_from_block(self, genesis_block: GenesisBlock) -> str:
        """Calculate state root from genesis block"""
        state_data = {
            "chain_id": genesis_block.chain_id,
            "chain_type": genesis_block.chain_type.value,
            "purpose": genesis_block.purpose,
            "name": genesis_block.name,
            "timestamp": genesis_block.timestamp.isoformat(),
            "accounts": [account.dict() for account in genesis_block.accounts],
            "contracts": [contract.dict() for contract in genesis_block.contracts],
            "parameters": genesis_block.parameters.dict()
        }
        
        state_json = json.dumps(state_data, sort_keys=True)
        return hashlib.sha256(state_json.encode()).hexdigest()
    
    def _merge_configs(self, template: Dict[str, Any], custom: Dict[str, Any]) -> Dict[str, Any]:
        """Merge template configuration with custom overrides"""
        result = template.copy()
        
        if 'genesis' in custom:
            for key, value in custom['genesis'].items():
                if isinstance(value, dict) and key in result.get('genesis', {}):
                    result['genesis'][key].update(value)
                else:
                    if 'genesis' not in result:
                        result['genesis'] = {}
                    result['genesis'][key] = value
        
        return result


class ValidationResult:
    """Genesis validation result"""
    
    def __init__(self, is_valid: bool, errors: list, checks: dict):
        self.is_valid = is_valid
        self.errors = errors
        self.checks = checks
