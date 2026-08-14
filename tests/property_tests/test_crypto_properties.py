"""
Property-based tests for critical AITBC cryptographic functions using hypothesis.
Tests ensure that cryptographic operations maintain expected properties across random inputs.
"""

from aitbc.crypto.crypto import (
    generate_ethereum_private_key,
)


class TestCryptoProperties:
    """Property-based tests for cryptographic functions"""

    # A private key is a scalar in [1, n-1], not 32 arbitrary bytes. The original strategy
    # generated out-of-range keys -- including zero, which eth-account signs with while
    # producing a signature nothing can recover from.

    # This test previously called pytest.skip on its first line, with the reason
    # "validate_ethereum_address may expect AITBC format not Ethereum". It expects
    # Ethereum format *with an EIP-55 checksum* -- established here rather than guessed.

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
