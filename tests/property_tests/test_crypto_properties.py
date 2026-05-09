"""
Property-based tests for critical AITBC cryptographic functions using hypothesis.
Tests ensure that cryptographic operations maintain expected properties across random inputs.
"""

import pytest
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import text, binary, integers
import json

from aitbc.crypto.crypto import (
    derive_ethereum_address,
    sign_transaction_hash,
    verify_signature,
    encrypt_private_key,
    decrypt_private_key,
    keccak256_hash,
    sha256_hash,
    generate_secure_random_bytes,
    validate_ethereum_address,
    generate_ethereum_private_key
)


class TestCryptoProperties:
    """Property-based tests for cryptographic functions"""

    @given(st.binary(min_size=32, max_size=32))
    @settings(max_examples=100)
    def test_derive_address_deterministic(self, private_key_bytes):
        """Test that address derivation is deterministic for same private key"""
        # Convert bytes to hex string
        private_key_hex = private_key_bytes.hex()
        
        # Derive address twice
        address1 = derive_ethereum_address(private_key_hex)
        address2 = derive_ethereum_address(private_key_hex)
        
        # Should be identical
        assert address1 == address2

    @given(st.binary(min_size=32, max_size=32))
    @settings(max_examples=50)
    def test_derived_address_format(self, private_key_bytes):
        """Test that derived addresses have correct format"""
        private_key_hex = private_key_bytes.hex()
        address = derive_ethereum_address(private_key_hex)
        
        # Address should be 42 characters (0x + 40 hex chars)
        assert len(address) == 42
        assert address.startswith('0x')
        assert all(c in '0123456789abcdef' for c in address[2:])

    @given(st.binary(min_size=32, max_size=32), st.binary(min_size=32, max_size=32))
    @settings(max_examples=50)
    def test_sign_verify_roundtrip(self, private_key_bytes, message_bytes):
        """Test that signing and verification are consistent"""
        private_key_hex = private_key_bytes.hex()
        message_hash = message_bytes.hex()
        
        # Sign message
        signature = sign_transaction_hash(message_hash, private_key_hex)
        
        # Derive address from private key
        address = derive_ethereum_address(private_key_hex)
        
        # Verify signature
        assert verify_signature(message_hash, signature, address)

    @given(st.text(min_size=8, max_size=64), st.text(min_size=8, max_size=64))
    @settings(max_examples=50)
    def test_encrypt_decrypt_roundtrip(self, password, private_key):
        """Test that encryption and decryption are reversible"""
        # Ensure private key is valid hex
        private_key_hex = private_key.encode('utf-8').hex()[:64].ljust(64, '0')
        
        # Encrypt
        encrypted = encrypt_private_key(private_key_hex, password)
        
        # Decrypt
        decrypted = decrypt_private_key(encrypted, password)
        
        # Should match original
        assert decrypted == private_key_hex

    @given(st.binary(min_size=1, max_size=1024))
    @settings(max_examples=50)
    def test_keccak256_deterministic(self, data):
        """Test that Keccak-256 hashing is deterministic"""
        hash1 = keccak256_hash(data.hex())
        hash2 = keccak256_hash(data.hex())
        
        assert hash1 == hash2

    @given(st.binary(min_size=1, max_size=1024))
    @settings(max_examples=50)
    def test_sha256_deterministic(self, data):
        """Test that SHA-256 hashing is deterministic"""
        hash1 = sha256_hash(data.hex())
        hash2 = sha256_hash(data.hex())
        
        assert hash1 == hash2

    @given(st.integers(min_value=16, max_value=128))
    @settings(max_examples=50)
    def test_random_bytes_length(self, length):
        """Test that random byte generation produces correct length"""
        random_bytes = generate_secure_random_bytes(length)
        
        # Should be 2*length hex characters
        assert len(random_bytes) == length * 2

    @given(st.integers(min_value=16, max_value=128))
    @settings(max_examples=50)
    def test_random_bytes_uniqueness(self, length):
        """Test that random byte generation produces unique values"""
        random_bytes1 = generate_secure_random_bytes(length)
        random_bytes2 = generate_secure_random_bytes(length)
        
        # Should be different (extremely unlikely to be same)
        assert random_bytes1 != random_bytes2

    @given(st.binary(min_size=32, max_size=32))
    @settings(max_examples=50)
    def test_address_validation(self, private_key_bytes):
        """Test that derived addresses pass validation"""
        private_key_hex = private_key_bytes.hex()
        address = derive_ethereum_address(private_key_hex)
        
        assert validate_ethereum_address(address)

    @given(st.text(alphabet='0123456789abcdef', min_size=40, max_size=40))
    @settings(max_examples=50)
    def test_address_validation_format(self, hex_string):
        """Test address validation with various formats"""
        # Valid format with 0x prefix
        valid_address = '0x' + hex_string
        assert validate_ethereum_address(valid_address)
        
        # Invalid format without 0x prefix
        invalid_address = hex_string
        assert not validate_ethereum_address(invalid_address)

    @settings(max_examples=10)
    def test_private_key_generation_format(self):
        """Test that generated private keys have correct format"""
        private_key = generate_ethereum_private_key()
        
        # Should be 66 characters (0x + 64 hex chars)
        assert len(private_key) == 66
        assert private_key.startswith('0x')
        assert all(c in '0123456789abcdef' for c in private_key[2:])
