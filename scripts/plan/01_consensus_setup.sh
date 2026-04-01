#!/bin/bash

# Phase 1: Consensus Layer Setup Script
# Implements multi-validator PoA and PBFT consensus mechanisms

set -e

echo "=== PHASE 1: CONSENSUS LAYER SETUP ==="

# Configuration
CONSENSUS_DIR="/opt/aitbc/apps/blockchain-node/src/aitbc_chain/consensus"
VALIDATOR_COUNT=5
TEST_NETWORK="consensus-test"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to backup existing consensus files
backup_consensus() {
    log_info "Backing up existing consensus files..."
    if [ -d "$CONSENSUS_DIR" ]; then
        cp -r "$CONSENSUS_DIR" "${CONSENSUS_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
        log_info "Backup completed"
    fi
}

# Function to create multi-validator PoA implementation
create_multi_validator_poa() {
    log_info "Creating multi-validator PoA implementation..."
    
    cat > "$CONSENSUS_DIR/multi_validator_poa.py" << 'EOF'
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
EOF

    log_info "Multi-validator PoA implementation created"
}

# Function to create validator rotation mechanism
create_validator_rotation() {
    log_info "Creating validator rotation mechanism..."
    
    cat > "$CONSENSUS_DIR/rotation.py" << 'EOF'
"""
Validator Rotation Mechanism
Handles automatic rotation of validators based on performance and stake
"""

import asyncio
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

from .multi_validator_poa import MultiValidatorPoA, Validator, ValidatorRole

class RotationStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    STAKE_WEIGHTED = "stake_weighted"
    REPUTATION_BASED = "reputation_based"
    HYBRID = "hybrid"

@dataclass
class RotationConfig:
    strategy: RotationStrategy
    rotation_interval: int  # blocks
    min_stake: float
    reputation_threshold: float
    max_validators: int

class ValidatorRotation:
    """Manages validator rotation based on various strategies"""
    
    def __init__(self, consensus: MultiValidatorPoA, config: RotationConfig):
        self.consensus = consensus
        self.config = config
        self.last_rotation_height = 0
        
    def should_rotate(self, current_height: int) -> bool:
        """Check if rotation should occur at current height"""
        return (current_height - self.last_rotation_height) >= self.config.rotation_interval
    
    def rotate_validators(self, current_height: int) -> bool:
        """Perform validator rotation based on configured strategy"""
        if not self.should_rotate(current_height):
            return False
        
        if self.config.strategy == RotationStrategy.ROUND_ROBIN:
            return self._rotate_round_robin()
        elif self.config.strategy == RotationStrategy.STAKE_WEIGHTED:
            return self._rotate_stake_weighted()
        elif self.config.strategy == RotationStrategy.REPUTATION_BASED:
            return self._rotate_reputation_based()
        elif self.config.strategy == RotationStrategy.HYBRID:
            return self._rotate_hybrid()
        
        return False
    
    def _rotate_round_robin(self) -> bool:
        """Round-robin rotation of validator roles"""
        validators = list(self.consensus.validators.values())
        active_validators = [v for v in validators if v.is_active]
        
        # Rotate roles among active validators
        for i, validator in enumerate(active_validators):
            if i == 0:
                validator.role = ValidatorRole.PROPOSER
            elif i < 3:  # Top 3 become validators
                validator.role = ValidatorRole.VALIDATOR
            else:
                validator.role = ValidatorRole.STANDBY
        
        self.last_rotation_height += self.config.rotation_interval
        return True
    
    def _rotate_stake_weighted(self) -> bool:
        """Stake-weighted rotation"""
        validators = sorted(
            [v for v in self.consensus.validators.values() if v.is_active],
            key=lambda v: v.stake,
            reverse=True
        )
        
        for i, validator in enumerate(validators[:self.config.max_validators]):
            if i == 0:
                validator.role = ValidatorRole.PROPOSER
            elif i < 4:
                validator.role = ValidatorRole.VALIDATOR
            else:
                validator.role = ValidatorRole.STANDBY
        
        self.last_rotation_height += self.config.rotation_interval
        return True
    
    def _rotate_reputation_based(self) -> bool:
        """Reputation-based rotation"""
        validators = sorted(
            [v for v in self.consensus.validators.values() if v.is_active],
            key=lambda v: v.reputation,
            reverse=True
        )
        
        # Filter by reputation threshold
        qualified_validators = [
            v for v in validators 
            if v.reputation >= self.config.reputation_threshold
        ]
        
        for i, validator in enumerate(qualified_validators[:self.config.max_validators]):
            if i == 0:
                validator.role = ValidatorRole.PROPOSER
            elif i < 4:
                validator.role = ValidatorRole.VALIDATOR
            else:
                validator.role = ValidatorRole.STANDBY
        
        self.last_rotation_height += self.config.rotation_interval
        return True
    
    def _rotate_hybrid(self) -> bool:
        """Hybrid rotation considering both stake and reputation"""
        validators = [v for v in self.consensus.validators.values() if v.is_active]
        
        # Calculate hybrid score
        for validator in validators:
            validator.hybrid_score = validator.stake * validator.reputation
        
        # Sort by hybrid score
        validators.sort(key=lambda v: v.hybrid_score, reverse=True)
        
        for i, validator in enumerate(validators[:self.config.max_validators]):
            if i == 0:
                validator.role = ValidatorRole.PROPOSER
            elif i < 4:
                validator.role = ValidatorRole.VALIDATOR
            else:
                validator.role = ValidatorRole.STANDBY
        
        self.last_rotation_height += self.config.rotation_interval
        return True

# Default rotation configuration
DEFAULT_ROTATION_CONFIG = RotationConfig(
    strategy=RotationStrategy.HYBRID,
    rotation_interval=100,  # Rotate every 100 blocks
    min_stake=1000.0,
    reputation_threshold=0.7,
    max_validators=10
)
EOF

    log_info "Validator rotation mechanism created"
}

# Function to create PBFT consensus implementation
create_pbft_consensus() {
    log_info "Creating PBFT consensus implementation..."
    
    cat > "$CONSENSUS_DIR/pbft.py" << 'EOF'
"""
Practical Byzantine Fault Tolerance (PBFT) Consensus Implementation
Provides Byzantine fault tolerance for up to 1/3 faulty validators
"""

import asyncio
import time
import hashlib
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from .multi_validator_poa import MultiValidatorPoA, Validator

class PBFTPhase(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    EXECUTE = "execute"

class PBFTMessageType(Enum):
    PRE_PREPARE = "pre_prepare"
    PREPARE = "prepare"
    COMMIT = "commit"
    VIEW_CHANGE = "view_change"

@dataclass
class PBFTMessage:
    message_type: PBFTMessageType
    sender: str
    view_number: int
    sequence_number: int
    digest: str
    signature: str
    timestamp: float

@dataclass
class PBFTState:
    current_view: int
    current_sequence: int
    prepared_messages: Dict[str, List[PBFTMessage]]
    committed_messages: Dict[str, List[PBFTMessage]]
    pre_prepare_messages: Dict[str, PBFTMessage]

class PBFTConsensus:
    """PBFT consensus implementation"""
    
    def __init__(self, consensus: MultiValidatorPoA):
        self.consensus = consensus
        self.state = PBFTState(
            current_view=0,
            current_sequence=0,
            prepared_messages={},
            committed_messages={},
            pre_prepare_messages={}
        )
        self.fault_tolerance = max(1, len(consensus.get_consensus_participants()) // 3)
        self.required_messages = 2 * self.fault_tolerance + 1
        
    def get_message_digest(self, block_hash: str, sequence: int, view: int) -> str:
        """Generate message digest for PBFT"""
        content = f"{block_hash}:{sequence}:{view}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def pre_prepare_phase(self, proposer: str, block_hash: str) -> bool:
        """Phase 1: Pre-prepare"""
        sequence = self.state.current_sequence + 1
        view = self.state.current_view
        digest = self.get_message_digest(block_hash, sequence, view)
        
        message = PBFTMessage(
            message_type=PBFTMessageType.PRE_PREPARE,
            sender=proposer,
            view_number=view,
            sequence_number=sequence,
            digest=digest,
            signature="",  # Would be signed in real implementation
            timestamp=time.time()
        )
        
        # Store pre-prepare message
        key = f"{sequence}:{view}"
        self.state.pre_prepare_messages[key] = message
        
        # Broadcast to all validators
        await self._broadcast_message(message)
        return True
    
    async def prepare_phase(self, validator: str, pre_prepare_msg: PBFTMessage) -> bool:
        """Phase 2: Prepare"""
        key = f"{pre_prepare_msg.sequence_number}:{pre_prepare_msg.view_number}"
        
        if key not in self.state.pre_prepare_messages:
            return False
        
        # Create prepare message
        prepare_msg = PBFTMessage(
            message_type=PBFTMessageType.PREPARE,
            sender=validator,
            view_number=pre_prepare_msg.view_number,
            sequence_number=pre_prepare_msg.sequence_number,
            digest=pre_prepare_msg.digest,
            signature="",  # Would be signed
            timestamp=time.time()
        )
        
        # Store prepare message
        if key not in self.state.prepared_messages:
            self.state.prepared_messages[key] = []
        self.state.prepared_messages[key].append(prepare_msg)
        
        # Broadcast prepare message
        await self._broadcast_message(prepare_msg)
        
        # Check if we have enough prepare messages
        return len(self.state.prepared_messages[key]) >= self.required_messages
    
    async def commit_phase(self, validator: str, prepare_msg: PBFTMessage) -> bool:
        """Phase 3: Commit"""
        key = f"{prepare_msg.sequence_number}:{prepare_msg.view_number}"
        
        # Create commit message
        commit_msg = PBFTMessage(
            message_type=PBFTMessageType.COMMIT,
            sender=validator,
            view_number=prepare_msg.view_number,
            sequence_number=prepare_msg.sequence_number,
            digest=prepare_msg.digest,
            signature="",  # Would be signed
            timestamp=time.time()
        )
        
        # Store commit message
        if key not in self.state.committed_messages:
            self.state.committed_messages[key] = []
        self.state.committed_messages[key].append(commit_msg)
        
        # Broadcast commit message
        await self._broadcast_message(commit_msg)
        
        # Check if we have enough commit messages
        if len(self.state.committed_messages[key]) >= self.required_messages:
            return await self.execute_phase(key)
        
        return False
    
    async def execute_phase(self, key: str) -> bool:
        """Phase 4: Execute"""
        # Extract sequence and view from key
        sequence, view = map(int, key.split(':'))
        
        # Update state
        self.state.current_sequence = sequence
        
        # Clean up old messages
        self._cleanup_messages(sequence)
        
        return True
    
    async def _broadcast_message(self, message: PBFTMessage):
        """Broadcast message to all validators"""
        validators = self.consensus.get_consensus_participants()
        
        for validator in validators:
            if validator != message.sender:
                # In real implementation, this would send over network
                await self._send_to_validator(validator, message)
    
    async def _send_to_validator(self, validator: str, message: PBFTMessage):
        """Send message to specific validator"""
        # Network communication would be implemented here
        pass
    
    def _cleanup_messages(self, sequence: int):
        """Clean up old messages to prevent memory leaks"""
        old_keys = [
            key for key in self.state.prepared_messages.keys()
            if int(key.split(':')[0]) < sequence
        ]
        
        for key in old_keys:
            self.state.prepared_messages.pop(key, None)
            self.state.committed_messages.pop(key, None)
            self.state.pre_prepare_messages.pop(key, None)
    
    def handle_view_change(self, new_view: int) -> bool:
        """Handle view change when proposer fails"""
        self.state.current_view = new_view
        # Reset state for new view
        self.state.prepared_messages.clear()
        self.state.committed_messages.clear()
        self.state.pre_prepare_messages.clear()
        return True
EOF

    log_info "PBFT consensus implementation created"
}

# Function to create slashing conditions
create_slashing_conditions() {
    log_info "Creating slashing conditions implementation..."
    
    cat > "$CONSENSUS_DIR/slashing.py" << 'EOF'
"""
Slashing Conditions Implementation
Handles detection and penalties for validator misbehavior
"""

import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from .multi_validator_poa import Validator, ValidatorRole

class SlashingCondition(Enum):
    DOUBLE_SIGN = "double_sign"
    UNAVAILABLE = "unavailable"
    INVALID_BLOCK = "invalid_block"
    SLOW_RESPONSE = "slow_response"

@dataclass
class SlashingEvent:
    validator_address: str
    condition: SlashingCondition
    evidence: str
    block_height: int
    timestamp: float
    slash_amount: float

class SlashingManager:
    """Manages validator slashing conditions and penalties"""
    
    def __init__(self):
        self.slashing_events: List[SlashingEvent] = []
        self.slash_rates = {
            SlashingCondition.DOUBLE_SIGN: 0.5,      # 50% slash
            SlashingCondition.UNAVAILABLE: 0.1,      # 10% slash
            SlashingCondition.INVALID_BLOCK: 0.3,     # 30% slash
            SlashingCondition.SLOW_RESPONSE: 0.05    # 5% slash
        }
        self.slash_thresholds = {
            SlashingCondition.DOUBLE_SIGN: 1,         # Immediate slash
            SlashingCondition.UNAVAILABLE: 3,        # After 3 offenses
            SlashingCondition.INVALID_BLOCK: 1,       # Immediate slash
            SlashingCondition.SLOW_RESPONSE: 5       # After 5 offenses
        }
    
    def detect_double_sign(self, validator: str, block_hash1: str, block_hash2: str, height: int) -> Optional[SlashingEvent]:
        """Detect double signing (validator signed two different blocks at same height)"""
        if block_hash1 == block_hash2:
            return None
        
        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.DOUBLE_SIGN,
            evidence=f"Double sign detected: {block_hash1} vs {block_hash2} at height {height}",
            block_height=height,
            timestamp=time.time(),
            slash_amount=self.slash_rates[SlashingCondition.DOUBLE_SIGN]
        )
    
    def detect_unavailability(self, validator: str, missed_blocks: int, height: int) -> Optional[SlashingEvent]:
        """Detect validator unavailability (missing consensus participation)"""
        if missed_blocks < self.slash_thresholds[SlashingCondition.UNAVAILABLE]:
            return None
        
        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.UNAVAILABLE,
            evidence=f"Missed {missed_blocks} consecutive blocks",
            block_height=height,
            timestamp=time.time(),
            slash_amount=self.slash_rates[SlashingCondition.UNAVAILABLE]
        )
    
    def detect_invalid_block(self, validator: str, block_hash: str, reason: str, height: int) -> Optional[SlashingEvent]:
        """Detect invalid block proposal"""
        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.INVALID_BLOCK,
            evidence=f"Invalid block {block_hash}: {reason}",
            block_height=height,
            timestamp=time.time(),
            slash_amount=self.slash_rates[SlashingCondition.INVALID_BLOCK]
        )
    
    def detect_slow_response(self, validator: str, response_time: float, threshold: float, height: int) -> Optional[SlashingEvent]:
        """Detect slow consensus participation"""
        if response_time <= threshold:
            return None
        
        return SlashingEvent(
            validator_address=validator,
            condition=SlashingCondition.SLOW_RESPONSE,
            evidence=f"Slow response: {response_time}s (threshold: {threshold}s)",
            block_height=height,
            timestamp=time.time(),
            slash_amount=self.slash_rates[SlashingCondition.SLOW_RESPONSE]
        )
    
    def apply_slashing(self, validator: Validator, event: SlashingEvent) -> bool:
        """Apply slashing penalty to validator"""
        slash_amount = validator.stake * event.slash_amount
        validator.stake -= slash_amount
        
        # Demote validator role if stake is too low
        if validator.stake < 100:  # Minimum stake threshold
            validator.role = ValidatorRole.STANDBY
        
        # Record slashing event
        self.slashing_events.append(event)
        
        return True
    
    def get_validator_slash_count(self, validator_address: str, condition: SlashingCondition) -> int:
        """Get count of slashing events for validator and condition"""
        return len([
            event for event in self.slashing_events
            if event.validator_address == validator_address and event.condition == condition
        ])
    
    def should_slash(self, validator: str, condition: SlashingCondition) -> bool:
        """Check if validator should be slashed for condition"""
        current_count = self.get_validator_slash_count(validator, condition)
        threshold = self.slash_thresholds.get(condition, 1)
        return current_count >= threshold
    
    def get_slashing_history(self, validator_address: Optional[str] = None) -> List[SlashingEvent]:
        """Get slashing history for validator or all validators"""
        if validator_address:
            return [event for event in self.slashing_events if event.validator_address == validator_address]
        return self.slashing_events.copy()
    
    def calculate_total_slashed(self, validator_address: str) -> float:
        """Calculate total amount slashed for validator"""
        events = self.get_slashing_history(validator_address)
        return sum(event.slash_amount for event in events)

# Global slashing manager
slashing_manager = SlashingManager()
EOF

    log_info "Slashing conditions implementation created"
}

# Function to create validator key management
create_key_management() {
    log_info "Creating validator key management..."
    
    cat > "$CONSENSUS_DIR/keys.py" << 'EOF'
"""
Validator Key Management
Handles cryptographic key operations for validators
"""

import os
import json
import time
from typing import Dict, Optional, Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

@dataclass
class ValidatorKeyPair:
    address: str
    private_key_pem: str
    public_key_pem: str
    created_at: float
    last_rotated: float

class KeyManager:
    """Manages validator cryptographic keys"""
    
    def __init__(self, keys_dir: str = "/opt/aitbc/keys"):
        self.keys_dir = keys_dir
        self.key_pairs: Dict[str, ValidatorKeyPair] = {}
        self._ensure_keys_directory()
        self._load_existing_keys()
    
    def _ensure_keys_directory(self):
        """Ensure keys directory exists and has proper permissions"""
        os.makedirs(self.keys_dir, mode=0o700, exist_ok=True)
    
    def _load_existing_keys(self):
        """Load existing key pairs from disk"""
        keys_file = os.path.join(self.keys_dir, "validator_keys.json")
        
        if os.path.exists(keys_file):
            try:
                with open(keys_file, 'r') as f:
                    keys_data = json.load(f)
                
                for address, key_data in keys_data.items():
                    self.key_pairs[address] = ValidatorKeyPair(
                        address=address,
                        private_key_pem=key_data['private_key_pem'],
                        public_key_pem=key_data['public_key_pem'],
                        created_at=key_data['created_at'],
                        last_rotated=key_data['last_rotated']
                    )
            except Exception as e:
                print(f"Error loading keys: {e}")
    
    def generate_key_pair(self, address: str) -> ValidatorKeyPair:
        """Generate new RSA key pair for validator"""
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Serialize private key
        private_key_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption()
        ).decode('utf-8')
        
        # Get public key
        public_key = private_key.public_key()
        public_key_pem = public_key.public_bytes(
            encoding=Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # Create key pair object
        current_time = time.time()
        key_pair = ValidatorKeyPair(
            address=address,
            private_key_pem=private_key_pem,
            public_key_pem=public_key_pem,
            created_at=current_time,
            last_rotated=current_time
        )
        
        # Store key pair
        self.key_pairs[address] = key_pair
        self._save_keys()
        
        return key_pair
    
    def get_key_pair(self, address: str) -> Optional[ValidatorKeyPair]:
        """Get key pair for validator"""
        return self.key_pairs.get(address)
    
    def rotate_key(self, address: str) -> Optional[ValidatorKeyPair]:
        """Rotate validator keys"""
        if address not in self.key_pairs:
            return None
        
        # Generate new key pair
        new_key_pair = self.generate_key_pair(address)
        
        # Update rotation time
        new_key_pair.created_at = self.key_pairs[address].created_at
        new_key_pair.last_rotated = time.time()
        
        self._save_keys()
        return new_key_pair
    
    def sign_message(self, address: str, message: str) -> Optional[str]:
        """Sign message with validator private key"""
        key_pair = self.get_key_pair(address)
        if not key_pair:
            return None
        
        try:
            # Load private key from PEM
            private_key = serialization.load_pem_private_key(
                key_pair.private_key_pem.encode(),
                password=None,
                backend=default_backend()
            )
            
            # Sign message
            signature = private_key.sign(
                message.encode('utf-8'),
                hashes.SHA256(),
                default_backend()
            )
            
            return signature.hex()
        except Exception as e:
            print(f"Error signing message: {e}")
            return None
    
    def verify_signature(self, address: str, message: str, signature: str) -> bool:
        """Verify message signature"""
        key_pair = self.get_key_pair(address)
        if not key_pair:
            return False
        
        try:
            # Load public key from PEM
            public_key = serialization.load_pem_public_key(
                key_pair.public_key_pem.encode(),
                backend=default_backend()
            )
            
            # Verify signature
            public_key.verify(
                bytes.fromhex(signature),
                message.encode('utf-8'),
                hashes.SHA256(),
                default_backend()
            )
            
            return True
        except Exception as e:
            print(f"Error verifying signature: {e}")
            return False
    
    def get_public_key_pem(self, address: str) -> Optional[str]:
        """Get public key PEM for validator"""
        key_pair = self.get_key_pair(address)
        return key_pair.public_key_pem if key_pair else None
    
    def _save_keys(self):
        """Save key pairs to disk"""
        keys_file = os.path.join(self.keys_dir, "validator_keys.json")
        
        keys_data = {}
        for address, key_pair in self.key_pairs.items():
            keys_data[address] = {
                'private_key_pem': key_pair.private_key_pem,
                'public_key_pem': key_pair.public_key_pem,
                'created_at': key_pair.created_at,
                'last_rotated': key_pair.last_rotated
            }
        
        try:
            with open(keys_file, 'w') as f:
                json.dump(keys_data, f, indent=2)
            
            # Set secure permissions
            os.chmod(keys_file, 0o600)
        except Exception as e:
            print(f"Error saving keys: {e}")
    
    def should_rotate_key(self, address: str, rotation_interval: int = 86400) -> bool:
        """Check if key should be rotated (default: 24 hours)"""
        key_pair = self.get_key_pair(address)
        if not key_pair:
            return True
        
        return (time.time() - key_pair.last_rotated) >= rotation_interval
    
    def get_key_age(self, address: str) -> Optional[float]:
        """Get age of key in seconds"""
        key_pair = self.get_key_pair(address)
        if not key_pair:
            return None
        
        return time.time() - key_pair.created_at

# Global key manager
key_manager = KeyManager()
EOF

    log_info "Validator key management created"
}

# Function to create consensus tests
create_consensus_tests() {
    log_info "Creating consensus test suite..."
    
    mkdir -p "/opt/aitbc/apps/blockchain-node/tests/consensus"
    
    cat > "/opt/aitbc/apps/blockchain-node/tests/consensus/test_multi_validator_poa.py" << 'EOF'
"""
Tests for Multi-Validator PoA Consensus
"""

import pytest
import asyncio
from unittest.mock import Mock, patch

from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole

class TestMultiValidatorPoA:
    """Test cases for multi-validator PoA consensus"""
    
    def setup_method(self):
        """Setup test environment"""
        self.consensus = MultiValidatorPoA("test-chain")
        
        # Add test validators
        self.validator_addresses = [
            "0x1234567890123456789012345678901234567890",
            "0x2345678901234567890123456789012345678901",
            "0x3456789012345678901234567890123456789012",
            "0x4567890123456789012345678901234567890123",
            "0x5678901234567890123456789012345678901234"
        ]
        
        for address in self.validator_addresses:
            self.consensus.add_validator(address, 1000.0)
    
    def test_add_validator(self):
        """Test adding a new validator"""
        new_validator = "0x6789012345678901234567890123456789012345"
        
        result = self.consensus.add_validator(new_validator, 1500.0)
        assert result is True
        assert new_validator in self.consensus.validators
        assert self.consensus.validators[new_validator].stake == 1500.0
    
    def test_add_duplicate_validator(self):
        """Test adding duplicate validator fails"""
        result = self.consensus.add_validator(self.validator_addresses[0], 2000.0)
        assert result is False
    
    def test_remove_validator(self):
        """Test removing a validator"""
        validator_to_remove = self.validator_addresses[0]
        
        result = self.consensus.remove_validator(validator_to_remove)
        assert result is True
        assert not self.consensus.validators[validator_to_remove].is_active
        assert self.consensus.validators[validator_to_remove].role == ValidatorRole.STANDBY
    
    def test_remove_nonexistent_validator(self):
        """Test removing non-existent validator fails"""
        result = self.consensus.remove_validator("0xnonexistent")
        assert result is False
    
    def test_select_proposer_round_robin(self):
        """Test round-robin proposer selection"""
        # Set all validators as proposers
        for address in self.validator_addresses:
            self.consensus.validators[address].role = ValidatorRole.PROPOSER
        
        # Test proposer selection for different heights
        proposer_0 = self.consensus.select_proposer(0)
        proposer_1 = self.consensus.select_proposer(1)
        proposer_2 = self.consensus.select_proposer(2)
        
        assert proposer_0 in self.validator_addresses
        assert proposer_1 in self.validator_addresses
        assert proposer_2 in self.validator_addresses
        assert proposer_0 != proposer_1
        assert proposer_1 != proposer_2
    
    def test_select_proposer_no_validators(self):
        """Test proposer selection with no active validators"""
        # Deactivate all validators
        for address in self.validator_addresses:
            self.consensus.validators[address].is_active = False
        
        proposer = self.consensus.select_proposer(0)
        assert proposer is None
    
    def test_validate_block_valid_proposer(self):
        """Test block validation with valid proposer"""
        from aitbc_chain.models import Block
        
        # Set first validator as proposer
        proposer = self.validator_addresses[0]
        self.consensus.validators[proposer].role = ValidatorRole.PROPOSER
        
        # Create mock block
        block = Mock(spec=Block)
        block.hash = "0xblockhash"
        block.height = 1
        
        result = self.consensus.validate_block(block, proposer)
        assert result is True
    
    def test_validate_block_invalid_proposer(self):
        """Test block validation with invalid proposer"""
        from aitbc_chain.models import Block
        
        # Create mock block
        block = Mock(spec=Block)
        block.hash = "0xblockhash"
        block.height = 1
        
        # Try to validate with non-existent validator
        result = self.consensus.validate_block(block, "0xnonexistent")
        assert result is False
    
    def test_get_consensus_participants(self):
        """Test getting consensus participants"""
        # Set first 3 validators as active
        for i, address in enumerate(self.validator_addresses[:3]):
            self.consensus.validators[address].role = ValidatorRole.PROPOSER if i == 0 else ValidatorRole.VALIDATOR
            self.consensus.validators[address].is_active = True
        
        # Set remaining validators as standby
        for address in self.validator_addresses[3:]:
            self.consensus.validators[address].role = ValidatorRole.STANDBY
            self.consensus.validators[address].is_active = False
        
        participants = self.consensus.get_consensus_participants()
        assert len(participants) == 3
        assert self.validator_addresses[0] in participants
        assert self.validator_addresses[1] in participants
        assert self.validator_addresses[2] in participants
        assert self.validator_addresses[3] not in participants
    
    def test_update_validator_reputation(self):
        """Test updating validator reputation"""
        validator = self.validator_addresses[0]
        initial_reputation = self.consensus.validators[validator].reputation
        
        # Increase reputation
        result = self.consensus.update_validator_reputation(validator, 0.1)
        assert result is True
        assert self.consensus.validators[validator].reputation == initial_reputation + 0.1
        
        # Decrease reputation
        result = self.consensus.update_validator_reputation(validator, -0.2)
        assert result is True
        assert self.consensus.validators[validator].reputation == initial_reputation - 0.1
        
        # Try to update non-existent validator
        result = self.consensus.update_validator_reputation("0xnonexistent", 0.1)
        assert result is False
    
    def test_reputation_bounds(self):
        """Test reputation stays within bounds [0.0, 1.0]"""
        validator = self.validator_addresses[0]
        
        # Try to increase beyond 1.0
        result = self.consensus.update_validator_reputation(validator, 0.5)
        assert result is True
        assert self.consensus.validators[validator].reputation == 1.0
        
        # Try to decrease below 0.0
        result = self.consensus.update_validator_reputation(validator, -1.5)
        assert result is True
        assert self.consensus.validators[validator].reputation == 0.0

if __name__ == "__main__":
    pytest.main([__file__])
EOF

    log_info "Consensus test suite created"
}

# Function to setup test network
setup_test_network() {
    log_info "Setting up consensus test network..."
    
    # Create test network configuration
    cat > "/opt/aitbc/config/consensus_test.json" << 'EOF'
{
    "network_name": "consensus-test",
    "chain_id": "consensus-test",
    "validators": [
        {
            "address": "0x1234567890123456789012345678901234567890",
            "stake": 1000.0,
            "role": "proposer"
        },
        {
            "address": "0x2345678901234567890123456789012345678901",
            "stake": 1000.0,
            "role": "validator"
        },
        {
            "address": "0x3456789012345678901234567890123456789012",
            "stake": 1000.0,
            "role": "validator"
        },
        {
            "address": "0x4567890123456789012345678901234567890123",
            "stake": 1000.0,
            "role": "validator"
        },
        {
            "address": "0x5678901234567890123456789012345678901234",
            "stake": 1000.0,
            "role": "validator"
        }
    ],
    "consensus": {
        "type": "multi_validator_poa",
        "block_time": 5,
        "rotation_interval": 10,
        "fault_tolerance": 1
    },
    "slashing": {
        "double_sign_slash": 0.5,
        "unavailable_slash": 0.1,
        "invalid_block_slash": 0.3,
        "slow_response_slash": 0.05
    }
}
EOF

    log_info "Test network configuration created"
}

# Function to run consensus tests
run_consensus_tests() {
    log_info "Running consensus tests..."
    
    cd /opt/aitbc/apps/blockchain-node
    
    # Install test dependencies if needed
    if ! python -c "import pytest" 2>/dev/null; then
        log_info "Installing pytest..."
        pip install pytest pytest-asyncio
    fi
    
    # Run tests
    python -m pytest tests/consensus/ -v
    
    if [ $? -eq 0 ]; then
        log_info "All consensus tests passed!"
    else
        log_error "Some consensus tests failed!"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting Phase 1: Consensus Layer Setup"
    
    # Create necessary directories
    mkdir -p "$CONSENSUS_DIR"
    mkdir -p "/opt/aitbc/config"
    mkdir -p "/opt/aitbc/keys"
    
    # Execute setup steps
    backup_consensus
    create_multi_validator_poa
    create_validator_rotation
    create_pbft_consensus
    create_slashing_conditions
    create_key_management
    create_consensus_tests
    setup_test_network
    
    # Run tests
    if run_consensus_tests; then
        log_info "Phase 1 consensus setup completed successfully!"
        log_info "Next steps:"
        log_info "1. Configure test validators"
        log_info "2. Start test network"
        log_info "3. Monitor consensus performance"
        log_info "4. Proceed to Phase 2: Network Infrastructure"
    else
        log_error "Phase 1 setup failed - check test output"
        return 1
    fi
}

# Execute main function
main "$@"
