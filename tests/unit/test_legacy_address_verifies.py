"""0x secp256k1/EVM address verification for block signatures.

Recovery returns ``0x`` + 40 hex. The chain now stores and verifies only the
canonical EIP-55 ``0x`` form, so a block proposer must be a valid 0x address.
Legacy ``ait1``/``aitbc1`` spellings are no longer accepted.
"""

from __future__ import annotations

import hashlib

from eth_account import Account

from aitbc.crypto.consensus_signing import sign_block_hash, verify_block_signature
from aitbc.crypto.signature_recovery import canonical_address

BLOCK_HASH = "0x" + hashlib.sha256(b"v23-54").hexdigest()


def test_a_block_with_a_valid_0x_proposer_verifies() -> None:
    signer = Account.create()
    signature = sign_block_hash(BLOCK_HASH, signer.key.hex())

    assert verify_block_signature(BLOCK_HASH, signature, signer.address) is True
    assert verify_block_signature(BLOCK_HASH, signature, signer.address.lower()) is True


def test_a_different_key_still_fails() -> None:
    """A signature from a different signer must not verify against the proposer."""
    signer, impostor = Account.create(), Account.create()
    signature = sign_block_hash(BLOCK_HASH, signer.key.hex())

    assert verify_block_signature(BLOCK_HASH, signature, impostor.address) is False


def test_canonical_address_is_one_to_one_on_the_body() -> None:
    address = Account.create().address
    assert canonical_address(address) == address
    assert canonical_address(address.lower()) == address
    assert canonical_address(address.upper().replace("0X", "0x")) == address
    # Two different bodies are not equal; different 0x addresses stay distinct.
    assert canonical_address(address) != canonical_address(Account.create().address)


def test_a_non_address_does_not_verify() -> None:
    """A proposer string that is not a valid 0x address is rejected."""
    signer = Account.create()
    signature = sign_block_hash(BLOCK_HASH, signer.key.hex())

    assert verify_block_signature(BLOCK_HASH, signature, "not-an-address") is False
