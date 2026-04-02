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
