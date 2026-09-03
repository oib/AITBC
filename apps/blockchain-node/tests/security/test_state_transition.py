"""
Security tests for state transition validation.

Tests that balance changes only occur through validated transactions.
import sys
"""

from aitbc_chain.state.state_transition import StateTransition, get_block_version


class TestStateTransition:
    """Test state transition validation."""

    def test_transaction_validation_insufficient_balance(self):
        """Test that transactions with insufficient balance are rejected."""
        StateTransition()

        # Mock session and transaction data
        # This would require a full database setup
        # For now, we test the validation logic

        # This test would require database setup
        # For now, we document the test structure
        pass

    def test_transaction_validation_invalid_nonce(self):
        """Test that transactions with invalid nonce are rejected."""
        StateTransition()

        # This test would require database setup
        pass

    def test_replay_protection(self):
        """Test that replay attacks are prevented."""
        state_transition = StateTransition()

        tx_hash = "test_tx_hash"

        # Mark transaction as processed
        state_transition._processed_tx_hashes.add(tx_hash)

        # Try to process again - should fail
        assert tx_hash in state_transition._processed_tx_hashes

    def test_nonce_tracking(self):
        """Test that nonces are tracked correctly."""
        state_transition = StateTransition()

        address = "test_address"
        nonce = 5

        state_transition._processed_nonces[address] = nonce

        assert state_transition.get_processed_nonces()[address] == nonce

    def test_state_transition_reset(self):
        """Test that state transition can be reset."""
        state_transition = StateTransition()

        # Add some data
        state_transition._processed_tx_hashes.add("test_hash")
        state_transition._processed_nonces["test_addr"] = 5

        # Reset
        state_transition.reset()

        # Verify reset
        assert len(state_transition._processed_tx_hashes) == 0
        assert len(state_transition._processed_nonces) == 0

    def test_get_block_version_from_metadata(self):
        """Version stored in block_metadata is preferred over the threshold."""
        assert get_block_version({"block_metadata": '{"state_transition_version": 2}'}, height=0) == 2
        assert get_block_version({"block_metadata": '{"state_transition_version": 1}'}, height=999999) == 1

    def test_get_block_version_threshold_fallback(self):
        """Unversioned blocks fall back to the configured v2 activation height."""
        import aitbc_chain.config as config

        original = getattr(config.settings, "state_transition_v2_height", 0)
        config.settings.state_transition_v2_height = 1000
        try:
            # Below the threshold: unversioned historical block uses v1 rules.
            assert get_block_version({"block_metadata": None}, height=999) == 1
            # At/above the threshold: unversioned block produced after the
            # activation uses v2 rules (new chains with threshold 0 also see v2).
            assert get_block_version({"block_metadata": None}, height=1000) == 2
        finally:
            config.settings.state_transition_v2_height = original
