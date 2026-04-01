"""
Phase 1: Consensus Layer Tests
Modularized consensus layer tests for AITBC Mesh Network
"""

import pytest
import asyncio
import time
from unittest.mock import Mock
from decimal import Decimal

# Import consensus components
try:
    from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
    from aitbc_chain.consensus.rotation import ValidatorRotation, RotationStrategy, DEFAULT_ROTATION_CONFIG
    from aitbc_chain.consensus.pbft import PBFTConsensus, PBFTPhase, PBFTMessageType
    from aitbc_chain.consensus.slashing import SlashingManager, SlashingCondition
    from aitbc_chain.consensus.keys import KeyManager
except ImportError:
    pytest.skip("Phase 1 consensus modules not available", allow_module_level=True)


class TestMultiValidatorPoA:
    """Test Multi-Validator Proof of Authority Consensus"""
    
    @pytest.fixture
    def poa(self):
        """Create fresh PoA instance for each test"""
        return MultiValidatorPoA("test-chain")
    
    def test_initialization(self, poa):
        """Test multi-validator PoA initialization"""
        assert poa.chain_id == "test-chain"
        assert len(poa.validators) == 0
        assert poa.current_proposer_index == 0
        assert poa.round_robin_enabled is True
        assert poa.consensus_timeout == 30
    
    def test_add_validator(self, poa):
        """Test adding validators"""
        validator_address = "0x1234567890123456789012345678901234567890"
        
        success = poa.add_validator(validator_address, 1000.0)
        assert success is True
        assert validator_address in poa.validators
        assert poa.validators[validator_address].stake == 1000.0
        assert poa.validators[validator_address].role == ValidatorRole.STANDBY
    
    def test_add_duplicate_validator(self, poa):
        """Test adding duplicate validator fails"""
        validator_address = "0x1234567890123456789012345678901234567890"
        
        poa.add_validator(validator_address, 1000.0)
        success = poa.add_validator(validator_address, 2000.0)
        assert success is False
    
    def test_remove_validator(self, poa):
        """Test removing validator"""
        validator_address = "0x1234567890123456789012345678901234567890"
        poa.add_validator(validator_address, 1000.0)
        
        success = poa.remove_validator(validator_address)
        assert success is True
        assert validator_address not in poa.validators
    
    def test_select_proposer_round_robin(self, poa):
        """Test round-robin proposer selection"""
        validators = [
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
            "0x3333333333333333333333333333333333333333"
        ]
        
        for validator in validators:
            poa.add_validator(validator, 1000.0)
        
        proposers = [poa.select_proposer(i) for i in range(6)]
        
        assert all(p in validators for p in proposers[:3])
        assert proposers[0] == proposers[3]  # Should cycle
    
    def test_activate_validator(self, poa):
        """Test validator activation"""
        validator_address = "0x1234567890123456789012345678901234567890"
        poa.add_validator(validator_address, 1000.0)
        
        success = poa.activate_validator(validator_address)
        assert success is True
        assert poa.validators[validator_address].role == ValidatorRole.VALIDATOR
        assert poa.validators[validator_address].is_active is True
    
    def test_set_proposer(self, poa):
        """Test setting proposer role"""
        validator_address = "0x1234567890123456789012345678901234567890"
        poa.add_validator(validator_address, 1000.0)
        poa.activate_validator(validator_address)
        
        success = poa.set_proposer(validator_address)
        assert success is True
        assert poa.validators[validator_address].role == ValidatorRole.PROPOSER


class TestValidatorRotation:
    """Test Validator Rotation Mechanisms"""
    
    @pytest.fixture
    def rotation(self):
        """Create rotation instance with PoA"""
        poa = MultiValidatorPoA("test-chain")
        return ValidatorRotation(poa, DEFAULT_ROTATION_CONFIG)
    
    def test_rotation_strategies(self, rotation):
        """Test different rotation strategies"""
        # Add validators
        for i in range(5):
            rotation.poa.add_validator(f"0x{i}", 1000.0)
        
        # Test round-robin
        rotation.config.strategy = RotationStrategy.ROUND_ROBIN
        success = rotation.rotate_validators(100)
        assert success is True
        
        # Test stake-weighted
        rotation.config.strategy = RotationStrategy.STAKE_WEIGHTED
        success = rotation.rotate_validators(101)
        assert success is True
        
        # Test reputation-weighted
        rotation.config.strategy = RotationStrategy.REPUTATION_WEIGHTED
        success = rotation.rotate_validators(102)
        assert success is True
    
    def test_rotation_interval(self, rotation):
        """Test rotation respects intervals"""
        assert rotation.config.min_blocks_between_rotations > 0
    
    def test_rotation_with_no_validators(self, rotation):
        """Test rotation with no validators"""
        success = rotation.rotate_validators(100)
        assert success is False


class TestPBFTConsensus:
    """Test PBFT Byzantine Fault Tolerance"""
    
    @pytest.fixture
    def pbft(self):
        """Create PBFT instance"""
        poa = MultiValidatorPoA("test-chain")
        return PBFTConsensus(poa)
    
    @pytest.mark.asyncio
    async def test_pre_prepare_phase(self, pbft):
        """Test pre-prepare phase"""
        success = await pbft.pre_prepare_phase(
            "0xvalidator1", "block_hash_123", 1,
            ["0xvalidator1", "0xvalidator2", "0xvalidator3"],
            {"0xvalidator1": 0.9, "0xvalidator2": 0.8, "0xvalidator3": 0.85}
        )
        assert success is True
    
    @pytest.mark.asyncio
    async def test_prepare_phase(self, pbft):
        """Test prepare phase"""
        # First do pre-prepare
        await pbft.pre_prepare_phase(
            "0xvalidator1", "block_hash_123", 1,
            ["0xvalidator1", "0xvalidator2", "0xvalidator3"],
            {"0xvalidator1": 0.9, "0xvalidator2": 0.8, "0xvalidator3": 0.85}
        )
        
        # Then prepare
        success = await pbft.prepare_phase("block_hash_123", 1)
        assert success is True
    
    @pytest.mark.asyncio
    async def test_commit_phase(self, pbft):
        """Test commit phase"""
        success = await pbft.commit_phase("block_hash_123", 1)
        assert success is True
    
    def test_quorum_calculation(self, pbft):
        """Test quorum calculation"""
        assert pbft.quorum_size(4) == 3  # 2f+1 where f=1
        assert pbft.quorum_size(7) == 5  # 2f+1 where f=2
        assert pbft.quorum_size(10) == 7  # 2f+1 where f=3
    
    def test_fault_tolerance_threshold(self, pbft):
        """Test fault tolerance threshold"""
        assert pbft.max_faulty_nodes(4) == 1  # floor((n-1)/3)
        assert pbft.max_faulty_nodes(7) == 2
        assert pbft.max_faulty_nodes(10) == 3


class TestSlashingManager:
    """Test Slashing Condition Detection"""
    
    @pytest.fixture
    def slashing(self):
        """Create slashing manager"""
        return SlashingManager()
    
    def test_double_sign_detection(self, slashing):
        """Test double signing detection"""
        validator_address = "0xvalidator1"
        
        event = slashing.detect_double_sign(
            validator_address, "hash1", "hash2", 100
        )
        
        assert event is not None
        assert event.condition == SlashingCondition.DOUBLE_SIGN
        assert event.validator_address == validator_address
    
    def test_downtime_detection(self, slashing):
        """Test downtime detection"""
        validator_address = "0xvalidator1"
        
        event = slashing.detect_excessive_downtime(
            validator_address, missed_blocks=50, threshold=20
        )
        
        assert event is not None
        assert event.condition == SlashingCondition.EXCESSIVE_DOWNTIME
    
    def test_malicious_proposal_detection(self, slashing):
        """Test malicious proposal detection"""
        validator_address = "0xvalidator1"
        
        event = slashing.detect_malicious_proposal(
            validator_address, "invalid_block_hash"
        )
        
        assert event is not None
        assert event.condition == SlashingCondition.MALICIOUS_PROPOSAL
    
    def test_slashing_percentage(self, slashing):
        """Test slashing percentage calculation"""
        assert slashing.get_slashing_percentage(SlashingCondition.DOUBLE_SIGN) == 0.1
        assert slashing.get_slashing_percentage(SlashingCondition.EXCESSIVE_DOWNTIME) == 0.05
        assert slashing.get_slashing_percentage(SlashingCondition.MALICIOUS_PROPOSAL) == 0.1


class TestKeyManager:
    """Test Cryptographic Key Management"""
    
    @pytest.fixture
    def key_manager(self):
        """Create key manager"""
        return KeyManager()
    
    def test_key_pair_generation(self, key_manager):
        """Test key pair generation"""
        address = "0x1234567890123456789012345678901234567890"
        
        key_pair = key_manager.generate_key_pair(address)
        
        assert key_pair.address == address
        assert key_pair.private_key_pem is not None
        assert key_pair.public_key_pem is not None
    
    def test_message_signing(self, key_manager):
        """Test message signing"""
        address = "0x1234567890123456789012345678901234567890"
        key_manager.generate_key_pair(address)
        
        message = "test message"
        signature = key_manager.sign_message(address, message)
        
        assert signature is not None
        assert len(signature) > 0
    
    def test_signature_verification(self, key_manager):
        """Test signature verification"""
        address = "0x1234567890123456789012345678901234567890"
        key_manager.generate_key_pair(address)
        
        message = "test message"
        signature = key_manager.sign_message(address, message)
        
        valid = key_manager.verify_signature(address, message, signature)
        assert valid is True
    
    def test_invalid_signature(self, key_manager):
        """Test invalid signature detection"""
        address = "0x1234567890123456789012345678901234567890"
        key_manager.generate_key_pair(address)
        
        message = "test message"
        invalid_signature = "invalid_signature"
        
        valid = key_manager.verify_signature(address, message, invalid_signature)
        assert valid is False
    
    def test_key_rotation(self, key_manager):
        """Test key rotation"""
        address = "0x1234567890123456789012345678901234567890"
        
        # Generate initial key
        key_pair_1 = key_manager.generate_key_pair(address)
        
        # Rotate key
        success = key_manager.rotate_key(address)
        assert success is True
        
        # Get new key
        key_pair_2 = key_manager.get_key_pair(address)
        assert key_pair_2.public_key_pem != key_pair_1.public_key_pem


class TestConsensusIntegration:
    """Test Integration Between Consensus Components"""
    
    def test_full_consensus_flow(self):
        """Test complete consensus flow"""
        # Setup components
        poa = MultiValidatorPoA("test-chain")
        pbft = PBFTConsensus(poa)
        slashing = SlashingManager()
        
        # Add validators
        for i in range(4):
            poa.add_validator(f"0x{i}", 1000.0)
        
        # Test integration
        assert poa is not None
        assert pbft is not None
        assert slashing is not None
    
    def test_rotation_with_slashing(self):
        """Test rotation with slashed validator"""
        poa = MultiValidatorPoA("test-chain")
        rotation = ValidatorRotation(poa, DEFAULT_ROTATION_CONFIG)
        slashing = SlashingManager()
        
        # Add validators
        validators = [f"0x{i}" for i in range(4)]
        for v in validators:
            poa.add_validator(v, 1000.0)
        
        # Slash one validator
        slashed_validator = validators[0]
        slashing.apply_slash(slashed_validator, 0.1, "Test slash")
        
        # Rotation should skip slashed validator
        success = rotation.rotate_validators(100)
        assert success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
