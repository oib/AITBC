"""Property-based tests for transaction signing/verification (hypothesis).

These tests use Hypothesis to generate arbitrary valid transactions and
verify cryptographic invariants that must hold for ALL inputs:

1. Round-trip: sign → verify == True (always)
2. Tamper detection: mutating any signed field → verify == False (always)
3. Canonical message determinism: same input → same bytes (always)
4. Signature format: 65 bytes, v in {0, 1} (always)

Run: pytest tests/unit/test_property_crypto.py -q -o addopts=""
"""

from __future__ import annotations

import json

from eth_keys import keys
from eth_utils import keccak
from hypothesis import HealthCheck, given, settings, strategies as st

from aitbc.crypto.transaction_service import _canonical_signing_message

# Deterministic test key
PK_HEX = "4c0883a69102937d6231471b5dbb6204fe512961708279e1c1d4f0e0a1d9d2e3"
PK = keys.PrivateKey(bytes.fromhex(PK_HEX))
ADDR = PK.public_key.to_checksum_address()

# Strategies for valid transaction fields
st_amount = st.integers(min_value=0, max_value=2**64 - 1)
st_fee = st.integers(min_value=0, max_value=2**32 - 1)
st_nonce = st.integers(min_value=0, max_value=2**32 - 1)
st_chain_id = st.sampled_from(["ait-hub", "ait-island1", "ait-island2", "test-chain"])
st_address = st.builds(
    lambda b: "0x" + b.hex(),
    st.binary(min_size=20, max_size=20),
)
st_payload = st.fixed_dictionaries(
    {},
    optional={
        "amount": st_amount,
        "data": st.text(max_size=100),
        "nonce": st_nonce,
    },
)


@st.composite
def st_tx(draw: st.DrawFn) -> dict:
    """Generate a valid transaction dict matching the signer's output shape."""
    amount = draw(st_amount)
    return {
        "from": ADDR,
        "to": draw(st_address),
        "amount": amount,
        "fee": draw(st_fee),
        "nonce": draw(st_nonce),
        "payload": {"amount": amount} | draw(st_payload),
        "type": "TRANSFER",
        "chain_id": draw(st_chain_id),
    }


def _sign(tx: dict) -> str:
    """Sign a tx with the test key, returning hex signature."""
    msg_hash = keccak(_canonical_signing_message(tx))
    sig = PK.sign_msg_hash(msg_hash)
    return sig.to_bytes().hex()


def _verify(tx: dict, signature: str, sender: str) -> bool:
    """Replicate the node verifier's logic (strips signature, canonical JSON)."""
    from aitbc_chain.rpc.utils import verify_transaction_signature

    return verify_transaction_signature(tx, signature, sender)


# --- Properties ---


class TestCanonicalMessage:
    """Properties of _canonical_signing_message."""

    @given(tx=st_tx())
    @settings(max_examples=200, deadline=None)
    def test_deterministic(self, tx: dict) -> None:
        """Same input always produces the same bytes."""
        msg1 = _canonical_signing_message(tx)
        msg2 = _canonical_signing_message(tx.copy())
        assert msg1 == msg2

    @given(tx=st_tx())
    @settings(max_examples=200, deadline=None)
    def test_excludes_signature(self, tx: dict) -> None:
        """The signature field must not be part of the signed message."""
        tx_with_sig = {**tx, "signature": "deadbeef" * 16}
        msg_with = _canonical_signing_message(tx_with_sig)
        msg_without = _canonical_signing_message(tx)
        assert msg_with == msg_without

    @given(tx=st_tx())
    @settings(max_examples=200, deadline=None)
    def test_is_valid_canonical_json(self, tx: dict) -> None:
        """Output must be valid canonical JSON (sorted keys, no spaces)."""
        msg = _canonical_signing_message(tx)
        decoded = json.loads(msg)
        # Re-serialize with canonical settings → must match
        re_encoded = json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode()
        assert msg == re_encoded


class TestSignatureFormat:
    """Properties of the secp256k1 signature output."""

    @given(tx=st_tx())
    @settings(max_examples=200, deadline=None)
    def test_signature_is_65_bytes(self, tx: dict) -> None:
        """Signature must be 65 bytes (r||s||v format)."""
        sig_hex = _sign(tx)
        sig_bytes = bytes.fromhex(sig_hex)
        assert len(sig_bytes) == 65

    @given(tx=st_tx())
    @settings(max_examples=200, deadline=None)
    def test_recovery_id_is_valid(self, tx: dict) -> None:
        """Recovery id (v) must be 0 or 1 for secp256k1."""
        sig_hex = _sign(tx)
        sig_bytes = bytes.fromhex(sig_hex)
        assert sig_bytes[64] in (0, 1)


class TestRoundTrip:
    """Sign → verify round-trip must always succeed."""

    @given(tx=st_tx())
    @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_signed_tx_verifies(self, tx: dict) -> None:
        """A properly signed transaction must pass verification."""
        sig = _sign(tx)
        tx_signed = {**tx, "signature": sig}
        assert _verify(tx_signed, sig, ADDR) is True


class TestTamperDetection:
    """Any mutation of a signed field must fail verification."""

    @given(tx=st_tx(), new_amount=st_amount)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_tamper_amount(self, tx: dict, new_amount: int) -> None:
        """Changing amount after signing must fail verification."""
        if new_amount == tx["amount"]:
            return  # skip if same value
        sig = _sign(tx)
        tampered = {**tx, "amount": new_amount, "signature": sig}
        assert _verify(tampered, sig, ADDR) is False

    @given(tx=st_tx(), new_fee=st_fee)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_tamper_fee(self, tx: dict, new_fee: int) -> None:
        """Changing fee after signing must fail verification."""
        if new_fee == tx["fee"]:
            return
        sig = _sign(tx)
        tampered = {**tx, "fee": new_fee, "signature": sig}
        assert _verify(tampered, sig, ADDR) is False

    @given(tx=st_tx(), new_chain=st_chain_id)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_tamper_chain_id(self, tx: dict, new_chain: str) -> None:
        """Changing chain_id after signing must fail verification (replay protection)."""
        if new_chain == tx["chain_id"]:
            return
        sig = _sign(tx)
        tampered = {**tx, "chain_id": new_chain, "signature": sig}
        assert _verify(tampered, sig, ADDR) is False

    @given(tx=st_tx(), new_to=st_address)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_tamper_recipient(self, tx: dict, new_to: str) -> None:
        """Changing recipient after signing must fail verification."""
        if new_to == tx["to"]:
            return
        sig = _sign(tx)
        tampered = {**tx, "to": new_to, "signature": sig}
        assert _verify(tampered, sig, ADDR) is False

    @given(tx=st_tx(), new_nonce=st_nonce)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_tamper_nonce(self, tx: dict, new_nonce: int) -> None:
        """Changing nonce after signing must fail verification."""
        if new_nonce == tx["nonce"]:
            return
        sig = _sign(tx)
        tampered = {**tx, "nonce": new_nonce, "signature": sig}
        assert _verify(tampered, sig, ADDR) is False


class TestInvalidSignatures:
    """Malformed signatures must be rejected, never crash."""

    @given(tx=st_tx())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_empty_signature_rejected(self, tx: dict) -> None:
        """Empty signature string must return False, not crash."""
        assert _verify(tx, "", ADDR) is False

    @given(tx=st_tx())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_wrong_length_rejected(self, tx: dict) -> None:
        """Non-65-byte signatures must be rejected."""
        assert _verify(tx, "deadbeef", ADDR) is False

    @given(tx=st_tx(), wrong_addr=st_address)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_wrong_sender_rejected(self, tx: dict, wrong_addr: str) -> None:
        """A valid signature for ADDR must not verify against a different sender."""
        if wrong_addr.lower() == ADDR.lower():
            return
        sig = _sign(tx)
        tx_signed = {**tx, "signature": sig}
        assert _verify(tx_signed, sig, wrong_addr) is False
