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
