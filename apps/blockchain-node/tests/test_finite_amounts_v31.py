"""#2789 AUDIT-CHAIN-TX-NAN-VALUE-1: finite-int value/fee/amount gate (v31).

``_vt_prepare`` reads ``value``/``fee`` raw from ``tx_data``; the v20
amount-compare only fires when ``amount`` is present, and even then
``fee`` is never type-checked. A float NaN survives every downstream
guard — ``value < 0``, ``value > MAX``, ``balance < total_cost`` are all
False for NaN — then ``balance ± NaN`` binds NULL through sqlite3 and
silently NULLs the account balance column. ``Infinity`` raises
OverflowError inside ``int()`` on the validation path itself.

v31 requires ``value``, ``fee`` — and ``amount`` when present — to be
JSON integers (``bool`` excluded). ``normalize_transaction_data`` already
emits int for every mempool-admitted tx, so no legitimate sealed shape
is refused. Below v31 the rules are unchanged so historical blocks
replay identically.
"""

from __future__ import annotations

import math

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from aitbc_chain.base_models import Account
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "ait-test-2789"
USER = "0x" + "11" * 20
RECIPIENT = "0x" + "22" * 20


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'finite-2789.db'}", echo=False)
    chain_metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=USER, balance=10**9, nonce=0))
        s.add(Account(chain_id=CHAIN, address=RECIPIENT, balance=0, nonce=0))
        s.commit()
        yield s


def _tx(**overrides):
    tx = {
        "from": USER,
        "to": RECIPIENT,
        "amount": 5,
        "value": 5,
        "fee": 1,
        "nonce": 0,
        "type": "TRANSFER",
        "chain_id": CHAIN,
    }
    tx.update(overrides)
    return tx


def _validate(st: StateTransition, session: Session, tx: dict, tx_hash: str, version: int):
    return st.validate_transaction(session, CHAIN, tx, tx_hash=tx_hash, block_version=version, block_height=2)


# --- v31 rejects non-integer money fields ---


def test_v31_nan_value_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(value=math.nan), "0xnan-value", 31)
    assert ok is False and "value must be an integer" in err


def test_v31_nan_fee_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(fee=math.nan), "0xnan-fee", 31)
    assert ok is False and "fee must be an integer" in err


def test_v31_nan_amount_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(amount=math.nan, value=math.nan), "0xnan-amount", 31)
    assert ok is False and "amount must be an integer" in err


def test_v31_infinity_fee_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(fee=math.inf), "0xinf-fee", 31)
    assert ok is False and "fee must be an integer" in err


def test_v31_float_value_rejected(engine, session):
    """Even an integral float is refused — the column is INTEGER."""
    st = StateTransition()
    ok, err = _validate(st, session, _tx(value=5.0, amount=5), "0xfloat-value", 31)
    assert ok is False and "value must be an integer" in err


def test_v31_bool_value_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(value=True, amount=1), "0xbool-value", 31)
    assert ok is False and "value must be an integer" in err


def test_v31_string_amount_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(amount="5", value="5", fee="1"), "0xstr-amount", 31)
    assert ok is False


def test_v31_missing_amount_still_gated(engine, session):
    """The #2789 hole: value/fee without an ``amount`` key must not skip
    the finite check — ``_vt_prepare``'s v20 compare never runs."""
    st = StateTransition()
    tx = _tx(value=math.nan, fee=0)
    del tx["amount"]
    ok, err = _validate(st, session, tx, "0xno-amount-nan", 31)
    assert ok is False and "value must be an integer" in err


# --- below v31 the rules are unchanged ---


def test_v30_nan_value_not_gated(engine, session):
    """Pre-rung replay keeps the historical verdict path: the finite gate
    does not fire, so the tx is judged by the later gates instead (here it
    fails signature/account checks — the point is it is NOT the v31 reason)."""
    st = StateTransition()
    ok, err = _validate(st, session, _tx(value=math.nan), "0xv30-nan", 30)
    assert "must be an integer" not in err


def test_v31_int_tx_passes_finite_gate(engine, session):
    """A well-formed int tx is not refused by the new gate — whatever later
    gates decide, the finite-amounts reason never appears."""
    st = StateTransition()
    ok, err = _validate(st, session, _tx(), "0xok-int", 31)
    assert "must be an integer" not in err
