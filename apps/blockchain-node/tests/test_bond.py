"""Tests for on-chain performance bonds."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import Account, Bond
from aitbc_chain.database import chain_metadata
from aitbc_chain.state.state_transition import StateTransition, _BOND_BURN_ADDRESS, _BOND_ESCROW_ADDRESS, _to_ait_address


def _sign_data(private_key: str, data: dict) -> str:
    from eth_utils import keccak
    from aitbc.crypto.crypto import sign_transaction_hash

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _make_tx(private_key: str, tx_data: dict) -> dict:
    from aitbc.crypto.crypto import derive_ethereum_address

    tx = dict(tx_data)
    from_address = derive_ethereum_address(private_key)
    tx["from"] = from_address
    if tx.get("type") == "BOND_LOCK":
        tx["to"] = _BOND_ESCROW_ADDRESS
    elif tx.get("type") == "BOND_SLASH":
        tx["to"] = _BOND_BURN_ADDRESS
    elif tx.get("type") == "BOND_RELEASE":
        tx["to"] = from_address

    signable = {k: v for k, v in tx.items() if k not in ("signature",)}
    if "amount" in signable:
        signable.pop("value", None)
    tx["signature"] = _sign_data(private_key, signable)
    return tx


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_bond_lock_records_bond_and_moves_funds(session):
    st = StateTransition()
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    from aitbc.crypto.crypto import derive_ethereum_address

    provider_addr = derive_ethereum_address(private_key)

    escrow = _BOND_ESCROW_ADDRESS
    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1000000, nonce=0))
    session.add(Account(chain_id=chain_id, address=escrow, balance=0, nonce=0))
    session.commit()

    tx_data = _make_tx(
        private_key,
        {
            "to": escrow,
            "amount": 5000,
            "value": 5000,
            "fee": 36,
            "nonce": 0,
            "type": "BOND_LOCK",
            "chain_id": chain_id,
            "payload": {"bond_id": "bond_1", "provider": provider_addr, "lock_days": 7},
        },
    )
    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_hash_1")
    assert success, msg

    provider = session.get(Account, (chain_id, provider_addr))
    escrow_account = session.get(Account, (chain_id, escrow))
    assert provider.balance == 1000000 - 5000 - 36
    assert escrow_account.balance == 5000

    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond is not None
    assert bond.amount == 5000
    assert bond.provider == _to_ait_address(provider_addr)


def test_bond_release_after_lock_expired(session):
    st = StateTransition()
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    from aitbc.crypto.crypto import derive_ethereum_address

    provider_addr = derive_ethereum_address(private_key)
    escrow = _BOND_ESCROW_ADDRESS

    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1000, nonce=0))
    session.add(Account(chain_id=chain_id, address=escrow, balance=5000, nonce=0))
    session.add(
        Bond(
            chain_id=chain_id,
            bond_id="bond_1",
            provider=provider_addr,
            amount=5000,
            locked_until=datetime.now(UTC) - timedelta(days=1),
            status="active",
            created_tx_hash="tx_hash_1",
        )
    )
    session.commit()

    tx_data = _make_tx(
        private_key,
        {
            "to": provider_addr,
            "amount": 0,
            "value": 0,
            "fee": 36,
            "nonce": 0,
            "type": "BOND_RELEASE",
            "chain_id": chain_id,
            "payload": {"bond_id": "bond_1", "provider": provider_addr},
        },
    )
    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_hash_2")
    assert success, msg

    provider = session.get(Account, (chain_id, provider_addr))
    escrow_account = session.get(Account, (chain_id, escrow))
    assert provider.balance == 1000 - 36 + 5000
    assert escrow_account.balance == 0

    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond is not None
    assert bond.status == "released"
    assert bond.amount == 0


def test_bond_slash_by_authority(session, monkeypatch):
    from aitbc.crypto.crypto import derive_ethereum_address

    chain_id = "ait-test"
    private_key = "0x" + "22" * 32
    authority_addr = derive_ethereum_address(private_key)
    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", authority_addr)

    provider_private_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(provider_private_key)
    escrow = _BOND_ESCROW_ADDRESS
    burn = _BOND_BURN_ADDRESS

    st = StateTransition()
    session.add(Account(chain_id=chain_id, address=authority_addr, balance=1000, nonce=0))
    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1000, nonce=0))
    session.add(Account(chain_id=chain_id, address=escrow, balance=5000, nonce=0))
    session.add(Account(chain_id=chain_id, address=burn, balance=0, nonce=0))
    session.add(
        Bond(
            chain_id=chain_id,
            bond_id="bond_1",
            provider=provider_addr,
            amount=5000,
            locked_until=datetime.now(UTC) + timedelta(days=7),
            status="active",
            created_tx_hash="tx_hash_1",
        )
    )
    session.commit()

    tx_data = _make_tx(
        private_key,
        {
            "to": burn,
            "amount": 0,
            "value": 0,
            "fee": 36,
            "nonce": 0,
            "type": "BOND_SLASH",
            "chain_id": chain_id,
            "payload": {"bond_id": "bond_1", "provider": provider_addr, "amount": 2000},
        },
    )
    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_hash_3")
    assert success, msg

    escrow_account = session.get(Account, (chain_id, escrow))
    burn_account = session.get(Account, (chain_id, burn))
    assert escrow_account.balance == 3000
    assert burn_account.balance == 2000

    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond is not None
    assert bond.amount == 3000
    assert bond.status == "active"
