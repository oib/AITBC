"""#1067 pin: BOND_LOCK provider==signer + lock_days bound at block_version 20.

Below v20 the pre-gate behavior is pinned unchanged (a forged top-up still
applies — replay compat).
"""

from sqlmodel import Session

from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import StateTransition

from aitbc_chain.base_models import Account
from .test_apply_parity import (
    CHAIN,
    PROVIDER,
    BUYER,
    BUYER_KEY,
    PROVIDER_KEY,
    _BOND_ESCROW_ADDRESS as ESCROW,
    _attach_sender_sig,
    _seed_bond,
    _tx,
)


def _engine(tmp_path):
    from sqlmodel import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'bond-v20.db'}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def test_forged_topup_refused_at_v20(tmp_path):
    """A non-provider top-up that would reset locked_until is refused at v20."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(BUYER, ESCROW, 1, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": PROVIDER, "lock_days": 36500}), BUYER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        session.add(Account(chain_id=CHAIN, address=BUYER, balance=10**9, nonce=0))
        session.add(Account(chain_id=CHAIN, address=PROVIDER, balance=10**9, nonce=0))
        session.commit()
        ok, err = st.apply_transaction(session, CHAIN, tx, tx_hash="h1", block_version=20, block_height=1)
        assert ok is False and "provider" in err


def test_same_forged_topup_applies_below_v20(tmp_path):
    """Replay compat: before v20 the forged top-up behaved exactly as before."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(BUYER, ESCROW, 1, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": PROVIDER, "lock_days": 7}), BUYER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        session.add(Account(chain_id=CHAIN, address=BUYER, balance=10**9, nonce=0))
        session.add(Account(chain_id=CHAIN, address=PROVIDER, balance=10**9, nonce=0))
        session.commit()
        ok, err = st.apply_transaction(session, CHAIN, tx, tx_hash="h2", block_version=19, block_height=1)
        assert ok is True, err


def test_lock_days_out_of_range_refused_at_v20(tmp_path):
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, ESCROW, 1, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": PROVIDER, "lock_days": 99999}),
        PROVIDER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        session.add(Account(chain_id=CHAIN, address=BUYER, balance=10**9, nonce=0))
        session.add(Account(chain_id=CHAIN, address=PROVIDER, balance=10**9, nonce=0))
        session.commit()
        ok, err = st.apply_transaction(session, CHAIN, tx, tx_hash="h3", block_version=20, block_height=1)
        assert ok is False and "lock_days" in err
