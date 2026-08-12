"""V23-54: a block whose proposer is written in the legacy spelling must still verify.

Recovery returns ``0x`` + 40 hex. The chain writes proposers as ``ait1`` + the same 40 hex:
``validate_address`` accepts that spelling, ``cli/aitbc_cli/utils/crypto_utils.py`` strips it
to the ``0x`` body, and every block the deployed hub has ever produced declares its proposer
that way. ``verify_signature`` compared the two as plain strings, so the prefix alone made
every legacy-addressed block fail verification regardless of which key signed it.

That stayed hidden behind V23-51 and V23-52. While the signature was never transmitted, no
block reached the comparison at all; once it was, the hub happened to be signing with a key
that genuinely did not match, so the rejection looked fully explained. Only after the hub was
repointed at its real key did the remaining failure isolate to the prefix — the recovered and
declared addresses agreed on all forty hex characters and compared unequal.

The stripping is deliberately narrow: only when what follows the prefix is exactly 40 hex
characters, which is one-to-one with the ``0x`` body and cannot merge two different addresses.
"""

from __future__ import annotations

import hashlib

import pytest
from eth_account import Account

from aitbc.crypto.consensus_signing import sign_block_hash, verify_block_signature
from aitbc.crypto.signature_recovery import canonical_address

BLOCK_HASH = "0x" + hashlib.sha256(b"v23-54").hexdigest()


def _legacy(address: str, prefix: str = "ait1") -> str:
    """The chain's spelling of an 0x address: prefix + the same 40 hex, lowercased."""
    return prefix + address.removeprefix("0x").lower()


@pytest.mark.parametrize("prefix", ["ait1", "aitbc1"])
def test_a_block_declaring_the_legacy_proposer_spelling_verifies(prefix: str) -> None:
    signer = Account.create()
    signature = sign_block_hash(BLOCK_HASH, signer.key.hex())

    assert verify_block_signature(BLOCK_HASH, signature, signer.address) is True
    assert verify_block_signature(BLOCK_HASH, signature, _legacy(signer.address, prefix)) is True


def test_the_legacy_spelling_of_a_different_key_still_fails() -> None:
    """Normalising the prefix must not make the check accept anything it should not."""
    signer, impostor = Account.create(), Account.create()
    signature = sign_block_hash(BLOCK_HASH, signer.key.hex())

    assert verify_block_signature(BLOCK_HASH, signature, _legacy(impostor.address)) is False


def test_canonical_address_is_one_to_one_on_the_body() -> None:
    address = Account.create().address
    assert canonical_address(_legacy(address)) == address.lower()
    assert canonical_address(_legacy(address, "aitbc1")) == address.lower()
    assert canonical_address(address) == address.lower()
    # Checksummed and lowercase are the same address; two different bodies are not.
    assert canonical_address(address.upper().replace("0X", "0x")) == canonical_address(address)
    assert canonical_address(_legacy(address)) != canonical_address(_legacy(Account.create().address))


def test_a_prefix_followed_by_something_that_is_not_forty_hex_is_left_alone() -> None:
    """Real bech32 payloads are longer and not hex — stripping those would be a guess."""
    for address in ("ait1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "ait1short", "ait1" + "z" * 40):
        assert canonical_address(address) == address.lower()
        assert not canonical_address(address).startswith("0x")
