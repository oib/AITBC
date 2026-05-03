"""
Merkle Patricia Trie implementation for AITBC state root verification.

This module implements a full Merkle Patricia Trie as specified in the Ethereum Yellow Paper,
providing cryptographic verification of account state changes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Dict, List, Optional, Tuple, Union

from ..models import Account


@dataclass(frozen=True)
class LeafNode:
    path: Tuple[int, ...]
    value: bytes


@dataclass(frozen=True)
class ExtensionNode:
    path: Tuple[int, ...]
    child: "TrieNode"


@dataclass(frozen=True)
class BranchNode:
    children: Tuple[Optional["TrieNode"], ...]
    value: Optional[bytes] = None


TrieNode = Union[LeafNode, ExtensionNode, BranchNode]


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
        self._root: Optional[TrieNode] = None
    
    def get(self, key: bytes) -> Optional[bytes]:
        """Get value by key from the trie."""
        return self._get(self._root, self._to_nibbles(key))
    
    def put(self, key: bytes, value: bytes) -> None:
        """Insert or update a key-value pair in the trie."""
        self._root = self._insert(self._root, self._to_nibbles(key), value)
    
    def delete(self, key: bytes) -> None:
        """Delete a key from the trie."""
        self._root = self._delete(self._root, self._to_nibbles(key))
    
    def _compute_root(self) -> bytes:
        """Compute the Merkle root of the trie."""
        return self.get_root()
    
    def get_root(self) -> bytes:
        """Get the current root hash of the trie."""
        if not self._root:
            return b'\x00' * 32
        return self._hash_node(self._root)
    
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
        if not proof:
            return False

        expected_hash = self.get_root()
        path = self._to_nibbles(key)

        for index, encoded_node in enumerate(proof):
            if hashlib.sha256(encoded_node).digest() != expected_hash:
                return False

            node_type, node_path, node_value, child_hashes = self._decode_node(encoded_node)

            if node_type == b"L":
                return index == len(proof) - 1 and path == node_path and node_value == value

            if node_type == b"E":
                if not self._starts_with(path, node_path):
                    return False
                path = path[len(node_path):]
                if child_hashes[0] is None:
                    return False
                expected_hash = child_hashes[0]
                continue

            if node_type == b"B":
                if not path:
                    return index == len(proof) - 1 and node_value == value
                next_hash = child_hashes[path[0]]
                if next_hash is None:
                    return False
                expected_hash = next_hash
                path = path[1:]
                continue

            return False

        return False

    def get_proof(self, key: bytes) -> List[bytes]:
        proof: List[bytes] = []
        if self._collect_proof(self._root, self._to_nibbles(key), proof):
            return proof
        return []

    @staticmethod
    def _to_nibbles(key: bytes) -> Tuple[int, ...]:
        nibbles: List[int] = []
        for byte in key:
            nibbles.append(byte >> 4)
            nibbles.append(byte & 0x0F)
        return tuple(nibbles)

    @staticmethod
    def _starts_with(path: Tuple[int, ...], prefix: Tuple[int, ...]) -> bool:
        return len(path) >= len(prefix) and path[:len(prefix)] == prefix

    @staticmethod
    def _common_prefix_len(left: Tuple[int, ...], right: Tuple[int, ...]) -> int:
        limit = min(len(left), len(right))
        for index in range(limit):
            if left[index] != right[index]:
                return index
        return limit

    @staticmethod
    def _empty_children() -> Tuple[Optional[TrieNode], ...]:
        return (None,) * 16

    @staticmethod
    def _set_child(children: Tuple[Optional[TrieNode], ...], index: int, child: Optional[TrieNode]) -> Tuple[Optional[TrieNode], ...]:
        updated = list(children)
        updated[index] = child
        return tuple(updated)

    def _get(self, node: Optional[TrieNode], path: Tuple[int, ...]) -> Optional[bytes]:
        if node is None:
            return None
        if isinstance(node, LeafNode):
            if node.path == path:
                return node.value
            return None
        if isinstance(node, ExtensionNode):
            if self._starts_with(path, node.path):
                return self._get(node.child, path[len(node.path):])
            return None
        if not path:
            return node.value
        child = node.children[path[0]]
        if child is None:
            return None
        return self._get(child, path[1:])

    def _insert(self, node: Optional[TrieNode], path: Tuple[int, ...], value: bytes) -> TrieNode:
        if node is None:
            return LeafNode(path, value)

        if isinstance(node, LeafNode):
            common_len = self._common_prefix_len(path, node.path)
            if common_len == len(path) and common_len == len(node.path):
                return LeafNode(node.path, value)

            branch = BranchNode(self._empty_children())
            existing_suffix = node.path[common_len:]
            new_suffix = path[common_len:]
            branch = self._attach_to_branch(branch, existing_suffix, node.value)
            branch = self._attach_to_branch(branch, new_suffix, value)
            normalized = self._normalize_branch(branch)
            if common_len == 0:
                return normalized
            return self._normalize_extension(ExtensionNode(path[:common_len], normalized))

        if isinstance(node, ExtensionNode):
            common_len = self._common_prefix_len(path, node.path)
            if common_len == len(node.path):
                child = self._insert(node.child, path[common_len:], value)
                return self._normalize_extension(ExtensionNode(node.path, child))

            branch = BranchNode(self._empty_children())
            existing_suffix = node.path[common_len:]
            new_suffix = path[common_len:]
            branch = self._attach_node_to_branch(branch, existing_suffix, node.child)
            branch = self._attach_to_branch(branch, new_suffix, value)
            normalized = self._normalize_branch(branch)
            if common_len == 0:
                return normalized
            return self._normalize_extension(ExtensionNode(path[:common_len], normalized))

        if not path:
            return BranchNode(node.children, value)
        child = self._insert(node.children[path[0]], path[1:], value)
        return self._normalize_branch(BranchNode(self._set_child(node.children, path[0], child), node.value))

    def _delete(self, node: Optional[TrieNode], path: Tuple[int, ...]) -> Optional[TrieNode]:
        if node is None:
            return None

        if isinstance(node, LeafNode):
            if node.path == path:
                return None
            return node

        if isinstance(node, ExtensionNode):
            if not self._starts_with(path, node.path):
                return node
            child = self._delete(node.child, path[len(node.path):])
            if child is None:
                return None
            return self._normalize_extension(ExtensionNode(node.path, child))

        if not path:
            return self._normalize_branch(BranchNode(node.children, None))

        child = self._delete(node.children[path[0]], path[1:])
        return self._normalize_branch(BranchNode(self._set_child(node.children, path[0], child), node.value))

    def _attach_to_branch(self, branch: BranchNode, suffix: Tuple[int, ...], value: bytes) -> BranchNode:
        if not suffix:
            return BranchNode(branch.children, value)
        child = LeafNode(suffix[1:], value)
        return BranchNode(self._set_child(branch.children, suffix[0], child), branch.value)

    def _attach_node_to_branch(self, branch: BranchNode, suffix: Tuple[int, ...], child: TrieNode) -> BranchNode:
        if not suffix:
            return BranchNode(branch.children, self._value_from_node(child))
        if len(suffix) == 1:
            new_child = child
        else:
            new_child = ExtensionNode(suffix[1:], child)
        return BranchNode(self._set_child(branch.children, suffix[0], new_child), branch.value)

    @staticmethod
    def _value_from_node(node: TrieNode) -> bytes:
        if isinstance(node, LeafNode) and not node.path:
            return node.value
        raise ValueError("Cannot attach non-terminal node as branch value")

    def _normalize_extension(self, node: ExtensionNode) -> TrieNode:
        if not node.path:
            return node.child
        if isinstance(node.child, LeafNode):
            return LeafNode(node.path + node.child.path, node.child.value)
        if isinstance(node.child, ExtensionNode):
            return ExtensionNode(node.path + node.child.path, node.child.child)
        return node

    def _normalize_branch(self, node: BranchNode) -> Optional[TrieNode]:
        child_indexes = [index for index, child in enumerate(node.children) if child is not None]
        if node.value is not None:
            return node
        if not child_indexes:
            return None
        if len(child_indexes) > 1:
            return node

        index = child_indexes[0]
        child = node.children[index]
        if child is None:
            return None
        if isinstance(child, LeafNode):
            return LeafNode((index,) + child.path, child.value)
        if isinstance(child, ExtensionNode):
            return ExtensionNode((index,) + child.path, child.child)
        return ExtensionNode((index,), child)

    def _hash_node(self, node: TrieNode) -> bytes:
        return hashlib.sha256(self._encode_node(node)).digest()

    def _encode_node(self, node: TrieNode) -> bytes:
        if isinstance(node, LeafNode):
            return b"L" + self._encode_path(node.path) + self._encode_value(node.value)
        if isinstance(node, ExtensionNode):
            return b"E" + self._encode_path(node.path) + self._hash_node(node.child)

        encoded = bytearray(b"B")
        for child in node.children:
            if child is None:
                encoded.extend(b"\x00")
            else:
                encoded.extend(b"\x01")
                encoded.extend(self._hash_node(child))
        if node.value is None:
            encoded.extend(b"\x00")
        else:
            encoded.extend(b"\x01")
            encoded.extend(self._encode_value(node.value))
        return bytes(encoded)

    @staticmethod
    def _encode_path(path: Tuple[int, ...]) -> bytes:
        return len(path).to_bytes(4, "big") + bytes(path)

    @staticmethod
    def _encode_value(value: bytes) -> bytes:
        return len(value).to_bytes(8, "big") + value

    def _decode_node(self, encoded_node: bytes) -> Tuple[bytes, Tuple[int, ...], Optional[bytes], List[Optional[bytes]]]:
        node_type = encoded_node[:1]
        offset = 1

        if node_type in {b"L", b"E"}:
            path_len = int.from_bytes(encoded_node[offset:offset + 4], "big")
            offset += 4
            path = tuple(encoded_node[offset:offset + path_len])
            offset += path_len
            if node_type == b"L":
                value_len = int.from_bytes(encoded_node[offset:offset + 8], "big")
                offset += 8
                return node_type, path, encoded_node[offset:offset + value_len], []
            return node_type, path, None, [encoded_node[offset:offset + 32]]

        if node_type == b"B":
            child_hashes: List[Optional[bytes]] = []
            for _ in range(16):
                has_child = encoded_node[offset:offset + 1] == b"\x01"
                offset += 1
                if has_child:
                    child_hashes.append(encoded_node[offset:offset + 32])
                    offset += 32
                else:
                    child_hashes.append(None)
            has_value = encoded_node[offset:offset + 1] == b"\x01"
            offset += 1
            if not has_value:
                return node_type, (), None, child_hashes
            value_len = int.from_bytes(encoded_node[offset:offset + 8], "big")
            offset += 8
            return node_type, (), encoded_node[offset:offset + value_len], child_hashes

        return b"", (), None, []

    def _collect_proof(self, node: Optional[TrieNode], path: Tuple[int, ...], proof: List[bytes]) -> bool:
        if node is None:
            return False

        proof.append(self._encode_node(node))

        if isinstance(node, LeafNode):
            return node.path == path

        if isinstance(node, ExtensionNode):
            if not self._starts_with(path, node.path):
                return False
            return self._collect_proof(node.child, path[len(node.path):], proof)

        if not path:
            return node.value is not None
        child = node.children[path[0]]
        if child is None:
            return False
        return self._collect_proof(child, path[1:], proof)


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
        
        for address, account in sorted(accounts.items()):
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
