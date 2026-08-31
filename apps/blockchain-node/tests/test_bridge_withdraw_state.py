"""Tests for BRIDGE_WITHDRAW state transition.

Covers validation and application of the AIT->ETH withdrawal burn:
- successful burn of AIT and increment of sender nonce
- payload must contain a valid 0x Ethereum destination address
- payload with invalid/missing eth_address is rejected
- non-positive amount is rejected
- insufficient balance is rejected
- wrong nonce is rejected
- invalid signature is rejected
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account
from aitbc_chain.database import chain_metadata
from aitbc_chain.state.state_transition import StateTransition


TEST_PRIVATE_KEY = "0x" + "11" * 32
TEST_CHAIN = "ait-test"


def _derive_address(private_key: str) -> str:
    from aitbc.crypto.crypto import derive_ethereum_address

    return derive_ethereum_address(private_key)


def _sign_tx(private_key: str, tx_data: dict) -> str:
    from eth_utils import keccak
    from aitbc.crypto.crypto import sign_transaction_hash

    signable = {k: v for k, v in tx_data.items() if k not in ("signature", "tx_hash")}
    signable.pop("value", None)
    message = json.dumps(signable, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _make_tx(private_key: str, overrides: dict | None = None) -> dict:
    sender = _derive_address(private_key)
    tx_data: dict = {
        "type": "BRIDGE_WITHDRAW",
        "chain_id": TEST_CHAIN,
        "from": sender,
        "to": "0x0000000000000000000000000000000000000000",
        "amount": 1000,
        "value": 1000,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "payload": {
            "eth_address": "0x1234567890123456789012345678901234567890",
            "amount": 1000,
        },
    }
    if overrides:
        tx_data.update(overrides)
        if "payload" in overrides:
            tx_data["payload"].update(overrides["payload"])
    tx_data["value"] = tx_data["amount"]
    tx_data["payload"]["amount"] = tx_data["amount"]
    tx_data["signature"] = _sign_tx(private_key, tx_data)
    return tx_data


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestBridgeWithdrawStateTransition:
    """BRIDGE_WITHDRAW state transition correctness."""

    def test_valid_withdraw_burns_ait_and_increments_nonce(self, session):
        st = StateTransition()
        sender = _derive_address(TEST_PRIVATE_KEY)
        start_balance = 1_000_000

        session.add(
            Account(
                chain_id=TEST_CHAIN,
                address=sender,
                balance=start_balance,
                nonce=0,
            )
        )
        session.commit()

        tx_data = _make_tx(TEST_PRIVATE_KEY, {"amount": 5000, "fee": DEFAULT_TX_FEE_UNITS})

        success, msg = st.apply_transaction(session, TEST_CHAIN, tx_data, "tx_hash_withdraw_1")
        assert success, msg

        account = session.get(Account, (TEST_CHAIN, sender))
        assert account is not None
        assert account.nonce == 1
        assert account.balance == start_balance - 5000 - DEFAULT_TX_FEE_UNITS

    def test_missing_eth_address_rejected(self, session):
        st = StateTransition()
        sender = _derive_address(TEST_PRIVATE_KEY)
        session.add(Account(chain_id=TEST_CHAIN, address=sender, balance=1_000_000, nonce=0))
        session.commit()

        tx_data = _make_tx(TEST_PRIVATE_KEY)
        tx_data["payload"] = {"amount": 1000}  # no eth_address

        success, msg = st.apply_transaction(session, TEST_CHAIN, tx_data, "tx_hash_2")
        assert not success
        assert "eth_address" in msg.lower()

    def test_invalid_eth_address_rejected(self, session):
        st = StateTransition()
        sender = _derive_address(TEST_PRIVATE_KEY)
        session.add(Account(chain_id=TEST_CHAIN, address=sender, balance=1_000_000, nonce=0))
        session.commit()

        tx_data = _make_tx(TEST_PRIVATE_KEY, {"payload": {"eth_address": "0xdeadbeef"}})

        success, msg = st.apply_transaction(session, TEST_CHAIN, tx_data, "tx_hash_3")
        assert not success
        assert "eth_address" in msg.lower()

    def test_non_positive_value_rejected(self, session):
        st = StateTransition()
        sender = _derive_address(TEST_PRIVATE_KEY)
        session.add(Account(chain_id=TEST_CHAIN, address=sender, balance=1_000_000, nonce=0))
        session.commit()

        tx_data = _make_tx(TEST_PRIVATE_KEY, {"amount": 0})
        tx_data["payload"]["amount"] = 0

        success, msg = st.apply_transaction(session, TEST_CHAIN, tx_data, "tx_hash_4")
        assert not success
        assert "positive" in msg.lower()

    def test_insufficient_balance_rejected(self, session):
        st = StateTransition()
        sender = _derive_address(TEST_PRIVATE_KEY)
        session.add(Account(chain_id=TEST_CHAIN, address=sender, balance=100, nonce=0))
        session.commit()

        tx_data = _make_tx(TEST_PRIVATE_KEY, {"amount": 1000})

        success, msg = st.apply_transaction(session, TEST_CHAIN, tx_data, "tx_hash_5")
        assert not success
        assert "insufficient" in msg.lower()

    def test_invalid_nonce_rejected(self, session):
        st = StateTransition()
        sender = _derive_address(TEST_PRIVATE_KEY)
        session.add(Account(chain_id=TEST_CHAIN, address=sender, balance=1_000_000, nonce=5))
        session.commit()

        tx_data = _make_tx(TEST_PRIVATE_KEY, {"nonce": 0})

        success, msg = st.apply_transaction(session, TEST_CHAIN, tx_data, "tx_hash_6")
        assert not success
        assert "nonce" in msg.lower()

    def test_invalid_signature_rejected(self, session):
        st = StateTransition()
        sender = _derive_address(TEST_PRIVATE_KEY)
        session.add(Account(chain_id=TEST_CHAIN, address=sender, balance=1_000_000, nonce=0))
        session.commit()

        tx_data = _make_tx(TEST_PRIVATE_KEY)
        tx_data["signature"] = "0x" + "00" * 65

        success, msg = st.apply_transaction(session, TEST_CHAIN, tx_data, "tx_hash_7")
        assert not success
        assert "signature" in msg.lower() or "invalid" in msg.lower()

    def test_withdraw_does_not_credit_zero_address(self, session):
        st = StateTransition()
        sender = _derive_address(TEST_PRIVATE_KEY)
        zero = "0x0000000000000000000000000000000000000000"
        session.add(Account(chain_id=TEST_CHAIN, address=sender, balance=1_000_000, nonce=0))
        session.add(Account(chain_id=TEST_CHAIN, address=zero, balance=0, nonce=0))
        session.commit()

        tx_data = _make_tx(TEST_PRIVATE_KEY, {"amount": 5000, "fee": DEFAULT_TX_FEE_UNITS})

        success, msg = st.apply_transaction(session, TEST_CHAIN, tx_data, "tx_hash_8")
        assert success, msg

        zero_account = session.get(Account, (TEST_CHAIN, zero))
        assert zero_account.balance == 0
