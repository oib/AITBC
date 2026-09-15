"""Regression tests: gossip mempool ingest must enforce the signature policy.

The ``transactions`` gossip topics are public-publish by design — any peer that
can reach ``/rpc/gossip/ws`` (or the legacy relay/p2p transports) may inject a
transaction envelope. Before this fix, ``main.process_txs`` and
``p2p_network._handle_inbound_connection`` fed such payloads straight into
``mempool.add`` with no signature check, while the consensus signature check
only fires when a signature is present — so an unsigned TRANSFER naming any
funded sender was mineable, bypassing every REST admission guard.

``gossip_transaction_drop_reason`` mirrors the REST admission contract: signed
transactions must verify against ``from``; the only unsigned shape admitted is
a zero-amount GPU_MARKETPLACE listing action (the route's deliberate V23-90
exemption).
"""

from __future__ import annotations

from typing import Any

from eth_keys import keys

from aitbc_chain.rpc.utils import gossip_transaction_drop_reason, sign_transaction_data

SENDER_KEY = keys.PrivateKey(b"\x33" * 32)
SENDER = SENDER_KEY.public_key.to_checksum_address()
VICTIM = "0x0000000000000000000000000000000000000bad"


def _transfer_tx(**overrides: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": SENDER,
        "to": "0x0000000000000000000000000000000000000eef",
        "amount": 100,
        "fee": 1,
        "nonce": 0,
        "type": "TRANSFER",
        "payload": {},
        "chain_id": "test",
    }
    tx.update(overrides)
    return tx


def _offer_tx(amount: int, action: str = "software_offer") -> dict[str, Any]:
    return {
        "from": SENDER,
        "to": "0x0000000000000000000000000000000000000eef",
        "amount": amount,
        "fee": 0,
        "nonce": 0,
        "type": "GPU_MARKETPLACE",
        "payload": {"action": action, "service_type": "whisper", "price_per_unit": 0},
        "chain_id": "test",
    }


def test_unsigned_transfer_dropped():
    assert gossip_transaction_drop_reason(_transfer_tx()) == "missing_signature"


def test_unsigned_transfer_naming_foreign_sender_dropped():
    """The exact exploit shape: sender the caller does not control."""
    assert gossip_transaction_drop_reason(_transfer_tx(**{"from": VICTIM})) == "missing_signature"


def test_invalid_signature_dropped():
    tx = _transfer_tx(signature="0x" + "00" * 65)
    assert gossip_transaction_drop_reason(tx) == "invalid_signature"


def test_signature_for_other_sender_dropped():
    """A real signature from a different key must not admit the tx."""
    tx = _transfer_tx()
    tx["signature"] = sign_transaction_data(tx, "0x" + "44" * 32)
    assert gossip_transaction_drop_reason(tx) == "invalid_signature"


def test_valid_signed_transfer_admitted():
    tx = _transfer_tx()
    tx["signature"] = sign_transaction_data(tx, "0x" + "33" * 32)
    assert gossip_transaction_drop_reason(tx) is None


def test_valid_signed_transfer_with_value_alias_admitted():
    """Gossip fan-out sends the normalized dict — the extra ``value`` key must
    not break verification of the originally signed field set."""
    tx = _transfer_tx()
    tx["signature"] = sign_transaction_data(tx, "0x" + "33" * 32)
    tx["value"] = tx["amount"]
    assert gossip_transaction_drop_reason(tx) is None


def test_unsigned_zero_amount_offer_admitted():
    """Legit zero-amount listings still propagate unsigned (V23-90)."""
    assert gossip_transaction_drop_reason(_offer_tx(0)) is None
    assert gossip_transaction_drop_reason(_offer_tx(0, action="offer")) is None


def test_unsigned_nonzero_offer_dropped():
    assert gossip_transaction_drop_reason(_offer_tx(10**9)) == "nonzero_unsigned_offer"


def test_unsigned_nonoffer_marketplace_dropped():
    """Non-offer GPU_MARKETPLACE actions (buy, cancel, job) are not exempt."""
    assert gossip_transaction_drop_reason(_offer_tx(0, action="buy")) == "missing_signature"


def test_unsigned_other_types_dropped():
    for tx_type in ("STAKE_LOCK", "ESCROW_LOCK", "BOND_LOCK", "MESSAGE"):
        tx = _transfer_tx(type=tx_type)
        assert gossip_transaction_drop_reason(tx) == "missing_signature", tx_type
