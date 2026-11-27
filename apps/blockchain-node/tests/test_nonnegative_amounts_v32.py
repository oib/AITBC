"""#3069 AUDIT-CONSENSUS-NEGATIVE-AMOUNT-1: non-negative value/fee gate (v32).

``validate_transaction`` carried no sign check for ``value``/``fee`` —
``_vt_sender_balance``'s ``sender_balance < value + fee`` trivially passes
for negative amounts — while ``apply_transaction`` raises ``ValueError``
on ``value < 0 or fee < 0``. A block containing such a tx is therefore
unimportable by construction: the last validate-pass/apply-raise
asymmetry class. Not exploitable today (mempool intake rejects negatives
in ``rpc/utils.py``), so v32 is defense-in-depth, replay-safe below the
activation height.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from aitbc_chain.base_models import Account
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import StateTransition
from aitbc_chain.state.state_transition_txmeta import get_block_version_for_height

CHAIN = "ait-test-3069"
USER = "0x" + "11" * 20
RECIPIENT = "0x" + "22" * 20


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'nonneg-3069.db'}", echo=False)
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


# --- v32 rejects negative value/fee ---


def test_v32_negative_value_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(value=-5, amount=-5), "0xneg-value", 32)
    assert ok is False and "value must be non-negative" in err


def test_v32_negative_fee_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(fee=-1), "0xneg-fee", 32)
    assert ok is False and "fee must be non-negative" in err


def test_v32_negative_both_rejected(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(value=-5, amount=-5, fee=-1), "0xneg-both", 32)
    assert ok is False and "non-negative" in err


def test_v32_zero_amounts_pass_gate(engine, session):
    """Zero is non-negative — the gate must not over-reject."""
    st = StateTransition()
    ok, err = _validate(st, session, _tx(value=0, amount=0, fee=0), "0xzero-amounts", 32)
    assert "non-negative" not in err


# --- below v32 the rules are unchanged ---


def test_v31_negative_value_not_gated(engine, session):
    """Pre-rung replay keeps the historical verdict path: the sign gate
    does not fire, so the tx is judged by the later gates instead (here it
    may even validate — apply is what raises; the point is it is NOT the
    v32 reason)."""
    st = StateTransition()
    ok, err = _validate(st, session, _tx(value=-5, amount=-5), "0xv31-neg", 31)
    assert "non-negative" not in err


def test_v31_negative_fee_not_gated(engine, session):
    st = StateTransition()
    ok, err = _validate(st, session, _tx(fee=-1), "0xv31-neg-fee", 31)
    assert "non-negative" not in err


# --- version derivation ---


def test_v32_height_derives_version_32(monkeypatch):
    """With the dormant pin set, a block at/above the height resolves v32."""
    from aitbc_chain.config import settings

    monkeypatch.setattr(settings, "state_transition_v32_height", 100)
    try:
        assert get_block_version_for_height(99) < 32
        assert get_block_version_for_height(100) == 32
        assert get_block_version_for_height(500) == 32
    finally:
        monkeypatch.setattr(settings, "state_transition_v32_height", None)
