"""V23-01…V23-05: one signature-recovery implementation, and a guard against a tenth.

The audit found nine independent ECDSA recovery implementations. Eight constructed
``eth_keys.Signature(sig_bytes)`` directly, which requires a recovery id of 0 or 1 —
while every standard Ethereum signer emits 27 or 28. ``eth_keys`` raised
``BadSignature``, a broad ``except Exception`` turned it into "signature invalid", and
correctly signed messages were rejected across the RPC path, the bridge validator,
dispute evidence and consensus.

Only ``poa.py`` normalised, because v0.22 fixed one call site and did not look for the
others. V23-05's point is that fixing them one at a time is what produced nine copies,
so the grep assertion below matters more than any of the individual round trips.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from eth_account import Account
from eth_utils import keccak

from aitbc.crypto.signature_recovery import (
    SignatureMalformed,
    normalize_signature,
    recover_address,
    verify_signature,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_MODULE = "aitbc/crypto/signature_recovery.py"

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)


def _sign(digest: bytes) -> str:
    return "0x" + ACCOUNT.unsafe_sign_hash(digest).signature.hex()


class TestOnlyOneImplementation:
    """V23-05: the defect was the duplication, not any single copy of it."""

    def test_no_other_module_constructs_a_signature(self):
        result = subprocess.run(
            ["git", "grep", "-n", "keys.Signature(", "--", "aitbc/", "apps/", "cli/", "packages/"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        # git grep exits 1 when there are no matches, which is a legitimate outcome here.
        files = set()
        for line in result.stdout.splitlines():
            if not line or "/tests/" in line:
                continue
            path, _, rest = line.partition(":")
            _lineno, _, source = rest.partition(":")
            # Prose about the call is not the call. transaction_service.py carries a comment
            # explaining why its signatures are shaped the way they are, and flagging that
            # as a tenth implementation would teach people to delete the explanation.
            if source.strip().startswith("#"):
                continue
            files.add(path)

        assert files <= {CANONICAL_MODULE}, (
            "ECDSA signature recovery must go through aitbc/crypto/signature_recovery.py. "
            f"Found keys.Signature( in: {sorted(files - {CANONICAL_MODULE})}. "
            "Nine copies of this call is what V23-01..V23-05 were about; call "
            "recover_address() or verify_signature() instead."
        )


class TestRoundTrip:
    """The only assertion that matters: sign with a real signer, verify with our path."""

    def test_eth_account_signature_verifies(self):
        digest = keccak(b"a message")
        assert verify_signature(digest, _sign(digest), ACCOUNT.address) is True

    def test_v_is_27_or_28_from_a_standard_signer(self):
        """Pins the premise of the whole finding rather than assuming it."""
        raw = ACCOUNT.unsafe_sign_hash(keccak(b"x")).signature
        assert raw[64] in (27, 28)

    def test_canonical_json_request_round_trip(self):
        """The shape used by verify_request_signature and recover_signer."""
        message = {"action": "bridge", "amount": "100"}
        digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())

        assert recover_address(digest, _sign(digest)).lower() == ACCOUNT.address.lower()

    def test_block_hash_round_trip(self):
        """The shape used by verify_block_signature: a sha256 hash signed directly."""
        digest = hashlib.sha256(b"block").digest()

        assert verify_signature(digest, _sign(digest), ACCOUNT.address) is True

    def test_wrong_address_is_rejected(self):
        digest = keccak(b"a message")
        other = Account.from_key("0x" + "43" * 32)

        assert verify_signature(digest, _sign(digest), other.address) is False

    def test_tampered_message_is_rejected(self):
        signature = _sign(keccak(b"original"))

        assert verify_signature(keccak(b"tampered"), signature, ACCOUNT.address) is False

    def test_address_comparison_is_case_insensitive(self):
        digest = keccak(b"a message")

        assert verify_signature(digest, _sign(digest), ACCOUNT.address.lower()) is True


class TestRecoveryIdNormalisation:
    def test_27_and_28_are_accepted(self):
        for v in (27, 28):
            sig = bytes(64) + bytes([v])
            assert normalize_signature(sig)[64] == v - 27

    def test_0_and_1_pass_through(self):
        for v in (0, 1):
            sig = bytes(64) + bytes([v])
            assert normalize_signature(sig)[64] == v

    def test_hex_with_and_without_prefix_agree(self):
        raw = bytes(range(64)) + bytes([27])
        assert normalize_signature(raw.hex()) == normalize_signature("0x" + raw.hex())

    @pytest.mark.parametrize("v", [2, 26, 29, 35, 255])
    def test_other_recovery_ids_are_malformed(self, v):
        with pytest.raises(SignatureMalformed, match="recovery id"):
            normalize_signature(bytes(64) + bytes([v]))


class TestMalformedIsDistinguishable:
    """V23-04: 'could not parse' and 'did not verify' must not be the same answer."""

    def test_short_signature_raises_rather_than_returning_false(self):
        with pytest.raises(SignatureMalformed, match="65 bytes"):
            verify_signature(keccak(b"m"), "0xdeadbeef", ACCOUNT.address)

    def test_non_hex_raises(self):
        with pytest.raises(SignatureMalformed, match="not valid hex"):
            normalize_signature("zz" * 65)

    def test_a_failed_check_returns_false_and_does_not_raise(self):
        """The contrast that gives the exception its meaning."""
        digest = keccak(b"a message")
        other = Account.from_key("0x" + "44" * 32)

        assert verify_signature(digest, _sign(digest), other.address) is False

    def test_empty_signature_is_false_not_an_error(self):
        """An absent signature is a normal 'no' — callers pass it constantly."""
        assert verify_signature(keccak(b"m"), "", ACCOUNT.address) is False


class TestCallSitesAcceptStandardSignatures:
    """The eight sites the audit named, each exercised through its own entry point."""

    def test_recover_signer(self):
        from aitbc.crypto.crypto import recover_signer

        message = {"action": "bridge", "amount": "100"}
        digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())

        assert recover_signer(message, _sign(digest)).lower() == ACCOUNT.address.lower()

    def test_verify_consensus_message(self):
        from aitbc.crypto.consensus_signing import verify_consensus_message

        message = {"type": "prepare", "view": 1}
        digest = keccak(json.dumps(message, sort_keys=True, separators=(",", ":")).encode())

        assert verify_consensus_message(message, _sign(digest), ACCOUNT.address) is True

    def test_verify_block_signature(self):
        from aitbc.crypto.consensus_signing import verify_block_signature

        block_hash = hashlib.sha256(b"block").hexdigest()
        signature = _sign(bytes.fromhex(block_hash))

        assert verify_block_signature(block_hash, signature, ACCOUNT.address) is True

    def test_sign_and_verify_block_hash_round_trip(self):
        """V23-02's repro: this repo's own signer against this repo's own verifier."""
        from aitbc.crypto.consensus_signing import sign_block_hash, verify_block_signature

        block_hash = "0x" + hashlib.sha256(b"blk").hexdigest()
        signature = sign_block_hash(block_hash, PRIVATE_KEY)

        assert verify_block_signature(block_hash, signature, ACCOUNT.address) is True
