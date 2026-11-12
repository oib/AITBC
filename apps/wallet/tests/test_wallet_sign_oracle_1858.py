"""#1858: /sign must not be a transaction-signing oracle.

Pre-fix ``sign_message`` signed ``keccak256(message)`` — byte-identical to
the ``sign_and_submit_transaction`` digest. An admin-key holder could pass
``message=<canonical tx JSON>`` and receive a signature the node's
``verify_transaction_signature`` accepts for ANY tx payload.

Post-fix the digest is ``keccak256(_MESSAGE_SIGN_DOMAIN + message)``; the
tags make the two domains disjoint, so a /sign output can never verify as
a transaction signature.
"""

import json

import pytest
from eth_keys import keys as eth_keys
from eth_utils import keccak, to_checksum_address

from wallet_app.keystore.persistent_service import PersistentKeystoreService, _MESSAGE_SIGN_DOMAIN

from .conftest import TEST_PASSWORD

pytestmark = pytest.mark.usefixtures("keystore")


def _canonical_tx_json() -> bytes:
    """The exact bytes sign_and_submit_transaction signs for a TRANSFER."""
    tx_data = {
        "from": "0x" + "11" * 20,
        "to": "0x" + "22" * 20,
        "amount": 1,
        "fee": 1,
        "nonce": 0,
        "chain_id": "ait-test-chain",
        "type": "TRANSFER",
        "payload": {"to": "0x" + "22" * 20, "amount": 1},
    }
    return json.dumps(tx_data, sort_keys=True, separators=(",", ":")).encode()


def _recover_address(signature: bytes, digest_preimage: bytes) -> str:
    recovered = eth_keys.Signature(signature).recover_public_key_from_msg_hash(keccak(digest_preimage))
    return to_checksum_address(recovered.to_checksum_address())


def test_sign_output_does_not_verify_as_tx_signature(keystore: PersistentKeystoreService) -> None:
    """The exploit: sign the canonical tx JSON via /sign — the result must
    NOT recover the wallet address under the node's tx digest."""
    secret = bytes(range(1, 33))
    record = keystore.create_wallet("oracle", TEST_PASSWORD, secret=secret)
    tx_json = _canonical_tx_json()

    signature = keystore.sign_message("oracle", TEST_PASSWORD, tx_json)

    # Node-side check, replicated: verify_transaction_signature recovers the
    # sender from keccak(canonical unsigned-tx JSON). The /sign output must
    # recover a DIFFERENT address (or fail) — never the wallet's.
    assert _recover_address(signature, tx_json) != record.public_key


def test_sign_output_verifies_under_domain_digest(keystore: PersistentKeystoreService) -> None:
    """Legitimate /sign consumers verify over the domain-separated digest."""
    secret = bytes(range(1, 33))
    record = keystore.create_wallet("oracle2", TEST_PASSWORD, secret=secret)
    message = b"login challenge"

    signature = keystore.sign_message("oracle2", TEST_PASSWORD, message)

    assert _recover_address(signature, _MESSAGE_SIGN_DOMAIN + message) == record.public_key


def test_domain_tag_cannot_prefix_collide_with_tx_json() -> None:
    """Structural pin: tag + message can never equal canonical tx JSON —
    tx JSON always starts with '{', the tag does not."""
    assert not _MESSAGE_SIGN_DOMAIN.startswith(b"{")
    # And tx canonical JSON for any field set starts with '{"'.
    assert _canonical_tx_json().startswith(b'{"')
