"""#2834 AUDIT-CHAIN-LIQ-LOCKDAYS-CRASH-1: liquidity payload type/range gate (v31).

``_vt_liquidity`` checked only key *presence* — ``lock_days`` reached
``int()``/``timedelta()`` at apply unchecked (``"x"``/``Infinity``/NaN →
uncaught crash inside the block-apply loop on every node; huge ints →
``OverflowError`` in ``now + delta``), ``pool_id``/``stake_id`` reached
composite-PK ``session.get``/``INSERT`` unchecked (dict/list unhashable,
None/NaN → NULL primary key). v31 requires strict types and a sane
``lock_days`` range; ``_vt_finite_amounts`` already gates value/fee.

The apply handlers additionally convert crash-shaped inputs into
``(False, ...)`` rejections — replay-safe because a tx that crashes
apply can never appear in a sealed block — while preserving every
coercion that previously succeeded (``int("30")``, int pool_id, ...).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from aitbc_chain.base_models import Account
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.liquidity_transition import (
    apply_liquidity_claim,
    apply_liquidity_deposit,
    apply_liquidity_withdraw,
)
from aitbc_chain.state.state_transition import StateTransition

CHAIN = "ait-test-2834"
USER = "0x" + "33" * 20


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'liq-2834.db'}", echo=False)
    chain_metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=USER, balance=10**9, nonce=0))
        s.commit()
        yield s


def _deposit_tx(**payload_overrides):
    payload = {"pool_id": "main", "lock_days": 30}
    payload.update(payload_overrides)
    return {
        "from": USER,
        "to": USER,
        "amount": 100,
        "value": 100,
        "fee": 1,
        "nonce": 0,
        "type": "LIQUIDITY_DEPOSIT",
        "chain_id": CHAIN,
        "payload": payload,
    }


def _validate(st: StateTransition, session: Session, tx: dict, tx_hash: str, version: int):
    return st.validate_transaction(session, CHAIN, tx, tx_hash=tx_hash, block_version=version, block_height=2)


# --- v31 validation gate ---


def test_v31_lock_days_string_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(lock_days="30"), "0xld-str", 31)
    assert ok is False and "lock_days must be an integer" in err


def test_v31_lock_days_float_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(lock_days=30.5), "0xld-float", 31)
    assert ok is False and "lock_days must be an integer" in err


def test_v31_lock_days_bool_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(lock_days=True), "0xld-bool", 31)
    assert ok is False and "lock_days must be an integer" in err


def test_v31_lock_days_negative_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(lock_days=-1), "0xld-neg", 31)
    assert ok is False and "lock_days out of range" in err


def test_v31_lock_days_huge_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(lock_days=10**18), "0xld-huge", 31)
    assert ok is False and "lock_days out of range" in err


def test_v31_pool_id_non_string_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(pool_id=123), "0xpid-int", 31)
    assert ok is False and "pool_id must be a string" in err


def test_v31_pool_id_null_rejected(engine, session):
    """``pool_id=None`` never reaches the v31 type check — the pre-existing
    presence guard refuses it first (same verdict, earlier reason)."""
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(pool_id=None), "0xpid-null", 31)
    assert ok is False


def test_v31_stake_id_non_string_rejected(engine, session):
    st = StateTransition()
    tx = {
        "from": USER,
        "to": USER,
        "value": 0,
        "fee": 1,
        "nonce": 0,
        "type": "LIQUIDITY_CLAIM",
        "chain_id": CHAIN,
        "payload": {"pool_id": "main", "stake_id": ["not", "a", "string"]},
    }
    ok, err = _validate(st, session, tx, "0xsid-list", 31)
    assert ok is False and "stake_id must be a string" in err


def test_v30_lock_days_not_gated(engine, session):
    """Below the rung the new reasons never fire — the tx is judged by the
    later gates instead."""
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(lock_days="x"), "0xv30-ld", 30)
    assert "lock_days must be an integer" not in err
    assert "lock_days out of range" not in err


def test_v31_wellformed_lock_days_passes_gate(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _deposit_tx(lock_days=0), "0xld-ok", 31)
    assert "lock_days must be an integer" not in err
    assert "lock_days out of range" not in err


# --- apply-side crash guards (all versions — crash inputs can't be sealed) ---


def _apply_deposit(session: Session, payload: dict, tx_hash: str = "0xapply-1"):
    return apply_liquidity_deposit(
        session,
        CHAIN,
        {
            "from": USER,
            "to": USER,
            "value": 100,
            "fee": 1,
            "payload": payload,
        },
        tx_hash,
        None,
        block_version=31,
    )


def test_apply_lock_days_string_returns_false(session):
    ok, err = _apply_deposit(session, {"pool_id": "main", "lock_days": "x"})
    assert ok is False and "lock_days" in err


def test_apply_lock_days_huge_returns_false(session):
    ok, err = _apply_deposit(session, {"pool_id": "main", "lock_days": 10**18})
    assert ok is False


def test_apply_lock_days_null_returns_false(session):
    ok, err = _apply_deposit(session, {"pool_id": "main", "lock_days": None})
    assert ok is False


def test_apply_pool_id_dict_returns_false(session):
    ok, err = _apply_deposit(session, {"pool_id": {"x": 1}, "lock_days": 30})
    assert ok is False and "pool_id" in err


def test_apply_pool_id_null_returns_false(session):
    ok, err = _apply_deposit(session, {"pool_id": None, "lock_days": 30})
    assert ok is False and "pool_id" in err


def test_apply_deposit_numeric_string_lock_days_still_applies(session):
    """``int("30")`` coerced successfully before — the apply guard must not
    tighten semantics for inputs that never crashed."""
    ok, err = _apply_deposit(session, {"pool_id": "main", "lock_days": "30"}, "0xapply-coerce")
    assert ok is True, err


def test_apply_claim_dict_stake_id_returns_false(session):
    ok, err = apply_liquidity_claim(
        session,
        CHAIN,
        {
            "from": USER,
            "to": USER,
            "fee": 1,
            "payload": {"pool_id": "main", "stake_id": {"bad": 1}},
        },
        "0xclaim-dict",
        None,
        block_version=31,
    )
    assert ok is False and "stake_id" in err


def test_apply_withdraw_list_stake_id_returns_false(session):
    ok, err = apply_liquidity_withdraw(
        session,
        CHAIN,
        {
            "from": USER,
            "to": USER,
            "fee": 1,
            "payload": {"pool_id": "main", "stake_id": ["bad"]},
        },
        "0xwd-list",
        None,
        block_version=31,
    )
    assert ok is False and "stake_id" in err
