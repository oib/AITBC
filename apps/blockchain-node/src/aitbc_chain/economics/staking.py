"""
Staking Mechanism Implementation
Handles validator staking, delegation, and stake management
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from decimal import Decimal

class StakingStatus(Enum):
    ACTIVE = "active"
    UNSTAKING = "unstaking"
    WITHDRAWN = "withdrawn"
    SLASHED = "slashed"

@dataclass
class StakePosition:
    validator_address: str
    delegator_address: str
    amount: Decimal
    staked_at: float
    lock_period: int  # days
    status: StakingStatus
    rewards: Decimal
    slash_count: int

@dataclass
class ValidatorStakeInfo:
    validator_address: str
    total_stake: Decimal
    self_stake: Decimal
    delegated_stake: Decimal
    delegators_count: int
    commission_rate: float  # percentage
    performance_score: float
    is_active: bool

class StakingManager:
    """Manages validator staking and delegation"""
    
    def __init__(self, min_stake_amount: float = 1000.0):
        self.min_stake_amount = Decimal(str(min_stake_amount))
        self.stake_positions: Dict[str, StakePosition] = {}  # key: validator:delegator
        self.validator_info: Dict[str, ValidatorStakeInfo] = {}
        self.unstaking_requests: Dict[str, float] = {}  # key: validator:delegator, value: request_time
        self.slashing_events: List[Dict] = []
        
        # Staking parameters
        self.unstaking_period = 21  # days
        self.max_delegators_per_validator = 100
        self.commission_range = (0.01, 0.10)  # 1% to 10%
        
    def stake(self, validator_address: str, delegator_address: str, amount: float, 
              lock_period: int = 30) -> Tuple[bool, str]:
        """Stake tokens for validator"""
        try:
            amount_decimal = Decimal(str(amount))
            
            # Validate amount
            if amount_decimal < self.min_stake_amount:
                return False, f"Amount must be at least {self.min_stake_amount}"
            
            # Check if validator exists and is active
            validator_info = self.validator_info.get(validator_address)
            if not validator_info or not validator_info.is_active:
                return False, "Validator not found or not active"
            
            # Check delegator limit
            if delegator_address != validator_address:
                delegator_count = len([
                    pos for pos in self.stake_positions.values()
                    if pos.validator_address == validator_address and 
                    pos.delegator_address == delegator_address and
                    pos.status == StakingStatus.ACTIVE
                ])
                
                if delegator_count >= 1:  # One stake per delegator per validator
                    return False, "Already staked to this validator"
                
                # Check total delegators limit
                total_delegators = len([
                    pos for pos in self.stake_positions.values()
                    if pos.validator_address == validator_address and
                    pos.delegator_address != validator_address and
                    pos.status == StakingStatus.ACTIVE
                ])
                
                if total_delegators >= self.max_delegators_per_validator:
                    return False, "Validator has reached maximum delegator limit"
            
            # Create stake position
            position_key = f"{validator_address}:{delegator_address}"
            stake_position = StakePosition(
                validator_address=validator_address,
                delegator_address=delegator_address,
                amount=amount_decimal,
                staked_at=time.time(),
                lock_period=lock_period,
                status=StakingStatus.ACTIVE,
                rewards=Decimal('0'),
                slash_count=0
            )
            
            self.stake_positions[position_key] = stake_position
            
            # Update validator info
            self._update_validator_stake_info(validator_address)
            
            return True, "Stake successful"
            
        except Exception as e:
            return False, f"Staking failed: {str(e)}"
    
    def unstake(self, validator_address: str, delegator_address: str) -> Tuple[bool, str]:
        """Request unstaking (start unlock period)"""
        position_key = f"{validator_address}:{delegator_address}"
        position = self.stake_positions.get(position_key)
        
        if not position:
            return False, "Stake position not found"
        
        if position.status != StakingStatus.ACTIVE:
            return False, f"Cannot unstake from {position.status.value} position"
        
        # Check lock period
        if time.time() - position.staked_at < (position.lock_period * 24 * 3600):
            return False, "Stake is still in lock period"
        
        # Start unstaking
        position.status = StakingStatus.UNSTAKING
        self.unstaking_requests[position_key] = time.time()
        
        # Update validator info
        self._update_validator_stake_info(validator_address)
        
        return True, "Unstaking request submitted"
    
    def withdraw(self, validator_address: str, delegator_address: str) -> Tuple[bool, str, float]:
        """Withdraw unstaked tokens"""
        position_key = f"{validator_address}:{delegator_address}"
        position = self.stake_positions.get(position_key)
        
        if not position:
            return False, "Stake position not found", 0.0
        
        if position.status != StakingStatus.UNSTAKING:
            return False, f"Position not in unstaking status: {position.status.value}", 0.0
        
        # Check unstaking period
        request_time = self.unstaking_requests.get(position_key, 0)
        if time.time() - request_time < (self.unstaking_period * 24 * 3600):
            remaining_time = (self.unstaking_period * 24 * 3600) - (time.time() - request_time)
            return False, f"Unstaking period not completed. {remaining_time/3600:.1f} hours remaining", 0.0
        
        # Calculate withdrawal amount (including rewards)
        withdrawal_amount = float(position.amount + position.rewards)
        
        # Update position status
        position.status = StakingStatus.WITHDRAWN
        
        # Clean up
        self.unstaking_requests.pop(position_key, None)
        
        # Update validator info
        self._update_validator_stake_info(validator_address)
        
        return True, "Withdrawal successful", withdrawal_amount
    
    def register_validator(self, validator_address: str, self_stake: float, 
                          commission_rate: float = 0.05) -> Tuple[bool, str]:
        """Register a new validator"""
        try:
            self_stake_decimal = Decimal(str(self_stake))
            
            # Validate self stake
            if self_stake_decimal < self.min_stake_amount:
                return False, f"Self stake must be at least {self.min_stake_amount}"
            
            # Validate commission rate
            if not (self.commission_range[0] <= commission_rate <= self.commission_range[1]):
                return False, f"Commission rate must be between {self.commission_range[0]} and {self.commission_range[1]}"
            
            # Check if already registered
            if validator_address in self.validator_info:
                return False, "Validator already registered"
            
            # Create validator info
            self.validator_info[validator_address] = ValidatorStakeInfo(
                validator_address=validator_address,
                total_stake=self_stake_decimal,
                self_stake=self_stake_decimal,
                delegated_stake=Decimal('0'),
                delegators_count=0,
                commission_rate=commission_rate,
                performance_score=1.0,
                is_active=True
            )
            
            # Create self-stake position
            position_key = f"{validator_address}:{validator_address}"
            stake_position = StakePosition(
                validator_address=validator_address,
                delegator_address=validator_address,
                amount=self_stake_decimal,
                staked_at=time.time(),
                lock_period=90,  # 90 days for validator self-stake
                status=StakingStatus.ACTIVE,
                rewards=Decimal('0'),
                slash_count=0
            )
            
            self.stake_positions[position_key] = stake_position
            
            return True, "Validator registered successfully"
            
        except Exception as e:
            return False, f"Validator registration failed: {str(e)}"
    
    def unregister_validator(self, validator_address: str) -> Tuple[bool, str]:
        """Unregister validator (if no delegators)"""
        validator_info = self.validator_info.get(validator_address)
        
        if not validator_info:
            return False, "Validator not found"
        
        # Check for delegators
        delegator_positions = [
            pos for pos in self.stake_positions.values()
            if pos.validator_address == validator_address and
            pos.delegator_address != validator_address and
            pos.status == StakingStatus.ACTIVE
        ]
        
        if delegator_positions:
            return False, "Cannot unregister validator with active delegators"
        
        # Unstake self stake
        success, message = self.unstake(validator_address, validator_address)
        if not success:
            return False, f"Cannot unstake self stake: {message}"
        
        # Mark as inactive
        validator_info.is_active = False
        
        return True, "Validator unregistered successfully"
    
    def slash_validator(self, validator_address: str, slash_percentage: float, 
                       reason: str) -> Tuple[bool, str]:
        """Slash validator for misbehavior"""
        try:
            validator_info = self.validator_info.get(validator_address)
            if not validator_info:
                return False, "Validator not found"
            
            # Get all stake positions for this validator
            validator_positions = [
                pos for pos in self.stake_positions.values()
                if pos.validator_address == validator_address and
                pos.status in [StakingStatus.ACTIVE, StakingStatus.UNSTAKING]
            ]
            
            if not validator_positions:
                return False, "No active stakes found for validator"
            
            # Apply slash to all positions
            total_slashed = Decimal('0')
            for position in validator_positions:
                slash_amount = position.amount * Decimal(str(slash_percentage))
                position.amount -= slash_amount
                position.rewards = Decimal('0')  # Reset rewards
                position.slash_count += 1
                total_slashed += slash_amount
                
                # Mark as slashed if amount is too low
                if position.amount < self.min_stake_amount:
                    position.status = StakingStatus.SLASHED
            
            # Record slashing event
            self.slashing_events.append({
                'validator_address': validator_address,
                'slash_percentage': slash_percentage,
                'reason': reason,
                'timestamp': time.time(),
                'total_slashed': float(total_slashed),
                'affected_positions': len(validator_positions)
            })
            
            # Update validator info
            validator_info.performance_score = max(0.0, validator_info.performance_score - 0.1)
            self._update_validator_stake_info(validator_address)
            
            return True, f"Slashed {len(validator_positions)} stake positions"
            
        except Exception as e:
            return False, f"Slashing failed: {str(e)}"
    
    def _update_validator_stake_info(self, validator_address: str):
        """Update validator stake information"""
        validator_positions = [
            pos for pos in self.stake_positions.values()
            if pos.validator_address == validator_address and
            pos.status == StakingStatus.ACTIVE
        ]
        
        if not validator_positions:
            if validator_address in self.validator_info:
                self.validator_info[validator_address].total_stake = Decimal('0')
                self.validator_info[validator_address].delegated_stake = Decimal('0')
                self.validator_info[validator_address].delegators_count = 0
            return
        
        validator_info = self.validator_info.get(validator_address)
        if not validator_info:
            return
        
        # Calculate stakes
        self_stake = Decimal('0')
        delegated_stake = Decimal('0')
        delegators = set()
        
        for position in validator_positions:
            if position.delegator_address == validator_address:
                self_stake += position.amount
            else:
                delegated_stake += position.amount
                delegators.add(position.delegator_address)
        
        validator_info.self_stake = self_stake
        validator_info.delegated_stake = delegated_stake
        validator_info.total_stake = self_stake + delegated_stake
        validator_info.delegators_count = len(delegators)
    
    def get_stake_position(self, validator_address: str, delegator_address: str) -> Optional[StakePosition]:
        """Get stake position"""
        position_key = f"{validator_address}:{delegator_address}"
        return self.stake_positions.get(position_key)
    
    def get_validator_stake_info(self, validator_address: str) -> Optional[ValidatorStakeInfo]:
        """Get validator stake information"""
        return self.validator_info.get(validator_address)
    
    def get_all_validators(self) -> List[ValidatorStakeInfo]:
        """Get all registered validators"""
        return list(self.validator_info.values())
    
    def get_active_validators(self) -> List[ValidatorStakeInfo]:
        """Get active validators"""
        return [v for v in self.validator_info.values() if v.is_active]
    
    def get_delegators(self, validator_address: str) -> List[StakePosition]:
        """Get delegators for validator"""
        return [
            pos for pos in self.stake_positions.values()
            if pos.validator_address == validator_address and
            pos.delegator_address != validator_address and
            pos.status == StakingStatus.ACTIVE
        ]
    
    def get_total_staked(self) -> Decimal:
        """Get total amount staked across all validators"""
        return sum(
            pos.amount for pos in self.stake_positions.values()
            if pos.status == StakingStatus.ACTIVE
        )
    
    def get_staking_statistics(self) -> Dict:
        """Get staking system statistics"""
        active_positions = [
            pos for pos in self.stake_positions.values()
            if pos.status == StakingStatus.ACTIVE
        ]
        
        return {
            'total_validators': len(self.get_active_validators()),
            'total_staked': float(self.get_total_staked()),
            'total_delegators': len(set(pos.delegator_address for pos in active_positions 
                                 if pos.delegator_address != pos.validator_address)),
            'average_stake_per_validator': float(sum(v.total_stake for v in self.get_active_validators()) / len(self.get_active_validators())) if self.get_active_validators() else 0,
            'total_slashing_events': len(self.slashing_events),
            'unstaking_requests': len(self.unstaking_requests)
        }

# Global staking manager
staking_manager: Optional[StakingManager] = None

def get_staking_manager() -> Optional[StakingManager]:
    """Get global staking manager"""
    return staking_manager

def create_staking_manager(min_stake_amount: float = 1000.0) -> StakingManager:
    """Create and set global staking manager"""
    global staking_manager
    staking_manager = StakingManager(min_stake_amount)
    return staking_manager
