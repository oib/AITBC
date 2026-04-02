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
