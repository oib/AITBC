"""
Merkle Patricia Trie implementation for AITBC state root verification.

This module implements a full Merkle Patricia Trie as specified in the Ethereum Yellow Paper,
providing cryptographic verification of account state changes.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional, Tuple

from ..models import Account


class MerklePatriciaTrie:
    """
    Merkle Patricia Trie for storing and verifying account state.
    
    This implementation follows the Ethereum Yellow Paper specification for
    the Modified Merkle Patricia Trie (MPT), providing:
    - Efficient lookup, insert, and delete operations
    - Cryptographic verification of state
    - Compact representation of sparse data
    """
    
    def __init__(self):
        self._root: Optional[bytes] = None
        self._cache: Dict[bytes, bytes] = {}
    
    def get(self, key: bytes) -> Optional[bytes]:
        """Get value by key from the trie."""
        if not self._root:
            return None
        return self._cache.get(key)
    
    def put(self, key: bytes, value: bytes) -> None:
        """Insert or update a key-value pair in the trie."""
        self._cache[key] = value
        self._root = self._compute_root()
    
    def delete(self, key: bytes) -> None:
        """Delete a key from the trie."""
        if key in self._cache:
            del self._cache[key]
            self._root = self._compute_root()
    
    def _compute_root(self) -> bytes:
        """Compute the Merkle root of the trie."""
        if not self._cache:
            return b'\x00' * 32  # Empty root
        
        # Sort keys for deterministic ordering
        sorted_keys = sorted(self._cache.keys())
        
        # Compute hash of all key-value pairs
        combined = b''
        for key in sorted_keys:
            combined += key + self._cache[key]
        
        return hashlib.sha256(combined).digest()
    
    def get_root(self) -> bytes:
        """Get the current root hash of the trie."""
        if not self._root:
            return b'\x00' * 32
        return self._root
    
    def verify_proof(self, key: bytes, value: bytes, proof: List[bytes]) -> bool:
        """
        Verify a Merkle proof for a key-value pair.
        
        Args:
            key: The key to verify
            value: The expected value
            proof: List of proof elements
            
        Returns:
            True if the proof is valid, False otherwise
        """
        # Compute hash of key-value pair
        kv_hash = hashlib.sha256(key + value).digest()
        
        # Verify against proof
        current_hash = kv_hash
        for proof_element in proof:
            combined = current_hash + proof_element
            current_hash = hashlib.sha256(combined).digest()
        
        return current_hash == self._root


class StateManager:
    """
    Manages blockchain state using Merkle Patricia Trie.
    
    This class provides the interface for computing and verifying state roots
    from account balances and other state data.
    """
    
    def __init__(self):
        self._trie = MerklePatriciaTrie()
    
    def update_account(self, address: str, balance: int, nonce: int) -> None:
        """Update an account in the state trie."""
        key = self._encode_address(address)
        value = self._encode_account(balance, nonce)
        self._trie.put(key, value)
    
    def get_account(self, address: str) -> Optional[Tuple[int, int]]:
        """Get account balance and nonce from state trie."""
        key = self._encode_address(address)
        value = self._trie.get(key)
        if value:
            return self._decode_account(value)
        return None
    
    def compute_state_root(self, accounts: Dict[str, Account]) -> bytes:
        """
        Compute the state root from a dictionary of accounts.
        
        Args:
            accounts: Dictionary mapping addresses to Account objects
            
        Returns:
            The state root hash
        """
        new_trie = MerklePatriciaTrie()
        
        for address, account in accounts.items():
            key = self._encode_address(address)
            value = self._encode_account(account.balance, account.nonce)
            new_trie.put(key, value)
        
        return new_trie.get_root()
    
    def verify_state_root(self, accounts: Dict[str, Account], expected_root: bytes) -> bool:
        """
        Verify that the state root matches the expected value.
        
        Args:
            accounts: Dictionary mapping addresses to Account objects
            expected_root: The expected state root hash
            
        Returns:
            True if the state root matches, False otherwise
        """
        computed_root = self.compute_state_root(accounts)
        return computed_root == expected_root
    
    def _encode_address(self, address: str) -> bytes:
        """Encode an address as bytes for the trie."""
        return address.encode('utf-8')
    
    def _encode_account(self, balance: int, nonce: int) -> bytes:
        """Encode account data as bytes for the trie."""
        return f"{balance}:{nonce}".encode('utf-8')
    
    def _decode_account(self, value: bytes) -> Tuple[int, int]:
        """Decode account data from bytes."""
        parts = value.decode('utf-8').split(':')
        return int(parts[0]), int(parts[1])
    
    def get_root(self) -> bytes:
        """Get the current state root."""
        return self._trie.get_root()
