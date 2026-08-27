"""The transfer built by ``mint-ait`` must satisfy the endpoint that receives it.

``/rpc/transactions/marketplace`` has rejected unsigned transactions since v0.10.13
(`80268e892`, 2026-07-14) with `403 Signature required`. The CLI kept sending a payload with
no signature field, so the command could not have worked for the four weeks after that — and
nothing failed at build time to say so, because the mismatch only exists across the wire.

So this test asserts against the server's real verifier rather than a copy of the format.
Canonical JSON is easy to almost match: a different key order or a space after a separator
yields a different keccak hash and a 403 that says nothing about which of the two sides
drifted.
"""

from __future__ import annotations

from eth_account import Account

pass

from aitbc_chain.rpc.utils import verify_transaction_signature  # noqa: E402

from aitbc_cli.commands.market.exchange import _sign_transaction  # noqa: E402

RECIPIENT = "0xC10F0E4fC10f0e4FC10f0e4fC10F0E4FC10F0e4f"


def _payload(sender: str) -> dict:
    return {
        "from": sender,
        "to": RECIPIENT,
        "value": "100000",
        "nonce": 7,
        "gas_limit": 21000,
        "gas_price": "1",
        "type": "TRANSFER",
        "chain_id": "ait-hub.aitbc.bubuit.net",
    }


def test_the_server_accepts_what_the_cli_signs() -> None:
    signer = Account.create()
    sender = signer.address

    tx = _payload(sender)
    tx["signature"] = _sign_transaction(tx, signer.key.hex())

    assert verify_transaction_signature(tx, tx["signature"], sender) is True


def test_a_signature_from_another_key_is_rejected() -> None:
    signer, impostor = Account.create(), Account.create()
    sender = signer.address

    tx = _payload(sender)
    tx["signature"] = _sign_transaction(tx, impostor.key.hex())

    assert verify_transaction_signature(tx, tx["signature"], sender) is False


def test_tampering_with_a_field_invalidates_the_signature() -> None:
    """The signature must cover the amount, not just the sender."""
    signer = Account.create()
    sender = signer.address

    tx = _payload(sender)
    tx["signature"] = _sign_transaction(tx, signer.key.hex())
    tx["value"] = "999999999"

    assert verify_transaction_signature(tx, tx["signature"], sender) is False


def test_the_signature_field_is_excluded_from_the_signed_bytes() -> None:
    """Both sides drop it before hashing; if only one did, nothing would ever verify."""
    signer = Account.create()
    tx = _payload(signer.address)

    without = _sign_transaction(tx, signer.key.hex())
    with_junk = _sign_transaction({**tx, "signature": "0xdeadbeef"}, signer.key.hex())

    assert without == with_junk
