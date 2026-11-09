"""#1314 S2 pin: v24 authoritative (scalar) reads bypass identity-map staleness.

Prod sessions run ``autoflush=False``/``expire_on_commit=False`` and the v22+
apply paths update ``account`` rows with raw SQL. An ORM ``Account`` object
already in the identity map keeps its pre-write balance/nonce; the v24
layer-2 reads (``read_current_account``) must see the post-write row while
pre-v24 verdicts keep the historical ORM read (replay compat).

The discriminating fixture: pin the escrow ``Account`` in the identity map,
then UPDATE its balance with raw SQL *in the same transaction* — exactly the
shape an earlier same-block apply leaves behind.
"""

from datetime import UTC, datetime

from sqlmodel import Session, create_engine
from sqlalchemy import text

from aitbc_chain.base_models import Account
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import bond_tx_verdict

from .test_apply_parity import (
    CHAIN,
    PROVIDER,
    _BOND_ESCROW_ADDRESS as ESCROW,
    _seed_bond,
)

BLOCK_TIME = datetime(2026, 11, 6, tzinfo=UTC)


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'v24-reads.db'}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _release_verdict(session: Session, block_version: int) -> str | None:
    return bond_tx_verdict(
        session,
        CHAIN,
        "BOND_RELEASE",
        {"bond_id": "bond-par-1", "provider": PROVIDER},
        PROVIDER,
        PROVIDER,
        0,
        block_version=block_version,
        block_time=BLOCK_TIME,
    )


def _pin_escrow_then_drop_balance(session: Session) -> Account:
    """Pin the escrow Account at 5000 in the identity map, then raw-SQL it
    to 4000 — below the seeded bond's 5000 release amount.

    Returns the pinned object: the identity map holds only weak references,
    so the caller MUST keep it alive or the next ``session.get`` re-queries
    and the staleness this fixture exists to create evaporates."""
    esc = session.get(Account, (CHAIN, ESCROW))
    assert esc is not None and esc.balance == 5000
    session.execute(
        text("UPDATE account SET balance = :bal WHERE chain_id = :c AND address = :a"),
        {"bal": 4000, "c": CHAIN, "a": ESCROW},
    )
    # Identity map still serves the pre-write value — the staleness the
    # v24 reads exist to bypass.
    assert esc.balance == 5000
    return esc


def test_bond_release_escrow_read_is_authoritative_at_v24(tmp_path):
    """At block_version>=24 the escrow-sufficiency check sees the raw-SQL
    post-write balance (4000 < 5000 → refuse), not the stale ORM 5000."""
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        session.commit()
        pinned = _pin_escrow_then_drop_balance(session)
        err = _release_verdict(session, 24)
        assert err is not None and "escrow balance 4000" in err
        assert pinned.balance == 5000  # ORM view still stale — read bypassed it


def test_bond_release_escrow_read_stays_orm_below_v24(tmp_path):
    """Replay compat: at block_version<24 the same stale row passes the
    escrow check — the pre-v24 divergence window is pinned, not fixed."""
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        session.commit()
        pinned = _pin_escrow_then_drop_balance(session)
        assert _release_verdict(session, 23) is None
        assert pinned.balance == 5000  # pre-v24 verdict consumed the stale ORM read


def test_authoritative_read_matches_committed_state(tmp_path):
    """read_current_account returns the same values a fresh SELECT sees —
    the helper is a read-source swap, not a semantics change."""
    from aitbc_chain.state.authoritative_reads import read_current_account

    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        session.commit()
        bal, nonce, exists = read_current_account(session, CHAIN, ESCROW)
        assert exists and bal == 5000 and nonce == 0
        # Missing account → (None-ish, 0-ish, False) triple, never raises.
        bal2, nonce2, exists2 = read_current_account(session, CHAIN, "0xdead")
        assert not exists2


def test_parity_session_expire_skips_dirty_instances(tmp_path):
    """E c23626 item 1: ParitySession._expire_written_tables must not discard
    pending ORM changes. A dirty instance keeps its unflushed attribute
    (pre-v24 semantics); a clean instance of the same table is still expired
    and reloads the raw-written value."""
    from aitbc_chain.database import prod_parity_sessionmaker
    from aitbc_chain.v24_rules import v24_rules_active

    engine = _engine(tmp_path)
    clean_addr = "0xcleanacct"
    with prod_parity_sessionmaker(bind=engine)() as session:
        session.add(Account(chain_id=CHAIN, address=ESCROW, balance=5000, nonce=0))
        session.add(Account(chain_id=CHAIN, address=clean_addr, balance=1, nonce=0))
        session.commit()

        esc = session.get(Account, (CHAIN, ESCROW))
        clean_obj = session.get(Account, (CHAIN, clean_addr))
        assert esc is not None and clean_obj is not None
        esc.balance = 4242  # pending ORM change; autoflush=False keeps it dirty

        with v24_rules_active():
            session.execute(
                text("UPDATE account SET balance=:b WHERE chain_id=:c AND address=:a"),
                [
                    {"b": 7777, "c": CHAIN, "a": ESCROW},
                    {"b": 9, "c": CHAIN, "a": clean_addr},
                ],
            )

        # Dirty instance: pending change survives (pre-v24 semantics preserved).
        assert esc.balance == 4242
        # Clean instance: expired -> attribute access reloads the raw write.
        assert clean_obj.balance == 9
