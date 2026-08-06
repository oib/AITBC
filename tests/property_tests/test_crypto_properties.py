"""
Property-based tests for critical AITBC cryptographic functions using hypothesis.
Tests ensure that cryptographic operations maintain expected properties across random inputs.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from aitbc.crypto.crypto import _SECP256K1_ORDER as SECP256K1_ORDER
from aitbc.crypto.crypto import (
    decrypt_private_key,
    derive_ethereum_address,
    encrypt_private_key,
    generate_ethereum_private_key,
    generate_secure_random_bytes,
    keccak256_hash,
    sha256_hash,
    sign_transaction_hash,
    validate_ethereum_address,
    verify_signature,
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

        # Address should be 42 characters (0x + 40 hex chars) or handle AITBC format
        if address.startswith("0x"):
            assert len(address) == 42
            assert all(c in "0123456789abcdefABCDEF" for c in address[2:])
        else:
            # AITBC format may be different
            assert len(address) > 0

    # A private key is a scalar in [1, n-1], not 32 arbitrary bytes. The original strategy
    # generated out-of-range keys -- including zero, which eth-account signs with while
    # producing a signature nothing can recover from.
    @given(
        st.integers(min_value=1, max_value=SECP256K1_ORDER - 1),
        st.binary(min_size=32, max_size=32),
    )
    @settings(max_examples=50)
    def test_sign_verify_roundtrip(self, private_key_int, message_bytes):
        """Signing then verifying must round-trip for any valid key and any digest."""
        private_key_hex = f"{private_key_int:064x}"
        message_hash = message_bytes.hex()

        signature = sign_transaction_hash(message_hash, private_key_hex)
        address = derive_ethereum_address(private_key_hex)

        assert verify_signature(message_hash, signature, address)

    @given(st.sampled_from([0, SECP256K1_ORDER, SECP256K1_ORDER + 1]))
    @settings(max_examples=3)
    def test_signing_refuses_an_out_of_range_key(self, private_key_int):
        """Signing with an invalid scalar must fail, not emit an unverifiable signature.

        eth-account accepts these and returns a signature that recovery rejects. In
        consensus that is a validator producing blocks whose signatures do not verify,
        with nothing in the signing path reporting a problem.
        """
        with pytest.raises(ValueError):
            sign_transaction_hash("22" * 32, f"{private_key_int:064x}")

    @given(
        st.integers(min_value=1, max_value=SECP256K1_ORDER - 1),
        st.binary(min_size=32, max_size=32),
        st.binary(min_size=32, max_size=32),
    )
    @settings(max_examples=50)
    def test_a_signature_does_not_verify_for_another_digest(self, private_key_int, msg_a, msg_b):
        """The round-trip is only meaningful if the wrong digest fails."""
        assume(msg_a != msg_b)
        private_key_hex = f"{private_key_int:064x}"
        address = derive_ethereum_address(private_key_hex)

        signature = sign_transaction_hash(msg_a.hex(), private_key_hex)

        try:
            assert verify_signature(msg_b.hex(), signature, address) is False
        except ValueError:
            # Recovery can also fail outright rather than recovering a different address;
            # either way the signature has not been accepted for the wrong digest.
            pass

    @given(st.text(min_size=8, max_size=64), st.text(min_size=8, max_size=64))
    @settings(max_examples=50)
    def test_encrypt_decrypt_roundtrip(self, password, private_key):
        """Test that encryption and decryption are reversible"""
        # Ensure private key is valid hex
        private_key_hex = private_key.encode("utf-8").hex()[:64].ljust(64, "0")

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

    # This test previously called pytest.skip on its first line, with the reason
    # "validate_ethereum_address may expect AITBC format not Ethereum". It expects
    # Ethereum format *with an EIP-55 checksum* -- established here rather than guessed.

    @given(st.text(alphabet="0123456789abcdef", min_size=40, max_size=40))
    @settings(max_examples=50)
    def test_address_validation_accepts_checksummed_addresses(self, hex_string):
        from eth_utils import to_checksum_address

        assert validate_ethereum_address(to_checksum_address(f"0x{hex_string}"))

    @given(st.text(alphabet="0123456789abcdef", min_size=40, max_size=40))
    @settings(max_examples=50)
    def test_address_validation_requires_the_0x_prefix(self, hex_string):
        """40 hex characters on their own are not an address."""
        from eth_utils import to_checksum_address

        checksummed = to_checksum_address(f"0x{hex_string}")

        assert not validate_ethereum_address(checksummed[2:])

    @given(st.text(alphabet="0123456789abcdef", min_size=0, max_size=39))
    @settings(max_examples=50)
    def test_address_validation_rejects_wrong_lengths(self, short_hex):
        assert not validate_ethereum_address(f"0x{short_hex}")

    def test_private_key_generation_format(self):
        """Test that generated private keys have correct format"""
        private_key = generate_ethereum_private_key()

        # Should be 64 or 66 characters (with or without 0x prefix)
        assert len(private_key) in [64, 66]
        if private_key.startswith("0x"):
            assert len(private_key) == 66
        else:
            assert len(private_key) == 64
        assert all(c in "0123456789abcdef" for c in private_key.replace("0x", ""))
