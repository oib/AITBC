"""
Security tests for state root verification.

Tests that state root verification prevents silent tampering.
import sys
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
    
    def test_merkle_patricia_trie_shared_prefix_keys(self):
        trie = MerklePatriciaTrie()
        entries = {
            b"account:alice": b"1000:0",
            b"account:alicia": b"2000:1",
            b"account:bob": b"3000:2",
        }
        
        for key, value in entries.items():
            trie.put(key, value)
        
        for key, value in entries.items():
            assert trie.get(key) == value
        
        assert trie.get(b"account:unknown") is None
        assert trie.get_root() != b'\x00' * 32
    
    def test_merkle_patricia_trie_update_changes_value_and_root(self):
        trie = MerklePatriciaTrie()
        trie.put(b"account:alice", b"1000:0")
        initial_root = trie.get_root()
        
        trie.put(b"account:alice", b"1500:1")
        
        assert trie.get(b"account:alice") == b"1500:1"
        assert trie.get_root() != initial_root
    
    def test_merkle_patricia_trie_deterministic_insertion_order(self):
        entries = [
            (b"account:alice", b"1000:0"),
            (b"account:alicia", b"2000:1"),
            (b"account:bob", b"3000:2"),
            (b"account:charlie", b"4000:3"),
        ]
        first = MerklePatriciaTrie()
        second = MerklePatriciaTrie()
        
        for key, value in entries:
            first.put(key, value)
        for key, value in reversed(entries):
            second.put(key, value)
        
        assert first.get_root() == second.get_root()
    
    def test_merkle_patricia_trie_delete_compacts_prefixes(self):
        trie = MerklePatriciaTrie()
        trie.put(b"account:alice", b"1000:0")
        trie.put(b"account:alicia", b"2000:1")
        trie.put(b"account:bob", b"3000:2")
        
        trie.delete(b"account:alicia")
        
        assert trie.get(b"account:alicia") is None
        assert trie.get(b"account:alice") == b"1000:0"
        assert trie.get(b"account:bob") == b"3000:2"
        assert trie.get_root() != b'\x00' * 32
    
    def test_merkle_patricia_trie_proof_verification(self):
        trie = MerklePatriciaTrie()
        trie.put(b"account:alice", b"1000:0")
        trie.put(b"account:bob", b"2000:1")
        
        proof = trie.get_proof(b"account:alice")
        
        assert proof
        assert trie.verify_proof(b"account:alice", b"1000:0", proof)
        assert not trie.verify_proof(b"account:alice", b"9999:0", proof)
        assert not trie.verify_proof(b"account:unknown", b"1000:0", proof)
    
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
    
    def test_state_manager_root_is_order_independent(self):
        state_manager = StateManager()
        
        accounts1 = {
            "address1": Account(chain_id="test", address="address1", balance=1000, nonce=0),
            "address2": Account(chain_id="test", address="address2", balance=2000, nonce=1),
            "address3": Account(chain_id="test", address="address3", balance=3000, nonce=2),
        }
        accounts2 = {
            "address3": Account(chain_id="test", address="address3", balance=3000, nonce=2),
            "address1": Account(chain_id="test", address="address1", balance=1000, nonce=0),
            "address2": Account(chain_id="test", address="address2", balance=2000, nonce=1),
        }
        
        assert state_manager.compute_state_root(accounts1) == state_manager.compute_state_root(accounts2)
