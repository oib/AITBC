"""Tests for GET /rpc/supply — the live supply aggregate (GAP-SUPPLY-LIVE-1 Phase 1).

The endpoint sums the committed `account` table and subtracts the bond-burn row.
Fee burns net by omission (the apply path never credits the fee), so the figure
matches `SUM(balance) - bond_burn` with no extra bookkeeping. `account` is a
committed table: at a given height the answer is identical on every synced host.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Block, Bond
from aitbc_chain.database import chain_metadata
from aitbc_chain.state import state_transition
from aitbc_chain.state.state_transition import (
    StateTransition,
    _BOND_BURN_ADDRESS,
    _BOND_ESCROW_ADDRESS,
    _to_ait_address,
)

CHAIN_ID = "ait-test"


def _sign_data(private_key: str, data: dict) -> str:
    from eth_utils import keccak

    from aitbc.crypto.crypto import sign_transaction_hash

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return sign_transaction_hash("0x" + keccak(message).hex(), private_key)


def _make_tx(private_key: str, tx_data: dict) -> dict:
    from aitbc.crypto.crypto import derive_ethereum_address

    tx = dict(tx_data)
    tx["from"] = derive_ethereum_address(private_key)
    signable = {k: v for k, v in tx.items() if k != "signature"}
    tx["signature"] = _sign_data(private_key, signable)
    return tx


@pytest.fixture
def supply_rpc(monkeypatch):
    """In-memory chain wired in place of the node's real session."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)

    import aitbc_chain.rpc.accounts as accounts_module
    from aitbc_chain.rpc import utils as rpc_utils

    @contextmanager
    def _session_scope(*_args, **_kwargs):
        with Session(engine) as open_session:
            yield open_session

    monkeypatch.setattr(accounts_module, "session_scope", _session_scope)
    monkeypatch.setattr(rpc_utils.settings, "chain_id", CHAIN_ID)
    return accounts_module, engine


def _accounts(engine):
    return Session(engine)


async def _get(module, chain_id: str | None = CHAIN_ID):
    return await module.get_supply.__wrapped__(None, chain_id)


async def test_supply_empty_db_zeroes(supply_rpc) -> None:
    module, _engine = supply_rpc
    result = await _get(module)

    assert result["chain_id"] == CHAIN_ID
    assert result["height"] == 0
    assert result["total_balance_units"] == 0
    assert result["bond_burned_units"] == 0
    assert result["circulating_units"] == 0
    assert result["circulating_ait"] == "0.00000000"
    assert result["accounts_with_balance"] == 0
    assert result["units_per_ait"] == 36_000_000


async def test_supply_sums_account_rows(supply_rpc) -> None:
    module, engine = supply_rpc
    with _accounts(engine) as session:
        session.add(Account(chain_id=CHAIN_ID, address="0x" + "aa" * 20, balance=1000, nonce=0))
        session.add(Account(chain_id=CHAIN_ID, address="0x" + "bb" * 20, balance=2000, nonce=0))
        session.add(Account(chain_id=CHAIN_ID, address="0x" + "cc" * 20, balance=0, nonce=0))
        session.commit()

    result = await _get(module)

    assert result["total_balance_units"] == 3000
    assert result["circulating_units"] == 3000
    # zero-balance rows exist but do not count
    assert result["accounts_with_balance"] == 2


async def test_supply_bond_slash_moves_out_of_circulating(supply_rpc, monkeypatch) -> None:
    """A sealed BOND_SLASH grows `bond_burned_units` and drops `circulating_units`
    while `total_balance_units` keeps the slashed amount — asserted via the
    `_BOND_BURN_ADDRESS` code constant, not a literal."""
    module, engine = supply_rpc
    from aitbc.crypto.crypto import derive_ethereum_address

    authority_key = "0x" + "22" * 32
    authority_addr = derive_ethereum_address(authority_key)
    monkeypatch.setenv("BOND_SLASH_AUTHORITY_ADDRESS", authority_addr)
    provider_key = "0x" + "11" * 32
    provider_addr = derive_ethereum_address(provider_key)

    with _accounts(engine) as session:
        session.add(Account(chain_id=CHAIN_ID, address=authority_addr, balance=1_000_000, nonce=0))
        session.add(Account(chain_id=CHAIN_ID, address=provider_addr, balance=1_000_000, nonce=0))
        session.add(Account(chain_id=CHAIN_ID, address=_to_ait_address(_BOND_ESCROW_ADDRESS), balance=5000, nonce=0))
        session.add(Account(chain_id=CHAIN_ID, address=_to_ait_address(_BOND_BURN_ADDRESS), balance=0, nonce=0))
        session.add(
            Bond(
                chain_id=CHAIN_ID,
                bond_id="bond_1",
                provider=provider_addr,
                amount=5000,
                locked_until=datetime.now(UTC) + timedelta(days=7),
                status="active",
                created_tx_hash="tx_hash_lock",
            )
        )
        session.commit()

        before = 1_000_000 + 1_000_000 + 5000
        st = StateTransition()
        tx = _make_tx(
            authority_key,
            {
                "to": _BOND_BURN_ADDRESS,
                "amount": 0,
                "value": 0,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "BOND_SLASH",
                "chain_id": CHAIN_ID,
                "payload": {"bond_id": "bond_1", "provider": provider_addr, "amount": 2000},
            },
        )
        success, msg = st.apply_transaction(session, CHAIN_ID, tx, "tx_hash_slash")
        assert success, msg
        session.commit()

    result = await _get(module)

    assert result["bond_burned_units"] == 2000
    # total keeps the burned row's balance; circulating excludes it (and the fee)
    assert result["total_balance_units"] == before - DEFAULT_TX_FEE_UNITS
    assert result["circulating_units"] == result["total_balance_units"] - 2000


async def test_supply_fee_burn_nets_by_omission(supply_rpc) -> None:
    """A fee-bearing TRANSFER lowers SUM(balance) by exactly the fee — no burn
    row is involved, the fee is simply never credited."""
    module, engine = supply_rpc
    from aitbc.crypto.crypto import derive_ethereum_address

    sender_key = "0x" + "33" * 32
    sender_addr = derive_ethereum_address(sender_key)
    recipient = "0x" + "dd" * 20

    with _accounts(engine) as session:
        session.add(Account(chain_id=CHAIN_ID, address=sender_addr, balance=1_000_000, nonce=0))
        session.commit()

        st = StateTransition()
        tx = _make_tx(
            sender_key,
            {
                "to": recipient,
                "amount": 1000,
                "value": 1000,
                "fee": DEFAULT_TX_FEE_UNITS,
                "nonce": 0,
                "type": "TRANSFER",
                "chain_id": CHAIN_ID,
            },
        )
        success, msg = st.apply_transaction(session, CHAIN_ID, tx, "tx_hash_transfer")
        assert success, msg
        session.commit()

    result = await _get(module)

    # genesis-side sum was 1_000_000; the fee left circulation by omission
    assert result["total_balance_units"] == 1_000_000 - DEFAULT_TX_FEE_UNITS
    assert result["bond_burned_units"] == 0
    assert result["circulating_units"] == result["total_balance_units"]


async def test_supply_mint_counts(supply_rpc) -> None:
    """A credit that lands in an account row (mint path) raises the aggregate."""
    module, engine = supply_rpc
    from aitbc.crypto.crypto import derive_ethereum_address

    payer_key = "0x" + "44" * 32
    payer_addr = derive_ethereum_address(payer_key)
    payee = "0x" + "ee" * 20

    with _accounts(engine) as session:
        session.add(Account(chain_id=CHAIN_ID, address=payer_addr, balance=1_000_000, nonce=0))
        session.commit()

    first = await _get(module)

    # simulate a minted credit arriving as a new account row (RECEIPT_CLAIM shape)
    with _accounts(engine) as session:
        session.add(Account(chain_id=CHAIN_ID, address=payee, balance=7_500, nonce=0))
        session.commit()

    second = await _get(module)

    assert second["circulating_units"] == first["circulating_units"] + 7_500


async def test_supply_height_is_head(supply_rpc) -> None:
    module, engine = supply_rpc
    with _accounts(engine) as session:
        session.add(
            Block(
                chain_id=CHAIN_ID,
                height=42,
                hash="0x" + "ab" * 32,
                parent_hash="0x" + "00" * 32,
                proposer="0x" + "ff" * 20,
                tx_count=0,
            )
        )
        session.commit()

    first = await _get(module)
    second = await _get(module)

    assert first["height"] == 42
    assert first == second


async def test_supply_bond_burn_address_from_code(supply_rpc, monkeypatch) -> None:
    """The burn row is located via the code constant — a configured
    BOND_BURN_ADDRESS path resolves the same way the writer resolves it."""
    module, engine = supply_rpc
    custom_burn = "0x" + "b1" * 20
    monkeypatch.setattr(state_transition, "_BOND_BURN_ADDRESS", custom_burn)

    with _accounts(engine) as session:
        session.add(Account(chain_id=CHAIN_ID, address="0x" + "aa" * 20, balance=1000, nonce=0))
        session.add(Account(chain_id=CHAIN_ID, address=custom_burn, balance=400, nonce=0))
        session.commit()

    result = await _get(module)

    assert result["bond_burned_units"] == 400
    assert result["total_balance_units"] == 1400
    assert result["circulating_units"] == 1000


async def test_supply_chain_scope(supply_rpc) -> None:
    """Accounts on another island never leak into this chain's figure."""
    module, engine = supply_rpc
    with _accounts(engine) as session:
        session.add(Account(chain_id=CHAIN_ID, address="0x" + "aa" * 20, balance=1000, nonce=0))
        session.add(Account(chain_id="ait-other", address="0x" + "bb" * 20, balance=9_000_000, nonce=0))
        session.commit()

    result = await _get(module)

    assert result["total_balance_units"] == 1000
    assert result["circulating_units"] == 1000
    assert result["accounts_with_balance"] == 1
