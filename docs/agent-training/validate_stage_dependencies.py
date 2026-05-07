#!/usr/bin/env python3
"""
Stage Dependency Validator

Validates that stage JSON files follow dependency rules:
1. Operations with wallet+password parameters should have wallet_balance check before them
2. Operations with amount/price parameters should have currency field
3. Operations that require resources (agent_id, dispute_id, etc.) should have corresponding create operations
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set

# Parameters that indicate wallet+password operations
WALLET_PASSWORD_PARAMS = {"wallet", "password"}

# Parameters that indicate currency requirement
CURRENCY_REQUIRED_PARAMS = {"amount", "price", "bounty_amount", "stake_amount", "spread"}

# Resource ID patterns
RESOURCE_PATTERNS = {
    "agent_id": "agent_*",
    "dispute_id": "dispute_*",
    "enterprise_id": "enterprise_*",
    "proposal_id": "proposal_*",
    "island_id": "island_*",
    "workflow_id": "workflow_*",
    "gpu_id": "gpu_*",
    "listing_id": "listing_*",
    "job_id": "job_*",
    "bounty_id": "bounty_*",
    "mm_id": "mm_*",
    "fl_id": "fl_*",
    "swarm_id": "swarm_*",
    "validator_id": "validator_*",
    "bridge_tx_id": "bridge_tx_*",
    "transfer_id": "transfer_*",
    "deployment_id": "deployment_*",
    "pubsub_config_id": "pubsub_config_*",
    "sync_config_id": "sync_config_*",
}

# Operations that create resources (can create multiple resources)
RESOURCE_CREATORS = {
    "agent_create": ["agent_id"],
    "dispute_create": ["dispute_id"],
    "enterprise_create": ["enterprise_id"],
    "governance_propose": ["proposal_id"],
    "island_create": ["island_id"],
    "multi_chain_island_setup": ["island_id"],
    "workflow_create": ["workflow_id"],
    "market_gpu_register": ["gpu_id", "listing_id"],
    "market_sell": ["listing_id"],
    "ai_submit": ["job_id"],
    "bounty_system": ["bounty_id"],
    "cross_chain_market_maker": ["mm_id"],
    "federated_learning_coordinator": ["fl_id"],
    "agent_swarm_create": ["swarm_id"],
    "staking_validator_agent": ["validator_id"],
    "cross_chain_bridge": ["bridge_tx_id"],
    "cross_chain_transfer": ["transfer_id"],
    "production_deploy": ["deployment_id"],
    "redis_pubsub_config": ["pubsub_config_id"],
    "gossip_sync_config": ["sync_config_id"],
}


class StageValidator:
    def __init__(self, stage_file: Path):
        self.stage_file = stage_file
        self.stage_data = json.loads(stage_file.read_text())
        self.errors = []
        self.warnings = []

    def validate(self) -> bool:
        """Run all validation checks."""
        operations = self.stage_data.get("training_data", {}).get("operations", [])
        
        self._validate_wallet_balance_checks(operations)
        self._validate_currency_fields(operations)
        self._validate_resource_dependencies(operations)
        
        return len(self.errors) == 0

    def _validate_wallet_balance_checks(self, operations: List[Dict]):
        """Ensure operations with wallet+password have wallet_balance check before them."""
        wallet_balance_found = False
        
        for i, op in enumerate(operations):
            op_name = op.get("operation", "")
            params = op.get("parameters", {})
            
            if op_name == "wallet_balance":
                wallet_balance_found = True
                continue
            
            # Check if operation requires wallet+password
            has_wallet = "wallet" in params
            has_password = "password" in params
            
            if has_wallet and has_password:
                if not wallet_balance_found:
                    self.errors.append(
                        f"Operation '{op_name}' (index {i}) has wallet+password parameters "
                        f"but no wallet_balance check before it"
                    )

    def _validate_currency_fields(self, operations: List[Dict]):
        """Ensure operations with amount/price parameters have currency field."""
        for i, op in enumerate(operations):
            op_name = op.get("operation", "")
            params = op.get("parameters", {})
            
            # Check if operation requires currency
            requires_currency = any(
                param in CURRENCY_REQUIRED_PARAMS for param in params.keys()
            )
            
            if requires_currency and "currency" not in params:
                self.errors.append(
                    f"Operation '{op_name}' (index {i}) has {CURRENCY_REQUIRED_PARAMS} parameter(s) "
                    f"but missing 'currency' field"
                )

    def _validate_resource_dependencies(self, operations: List[Dict]):
        """Ensure operations that require resources have corresponding create operations."""
        created_resources: Dict[str, Set[str]] = {}  # resource_type -> set of patterns
        required_resources: List[tuple] = []  # (index, op_name, resource_type, pattern)
        
        for i, op in enumerate(operations):
            op_name = op.get("operation", "")
            params = op.get("parameters", {})
            
            # Track resources created
            if op_name in RESOURCE_CREATORS:
                resource_types = RESOURCE_CREATORS[op_name]
                if isinstance(resource_types, str):
                    resource_types = [resource_types]
                for resource_type in resource_types:
                    if resource_type not in created_resources:
                        created_resources[resource_type] = set()
                    created_resources[resource_type].add(RESOURCE_PATTERNS.get(resource_type, f"{resource_type}_*"))
            
            # Track resources required
            for param_name, param_value in params.items():
                for resource_type, pattern in RESOURCE_PATTERNS.items():
                    if param_name == resource_type or (isinstance(param_value, str) and pattern in param_value):
                        required_resources.append((i, op_name, resource_type, pattern))
        
        # Validate that required resources have corresponding create operations
        for index, op_name, resource_type, pattern in required_resources:
            if resource_type not in created_resources:
                self.errors.append(
                    f"Operation '{op_name}' (index {index}) requires '{resource_type}' "
                    f"but no '{resource_type}' create operation found"
                )

    def report(self):
        """Print validation report."""
        stage_name = self.stage_data.get("stage", self.stage_file.name)
        
        if self.errors:
            print(f"❌ {stage_name}: {len(self.errors)} error(s)")
            for error in self.errors:
                print(f"   - {error}")
        else:
            print(f"✅ {stage_name}: No errors")
        
        if self.warnings:
            print(f"⚠️  {stage_name}: {len(self.warnings)} warning(s)")
            for warning in self.warnings:
                print(f"   - {warning}")


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_stage_dependencies.py <stage_file.json> [stage_file2.json ...]")
        sys.exit(1)
    
    all_valid = True
    for stage_path in sys.argv[1:]:
        stage_file = Path(stage_path)
        if not stage_file.exists():
            print(f"❌ File not found: {stage_file}")
            all_valid = False
            continue
        
        validator = StageValidator(stage_file)
        if not validator.validate():
            all_valid = False
        validator.report()
    
    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
