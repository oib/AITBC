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
        
        # Network partition tracking
        self.network_partitioned = False
        self.last_partition_healed = 0.0
        self.partitioned_validators: Set[str] = set()
        
        # Byzantine fault tolerance tracking
        self.prepare_messages: Dict[str, List[Dict]] = {}  # validator -> list of prepare messages
        self.consensus_attempts: int = 0
        
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
    
    def can_resume_consensus(self) -> bool:
        """Check if consensus can resume after network partition"""
        if not self.network_partitioned:
            return True
        
        # Require minimum time after partition healing
        if self.last_partition_healed > 0:
            return (time.time() - self.last_partition_healed) >= 5.0
        
        return False
    
    def mark_validator_partitioned(self, address: str) -> bool:
        """Mark a validator as partitioned"""
        if address not in self.validators:
            return False
        
        self.partitioned_validators.add(address)
        return True
    
    async def validate_transaction_async(self, transaction) -> bool:
        """Asynchronously validate a transaction"""
        # Simulate async validation
        await asyncio.sleep(0.001)
        
        # Basic validation
        if not hasattr(transaction, 'tx_id'):
            return False
        
        return True
    
    async def attempt_consensus(self, block_hash: str = "", round: int = 1) -> bool:
        """Attempt to reach consensus"""
        self.consensus_attempts += 1
        
        # Check if enough validators are available
        active_validators = self.get_consensus_participants()
        if len(active_validators) < 2:
            return False
        
        # Check if partitioned validators are too many
        if len(self.partitioned_validators) > len(self.validators) // 2:
            return False
        
        # Simulate consensus attempt
        await asyncio.sleep(0.01)
        
        # Simple consensus: succeed if majority of validators are active
        return len(active_validators) >= len(self.validators) // 2 + 1
    
    def record_prepare(self, validator: str, block_hash: str, round: int) -> bool:
        """Record a prepare message from a validator"""
        if validator not in self.validators:
            return False
        
        if validator not in self.prepare_messages:
            self.prepare_messages[validator] = []
        
        # Check for conflicting messages (Byzantine detection)
        for msg in self.prepare_messages[validator]:
            if msg['round'] == round and msg['block_hash'] != block_hash:
                # Conflicting message detected - still record it
                self.prepare_messages[validator].append({
                    'block_hash': block_hash,
                    'round': round,
                    'timestamp': time.time()
                })
                return True  # Return True even if conflicting
        
        self.prepare_messages[validator].append({
            'block_hash': block_hash,
            'round': round,
            'timestamp': time.time()
        })
        
        return True
    
    def detect_byzantine_behavior(self, validator: str) -> bool:
        """Detect if a validator exhibited Byzantine behavior"""
        if validator not in self.prepare_messages:
            return False
        
        messages = self.prepare_messages[validator]
        if len(messages) < 2:
            return False
        
        # Check for conflicting messages in same round
        rounds: Dict[int, Set[str]] = {}
        for msg in messages:
            if msg['round'] not in rounds:
                rounds[msg['round']] = set()
            rounds[msg['round']].add(msg['block_hash'])
        
        # Byzantine if any round has multiple block hashes
        for block_hashes in rounds.values():
            if len(block_hashes) > 1:
                return True
        
        return False
    
    def get_state_snapshot(self) -> Dict:
        """Get a snapshot of the current blockchain state"""
        return {
            'chain_id': self.chain_id,
            'validators': {
                addr: {
                    'stake': v.stake,
                    'role': v.role.value,
                    'is_active': v.is_active,
                    'reputation': v.reputation
                }
                for addr, v in self.validators.items()
            },
            'network_partitioned': self.network_partitioned,
            'partitioned_validators': list(self.partitioned_validators),
            'consensus_attempts': self.consensus_attempts,
            'timestamp': time.time()
        }
    
    def calculate_state_hash(self, state: Dict) -> str:
        """Calculate hash of blockchain state"""
        import json
        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()
    
    def create_block(self) -> Dict:
        """Create a new block"""
        proposer = self.select_proposer(len(self.validators))
        return {
            'block_height': len(self.validators),
            'proposer': proposer,
            'timestamp': time.time(),
            'hash': hashlib.sha256(str(time.time()).encode()).hexdigest()
        }
    
    def add_transaction(self, transaction) -> bool:
        """Add a transaction to the block"""
        return hasattr(transaction, 'tx_id')
    
    def simulate_crash(self):
        """Simulate a crash (for testing)"""
        self._crashed_state = self.get_state_snapshot()
    
    def recover_from_crash(self):
        """Recover from a crash (for testing)"""
        if hasattr(self, '_crashed_state'):
            self._crashed_state = None
    
    def recover_state(self, state: Dict) -> bool:
        """Recover state from snapshot (for testing)"""
        try:
            self.validators = {}
            for addr, v_data in state.get('validators', {}).items():
                self.validators[addr] = Validator(
                    address=addr,
                    stake=v_data.get('stake', 1000.0),
                    reputation=v_data.get('reputation', 1.0),
                    role=ValidatorRole(v_data.get('role', 'STANDBY')),
                    last_proposed=0,
                    is_active=v_data.get('is_active', True)
                )
            self.network_partitioned = state.get('network_partitioned', False)
            self.consensus_attempts = state.get('consensus_attempts', 0)
            return True
        except Exception:
            return False
    
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
