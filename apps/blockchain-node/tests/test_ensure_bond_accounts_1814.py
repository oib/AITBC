"""#1814: startup must not insert bond accounts into a chain that already has blocks.

The state root hashes every account row, zero-balance ones included. A row inserted
at startup after genesis changes the accounts hash with no block carrying it, so a
node whose BOND_ESCROW_ADDRESS differs from the chain's wedges on restart ("local
state diverged from our own head"). Genesis allocations carry the rows; startup only
creates them on an empty chain.
"""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import Account, Block
from aitbc_chain.database import _bond_burn_address, _bond_escrow_address, _to_ait_address, ensure_bond_accounts
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state import state_root_utils

CHAIN = "ait-1814"
NEW_ESCROW = "0xaf295d3c842bc1145E818d7FEf2c929726625620"


@pytest.fixture
def session(monkeypatch):
    for var in ("BOND_ESCROW_ADDRESS", "BOND_BURN_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _rows(session: Session) -> set[str]:
    return {a.address for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()}


def _add_block(session: Session) -> None:
    session.add(
        Block(chain_id=CHAIN, height=0, hash="0x" + "00" * 32, parent_hash="0x" + "00" * 32, proposer="0x" + "11" * 20)
    )
    session.commit()


def _missing_count() -> float:
    return metrics_registry._counters.get("startup_bond_account_missing_total", 0.0)


def _default_rows() -> set[str]:
    return {_to_ait_address(_bond_escrow_address()), _to_ait_address(_bond_burn_address())}


def test_empty_chain_creates_both_rows(session):
    ensure_bond_accounts(session, CHAIN)
    assert _rows(session) == _default_rows()


def test_chain_with_blocks_and_rows_is_untouched_and_idempotent(session):
    ensure_bond_accounts(session, CHAIN)
    _add_block(session)
    root = state_root_utils.compute_state_root_full(session, CHAIN)
    before = _missing_count()
    ensure_bond_accounts(session, CHAIN)
    ensure_bond_accounts(session, CHAIN)
    assert _rows(session) == _default_rows()
    assert state_root_utils.compute_state_root_full(session, CHAIN) == root
    assert _missing_count() == before


def test_env_escrow_differing_from_chain_does_not_insert_or_change_root(session, monkeypatch, caplog):
    ensure_bond_accounts(session, CHAIN)
    _add_block(session)
    expected = _default_rows()
    root = state_root_utils.compute_state_root_full(session, CHAIN)
    before = _missing_count()
    monkeypatch.setenv("BOND_ESCROW_ADDRESS", NEW_ESCROW)
    with caplog.at_level("ERROR"):
        ensure_bond_accounts(session, CHAIN)
    assert _rows(session) == expected  # no new row
    assert state_root_utils.compute_state_root_full(session, CHAIN) == root
    assert _missing_count() == before + 1
    assert any("disagrees with the chain" in r.message for r in caplog.records)


def test_missing_rows_on_chain_with_blocks_are_not_created(session):
    _add_block(session)  # legacy shape: head exists, rows do not
    ensure_bond_accounts(session, CHAIN)
    assert _rows(session) == set()


def _chain_with_block_and_rows(chain_id: str) -> None:
    from aitbc_chain.database import init_db, session_scope

    init_db(chain_id)
    with session_scope(chain_id) as s:
        s.add(
            Block(chain_id=chain_id, height=0, hash="0x" + "00" * 32, parent_hash="0x" + "00" * 32, proposer="0x" + "11" * 20)
        )
        s.commit()


def test_init_db_refuses_to_start_when_env_escrow_disagrees(monkeypatch):
    from aitbc_chain.config import settings
    from aitbc_chain.database import init_db

    for var in ("BOND_ESCROW_ADDRESS", "BOND_BURN_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    chain = "strict-1814-refuse"
    _chain_with_block_and_rows(chain)
    init_db(chain)  # same env: healthy restart is fine
    monkeypatch.setenv("BOND_ESCROW_ADDRESS", NEW_ESCROW)
    monkeypatch.setattr(settings, "startup_account_check_strict", True)
    with pytest.raises(RuntimeError, match="Refusing to start"):
        init_db(chain)


def test_init_db_strict_off_only_logs(monkeypatch):
    from aitbc_chain.config import settings
    from aitbc_chain.database import init_db

    for var in ("BOND_ESCROW_ADDRESS", "BOND_BURN_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    chain = "strict-1814-lenient"
    _chain_with_block_and_rows(chain)
    monkeypatch.setenv("BOND_ESCROW_ADDRESS", NEW_ESCROW)
    monkeypatch.setattr(settings, "startup_account_check_strict", False)
    init_db(chain)  # logs, does not raise, and inserts nothing
    from aitbc_chain.database import session_scope

    with session_scope(chain) as s:
        assert s.exec(select(Account).where(Account.chain_id == chain, Account.address == NEW_ESCROW)).first() is None
