"""
Crypto Utils Tests
Tests for cryptographic utility functions
"""

import pytest


class TestCreateSignatureChallenge:
    """Test create_signature_challenge function"""

    def test_create_signature_challenge(self):
        """Test creating a signature challenge"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge

        tx_data = {"tx_id": "tx123", "to": "0xabc123", "amount": 100, "timestamp": 1234567890}
        nonce = "nonce123"

        result = create_signature_challenge(tx_data, nonce)

        assert result.startswith("AITBC_MULTISIG_CHALLENGE:")
        assert len(result) > len("AITBC_MULTISIG_CHALLENGE:")

    def test_create_signature_challenge_deterministic(self):
        """Test that challenge is deterministic for same inputs"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge

        tx_data = {"tx_id": "tx123", "to": "0xabc123", "amount": 100, "timestamp": 1234567890}
        nonce = "nonce123"

        result1 = create_signature_challenge(tx_data, nonce)
        result2 = create_signature_challenge(tx_data, nonce)

        assert result1 == result2

    def test_create_signature_challenge_different_inputs(self):
        """Test that different inputs produce different challenges"""
        from aitbc_cli.utils.crypto_utils import create_signature_challenge

        tx_data1 = {"tx_id": "tx123", "to": "0xabc123", "amount": 100, "timestamp": 1234567890}
        tx_data2 = {"tx_id": "tx456", "to": "0xabc123", "amount": 100, "timestamp": 1234567890}
        nonce = "nonce123"

        result1 = create_signature_challenge(tx_data1, nonce)
        result2 = create_signature_challenge(tx_data2, nonce)

        assert result1 != result2


class TestVerifySignature:
    """Test verify_signature function"""

    def test_verify_signature_invalid_signature_format(self):
        """Test verifying with invalid signature format"""
        from aitbc_cli.utils.crypto_utils import verify_signature

        challenge = "test_challenge"
        invalid_signature = "not_a_hex_signature"
        signer_address = "0xabc123"

        result = verify_signature(challenge, invalid_signature, signer_address)

        assert result is False

    def test_verify_signature_empty_signature(self):
        """Test verifying with empty signature"""
        from aitbc_cli.utils.crypto_utils import verify_signature

        challenge = "test_challenge"
        empty_signature = ""
        signer_address = "0xabc123"

        result = verify_signature(challenge, empty_signature, signer_address)

        assert result is False


class TestSignChallenge:
    """Test sign_challenge function"""

    def test_sign_challenge_invalid_key(self):
        """Test signing with invalid private key"""
        from aitbc_cli.utils.crypto_utils import sign_challenge

        challenge = "test_challenge"
        invalid_key = "invalid_key"

        # Should raise ValueError for invalid key
        with pytest.raises(ValueError):
            sign_challenge(challenge, invalid_key)

    def test_sign_challenge_empty_key(self):
        """Test signing with empty private key"""
        from aitbc_cli.utils.crypto_utils import sign_challenge

        challenge = "test_challenge"
        empty_key = ""

        # Should raise ValueError for empty key
        with pytest.raises(ValueError):
            sign_challenge(challenge, empty_key)


def _keypair(seed_hex: str) -> tuple[str, str]:
    """Return (private_key_hex, checksum_address) for a fixed test key."""
    from eth_keys import keys

    pk = keys.PrivateKey(bytes.fromhex(seed_hex))
    return seed_hex, pk.public_key.to_checksum_address()


_KEY1, ADDR1 = _keypair("11" * 32)
_KEY2, ADDR2 = _keypair("22" * 32)
_KEY3, ADDR3 = _keypair("33" * 32)


class TestSignVerifyRoundTrip:
    """AUDIT-CRYPTO-UTILS-SIGN-VERIFY-1: sign_challenge/verify_signature must
    actually round-trip — the old code called eth_account APIs that do not
    exist, so every signature failed."""

    def test_sign_then_verify_round_trip(self):
        from aitbc_cli.utils.crypto_utils import sign_challenge, verify_signature

        challenge = "AITBC_MULTISIG_CHALLENGE:deadbeef"
        signature = sign_challenge(challenge, _KEY1)

        assert verify_signature(challenge, signature, ADDR1) is True

    def test_verify_rejects_different_signer(self):
        from aitbc_cli.utils.crypto_utils import sign_challenge, verify_signature

        challenge = "AITBC_MULTISIG_CHALLENGE:cafebabe"
        signature = sign_challenge(challenge, _KEY1)

        assert verify_signature(challenge, signature, ADDR2) is False

    def test_verify_rejects_tampered_challenge(self):
        from aitbc_cli.utils.crypto_utils import sign_challenge, verify_signature

        signature = sign_challenge("challenge-a", _KEY1)

        assert verify_signature("challenge-b", signature, ADDR1) is False


class TestValidateMultisigTransaction:
    """Amount must be a positive finite number — Infinity/1e400 used to pass."""

    def _tx(self, amount) -> dict:
        return {
            "tx_id": "tx1",
            "to": ADDR1,
            "amount": amount,
            "timestamp": 1234567890,
            "nonce": "n1",
        }

    @pytest.mark.parametrize("amount", ["Infinity", float("inf"), 1e400, float("nan"), 0, -5])
    def test_non_finite_or_nonpositive_amounts_rejected(self, amount):
        from aitbc_cli.utils.crypto_utils import validate_multisig_transaction

        valid, error = validate_multisig_transaction(self._tx(amount))

        assert valid is False
        assert error

    def test_positive_finite_amount_accepted(self):
        from aitbc_cli.utils.crypto_utils import validate_multisig_transaction

        valid, _ = validate_multisig_transaction(self._tx("12.5"))

        assert valid is True


class TestMultisigSignatureRecording:
    """Verified signatures are stored per signer: duplicates rejected and the
    reply reports progress against the required-signer threshold."""

    def _manager(self, tmp_path):
        from aitbc_cli.utils.crypto_utils import MultisigSecurityManager

        return MultisigSecurityManager(store_path=tmp_path / "challenges.json")

    def _request(self, mgr):
        tx_data = {
            "tx_id": "tx-multi",
            "to": ADDR3,
            "amount": "10",
            "timestamp": 1234567890,
            "nonce": "n-multi",
            "required_signers": [ADDR1, ADDR2],
        }
        return mgr.create_signing_request(tx_data, "wallet-1")

    def test_duplicate_signer_rejected_and_threshold_counted(self, tmp_path):
        from aitbc_cli.utils.crypto_utils import sign_challenge

        mgr = self._manager(tmp_path)
        req = self._request(mgr)
        challenge = req["challenge"]

        sig1 = sign_challenge(challenge, _KEY1)
        ok, msg = mgr.verify_and_add_signature("tx-multi", sig1, ADDR1)
        assert ok is True
        assert "1/2" in msg

        # Same signer replaying the same signature must not count twice.
        ok, msg = mgr.verify_and_add_signature("tx-multi", sig1, ADDR1)
        assert ok is False
        assert "already signed" in msg

        sig2 = sign_challenge(challenge, _KEY2)
        ok, msg = mgr.verify_and_add_signature("tx-multi", sig2, ADDR2)
        assert ok is True
        assert "threshold reached" in msg
        assert "2/2" in msg

    def test_unauthorized_signer_rejected(self, tmp_path):
        from aitbc_cli.utils.crypto_utils import sign_challenge

        mgr = self._manager(tmp_path)
        req = self._request(mgr)
        sig3 = sign_challenge(req["challenge"], _KEY3)

        ok, msg = mgr.verify_and_add_signature("tx-multi", sig3, ADDR3)
        assert ok is False
        assert "not authorized" in msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
