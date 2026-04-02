"""
Multi-Validator Proof of Authority Consensus Implementation
Extends single validator PoA to support multiple validators with rotation
"""

import asyncio
import time
import hashlib
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from enum import Enum

from ..config import settings
from ..models import Block, Transaction
from ..database import session_scope

class ValidatorRole(Enum):
    PROPOSER = "proposer"
    VALIDATOR = "validator"
    STANDBY = "standby"

@dataclass
class Validator:
    address: str
    stake: float
    reputation: float
    role: ValidatorRole
    last_proposed: int
    is_active: bool

class MultiValidatorPoA:
    """Multi-Validator Proof of Authority consensus mechanism"""
    
    def __init__(self, chain_id: str):
        self.chain_id = chain_id
        self.validators: Dict[str, Validator] = {}
        self.current_proposer_index = 0
        self.round_robin_enabled = True
        self.consensus_timeout = 30  # seconds
        
    def add_validator(self, address: str, stake: float = 1000.0) -> bool:
        """Add a new validator to the consensus"""
        if address in self.validators:
            return False
            
        self.validators[address] = Validator(
            address=address,
            stake=stake,
            reputation=1.0,
            role=ValidatorRole.STANDBY,
            last_proposed=0,
            is_active=True
        )
        return True
    
    def remove_validator(self, address: str) -> bool:
        """Remove a validator from the consensus"""
        if address not in self.validators:
            return False
        
        validator = self.validators[address]
        validator.is_active = False
        validator.role = ValidatorRole.STANDBY
        return True
    
    def select_proposer(self, block_height: int) -> Optional[str]:
        """Select proposer for the current block using round-robin"""
        active_validators = [
            v for v in self.validators.values() 
            if v.is_active and v.role in [ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR]
        ]
        
        if not active_validators:
            return None
        
        # Round-robin selection
        proposer_index = block_height % len(active_validators)
        return active_validators[proposer_index].address
    
    def validate_block(self, block: Block, proposer: str) -> bool:
        """Validate a proposed block"""
        if proposer not in self.validators:
            return False
        
        validator = self.validators[proposer]
        if not validator.is_active:
            return False
        
        # Check if validator is allowed to propose
        if validator.role not in [ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR]:
            return False
        
        # Additional validation logic here
        return True
    
    def get_consensus_participants(self) -> List[str]:
        """Get list of active consensus participants"""
        return [
            v.address for v in self.validators.values()
            if v.is_active and v.role in [ValidatorRole.PROPOSER, ValidatorRole.VALIDATOR]
        ]
    
    def update_validator_reputation(self, address: str, delta: float) -> bool:
        """Update validator reputation"""
        if address not in self.validators:
            return False
        
        validator = self.validators[address]
        validator.reputation = max(0.0, min(1.0, validator.reputation + delta))
        return True

# Global consensus instance
consensus_instances: Dict[str, MultiValidatorPoA] = {}

def get_consensus(chain_id: str) -> MultiValidatorPoA:
    """Get or create consensus instance for chain"""
    if chain_id not in consensus_instances:
        consensus_instances[chain_id] = MultiValidatorPoA(chain_id)
    return consensus_instances[chain_id]
