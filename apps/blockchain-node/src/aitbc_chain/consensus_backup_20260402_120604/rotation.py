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
