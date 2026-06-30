"""
Tests for Multi-Validator PoA Consensus
"""

from unittest.mock import Mock

import pytest
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole


class TestMultiValidatorPoA:
    """Test cases for multi-validator PoA consensus"""

    def setup_method(self):
        """Setup test environment"""
        self.consensus = MultiValidatorPoA("test-chain")
        # Disable signature requirement for basic CRUD tests (B3 tests cover sigs)
        self.consensus._require_block_signatures = False

        # Add test validators
        self.validator_addresses = [
            "0x1234567890123456789012345678901234567890",
            "0x2345678901234567890123456789012345678901",
            "0x3456789012345678901234567890123456789012",
            "0x4567890123456789012345678901234567890123",
            "0x5678901234567890123456789012345678901234",
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

        # Create mock block (signature="" since sig requirement disabled in setup)
        block = Mock(spec=Block)
        block.hash = "0xblockhash"
        block.height = 1
        block.signature = ""

        result = self.consensus.validate_block(block, proposer)
        assert result is True

    def test_validate_block_invalid_proposer(self):
        """Test block validation with invalid proposer"""
        from aitbc_chain.models import Block

        # Create mock block
        block = Mock(spec=Block)
        block.hash = "0xblockhash"
        block.height = 1
        block.signature = ""

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

        # Increase reputation (clamped to 1.0 since initial is already 1.0)
        result = self.consensus.update_validator_reputation(validator, 0.1)
        assert result is True
        assert self.consensus.validators[validator].reputation == 1.0  # clamped from 1.0 + 0.1

        # Decrease reputation (1.0 - 0.2 = 0.8)
        result = self.consensus.update_validator_reputation(validator, -0.2)
        assert result is True
        assert self.consensus.validators[validator].reputation == 0.8  # 1.0 (clamped) - 0.2

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


class TestConsensusSecurity:
    """B14: Security-focused consensus tests (C1, C2, C3, C6, H2, H3)"""

    def setup_method(self):
        self.consensus = MultiValidatorPoA("test-chain-sec")
        self.consensus._require_block_signatures = True
        self.addr1 = "0x1111111111111111111111111111111111111111"
        self.addr2 = "0x2222222222222222222222222222222222222222"
        self.addr3 = "0x3333333333333333333333333333333333333333"
        for addr in [self.addr1, self.addr2, self.addr3]:
            self.consensus.add_validator(addr, 1000.0)
            self.consensus.validators[addr].role = ValidatorRole.VALIDATOR

    def test_validate_block_rejects_forged_signature(self):
        """C1: block with invalid signature is rejected"""
        from aitbc_chain.models import Block

        block = Mock(spec=Block)
        block.hash = "0xabc"
        block.signature = "0xforged"
        result = self.consensus.validate_block(block, self.addr1)
        assert result is False

    def test_validate_block_accepts_valid_signature(self):
        """C1: block with valid signature is accepted"""
        from aitbc.crypto.consensus_signing import sign_block_hash
        from aitbc_chain.consensus.keys import KeyManager

        import tempfile

        # Generate a real key pair — let the address be derived from the public key
        with tempfile.TemporaryDirectory() as tmpdir:
            km = KeyManager(keys_dir=tmpdir)
            kp = km.generate_key_pair()  # address derived from the key
            # The proposer's address must match the key's derived address
            real_addr = kp.address
            self.consensus.add_validator(real_addr, 1000.0)
            self.consensus.validators[real_addr].role = ValidatorRole.VALIDATOR
            # Use a valid 32-byte hex block hash (sign_block_hash treats it as a message hash)
            block_hash = "a" * 64
            sig = sign_block_hash(block_hash, kp.private_key_hex)
            from aitbc_chain.models import Block

            block = Mock(spec=Block)
            block.hash = block_hash
            block.signature = sig
            result = self.consensus.validate_block(block, real_addr)
            assert result is True

    def test_validate_block_rejects_unsigned_when_required(self):
        """C1: unsigned block rejected when _require_block_signatures=True"""
        from aitbc_chain.models import Block

        block = Mock(spec=Block)
        block.hash = "0xabc"
        block.signature = ""
        result = self.consensus.validate_block(block, self.addr1)
        assert result is False

    def test_record_prepare_rejects_conflicting(self):
        """C6: conflicting prepare message returns False"""
        # First prepare for round 1 with hash A
        assert self.consensus.record_prepare(self.addr1, "hashA", 1) is True
        # Conflicting prepare for same round with hash B
        result = self.consensus.record_prepare(self.addr1, "hashB", 1)
        assert result is False

    def test_byzantine_detection_triggers_slashing(self):
        """C2: equivocation → slashing → validator has reduced stake"""
        initial_stake = self.consensus.validators[self.addr1].stake
        # Record conflicting prepares
        self.consensus.record_prepare(self.addr1, "hashA", 1)
        self.consensus.record_prepare(self.addr1, "hashB", 1)
        # Slashing should have been triggered
        history = self.consensus.get_slashing_history()
        assert len(history) > 0
        # Stake should be reduced
        assert self.consensus.validators[self.addr1].stake < initial_stake

    def test_slashing_reduces_stake(self):
        """Slashed validator has reduced stake (50% for double_sign)"""
        initial_stake = self.consensus.validators[self.addr1].stake
        self.consensus.record_prepare(self.addr1, "hashA", 1)
        self.consensus.record_prepare(self.addr1, "hashB", 1)
        # Double-sign slash rate is 50%
        expected_slash = initial_stake * 0.5
        actual_stake = self.consensus.validators[self.addr1].stake
        assert abs(actual_stake - (initial_stake - expected_slash)) < 0.01

    def test_slashing_deactivates_after_threshold(self):
        """3 slashing events → is_active=False"""
        # Set byzantine threshold to 3 (default)
        # Need to trigger 3 double-sign events
        for i in range(3):
            self.consensus.record_prepare(self.addr1, f"hashA{i}", 10 + i)
            self.consensus.record_prepare(self.addr1, f"hashB{i}", 10 + i)
        assert self.consensus.validators[self.addr1].is_active is False

    def test_validator_rotation_epoch_transition(self):
        """C3: rotation triggers at epoch boundary"""
        # Set all validators as proposers
        for addr in [self.addr1, self.addr2, self.addr3]:
            self.consensus.validators[addr].role = ValidatorRole.PROPOSER
        # Use a small epoch size for testing by directly setting _current_epoch
        from aitbc_chain.config import settings

        original_epoch = settings.consensus_validator_set_epoch_blocks
        settings.consensus_validator_set_epoch_blocks = 10
        # Set rotation config's interval to match
        from aitbc_chain.consensus.rotation import RotationConfig, RotationStrategy

        self.consensus._rotation.config = RotationConfig(
            strategy=RotationStrategy.ROUND_ROBIN,
            rotation_interval=10,
            min_stake=100.0,
            reputation_threshold=0.5,
            max_validators=10,
        )
        self.consensus._rotation.last_rotation_height = 0
        self.consensus.maybe_rotate(10)
        settings.consensus_validator_set_epoch_blocks = original_epoch
        # Rotation may or may not return True depending on strategy impl,
        # but epoch should have advanced
        assert self.consensus._current_epoch == 1

    def test_create_block_includes_parent_hash(self):
        """H3: block hash includes parent hash"""
        block = self.consensus.create_block(height=1, parent_hash="0xparent123")
        assert block["parent_hash"] == "0xparent123"

    def test_create_block_includes_tx_hashes(self):
        """H3: block includes transaction hashes"""
        tx1 = Mock()
        tx1.tx_id = "tx_hash_1"
        tx2 = Mock()
        tx2.tx_id = "tx_hash_2"
        block = self.consensus.create_block(height=1, transactions=[tx1, tx2])
        assert "tx_hash_1" in block["transactions"]
        assert "tx_hash_2" in block["transactions"]

    def test_validate_transaction_rejects_negative_amount(self):
        """H2: negative amount transaction is rejected"""
        tx = Mock()
        tx.tx_id = "tx1"
        tx.amount = -100
        import asyncio

        result = asyncio.run(self.consensus.validate_transaction_async(tx))
        assert result is False

    def test_validate_transaction_rejects_empty_chain_id(self):
        """H2: empty chain_id transaction is rejected"""
        tx = Mock()
        tx.tx_id = "tx1"
        tx.amount = 100  # valid amount so we reach the chain_id check
        tx.chain_id = ""
        import asyncio

        result = asyncio.run(self.consensus.validate_transaction_async(tx))
        assert result is False

    def test_collect_metrics(self):
        """B12: collect_metrics returns expected keys"""
        metrics = self.consensus.collect_metrics()
        assert "consensus_validators_active" in metrics
        assert "consensus_validators_total" in metrics
        assert "consensus_rounds_total" in metrics
        assert metrics["consensus_validators_total"] == 3


if __name__ == "__main__":
    pytest.main([__file__])
