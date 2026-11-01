"""Tests for on-chain performance bonds."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Block, Bond
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
    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1_000_000, nonce=0))
    session.add(Account(chain_id=chain_id, address=escrow, balance=0, nonce=0))
    session.commit()

    tx_data = _make_tx(
        private_key,
        {
            "to": escrow,
            "amount": 5000,
            "value": 5000,
            "fee": DEFAULT_TX_FEE_UNITS,
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
    assert provider.balance == 1_000_000 - 5000 - DEFAULT_TX_FEE_UNITS
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

    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1_000_000, nonce=0))
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
            "fee": DEFAULT_TX_FEE_UNITS,
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
    assert provider.balance == 1_000_000 - DEFAULT_TX_FEE_UNITS + 5000
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
    session.add(Account(chain_id=chain_id, address=authority_addr, balance=1_000_000, nonce=0))
    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1_000_000, nonce=0))
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
            "fee": DEFAULT_TX_FEE_UNITS,
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


def test_bond_slash_prefers_onchain_parameter(session, monkeypatch):
    """chain_parameter.bond_slash_authority wins over a disagreeing env var.

    The env var is per-node configuration; the parameter is chain state applied
    identically everywhere. A disagreeing env must not silently shadow it —
    that drift is what made the 1-2 Sep slashes apply on only part of the fleet.
    """
    from aitbc.crypto.crypto import derive_ethereum_address
    from aitbc_chain.base_models import ChainParameter

    chain_id = "ait-test"
    private_key = "0x" + "22" * 32
    authority_addr = derive_ethereum_address(private_key)
    wrong_addr = derive_ethereum_address("0x" + "99" * 32)
    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", wrong_addr)

    provider_private_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(provider_private_key)
    escrow = _BOND_ESCROW_ADDRESS
    burn = _BOND_BURN_ADDRESS

    st = StateTransition()
    session.add(Account(chain_id=chain_id, address=authority_addr, balance=1_000_000, nonce=0))
    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1_000_000, nonce=0))
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
    session.add(ChainParameter(chain_id=chain_id, parameter="bond_slash_authority", value=authority_addr))
    session.commit()

    tx_data = _make_tx(
        private_key,
        {
            "to": burn,
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "BOND_SLASH",
            "chain_id": chain_id,
            "payload": {"bond_id": "bond_1", "provider": provider_addr, "amount": 2000},
        },
    )
    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_hash_param")
    assert success, msg

    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond is not None
    assert bond.amount == 3000  # on-chain authority accepted the slash


def test_bond_slash_without_authority_skips_effect(session, monkeypatch):
    """With no chain parameter and no env var, the slash applies fee/nonce only
    and the handler returns the skip reason instead of a bare silent return."""
    from aitbc.crypto.crypto import derive_ethereum_address

    monkeypatch.delenv("BOND_SLASH_AUTHORITY_ADDRESS", raising=False)

    chain_id = "ait-test"
    signer_key = "0x" + "33" * 32
    signer_addr = derive_ethereum_address(signer_key)
    provider_private_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(provider_private_key)
    escrow = _BOND_ESCROW_ADDRESS
    burn = _BOND_BURN_ADDRESS

    st = StateTransition()
    session.add(Account(chain_id=chain_id, address=signer_addr, balance=1_000_000, nonce=0))
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
        signer_key,
        {
            "to": burn,
            "amount": 0,
            "value": 0,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "BOND_SLASH",
            "chain_id": chain_id,
            "payload": {"bond_id": "bond_1", "provider": provider_addr, "amount": 2000},
        },
    )
    success, _ = st.apply_transaction(session, chain_id, tx_data, "tx_hash_skip")
    assert success  # the tx itself still applies (fee/nonce)

    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond is not None
    assert bond.amount == 5000  # effect skipped, not silently slashed
    assert bond.slashed_tx_hash is None

    reason = st._handle_bond_transaction(
        session,
        chain_id,
        tx_data,
        "tx_hash_skip",
        "BOND_SLASH",
        _to_ait_address(signer_addr),
        _to_ait_address(burn),
        0,
    )
    assert reason is not None and "no slash authority" in reason


# ---------------------------------------------------------------------------
# v19 (BOND-LOCK-TOPUP-SLASHED-1, #782): top-up on a non-active bond refused
# ---------------------------------------------------------------------------


def _seed_non_active_bond(session, chain_id, provider_addr, status: str, amount: int = 5000):
    """Existing bond row in a terminal status, plus the two accounts a top-up needs."""
    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1_000_000, nonce=0))
    session.add(Account(chain_id=chain_id, address=_BOND_ESCROW_ADDRESS, balance=0, nonce=0))
    session.add(
        Bond(
            chain_id=chain_id,
            bond_id="bond_1",
            provider=_to_ait_address(provider_addr),
            amount=amount,
            locked_until=datetime.now(UTC) + timedelta(days=30),
            status=status,
            created_tx_hash="tx_seed",
        )
    )
    session.commit()


def _bond_topup_tx(private_key: str, chain_id: str, provider_addr: str, amount: int = 100) -> dict:
    return _make_tx(
        private_key,
        {
            "amount": amount,
            "value": amount,
            "fee": DEFAULT_TX_FEE_UNITS,
            "nonce": 0,
            "type": "BOND_LOCK",
            "chain_id": chain_id,
            "payload": {"bond_id": "bond_1", "provider": provider_addr, "lock_days": 7},
        },
    )


@pytest.mark.parametrize("status", ["slashed", "released"])
def test_bond_lock_topup_on_non_active_bond_refused_at_v19(session, status):
    """At/after v19 a top-up on a terminal bond refuses — topping up a slashed
    or released bond used to raise ``amount`` while the row kept its terminal
    status, stranding the added funds forever (#782)."""
    from aitbc.crypto.crypto import derive_ethereum_address

    st = StateTransition()
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(private_key)
    _seed_non_active_bond(session, chain_id, provider_addr, status)

    tx_data = _bond_topup_tx(private_key, chain_id, provider_addr)
    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_topup", block_version=19)
    assert not success
    assert "not active" in msg

    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond.amount == 5000
    assert bond.status == status
    provider = session.get(Account, (chain_id, provider_addr))
    assert provider.balance == 1_000_000  # refused outright: no fee, no nonce


def test_bond_lock_topup_on_slashed_bond_still_applies_below_v19(session):
    """Below v19 the old lenient path stays for replay of sealed history."""
    from aitbc.crypto.crypto import derive_ethereum_address

    st = StateTransition()
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(private_key)
    _seed_non_active_bond(session, chain_id, provider_addr, "slashed")

    tx_data = _bond_topup_tx(private_key, chain_id, provider_addr)
    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_topup", block_version=18)
    assert success, msg
    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond.amount == 5100  # the stranded-funds behavior the v19 gate ends


def test_bond_lock_topup_on_active_bond_still_applies_at_v19(session):
    """The gate only refuses non-active rows: a normal top-up still works."""
    from aitbc.crypto.crypto import derive_ethereum_address

    st = StateTransition()
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(private_key)
    _seed_non_active_bond(session, chain_id, provider_addr, "active")

    tx_data = _bond_topup_tx(private_key, chain_id, provider_addr)
    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_topup", block_version=19)
    assert success, msg
    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond.amount == 5100
    assert bond.status == "active"


def test_bond_lock_new_bond_at_v19_unaffected(session):
    """No existing row — the refusal only fires on a non-active top-up."""
    from aitbc.crypto.crypto import derive_ethereum_address

    st = StateTransition()
    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(private_key)
    session.add(Account(chain_id=chain_id, address=provider_addr, balance=1_000_000, nonce=0))
    session.add(Account(chain_id=chain_id, address=_BOND_ESCROW_ADDRESS, balance=0, nonce=0))
    session.commit()

    tx_data = _bond_topup_tx(private_key, chain_id, provider_addr)
    success, msg = st.apply_transaction(session, chain_id, tx_data, "tx_lock", block_version=19)
    assert success, msg
    bond = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == "bond_1")).first()
    assert bond is not None and bond.status == "active"


def test_bond_lock_topup_admission_refused_at_v19(session, monkeypatch):
    """The mempool door mirrors the block-time refusal (#782)."""
    import contextlib

    from aitbc.crypto.crypto import derive_ethereum_address
    from aitbc_chain.rpc import transactions as rpc_tx
    from aitbc_chain.config import settings

    chain_id = "ait-test"
    private_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(private_key)
    _seed_non_active_bond(session, chain_id, provider_addr, "slashed")
    session.add(Block(chain_id=chain_id, height=9700, hash="h9700", parent_hash="h9699", proposer="p1"))
    session.commit()

    monkeypatch.setattr(settings, "chain_id", chain_id)
    monkeypatch.setattr(settings, "state_transition_v19_height", 9701)
    monkeypatch.setattr(rpc_tx, "session_scope", lambda *a, **k: contextlib.nullcontext(session))

    tx_data = _bond_topup_tx(private_key, chain_id, provider_addr)
    tx_data["from"] = provider_addr
    with pytest.raises(ValueError, match="not active"):
        rpc_tx._validate_transaction_admission(tx_data, mempool=None)
