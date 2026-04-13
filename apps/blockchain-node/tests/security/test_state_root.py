"""
Security tests for state root verification.

Tests that state root verification prevents silent tampering.
"""

import pytest

from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie, StateManager
from aitbc_chain.models import Account


class TestStateRootVerification:
    """Test state root verification with Merkle Patricia Trie."""
    
    def test_merkle_patricia_trie_insert(self):
        """Test that Merkle Patricia Trie can insert key-value pairs."""
        trie = MerklePatriciaTrie()
        
        key = b"test_key"
        value = b"test_value"
        
        trie.put(key, value)
        
        assert trie.get(key) == value
    
    def test_merkle_patricia_trie_root_computation(self):
        """Test that Merkle Patricia Trie computes correct root."""
        trie = MerklePatriciaTrie()
        
        # Insert some data
        trie.put(b"key1", b"value1")
        trie.put(b"key2", b"value2")
        
        root = trie.get_root()
        
        # Root should not be empty
        assert root != b'\x00' * 32
        assert len(root) == 32
    
    def test_merkle_patricia_trie_delete(self):
        """Test that Merkle Patricia Trie can delete keys."""
        trie = MerklePatriciaTrie()
        
        key = b"test_key"
        value = b"test_value"
        
        trie.put(key, value)
        assert trie.get(key) == value
        
        trie.delete(key)
        assert trie.get(key) is None
    
    def test_state_manager_compute_state_root(self):
        """Test that StateManager computes state root from accounts."""
        state_manager = StateManager()
        
        accounts = {
            "address1": Account(chain_id="test", address="address1", balance=1000, nonce=0),
            "address2": Account(chain_id="test", address="address2", balance=2000, nonce=1),
        }
        
        root = state_manager.compute_state_root(accounts)
        
        # Root should be 32 bytes
        assert len(root) == 32
        assert root != b'\x00' * 32
    
    def test_state_manager_verify_state_root(self):
        """Test that StateManager can verify state root."""
        state_manager = StateManager()
        
        accounts = {
            "address1": Account(chain_id="test", address="address1", balance=1000, nonce=0),
            "address2": Account(chain_id="test", address="address2", balance=2000, nonce=1),
        }
        
        expected_root = state_manager.compute_state_root(accounts)
        
        # Verify should pass with correct root
        assert state_manager.verify_state_root(accounts, expected_root)
        
        # Verify should fail with incorrect root
        fake_root = b'\x00' * 32
        assert not state_manager.verify_state_root(accounts, fake_root)
    
    def test_state_manager_different_state_different_root(self):
        """Test that different account states produce different roots."""
        state_manager = StateManager()
        
        accounts1 = {
            "address1": Account(chain_id="test", address="address1", balance=1000, nonce=0),
        }
        
        accounts2 = {
            "address1": Account(chain_id="test", address="address1", balance=2000, nonce=0),
        }
        
        root1 = state_manager.compute_state_root(accounts1)
        root2 = state_manager.compute_state_root(accounts2)
        
        # Different balances should produce different roots
        assert root1 != root2
