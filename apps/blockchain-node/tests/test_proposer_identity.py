"""A node must prove it can sign as the identity it declares before it produces anything.

The deployed hub did neither check and did both harms: it signed 12,353 blocks as
`ait1db5247d0…` with a key controlling `0xFe2d63FE…`, then appended block 105,627 unsigned.
Nothing raised — the keystore matched files on the `address` they declared rather than the
address their key derives to, and a failed key load logged a warning and continued.

Every validating follower then stalls at the first bad block permanently, and the chain
commits to it. A refused start is cheap; an unverifiable range in the middle of a chain is
not.
"""

from __future__ import annotations

import json

import pytest
from eth_account import Account

from aitbc_chain.main import _load_private_key_from_keystore
from aitbc_chain.proposer_identity import address_of, assert_can_sign


def _legacy(address: str) -> str:
    """The chain's own spelling of an 0x address."""
    return "ait1" + address.removeprefix("0x").lower()


def _write_keystore(directory, address: str, private_key: str) -> None:
    (directory / "proposer.json").write_text(json.dumps({"address": address, "private_key": private_key}))


def test_address_of_returns_what_the_key_controls() -> None:
    account = Account.create()
    assert address_of(account.key.hex()).lower() == account.address.lower()


def test_a_matching_key_passes() -> None:
    account = Account.create()
    assert_can_sign(account.address, account.key.hex())
    # The chain writes proposers in the legacy spelling; that must still verify (V23-54).
    assert_can_sign(_legacy(account.address), account.key.hex())


def test_a_key_for_a_different_address_is_refused() -> None:
    """The exact hub failure: signing as the treasury with the block-signing key."""
    declared, actual = Account.create(), Account.create()

    with pytest.raises(RuntimeError) as excinfo:
        assert_can_sign(_legacy(declared.address), actual.key.hex())

    message = str(excinfo.value)
    assert actual.address in message, "the error must name the key that actually signed"
    assert _legacy(declared.address) in message


def test_no_key_at_all_is_refused() -> None:
    """Block 105,627 was appended unsigned because this path only logged a warning."""
    account = Account.create()

    with pytest.raises(RuntimeError, match="no usable signing key"):
        assert_can_sign(account.address, None)


def test_an_empty_proposer_id_is_refused() -> None:
    with pytest.raises(RuntimeError, match="PROPOSER_ID is empty"):
        assert_can_sign("", Account.create().key.hex())


def test_the_keystore_rejects_a_mislabelled_file(tmp_path) -> None:
    """A file may not vouch for itself: the declared address is the thing that was wrong."""
    declared, actual = Account.create(), Account.create()
    _write_keystore(tmp_path, _legacy(declared.address), actual.key.hex())

    loaded = _load_private_key_from_keystore(tmp_path, "unused", target_address=_legacy(declared.address))

    assert loaded is None, "a key that does not derive to its declared address must not be used"


def test_the_keystore_accepts_a_correctly_labelled_file(tmp_path) -> None:
    account = Account.create()
    _write_keystore(tmp_path, _legacy(account.address), account.key.hex())

    loaded = _load_private_key_from_keystore(tmp_path, "unused", target_address=_legacy(account.address))

    assert loaded is not None
    assert address_of(loaded.hex()).lower() == account.address.lower()


def test_the_keystore_matches_across_address_spellings(tmp_path) -> None:
    """PROPOSER_ID and the keystore may spell the same address differently."""
    account = Account.create()
    _write_keystore(tmp_path, _legacy(account.address), account.key.hex())

    assert _load_private_key_from_keystore(tmp_path, "unused", target_address=account.address) is not None
