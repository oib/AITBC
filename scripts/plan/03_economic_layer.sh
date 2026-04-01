#!/bin/bash

# Phase 3: Economic Layer Setup Script
# Implements staking mechanisms, reward distribution, and gas fee models

set -e

echo "=== PHASE 3: ECONOMIC LAYER SETUP ==="

# Configuration
ECONOMICS_DIR="/opt/aitbc/apps/blockchain-node/src/aitbc_chain/economics"
STAKING_MIN_AMOUNT=1000.0
REWARD_RATE=0.05  # 5% annual reward rate
GAS_PRICE_BASE=0.001

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Function to backup existing economics files
backup_economics() {
    log_info "Backing up existing economics files..."
    if [ -d "$ECONOMICS_DIR" ]; then
        cp -r "$ECONOMICS_DIR" "${ECONOMICS_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
        log_info "Backup completed"
    fi
}

# Function to create staking mechanism
create_staking_mechanism() {
    log_info "Creating staking mechanism implementation..."
    
    cat > "$ECONOMICS_DIR/staking.py" << 'EOF'
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
EOF

    log_info "Staking mechanism created"
}

# Function to create reward distribution system
create_reward_distribution() {
    log_info "Creating reward distribution system..."
    
    cat > "$ECONOMICS_DIR/rewards.py" << 'EOF'
"""
Reward Distribution System
Handles validator reward calculation and distribution
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

from .staking import StakingManager, StakePosition, StakingStatus

class RewardType(Enum):
    BLOCK_PROPOSAL = "block_proposal"
    BLOCK_VALIDATION = "block_validation"
    CONSENSUS_PARTICIPATION = "consensus_participation"
    UPTIME = "uptime"

@dataclass
class RewardEvent:
    validator_address: str
    reward_type: RewardType
    amount: Decimal
    block_height: int
    timestamp: float
    metadata: Dict

@dataclass
class RewardDistribution:
    distribution_id: str
    total_rewards: Decimal
    validator_rewards: Dict[str, Decimal]
    delegator_rewards: Dict[str, Decimal]
    distributed_at: float
    block_height: int

class RewardCalculator:
    """Calculates validator rewards based on performance"""
    
    def __init__(self, base_reward_rate: float = 0.05):
        self.base_reward_rate = Decimal(str(base_reward_rate))  # 5% annual
        self.reward_multipliers = {
            RewardType.BLOCK_PROPOSAL: Decimal('1.0'),
            RewardType.BLOCK_VALIDATION: Decimal('0.1'),
            RewardType.CONSENSUS_PARTICIPATION: Decimal('0.05'),
            RewardType.UPTIME: Decimal('0.01')
        }
        self.performance_bonus_max = Decimal('0.5')  # 50% max bonus
        self.uptime_requirement = 0.95  # 95% uptime required
    
    def calculate_block_reward(self, validator_address: str, block_height: int, 
                             is_proposer: bool, participated_validators: List[str],
                             uptime_scores: Dict[str, float]) -> Decimal:
        """Calculate reward for block participation"""
        base_reward = self.base_reward_rate / Decimal('365')  # Daily rate
        
        # Start with base reward
        reward = base_reward
        
        # Add proposer bonus
        if is_proposer:
            reward *= self.reward_multipliers[RewardType.BLOCK_PROPOSAL]
        elif validator_address in participated_validators:
            reward *= self.reward_multipliers[RewardType.BLOCK_VALIDATION]
        else:
            return Decimal('0')
        
        # Apply performance multiplier
        uptime_score = uptime_scores.get(validator_address, 0.0)
        if uptime_score >= self.uptime_requirement:
            performance_bonus = (uptime_score - self.uptime_requirement) / (1.0 - self.uptime_requirement)
            performance_bonus = min(performance_bonus, 1.0)  # Cap at 1.0
            reward *= (Decimal('1') + (performance_bonus * self.performance_bonus_max))
        else:
            # Penalty for low uptime
            reward *= Decimal(str(uptime_score))
        
        return reward
    
    def calculate_consensus_reward(self, validator_address: str, participation_rate: float) -> Decimal:
        """Calculate reward for consensus participation"""
        base_reward = self.base_reward_rate / Decimal('365')
        
        if participation_rate < 0.8:  # 80% participation minimum
            return Decimal('0')
        
        reward = base_reward * self.reward_multipliers[RewardType.CONSENSUS_PARTICIPATION]
        reward *= Decimal(str(participation_rate))
        
        return reward
    
    def calculate_uptime_reward(self, validator_address: str, uptime_score: float) -> Decimal:
        """Calculate reward for maintaining uptime"""
        base_reward = self.base_reward_rate / Decimal('365')
        
        if uptime_score < self.uptime_requirement:
            return Decimal('0')
        
        reward = base_reward * self.reward_multipliers[RewardType.UPTIME]
        reward *= Decimal(str(uptime_score))
        
        return reward

class RewardDistributor:
    """Manages reward distribution to validators and delegators"""
    
    def __init__(self, staking_manager: StakingManager, reward_calculator: RewardCalculator):
        self.staking_manager = staking_manager
        self.reward_calculator = reward_calculator
        self.reward_events: List[RewardEvent] = []
        self.distributions: List[RewardDistribution] = []
        self.pending_rewards: Dict[str, Decimal] = {}  # validator_address -> pending rewards
        
        # Distribution parameters
        self.distribution_interval = 86400  # 24 hours
        self.min_reward_amount = Decimal('0.001')  # Minimum reward to distribute
        self.delegation_reward_split = 0.9  # 90% to delegators, 10% to validator
        
    def add_reward_event(self, validator_address: str, reward_type: RewardType, 
                        amount: float, block_height: int, metadata: Dict = None):
        """Add a reward event"""
        reward_event = RewardEvent(
            validator_address=validator_address,
            reward_type=reward_type,
            amount=Decimal(str(amount)),
            block_height=block_height,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        
        self.reward_events.append(reward_event)
        
        # Add to pending rewards
        if validator_address not in self.pending_rewards:
            self.pending_rewards[validator_address] = Decimal('0')
        self.pending_rewards[validator_address] += reward_event.amount
    
    def calculate_validator_rewards(self, validator_address: str, period_start: float, 
                                 period_end: float) -> Dict[str, Decimal]:
        """Calculate rewards for validator over a period"""
        period_events = [
            event for event in self.reward_events
            if event.validator_address == validator_address and
            period_start <= event.timestamp <= period_end
        ]
        
        total_rewards = sum(event.amount for event in period_events)
        
        return {
            'total_rewards': total_rewards,
            'block_proposal_rewards': sum(
                event.amount for event in period_events
                if event.reward_type == RewardType.BLOCK_PROPOSAL
            ),
            'block_validation_rewards': sum(
                event.amount for event in period_events
                if event.reward_type == RewardType.BLOCK_VALIDATION
            ),
            'consensus_rewards': sum(
                event.amount for event in period_events
                if event.reward_type == RewardType.CONSENSUS_PARTICIPATION
            ),
            'uptime_rewards': sum(
                event.amount for event in period_events
                if event.reward_type == RewardType.UPTIME
            )
        }
    
    def distribute_rewards(self, block_height: int) -> Tuple[bool, str, Optional[str]]:
        """Distribute pending rewards to validators and delegators"""
        try:
            if not self.pending_rewards:
                return False, "No pending rewards to distribute", None
            
            # Create distribution
            distribution_id = f"dist_{int(time.time())}_{block_height}"
            total_rewards = sum(self.pending_rewards.values())
            
            if total_rewards < self.min_reward_amount:
                return False, "Total rewards below minimum threshold", None
            
            validator_rewards = {}
            delegator_rewards = {}
            
            # Calculate rewards for each validator
            for validator_address, validator_reward in self.pending_rewards.items():
                validator_info = self.staking_manager.get_validator_stake_info(validator_address)
                
                if not validator_info or not validator_info.is_active:
                    continue
                
                # Get validator's stake positions
                validator_positions = [
                    pos for pos in self.staking_manager.stake_positions.values()
                    if pos.validator_address == validator_address and
                    pos.status == StakingStatus.ACTIVE
                ]
                
                if not validator_positions:
                    continue
                
                total_stake = sum(pos.amount for pos in validator_positions)
                
                # Calculate validator's share (after commission)
                commission = validator_info.commission_rate
                validator_share = validator_reward * Decimal(str(commission))
                delegator_share = validator_reward * Decimal(str(1 - commission))
                
                # Add validator's reward
                validator_rewards[validator_address] = validator_share
                
                # Distribute to delegators (including validator's self-stake)
                for position in validator_positions:
                    delegator_reward = delegator_share * (position.amount / total_stake)
                    
                    delegator_key = f"{position.validator_address}:{position.delegator_address}"
                    delegator_rewards[delegator_key] = delegator_reward
                    
                    # Add to stake position rewards
                    position.rewards += delegator_reward
            
            # Create distribution record
            distribution = RewardDistribution(
                distribution_id=distribution_id,
                total_rewards=total_rewards,
                validator_rewards=validator_rewards,
                delegator_rewards=delegator_rewards,
                distributed_at=time.time(),
                block_height=block_height
            )
            
            self.distributions.append(distribution)
            
            # Clear pending rewards
            self.pending_rewards.clear()
            
            return True, f"Distributed {float(total_rewards)} rewards", distribution_id
            
        except Exception as e:
            return False, f"Reward distribution failed: {str(e)}", None
    
    def get_pending_rewards(self, validator_address: str) -> Decimal:
        """Get pending rewards for validator"""
        return self.pending_rewards.get(validator_address, Decimal('0'))
    
    def get_total_rewards_distributed(self) -> Decimal:
        """Get total rewards distributed"""
        return sum(dist.total_rewards for dist in self.distributions)
    
    def get_reward_history(self, validator_address: Optional[str] = None, 
                          limit: int = 100) -> List[RewardEvent]:
        """Get reward history"""
        events = self.reward_events
        
        if validator_address:
            events = [e for e in events if e.validator_address == validator_address]
        
        # Sort by timestamp (newest first)
        events.sort(key=lambda x: x.timestamp, reverse=True)
        
        return events[:limit]
    
    def get_distribution_history(self, validator_address: Optional[str] = None, 
                               limit: int = 50) -> List[RewardDistribution]:
        """Get distribution history"""
        distributions = self.distributions
        
        if validator_address:
            distributions = [
                d for d in distributions
                if validator_address in d.validator_rewards or
                any(validator_address in key for key in d.delegator_rewards.keys())
            ]
        
        # Sort by timestamp (newest first)
        distributions.sort(key=lambda x: x.distributed_at, reverse=True)
        
        return distributions[:limit]
    
    def get_reward_statistics(self) -> Dict:
        """Get reward system statistics"""
        total_distributed = self.get_total_rewards_distributed()
        total_pending = sum(self.pending_rewards.values())
        
        return {
            'total_events': len(self.reward_events),
            'total_distributions': len(self.distributions),
            'total_rewards_distributed': float(total_distributed),
            'total_pending_rewards': float(total_pending),
            'validators_with_pending': len(self.pending_rewards),
            'average_distribution_size': float(total_distributed / len(self.distributions)) if self.distributions else 0,
            'last_distribution_time': self.distributions[-1].distributed_at if self.distributions else None
        }

# Global reward distributor
reward_distributor: Optional[RewardDistributor] = None

def get_reward_distributor() -> Optional[RewardDistributor]:
    """Get global reward distributor"""
    return reward_distributor

def create_reward_distributor(staking_manager: StakingManager, 
                            reward_calculator: RewardCalculator) -> RewardDistributor:
    """Create and set global reward distributor"""
    global reward_distributor
    reward_distributor = RewardDistributor(staking_manager, reward_calculator)
    return reward_distributor
EOF

    log_info "Reward distribution system created"
}

# Function to create gas fee model
create_gas_fee_model() {
    log_info "Creating gas fee model implementation..."
    
    cat > "$ECONOMICS_DIR/gas.py" << 'EOF'
"""
Gas Fee Model Implementation
Handles transaction fee calculation and gas optimization
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal

class GasType(Enum):
    TRANSFER = "transfer"
    SMART_CONTRACT = "smart_contract"
    VALIDATOR_STAKE = "validator_stake"
    AGENT_OPERATION = "agent_operation"
    CONSENSUS = "consensus"

@dataclass
class GasSchedule:
    gas_type: GasType
    base_gas: int
    gas_per_byte: int
    complexity_multiplier: float

@dataclass
class GasPrice:
    price_per_gas: Decimal
    timestamp: float
    block_height: int
    congestion_level: float

@dataclass
class TransactionGas:
    gas_used: int
    gas_limit: int
    gas_price: Decimal
    total_fee: Decimal
    refund: Decimal

class GasManager:
    """Manages gas fees and pricing"""
    
    def __init__(self, base_gas_price: float = 0.001):
        self.base_gas_price = Decimal(str(base_gas_price))
        self.current_gas_price = self.base_gas_price
        self.gas_schedules: Dict[GasType, GasSchedule] = {}
        self.price_history: List[GasPrice] = []
        self.congestion_history: List[float] = []
        
        # Gas parameters
        self.max_gas_price = self.base_gas_price * Decimal('100')  # 100x base price
        self.min_gas_price = self.base_gas_price * Decimal('0.1')   # 10% of base price
        self.congestion_threshold = 0.8  # 80% block utilization triggers price increase
        self.price_adjustment_factor = 1.1  # 10% price adjustment
        
        # Initialize gas schedules
        self._initialize_gas_schedules()
    
    def _initialize_gas_schedules(self):
        """Initialize gas schedules for different transaction types"""
        self.gas_schedules = {
            GasType.TRANSFER: GasSchedule(
                gas_type=GasType.TRANSFER,
                base_gas=21000,
                gas_per_byte=0,
                complexity_multiplier=1.0
            ),
            GasType.SMART_CONTRACT: GasSchedule(
                gas_type=GasType.SMART_CONTRACT,
                base_gas=21000,
                gas_per_byte=16,
                complexity_multiplier=1.5
            ),
            GasType.VALIDATOR_STAKE: GasSchedule(
                gas_type=GasType.VALIDATOR_STAKE,
                base_gas=50000,
                gas_per_byte=0,
                complexity_multiplier=1.2
            ),
            GasType.AGENT_OPERATION: GasSchedule(
                gas_type=GasType.AGENT_OPERATION,
                base_gas=100000,
                gas_per_byte=32,
                complexity_multiplier=2.0
            ),
            GasType.CONSENSUS: GasSchedule(
                gas_type=GasType.CONSENSUS,
                base_gas=80000,
                gas_per_byte=0,
                complexity_multiplier=1.0
            )
        }
    
    def estimate_gas(self, gas_type: GasType, data_size: int = 0, 
                    complexity_score: float = 1.0) -> int:
        """Estimate gas required for transaction"""
        schedule = self.gas_schedules.get(gas_type)
        if not schedule:
            raise ValueError(f"Unknown gas type: {gas_type}")
        
        # Calculate base gas
        gas = schedule.base_gas
        
        # Add data gas
        if schedule.gas_per_byte > 0:
            gas += data_size * schedule.gas_per_byte
        
        # Apply complexity multiplier
        gas = int(gas * schedule.complexity_multiplier * complexity_score)
        
        return gas
    
    def calculate_transaction_fee(self, gas_type: GasType, data_size: int = 0,
                                complexity_score: float = 1.0, 
                                gas_price: Optional[Decimal] = None) -> TransactionGas:
        """Calculate transaction fee"""
        # Estimate gas
        gas_limit = self.estimate_gas(gas_type, data_size, complexity_score)
        
        # Use provided gas price or current price
        price = gas_price or self.current_gas_price
        
        # Calculate total fee
        total_fee = Decimal(gas_limit) * price
        
        return TransactionGas(
            gas_used=gas_limit,  # Assume full gas used for estimation
            gas_limit=gas_limit,
            gas_price=price,
            total_fee=total_fee,
            refund=Decimal('0')
        )
    
    def update_gas_price(self, block_utilization: float, transaction_pool_size: int,
                        block_height: int) -> GasPrice:
        """Update gas price based on network conditions"""
        # Calculate congestion level
        congestion_level = max(block_utilization, transaction_pool_size / 1000)  # Normalize pool size
        
        # Store congestion history
        self.congestion_history.append(congestion_level)
        if len(self.congestion_history) > 100:  # Keep last 100 values
            self.congestion_history.pop(0)
        
        # Calculate new gas price
        if congestion_level > self.congestion_threshold:
            # Increase price
            new_price = self.current_gas_price * Decimal(str(self.price_adjustment_factor))
        else:
            # Decrease price (gradually)
            avg_congestion = sum(self.congestion_history[-10:]) / min(10, len(self.congestion_history))
            if avg_congestion < self.congestion_threshold * 0.7:
                new_price = self.current_gas_price / Decimal(str(self.price_adjustment_factor))
            else:
                new_price = self.current_gas_price
        
        # Apply price bounds
        new_price = max(self.min_gas_price, min(self.max_gas_price, new_price))
        
        # Update current price
        self.current_gas_price = new_price
        
        # Record price history
        gas_price = GasPrice(
            price_per_gas=new_price,
            timestamp=time.time(),
            block_height=block_height,
            congestion_level=congestion_level
        )
        
        self.price_history.append(gas_price)
        if len(self.price_history) > 1000:  # Keep last 1000 values
            self.price_history.pop(0)
        
        return gas_price
    
    def get_optimal_gas_price(self, priority: str = "standard") -> Decimal:
        """Get optimal gas price based on priority"""
        if priority == "fast":
            # 2x current price for fast inclusion
            return min(self.current_gas_price * Decimal('2'), self.max_gas_price)
        elif priority == "slow":
            # 0.5x current price for slow inclusion
            return max(self.current_gas_price * Decimal('0.5'), self.min_gas_price)
        else:
            # Standard price
            return self.current_gas_price
    
    def predict_gas_price(self, blocks_ahead: int = 5) -> Decimal:
        """Predict gas price for future blocks"""
        if len(self.price_history) < 10:
            return self.current_gas_price
        
        # Simple linear prediction based on recent trend
        recent_prices = [p.price_per_gas for p in self.price_history[-10:]]
        
        # Calculate trend
        if len(recent_prices) >= 2:
            price_change = recent_prices[-1] - recent_prices[-2]
            predicted_price = self.current_gas_price + (price_change * blocks_ahead)
        else:
            predicted_price = self.current_gas_price
        
        # Apply bounds
        return max(self.min_gas_price, min(self.max_gas_price, predicted_price))
    
    def get_gas_statistics(self) -> Dict:
        """Get gas system statistics"""
        if not self.price_history:
            return {
                'current_price': float(self.current_gas_price),
                'price_history_length': 0,
                'average_price': float(self.current_gas_price),
                'price_volatility': 0.0
            }
        
        prices = [p.price_per_gas for p in self.price_history]
        avg_price = sum(prices) / len(prices)
        
        # Calculate volatility (standard deviation)
        if len(prices) > 1:
            variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
            volatility = (variance ** 0.5) / avg_price
        else:
            volatility = 0.0
        
        return {
            'current_price': float(self.current_gas_price),
            'price_history_length': len(self.price_history),
            'average_price': float(avg_price),
            'price_volatility': float(volatility),
            'min_price': float(min(prices)),
            'max_price': float(max(prices)),
            'congestion_history_length': len(self.congestion_history),
            'average_congestion': sum(self.congestion_history) / len(self.congestion_history) if self.congestion_history else 0.0
        }

class GasOptimizer:
    """Optimizes gas usage and fees"""
    
    def __init__(self, gas_manager: GasManager):
        self.gas_manager = gas_manager
        self.optimization_history: List[Dict] = []
    
    def optimize_transaction(self, gas_type: GasType, data: bytes, 
                          priority: str = "standard") -> Dict:
        """Optimize transaction for gas efficiency"""
        data_size = len(data)
        
        # Estimate base gas
        base_gas = self.gas_manager.estimate_gas(gas_type, data_size)
        
        # Calculate optimal gas price
        optimal_price = self.gas_manager.get_optimal_gas_price(priority)
        
        # Optimization suggestions
        optimizations = []
        
        # Data optimization
        if data_size > 1000 and gas_type == GasType.SMART_CONTRACT:
            optimizations.append({
                'type': 'data_compression',
                'potential_savings': data_size * 8,  # 8 gas per byte
                'description': 'Compress transaction data to reduce gas costs'
            })
        
        # Timing optimization
        if priority == "standard":
            fast_price = self.gas_manager.get_optimal_gas_price("fast")
            slow_price = self.gas_manager.get_optimal_gas_price("slow")
            
            if slow_price < optimal_price:
                savings = (optimal_price - slow_price) * base_gas
                optimizations.append({
                    'type': 'timing_optimization',
                    'potential_savings': float(savings),
                    'description': 'Use slower priority for lower fees'
                })
        
        # Bundle similar transactions
        if gas_type in [GasType.TRANSFER, GasType.VALIDATOR_STAKE]:
            optimizations.append({
                'type': 'transaction_bundling',
                'potential_savings': base_gas * 0.3,  # 30% savings estimate
                'description': 'Bundle similar transactions to share base gas costs'
            })
        
        # Record optimization
        optimization_result = {
            'gas_type': gas_type.value,
            'data_size': data_size,
            'base_gas': base_gas,
            'optimal_price': float(optimal_price),
            'estimated_fee': float(base_gas * optimal_price),
            'optimizations': optimizations,
            'timestamp': time.time()
        }
        
        self.optimization_history.append(optimization_result)
        
        return optimization_result
    
    def get_optimization_summary(self) -> Dict:
        """Get optimization summary statistics"""
        if not self.optimization_history:
            return {
                'total_optimizations': 0,
                'average_savings': 0.0,
                'most_common_type': None
            }
        
        total_savings = 0
        type_counts = {}
        
        for opt in self.optimization_history:
            for suggestion in opt['optimizations']:
                total_savings += suggestion['potential_savings']
                opt_type = suggestion['type']
                type_counts[opt_type] = type_counts.get(opt_type, 0) + 1
        
        most_common_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else None
        
        return {
            'total_optimizations': len(self.optimization_history),
            'total_potential_savings': total_savings,
            'average_savings': total_savings / len(self.optimization_history) if self.optimization_history else 0,
            'most_common_type': most_common_type,
            'optimization_types': list(type_counts.keys())
        }

# Global gas manager and optimizer
gas_manager: Optional[GasManager] = None
gas_optimizer: Optional[GasOptimizer] = None

def get_gas_manager() -> Optional[GasManager]:
    """Get global gas manager"""
    return gas_manager

def create_gas_manager(base_gas_price: float = 0.001) -> GasManager:
    """Create and set global gas manager"""
    global gas_manager
    gas_manager = GasManager(base_gas_price)
    return gas_manager

def get_gas_optimizer() -> Optional[GasOptimizer]:
    """Get global gas optimizer"""
    return gas_optimizer

def create_gas_optimizer(gas_manager: GasManager) -> GasOptimizer:
    """Create and set global gas optimizer"""
    global gas_optimizer
    gas_optimizer = GasOptimizer(gas_manager)
    return gas_optimizer
EOF

    log_info "Gas fee model created"
}

# Function to create economic attack prevention
create_attack_prevention() {
    log_info "Creating economic attack prevention..."
    
    cat > "$ECONOMICS_DIR/attacks.py" << 'EOF'
"""
Economic Attack Prevention
Detects and prevents various economic attacks on the network
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

from .staking import StakingManager
from .rewards import RewardDistributor
from .gas import GasManager

class AttackType(Enum):
    SYBIL = "sybil"
    STAKE_GRINDING = "stake_grinding"
    NOTHING_AT_STAKE = "nothing_at_stake"
    LONG_RANGE = "long_range"
    FRONT_RUNNING = "front_running"
    GAS_MANIPULATION = "gas_manipulation"

class ThreatLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class AttackDetection:
    attack_type: AttackType
    threat_level: ThreatLevel
    attacker_address: str
    evidence: Dict
    detected_at: float
    confidence: float
    recommended_action: str

@dataclass
class SecurityMetric:
    metric_name: str
    current_value: float
    threshold: float
    status: str
    last_updated: float

class EconomicSecurityMonitor:
    """Monitors and prevents economic attacks"""
    
    def __init__(self, staking_manager: StakingManager, reward_distributor: RewardDistributor,
                 gas_manager: GasManager):
        self.staking_manager = staking_manager
        self.reward_distributor = reward_distributor
        self.gas_manager = gas_manager
        
        self.detection_rules = self._initialize_detection_rules()
        self.attack_detections: List[AttackDetection] = []
        self.security_metrics: Dict[str, SecurityMetric] = {}
        self.blacklisted_addresses: Set[str] = set()
        
        # Monitoring parameters
        self.monitoring_interval = 60  # seconds
        self.detection_history_window = 3600  # 1 hour
        self.max_false_positive_rate = 0.05  # 5%
        
        # Initialize security metrics
        self._initialize_security_metrics()
    
    def _initialize_detection_rules(self) -> Dict[AttackType, Dict]:
        """Initialize detection rules for different attack types"""
        return {
            AttackType.SYBIL: {
                'threshold': 0.1,  # 10% of validators from same entity
                'min_stake': 1000.0,
                'time_window': 86400,  # 24 hours
                'max_similar_addresses': 5
            },
            AttackType.STAKE_GRINDING: {
                'threshold': 0.3,  # 30% stake variation
                'min_operations': 10,
                'time_window': 3600,  # 1 hour
                'max_withdrawal_frequency': 5
            },
            AttackType.NOTHING_AT_STAKE: {
                'threshold': 0.5,  # 50% abstention rate
                'min_validators': 10,
                'time_window': 7200,  # 2 hours
                'max_abstention_periods': 3
            },
            AttackType.LONG_RANGE: {
                'threshold': 0.8,  # 80% stake from old keys
                'min_history_depth': 1000,
                'time_window': 604800,  # 1 week
                'max_key_reuse': 2
            },
            AttackType.FRONT_RUNNING: {
                'threshold': 0.1,  # 10% transaction front-running
                'min_transactions': 100,
                'time_window': 3600,  # 1 hour
                'max_mempool_advantage': 0.05
            },
            AttackType.GAS_MANIPULATION: {
                'threshold': 2.0,  # 2x price manipulation
                'min_price_changes': 5,
                'time_window': 1800,  # 30 minutes
                'max_spikes_per_hour': 3
            }
        }
    
    def _initialize_security_metrics(self):
        """Initialize security monitoring metrics"""
        self.security_metrics = {
            'validator_diversity': SecurityMetric(
                metric_name='validator_diversity',
                current_value=0.0,
                threshold=0.7,
                status='healthy',
                last_updated=time.time()
            ),
            'stake_distribution': SecurityMetric(
                metric_name='stake_distribution',
                current_value=0.0,
                threshold=0.8,
                status='healthy',
                last_updated=time.time()
            ),
            'reward_distribution': SecurityMetric(
                metric_name='reward_distribution',
                current_value=0.0,
                threshold=0.9,
                status='healthy',
                last_updated=time.time()
            ),
            'gas_price_stability': SecurityMetric(
                metric_name='gas_price_stability',
                current_value=0.0,
                threshold=0.3,
                status='healthy',
                last_updated=time.time()
            )
        }
    
    async def start_monitoring(self):
        """Start economic security monitoring"""
        log_info("Starting economic security monitoring")
        
        while True:
            try:
                await self._monitor_security_metrics()
                await self._detect_attacks()
                await self._update_blacklist()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                log_error(f"Security monitoring error: {e}")
                await asyncio.sleep(10)
    
    async def _monitor_security_metrics(self):
        """Monitor security metrics"""
        current_time = time.time()
        
        # Update validator diversity
        await self._update_validator_diversity(current_time)
        
        # Update stake distribution
        await self._update_stake_distribution(current_time)
        
        # Update reward distribution
        await self._update_reward_distribution(current_time)
        
        # Update gas price stability
        await self._update_gas_price_stability(current_time)
    
    async def _update_validator_diversity(self, current_time: float):
        """Update validator diversity metric"""
        validators = self.staking_manager.get_active_validators()
        
        if len(validators) < 10:
            diversity_score = 0.0
        else:
            # Calculate diversity based on stake distribution
            total_stake = sum(v.total_stake for v in validators)
            if total_stake == 0:
                diversity_score = 0.0
            else:
                # Use Herfindahl-Hirschman Index
                stake_shares = [float(v.total_stake / total_stake) for v in validators]
                hhi = sum(share ** 2 for share in stake_shares)
                diversity_score = 1.0 - hhi
        
        metric = self.security_metrics['validator_diversity']
        metric.current_value = diversity_score
        metric.last_updated = current_time
        
        if diversity_score < metric.threshold:
            metric.status = 'warning'
        else:
            metric.status = 'healthy'
    
    async def _update_stake_distribution(self, current_time: float):
        """Update stake distribution metric"""
        validators = self.staking_manager.get_active_validators()
        
        if not validators:
            distribution_score = 0.0
        else:
            # Check for concentration (top 3 validators)
            stakes = [float(v.total_stake) for v in validators]
            stakes.sort(reverse=True)
            
            total_stake = sum(stakes)
            if total_stake == 0:
                distribution_score = 0.0
            else:
                top3_share = sum(stakes[:3]) / total_stake
                distribution_score = 1.0 - top3_share
        
        metric = self.security_metrics['stake_distribution']
        metric.current_value = distribution_score
        metric.last_updated = current_time
        
        if distribution_score < metric.threshold:
            metric.status = 'warning'
        else:
            metric.status = 'healthy'
    
    async def _update_reward_distribution(self, current_time: float):
        """Update reward distribution metric"""
        distributions = self.reward_distributor.get_distribution_history(limit=10)
        
        if len(distributions) < 5:
            distribution_score = 1.0  # Not enough data
        else:
            # Check for reward concentration
            total_rewards = sum(dist.total_rewards for dist in distributions)
            if total_rewards == 0:
                distribution_score = 0.0
            else:
                # Calculate variance in reward distribution
                validator_rewards = []
                for dist in distributions:
                    validator_rewards.extend(dist.validator_rewards.values())
                
                if not validator_rewards:
                    distribution_score = 0.0
                else:
                    avg_reward = sum(validator_rewards) / len(validator_rewards)
                    variance = sum((r - avg_reward) ** 2 for r in validator_rewards) / len(validator_rewards)
                    cv = (variance ** 0.5) / avg_reward if avg_reward > 0 else 0
                    distribution_score = max(0.0, 1.0 - cv)
        
        metric = self.security_metrics['reward_distribution']
        metric.current_value = distribution_score
        metric.last_updated = current_time
        
        if distribution_score < metric.threshold:
            metric.status = 'warning'
        else:
            metric.status = 'healthy'
    
    async def _update_gas_price_stability(self, current_time: float):
        """Update gas price stability metric"""
        gas_stats = self.gas_manager.get_gas_statistics()
        
        if gas_stats['price_history_length'] < 10:
            stability_score = 1.0  # Not enough data
        else:
            stability_score = 1.0 - gas_stats['price_volatility']
        
        metric = self.security_metrics['gas_price_stability']
        metric.current_value = stability_score
        metric.last_updated = current_time
        
        if stability_score < metric.threshold:
            metric.status = 'warning'
        else:
            metric.status = 'healthy'
    
    async def _detect_attacks(self):
        """Detect potential economic attacks"""
        current_time = time.time()
        
        # Detect Sybil attacks
        await self._detect_sybil_attacks(current_time)
        
        # Detect stake grinding
        await self._detect_stake_grinding(current_time)
        
        # Detect nothing-at-stake
        await self._detect_nothing_at_stake(current_time)
        
        # Detect long-range attacks
        await self._detect_long_range_attacks(current_time)
        
        # Detect front-running
        await self._detect_front_running(current_time)
        
        # Detect gas manipulation
        await self._detect_gas_manipulation(current_time)
    
    async def _detect_sybil_attacks(self, current_time: float):
        """Detect Sybil attacks (multiple identities)"""
        rule = self.detection_rules[AttackType.SYBIL]
        validators = self.staking_manager.get_active_validators()
        
        # Group validators by similar characteristics
        address_groups = {}
        for validator in validators:
            # Simple grouping by address prefix (more sophisticated in real implementation)
            prefix = validator.validator_address[:8]
            if prefix not in address_groups:
                address_groups[prefix] = []
            address_groups[prefix].append(validator)
        
        # Check for suspicious groups
        for prefix, group in address_groups.items():
            if len(group) >= rule['max_similar_addresses']:
                # Calculate threat level
                group_stake = sum(v.total_stake for v in group)
                total_stake = sum(v.total_stake for v in validators)
                stake_ratio = float(group_stake / total_stake) if total_stake > 0 else 0
                
                if stake_ratio > rule['threshold']:
                    threat_level = ThreatLevel.HIGH
                elif stake_ratio > rule['threshold'] * 0.5:
                    threat_level = ThreatLevel.MEDIUM
                else:
                    threat_level = ThreatLevel.LOW
                
                # Create detection
                detection = AttackDetection(
                    attack_type=AttackType.SYBIL,
                    threat_level=threat_level,
                    attacker_address=prefix,
                    evidence={
                        'similar_addresses': [v.validator_address for v in group],
                        'group_size': len(group),
                        'stake_ratio': stake_ratio,
                        'common_prefix': prefix
                    },
                    detected_at=current_time,
                    confidence=0.8,
                    recommended_action='Investigate validator identities'
                )
                
                self.attack_detections.append(detection)
    
    async def _detect_stake_grinding(self, current_time: float):
        """Detect stake grinding attacks"""
        rule = self.detection_rules[AttackType.STAKE_GRINDING]
        
        # Check for frequent stake changes
        recent_detections = [
            d for d in self.attack_detections
            if d.attack_type == AttackType.STAKE_GRINDING and
            current_time - d.detected_at < rule['time_window']
        ]
        
        # This would analyze staking patterns (simplified here)
        # In real implementation, would track stake movements over time
        
        pass  # Placeholder for stake grinding detection
    
    async def _detect_nothing_at_stake(self, current_time: float):
        """Detect nothing-at-stake attacks"""
        rule = self.detection_rules[AttackType.NOTHING_AT_STAKE]
        
        # Check for validator participation rates
        # This would require consensus participation data
        
        pass  # Placeholder for nothing-at-stake detection
    
    async def _detect_long_range_attacks(self, current_time: float):
        """Detect long-range attacks"""
        rule = self.detection_rules[AttackType.LONG_RANGE]
        
        # Check for key reuse from old blockchain states
        # This would require historical blockchain data
        
        pass  # Placeholder for long-range attack detection
    
    async def _detect_front_running(self, current_time: float):
        """Detect front-running attacks"""
        rule = self.detection_rules[AttackType.FRONT_RUNNING]
        
        # Check for transaction ordering patterns
        # This would require mempool and transaction ordering data
        
        pass  # Placeholder for front-running detection
    
    async def _detect_gas_manipulation(self, current_time: float):
        """Detect gas price manipulation"""
        rule = self.detection_rules[AttackType.GAS_MANIPULATION]
        
        gas_stats = self.gas_manager.get_gas_statistics()
        
        # Check for unusual gas price spikes
        if gas_stats['price_history_length'] >= 10:
            recent_prices = [p.price_per_gas for p in self.gas_manager.price_history[-10:]]
            avg_price = sum(recent_prices) / len(recent_prices)
            
            # Look for significant spikes
            for price in recent_prices:
                if float(price / avg_price) > rule['threshold']:
                    detection = AttackDetection(
                        attack_type=AttackType.GAS_MANIPULATION,
                        threat_level=ThreatLevel.MEDIUM,
                        attacker_address="unknown",  # Would need more sophisticated detection
                        evidence={
                            'spike_ratio': float(price / avg_price),
                            'current_price': float(price),
                            'average_price': float(avg_price)
                        },
                        detected_at=current_time,
                        confidence=0.6,
                        recommended_action='Monitor gas price patterns'
                    )
                    
                    self.attack_detections.append(detection)
                    break
    
    async def _update_blacklist(self):
        """Update blacklist based on detections"""
        current_time = time.time()
        
        # Remove old detections from history
        self.attack_detections = [
            d for d in self.attack_detections
            if current_time - d.detected_at < self.detection_history_window
        ]
        
        # Add high-confidence, high-threat attackers to blacklist
        for detection in self.attack_detections:
            if (detection.threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL] and
                detection.confidence > 0.8 and
                detection.attacker_address not in self.blacklisted_addresses):
                
                self.blacklisted_addresses.add(detection.attacker_address)
                log_warn(f"Added {detection.attacker_address} to blacklist due to {detection.attack_type.value} attack")
    
    def is_address_blacklisted(self, address: str) -> bool:
        """Check if address is blacklisted"""
        return address in self.blacklisted_addresses
    
    def get_attack_summary(self) -> Dict:
        """Get summary of detected attacks"""
        current_time = time.time()
        recent_detections = [
            d for d in self.attack_detections
            if current_time - d.detected_at < 3600  # Last hour
        ]
        
        attack_counts = {}
        threat_counts = {}
        
        for detection in recent_detections:
            attack_type = detection.attack_type.value
            threat_level = detection.threat_level.value
            
            attack_counts[attack_type] = attack_counts.get(attack_type, 0) + 1
            threat_counts[threat_level] = threat_counts.get(threat_level, 0) + 1
        
        return {
            'total_detections': len(recent_detections),
            'attack_types': attack_counts,
            'threat_levels': threat_counts,
            'blacklisted_addresses': len(self.blacklisted_addresses),
            'security_metrics': {
                name: {
                    'value': metric.current_value,
                    'threshold': metric.threshold,
                    'status': metric.status
                }
                for name, metric in self.security_metrics.items()
            }
        }

# Global security monitor
security_monitor: Optional[EconomicSecurityMonitor] = None

def get_security_monitor() -> Optional[EconomicSecurityMonitor]:
    """Get global security monitor"""
    return security_monitor

def create_security_monitor(staking_manager: StakingManager, reward_distributor: RewardDistributor,
                           gas_manager: GasManager) -> EconomicSecurityMonitor:
    """Create and set global security monitor"""
    global security_monitor
    security_monitor = EconomicSecurityMonitor(staking_manager, reward_distributor, gas_manager)
    return security_monitor
EOF

    log_info "Economic attack prevention created"
}

# Function to create economic tests
create_economic_tests() {
    log_info "Creating economic layer test suite..."
    
    mkdir -p "/opt/aitbc/apps/blockchain-node/tests/economics"
    
    cat > "/opt/aitbc/apps/blockchain-node/tests/economics/test_staking.py" << 'EOF'
"""
Tests for Staking Mechanism
"""

import pytest
import time
from decimal import Decimal
from unittest.mock import Mock, patch

from aitbc_chain.economics.staking import StakingManager, StakingStatus

class TestStakingManager:
    """Test cases for staking manager"""
    
    def setup_method(self):
        """Setup test environment"""
        self.staking_manager = StakingManager(min_stake_amount=1000.0)
        
        # Register a test validator
        success, message = self.staking_manager.register_validator(
            "0xvalidator1", 2000.0, 0.05
        )
        assert success, f"Failed to register validator: {message}"
    
    def test_register_validator(self):
        """Test validator registration"""
        # Valid registration
        success, message = self.staking_manager.register_validator(
            "0xvalidator2", 1500.0, 0.03
        )
        assert success, f"Validator registration failed: {message}"
        
        # Check validator info
        validator_info = self.staking_manager.get_validator_stake_info("0xvalidator2")
        assert validator_info is not None
        assert validator_info.validator_address == "0xvalidator2"
        assert float(validator_info.self_stake) == 1500.0
        assert validator_info.commission_rate == 0.03
    
    def test_register_validator_insufficient_stake(self):
        """Test validator registration with insufficient stake"""
        success, message = self.staking_manager.register_validator(
            "0xvalidator3", 500.0, 0.05
        )
        assert not success
        assert "insufficient stake" in message.lower()
    
    def test_register_validator_invalid_commission(self):
        """Test validator registration with invalid commission"""
        success, message = self.staking_manager.register_validator(
            "0xvalidator4", 1500.0, 0.15  # Too high
        )
        assert not success
        assert "commission" in message.lower()
    
    def test_register_duplicate_validator(self):
        """Test registering duplicate validator"""
        success, message = self.staking_manager.register_validator(
            "0xvalidator1", 2000.0, 0.05
        )
        assert not success
        assert "already registered" in message.lower()
    
    def test_stake_to_validator(self):
        """Test staking to validator"""
        success, message = self.staking_manager.stake(
            "0xvalidator1", "0xdelegator1", 1200.0
        )
        assert success, f"Staking failed: {message}"
        
        # Check stake position
        position = self.staking_manager.get_stake_position("0xvalidator1", "0xdelegator1")
        assert position is not None
        assert position.validator_address == "0xvalidator1"
        assert position.delegator_address == "0xdelegator1"
        assert float(position.amount) == 1200.0
        assert position.status == StakingStatus.ACTIVE
    
    def test_stake_insufficient_amount(self):
        """Test staking insufficient amount"""
        success, message = self.staking_manager.stake(
            "0xvalidator1", "0xdelegator2", 500.0
        )
        assert not success
        assert "at least" in message.lower()
    
    def test_stake_to_nonexistent_validator(self):
        """Test staking to non-existent validator"""
        success, message = self.staking_manager.stake(
            "0xnonexistent", "0xdelegator3", 1200.0
        )
        assert not success
        assert "not found" in message.lower() or "not active" in message.lower()
    
    def test_unstake(self):
        """Test unstaking"""
        # First stake
        success, _ = self.staking_manager.stake("0xvalidator1", "0xdelegator4", 1200.0)
        assert success
        
        # Then unstake
        success, message = self.staking_manager.unstake("0xvalidator1", "0xdelegator4")
        assert success, f"Unstaking failed: {message}"
        
        # Check position status
        position = self.staking_manager.get_stake_position("0xvalidator1", "0xdelegator4")
        assert position is not None
        assert position.status == StakingStatus.UNSTAKING
    
    def test_unstake_nonexistent_position(self):
        """Test unstaking non-existent position"""
        success, message = self.staking_manager.unstake("0xvalidator1", "0xnonexistent")
        assert not success
        assert "not found" in message.lower()
    
    def test_unstake_locked_position(self):
        """Test unstaking locked position"""
        # Stake with long lock period
        success, _ = self.staking_manager.stake("0xvalidator1", "0xdelegator5", 1200.0, 90)
        assert success
        
        # Try to unstake immediately
        success, message = self.staking_manager.unstake("0xvalidator1", "0xdelegator5")
        assert not success
        assert "lock period" in message.lower()
    
    def test_withdraw(self):
        """Test withdrawal after unstaking period"""
        # Stake and unstake
        success, _ = self.staking_manager.stake("0xvalidator1", "0xdelegator6", 1200.0, 1)  # 1 day lock
        assert success
        
        success, _ = self.staking_manager.unstake("0xvalidator1", "0xdelegator6")
        assert success
        
        # Wait for unstaking period (simulate with direct manipulation)
        position = self.staking_manager.get_stake_position("0xvalidator1", "0xdelegator6")
        if position:
            position.staked_at = time.time() - (2 * 24 * 3600)  # 2 days ago
        
        # Withdraw
        success, message, amount = self.staking_manager.withdraw("0xvalidator1", "0xdelegator6")
        assert success, f"Withdrawal failed: {message}"
        assert amount == 1200.0  # Should get back the full amount
        
        # Check position status
        position = self.staking_manager.get_stake_position("0xvalidator1", "0xdelegator6")
        assert position is not None
        assert position.status == StakingStatus.WITHDRAWN
    
    def test_withdraw_too_early(self):
        """Test withdrawal before unstaking period completes"""
        # Stake and unstake
        success, _ = self.staking_manager.stake("0xvalidator1", "0xdelegator7", 1200.0, 30)  # 30 days
        assert success
        
        success, _ = self.staking_manager.unstake("0xvalidator1", "0xdelegator7")
        assert success
        
        # Try to withdraw immediately
        success, message, amount = self.staking_manager.withdraw("0xvalidator1", "0xdelegator7")
        assert not success
        assert "not completed" in message.lower()
        assert amount == 0.0
    
    def test_slash_validator(self):
        """Test validator slashing"""
        # Stake to validator
        success, _ = self.staking_manager.stake("0xvalidator1", "0xdelegator8", 1200.0)
        assert success
        
        # Slash validator
        success, message = self.staking_manager.slash_validator("0xvalidator1", 0.1, "Test slash")
        assert success, f"Slashing failed: {message}"
        
        # Check stake reduction
        position = self.staking_manager.get_stake_position("0xvalidator1", "0xdelegator8")
        assert position is not None
        assert float(position.amount) == 1080.0  # 10% reduction
        assert position.slash_count == 1
    
    def test_get_validator_stake_info(self):
        """Test getting validator stake information"""
        # Add delegators
        self.staking_manager.stake("0xvalidator1", "0xdelegator9", 1000.0)
        self.staking_manager.stake("0xvalidator1", "0xdelegator10", 1500.0)
        
        info = self.staking_manager.get_validator_stake_info("0xvalidator1")
        assert info is not None
        assert float(info.self_stake) == 2000.0
        assert float(info.delegated_stake) == 2500.0
        assert float(info.total_stake) == 4500.0
        assert info.delegators_count == 2
    
    def test_get_all_validators(self):
        """Test getting all validators"""
        # Register another validator
        self.staking_manager.register_validator("0xvalidator5", 1800.0, 0.04)
        
        validators = self.staking_manager.get_all_validators()
        assert len(validators) >= 2
        
        validator_addresses = [v.validator_address for v in validators]
        assert "0xvalidator1" in validator_addresses
        assert "0xvalidator5" in validator_addresses
    
    def test_get_active_validators(self):
        """Test getting active validators only"""
        # Unregister one validator
        self.staking_manager.unregister_validator("0xvalidator1")
        
        active_validators = self.staking_manager.get_active_validators()
        validator_addresses = [v.validator_address for v in active_validators]
        
        assert "0xvalidator1" not in validator_addresses
    
    def test_get_total_staked(self):
        """Test getting total staked amount"""
        # Add some stakes
        self.staking_manager.stake("0xvalidator1", "0xdelegator11", 1000.0)
        self.staking_manager.stake("0xvalidator1", "0xdelegator12", 2000.0)
        
        total = self.staking_manager.get_total_staked()
        expected = 2000.0 + 1000.0 + 2000.0 + 2000.0  # validator1 self-stake + delegators
        assert float(total) == expected
    
    def test_get_staking_statistics(self):
        """Test staking statistics"""
        stats = self.staking_manager.get_staking_statistics()
        
        assert 'total_validators' in stats
        assert 'total_staked' in stats
        assert 'total_delegators' in stats
        assert 'average_stake_per_validator' in stats
        assert stats['total_validators'] >= 1
        assert stats['total_staked'] >= 2000.0  # At least the initial validator stake

if __name__ == "__main__":
    pytest.main([__file__])
EOF

    log_info "Economic test suite created"
}

# Function to setup test environment
setup_test_environment() {
    log_info "Setting up economic layer test environment..."
    
    # Create test configuration
    cat > "/opt/aitbc/config/economics_test.json" << 'EOF'
{
    "staking": {
        "min_stake_amount": 1000.0,
        "unstaking_period": 21,
        "max_delegators_per_validator": 100,
        "commission_range": [0.01, 0.10]
    },
    "rewards": {
        "base_reward_rate": 0.05,
        "distribution_interval": 86400,
        "min_reward_amount": 0.001,
        "delegation_reward_split": 0.9
    },
    "gas": {
        "base_gas_price": 0.001,
        "max_gas_price": 0.1,
        "min_gas_price": 0.0001,
        "congestion_threshold": 0.8,
        "price_adjustment_factor": 1.1
    },
    "security": {
        "monitoring_interval": 60,
        "detection_history_window": 3600,
        "max_false_positive_rate": 0.05
    }
}
EOF

    log_info "Economic test configuration created"
}

# Function to run economic tests
run_economic_tests() {
    log_info "Running economic layer tests..."
    
    cd /opt/aitbc/apps/blockchain-node
    
    # Install test dependencies if needed
    if ! python -c "import pytest" 2>/dev/null; then
        log_info "Installing pytest..."
        pip install pytest pytest-asyncio
    fi
    
    # Run tests
    python -m pytest tests/economics/ -v
    
    if [ $? -eq 0 ]; then
        log_info "All economic tests passed!"
    else
        log_error "Some economic tests failed!"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting Phase 3: Economic Layer Setup"
    
    # Create necessary directories
    mkdir -p "$ECONOMICS_DIR"
    mkdir -p "/opt/aitbc/config"
    
    # Execute setup steps
    backup_economics
    create_staking_mechanism
    create_reward_distribution
    create_gas_fee_model
    create_attack_prevention
    create_economic_tests
    setup_test_environment
    
    # Run tests
    if run_economic_tests; then
        log_info "Phase 3 economic layer setup completed successfully!"
        log_info "Next steps:"
        log_info "1. Configure economic parameters"
        log_info "2. Initialize staking contracts"
        log_info "3. Set up reward distribution"
        log_info "4. Configure gas fee mechanisms"
        log_info "5. Proceed to Phase 4: Agent Network Scaling"
    else
        log_error "Phase 3 setup failed - check test output"
        return 1
    fi
}

# Execute main function
main "$@"
