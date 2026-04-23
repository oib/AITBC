"""
Tests for Staking Mechanism
"""

import sys
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
