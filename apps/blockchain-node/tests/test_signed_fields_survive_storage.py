"""A signature covers bytes, so the bytes have to come back out unchanged (V23-65).

`EvmAddress` (``AccountAddress``) normalises every valid `0x…` address to its EIP-55
form on the way into the database and on the way out. For `Account.address` that is
exactly right: it is a lookup key, nothing signs it, and normalising it is what closed
V23-63.

`Transaction.sender` and `Transaction.recipient` are not lookup keys. They are `from` and
`to` in the message the client signed, and the node reconstructs that message from them to
verify it (`rpc/utils.verify_transaction_signature` → `json.dumps` of the transaction
fields). Rewriting either one changes the message, and a changed message does not recover
to the signer.

The node accepts a transaction signed with any `0x` spelling — `verify_signature` compares
the recovered address canonically (EIP-55), so hex-form clients verify fine on submission.
While storage rewrites both fields for accounts, `Transaction.sender`/`recipient` store
verbatim; the transaction a peer is served still verifies against the signature stored with
it. Lookups canonicalise the value they search *for* instead of the value they store — see
`evm_address_spellings` (V23-65).
"""

from __future__ import annotations

import json

import pytest
from sqlmodel import Session, create_engine, select

from aitbc.crypto.signature_recovery import canonical_address

from aitbc_chain.metadata import chain_metadata

from aitbc_chain.base_models import Transaction, evm_address_spellings
from aitbc_chain.rpc.utils import verify_transaction_signature

eth_keys = pytest.importorskip("eth_keys", reason="secp256k1 signing not available")

CHAIN_ID = "ait-test"
RECIPIENT_BODY = "c1" * 20
CANONICAL_RECIPIENT = canonical_address(f"0x{RECIPIENT_BODY}")


def _signed_transaction(to: str | None = None) -> tuple[dict, str, str]:
    """A transfer signed the way a hex-form client signs it, which the node accepts."""
    from eth_keys import keys
    from eth_utils import keccak

    private_key = keys.PrivateKey(bytes.fromhex("11" * 32))
    sender = str(private_key.public_key.to_checksum_address())
    transaction = {
        "from": sender,
        "to": to or f"0x{RECIPIENT_BODY}",
        "amount": 100,
        "fee": 10,
        "nonce": 0,
        "payload": {"amount": 100},
        "type": "TRANSFER",
        "chain_id": CHAIN_ID,
    }
    message = json.dumps(transaction, sort_keys=True, separators=(",", ":")).encode()
    signature = str(private_key.sign_msg_hash(keccak(message)).to_hex())
    return transaction, signature, sender


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


def _store_and_read(session, transaction: dict, signature: str) -> Transaction:
    session.add(
        Transaction(
            chain_id=CHAIN_ID,
            tx_hash="0x" + "ab" * 32,
            sender=transaction["from"],
            recipient=transaction["to"],
            value=transaction["amount"],
            fee=transaction["fee"],
            nonce=transaction["nonce"],
            payload=transaction["payload"],
            type=transaction["type"],
            signature=signature,
        )
    )
    session.commit()
    stored = session.exec(select(Transaction)).first()
    assert stored is not None
    return stored


def test_the_node_accepts_a_transaction_signed_in_hex_form() -> None:
    """The premise. If this ever fails the rest of the file is moot."""
    transaction, signature, sender = _signed_transaction()

    assert verify_transaction_signature(dict(transaction), signature, sender)


def test_the_addresses_come_back_out_as_they_went_in(session) -> None:
    transaction, signature, _ = _signed_transaction()

    stored = _store_and_read(session, transaction, signature)

    assert stored.sender == transaction["from"]
    assert stored.recipient == transaction["to"]


def test_a_stored_transaction_still_verifies_when_served_to_a_peer(session) -> None:
    """What a syncing follower does, and where it stops.

    The follower rebuilds the signed message from the fields the hub served it. If either
    address was rewritten in storage the message differs from the one that was signed, the
    signature does not recover, and `state_transition` rejects the transaction.
    """
    transaction, signature, _ = _signed_transaction()

    stored = _store_and_read(session, transaction, signature)
    served = {
        "from": stored.sender,
        "to": stored.recipient,
        "amount": stored.value,
        "fee": stored.fee,
        "nonce": stored.nonce,
        "payload": stored.payload,
        "type": stored.type,
        "chain_id": stored.chain_id,
    }

    assert verify_transaction_signature(served, signature, stored.sender)


def test_an_all_canonical_transaction_is_unaffected(session) -> None:
    """An already canonical EIP-55 0x transaction is stored verbatim."""
    transaction, signature, _ = _signed_transaction(to=CANONICAL_RECIPIENT)

    stored = _store_and_read(session, transaction, signature)

    assert stored.sender == transaction["from"]
    assert stored.recipient == transaction["to"]


# --- Lookups, now that the column holds whatever the signer wrote ------------------------


_SPELLINGS = {
    "lowercase": f"0x{RECIPIENT_BODY}",
    "upper-hex": f"0x{RECIPIENT_BODY.upper()}",
    "eip55": CANONICAL_RECIPIENT,
    "0X-prefix": f"0X{RECIPIENT_BODY.upper()}",
}


@pytest.mark.parametrize("stored_as", list(_SPELLINGS))
@pytest.mark.parametrize("searched_as", list(_SPELLINGS))
def test_a_transaction_is_found_by_any_spelling_of_its_address(session, stored_as: str, searched_as: str) -> None:
    """Storing verbatim would reintroduce V23-63 if the search did not widen to match."""
    from sqlmodel import func as sql_func

    written = _SPELLINGS[stored_as]
    searched = _SPELLINGS[searched_as]
    transaction, signature, _ = _signed_transaction()
    transaction["to"] = written
    _store_and_read(session, transaction, signature)

    found = session.exec(
        select(Transaction).where(sql_func.lower(Transaction.recipient).in_(evm_address_spellings(searched)))
    ).first()

    assert found is not None
    assert found.recipient == written


def test_the_search_does_not_widen_to_a_different_account(session) -> None:
    from sqlmodel import func as sql_func

    transaction, signature, _ = _signed_transaction()
    _store_and_read(session, transaction, signature)

    found = session.exec(
        select(Transaction).where(sql_func.lower(Transaction.recipient).in_(evm_address_spellings("0x" + "d4" * 20)))
    ).first()

    assert found is None


def test_a_non_address_value_is_searched_for_as_itself(session) -> None:
    """Proposer ids and aliases share these columns and must not be expanded into spellings."""
    assert evm_address_spellings("hub-coordinator") == ["hub-coordinator"]
    assert evm_address_spellings("genesis") == ["genesis"]
