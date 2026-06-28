"""Unit tests for aitbc.crypto.transaction_service (v0.5.16 §A1).

Regression guard: the shared TransactionService must sign transactions with
secp256k1 in a form the blockchain node's verifier accepts. Previously it signed
with ed25519 (64-byte sig), which the Bug 4 signature check rejects outright.

The real node verifier (``aitbc_chain.rpc.utils.verify_transaction_signature``)
and request model are importable here because the repo ``tests/conftest.py`` adds
``apps/blockchain-node/src`` to ``sys.path``.
"""

import pytest
from eth_keys import keys

from aitbc.crypto.transaction_service import _canonical_signing_message

# Deterministic secp256k1 test key and its derived Ethereum address.
PK_HEX = "4c0883a69102937d6231471b5dbb6204fe512961708279e1c1d4f0e0a1d9d2e3"
ADDR = keys.PrivateKey(bytes.fromhex(PK_HEX)).public_key.to_checksum_address()
TO_ADDR = "0x" + "11" * 20


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch):
    """A TransactionService wired to the test key with nonce lookups stubbed."""
    monkeypatch.setenv("GENESIS_PRIVATE_KEY", PK_HEX)
    monkeypatch.setenv("GENESIS_ADDRESS", ADDR)
    monkeypatch.setenv("CHAIN_ID", "ait-hub")
    from aitbc.crypto.transaction_service import TransactionService

    svc = TransactionService()
    monkeypatch.setattr(svc, "get_nonce", lambda _addr: 0)
    return svc


def test_canonical_message_is_pinned_to_node_format() -> None:
    """The signed bytes must match the node verifier's exact serialization."""
    tx = {
        "from": ADDR,
        "to": TO_ADDR,
        "amount": 100,
        "fee": 36,
        "nonce": 0,
        "payload": {"amount": 100},
        "type": "TRANSFER",
        "signature": "ignored",  # excluded from the signed message
        "chain_id": "ait-hub",  # NOW included in the signed message (B6 fix)
    }
    expected = (
        '{"amount":100,"chain_id":"ait-hub","fee":36,"from":"' + ADDR + '","nonce":0,'
        '"payload":{"amount":100},"to":"' + TO_ADDR + '","type":"TRANSFER"}'
    )
    assert _canonical_signing_message(tx) == expected.encode()


def test_signed_transaction_is_accepted_by_real_node_verifier(service) -> None:
    """End-to-end: a TransactionService-signed tx passes the node's Bug 4 check."""
    from aitbc_chain.rpc.transactions import TransactionRequest
    from aitbc_chain.rpc.utils import verify_transaction_signature

    tx = service.generate_signed_transaction(TO_ADDR, 100)
    assert tx is not None

    # secp256k1 r||s||v, 65 bytes, recovery id normalized to {0, 1}
    sig_bytes = bytes.fromhex(tx["signature"])
    assert len(sig_bytes) == 65
    assert sig_bytes[64] in (0, 1)
    assert tx["chain_id"] == "ait-hub"  # present in body for routing

    # Reconstruct exactly what the endpoint feeds the verifier.
    req = TransactionRequest(**tx)
    tx_data_dict = {
        "from": req.sender,
        "to": req.recipient,
        "amount": req.amount,
        "fee": req.fee,
        "nonce": req.nonce,
        "payload": req.payload,
        "type": req.type,
        "chain_id": req.chain_id,
        "signature": req.sig,
    }
    assert verify_transaction_signature(tx_data_dict, req.sig, req.sender) is True


def test_tampered_amount_is_rejected(service) -> None:
    """Mutating a signed field after signing must fail verification."""
    from aitbc_chain.rpc.transactions import TransactionRequest
    from aitbc_chain.rpc.utils import verify_transaction_signature

    tx = service.generate_signed_transaction(TO_ADDR, 100)
    assert tx is not None
    tx["amount"] = 999_999  # tamper

    req = TransactionRequest(**tx)
    tx_data_dict = {
        "from": req.sender,
        "to": req.recipient,
        "amount": req.amount,
        "fee": req.fee,
        "nonce": req.nonce,
        "payload": req.payload,
        "type": req.type,
        "chain_id": req.chain_id,
        "signature": req.sig,
    }
    assert verify_transaction_signature(tx_data_dict, req.sig, req.sender) is False


def test_fails_closed_on_genesis_address_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """If GENESIS_ADDRESS != address derived from the key, return None (don't emit)."""
    monkeypatch.setenv("GENESIS_PRIVATE_KEY", PK_HEX)
    monkeypatch.setenv("GENESIS_ADDRESS", "0x" + "00" * 20)  # wrong address
    monkeypatch.setenv("CHAIN_ID", "ait-hub")
    from aitbc.crypto.transaction_service import TransactionService

    svc = TransactionService()
    monkeypatch.setattr(svc, "get_nonce", lambda _addr: 0)
    assert svc.generate_signed_transaction(TO_ADDR, 100) is None


def test_cross_chain_replay_rejected(service) -> None:
    """A tx signed for chain_id=ait-hub must fail verification when chain_id is swapped."""
    from aitbc_chain.rpc.transactions import TransactionRequest
    from aitbc_chain.rpc.utils import verify_transaction_signature

    tx = service.generate_signed_transaction(TO_ADDR, 100)
    assert tx is not None
    assert tx["chain_id"] == "ait-hub"

    # Swap chain_id to a different chain (replay attempt)
    tx["chain_id"] = "ait-island1"

    req = TransactionRequest(**tx)
    tx_data_dict = {
        "from": req.sender,
        "to": req.recipient,
        "amount": req.amount,
        "fee": req.fee,
        "nonce": req.nonce,
        "payload": req.payload,
        "type": req.type,
        "chain_id": req.chain_id,
        "signature": req.sig,
    }
    # Signature was computed over chain_id="ait-hub", so swapping to "ait-island1"
    # changes the canonical message → recovery must fail.
    assert verify_transaction_signature(tx_data_dict, req.sig, req.sender) is False


def test_returns_none_when_key_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """No genesis key configured → no transaction."""
    monkeypatch.delenv("GENESIS_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("GENESIS_ADDRESS", ADDR)
    from aitbc.crypto.transaction_service import TransactionService

    svc = TransactionService()
    monkeypatch.setattr(svc, "get_nonce", lambda _addr: 0)
    assert svc.generate_signed_transaction(TO_ADDR, 100) is None
