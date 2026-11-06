"""#1166/#1167 pin: v22 bond ownership + absolute lock ceiling.

Spec v2.2 (SHA-256 5a0f22fd…): at block_version >= 22,
``payload.provider`` is mandatory and must equal both the signer and the
persisted ``bond.provider``; ``locked_until = min(now + lock_days,
created_at + PROTOCOL_MAX_LOCK_DURATION)``; post-ceiling top-ups and NULL
``locked_until`` releases are refused; every refusal is a hard reject —
validate False, zero mutation (no fee, no nonce, no bond/escrow/balance
change). Below v22 the pre-fix behavior is pinned unchanged for replay.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import Account, Bond, ChainParameter
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.state_transition import PROTOCOL_MAX_LOCK_DURATION, StateTransition

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

BLOCK_TIME = datetime(2026, 11, 6, tzinfo=UTC)


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bond-v22.db'}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _accounts(session: Session) -> None:
    session.add(Account(chain_id=CHAIN, address=BUYER, balance=10**9, nonce=0))
    session.add(Account(chain_id=CHAIN, address=PROVIDER, balance=10**9, nonce=0))


def _apply(st: StateTransition, session: Session, tx: dict, tag: str, version: int = 22):
    return st.apply_transaction(session, CHAIN, tx, tx_hash=tag, block_version=version, block_height=1, block_time=BLOCK_TIME)


def _bond(session: Session, bond_id: str = "bond-par-1") -> Bond:
    bond = session.exec(select(Bond).where(Bond.chain_id == CHAIN, Bond.bond_id == bond_id)).first()
    assert bond is not None
    return bond


def _snapshot(session: Session):
    buyer = session.get(Account, (CHAIN, BUYER))
    provider = session.get(Account, (CHAIN, PROVIDER))
    escrow = session.get(Account, (CHAIN, ESCROW))
    bond = _bond(session)
    return (
        (buyer.balance, buyer.nonce) if buyer else None,
        (provider.balance, provider.nonce) if provider else None,
        escrow.balance if escrow else None,
        (bond.amount, bond.status, bond.locked_until, bond.created_at),
    )


# --- BOND_RELEASE-001: forged release -------------------------------------


def test_forged_release_refused_at_v22(tmp_path):
    """Attacker signs a release naming the victim as payload.provider."""
    st = StateTransition()
    tx = _attach_sender_sig(_tx(BUYER, BUYER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), BUYER_KEY)
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        before = _snapshot(session)
        ok, err = _apply(st, session, tx, "rel-forge")
        assert ok is False and "provider" in err
        assert _snapshot(session) == before


def test_forged_release_self_provider_refused_at_v22(tmp_path):
    """Attacker names *themselves* as provider — persisted provider still binds."""
    st = StateTransition()
    tx = _attach_sender_sig(_tx(BUYER, BUYER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": BUYER}), BUYER_KEY)
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        before = _snapshot(session)
        ok, err = _apply(st, session, tx, "rel-self")
        assert ok is False
        assert _snapshot(session) == before


def test_honest_release_works_at_v22(tmp_path):
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), PROVIDER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "rel-ok")
        assert ok is True, err
        bond = _bond(session)
        assert bond.status == "released" and bond.amount == 0


def test_release_missing_provider_refused_at_v22(tmp_path):
    st = StateTransition()
    tx = _attach_sender_sig(_tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1"}), PROVIDER_KEY)
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        before = _snapshot(session)
        ok, err = _apply(st, session, tx, "rel-noprovider")
        assert ok is False and "provider" in err
        assert _snapshot(session) == before


def test_release_wrong_recipient_refused_at_v22(tmp_path):
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, BUYER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), PROVIDER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        before = _snapshot(session)
        ok, err = _apply(st, session, tx, "rel-wrongto")
        assert ok is False
        assert _snapshot(session) == before


def test_release_nonzero_value_refused_at_v22(tmp_path):
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, PROVIDER, 7, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), PROVIDER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        before = _snapshot(session)
        ok, err = _apply(st, session, tx, "rel-value")
        assert ok is False
        assert _snapshot(session) == before


def test_release_unknown_bond_refused_at_v22(tmp_path):
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "nope", "provider": PROVIDER}), PROVIDER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "rel-unknown")
        assert ok is False and "unknown" in err


def test_release_null_expiry_refused_at_v22(tmp_path):
    """NULL locked_until fails closed at v22 (was immediately releasable)."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), PROVIDER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        bond = _bond(session)
        bond.locked_until = None
        session.add(bond)
        _accounts(session)
        session.commit()
        before = _snapshot(session)
        ok, err = _apply(st, session, tx, "rel-null")
        assert ok is False and "expiry" in err
        assert _snapshot(session) == before


def test_release_null_expiry_still_releases_below_v22(tmp_path):
    """Replay compat: pre-v22 NULL rows keep the legacy immediate release."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), PROVIDER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        bond = _bond(session)
        bond.locked_until = None
        session.add(bond)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "rel-null-v21", version=21)
        assert ok is True, err
        assert _bond(session).status == "released"


# --- BOND-LOCK-TOPUP-PROVIDER-MISMATCH ------------------------------------


def test_forged_topup_refused_at_v22(tmp_path):
    """Attacker tops up the victim's bond naming the victim as provider."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(BUYER, ESCROW, 100, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": PROVIDER, "lock_days": 30}),
        BUYER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        before = _snapshot(session)
        ok, err = _apply(st, session, tx, "topup-forge")
        assert ok is False and "provider" in err
        assert _snapshot(session) == before


def test_forged_topup_self_provider_refused_at_v22(tmp_path):
    """#1167 exploit shape: attacker names *themsself* as provider on the
    victim's bond_id — passes the v20 signer==payload.provider check, and
    only the persisted-provider binding at v22 refuses it."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(BUYER, ESCROW, 100, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": BUYER, "lock_days": 30}),
        BUYER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        before = _snapshot(session)
        ok, err = _apply(st, session, tx, "topup-self")
        assert ok is False
        assert _snapshot(session) == before


def test_honest_topup_applies_ceiling_at_v22(tmp_path):
    """Provider top-up: locked_until = min(now+days, created_at+MAX)."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, ESCROW, 100, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": PROVIDER, "lock_days": 3650}),
        PROVIDER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "topup-ok")
        assert ok is True, err
        bond = _bond(session)
        assert bond.amount == 5100
        # now + 3650d (2036-11) exceeds created_at(2026-01-01) + 3650d → ceiling binds.
        # SQLite round-trips datetimes naive; compare instants, not tzinfo.
        assert bond.locked_until.replace(tzinfo=UTC) == datetime(2026, 1, 1, tzinfo=UTC) + PROTOCOL_MAX_LOCK_DURATION


def test_topup_post_ceiling_refused_at_v22(tmp_path):
    """created_at + MAX already passed → top-up refused, amount unchanged."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, ESCROW, 100, "BOND_LOCK", {"bond_id": "bond-old", "provider": PROVIDER, "lock_days": 30}),
        PROVIDER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        session.add(
            Bond(
                chain_id=CHAIN,
                bond_id="bond-old",
                provider=PROVIDER,
                amount=100,
                locked_until=datetime(2016, 1, 1, tzinfo=UTC),
                status="active",
                created_tx_hash="h-old",
                created_at=datetime(2010, 1, 1, tzinfo=UTC),
                updated_at=datetime(2010, 1, 1, tzinfo=UTC),
            )
        )
        _accounts(session)
        session.commit()
        _snapshot(session)
        ok, err = _apply(st, session, tx, "topup-postceiling")
        assert ok is False and "horizon" in err
        # bond-old untouched; bond-par-1 untouched.
        old = session.exec(select(Bond).where(Bond.chain_id == CHAIN, Bond.bond_id == "bond-old")).first()
        assert old.amount == 100


def test_topup_exact_ceiling_boundary_refused_at_v22(tmp_path):
    """now == created_at + MAX is post-ceiling (boundary inclusive-exclusive → reject)."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, ESCROW, 100, "BOND_LOCK", {"bond_id": "bond-edge", "provider": PROVIDER, "lock_days": 30}),
        PROVIDER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        session.add(
            Bond(
                chain_id=CHAIN,
                bond_id="bond-edge",
                provider=PROVIDER,
                amount=100,
                locked_until=BLOCK_TIME - timedelta(days=1),
                status="active",
                created_tx_hash="h-edge",
                created_at=BLOCK_TIME - PROTOCOL_MAX_LOCK_DURATION,
                updated_at=BLOCK_TIME - PROTOCOL_MAX_LOCK_DURATION,
            )
        )
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "topup-edge")
        assert ok is False and "horizon" in err


def test_topup_shortening_own_lock_allowed_at_v22(tmp_path):
    """Provider may shorten their own lock — self-inflicted, spec-pinned."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, ESCROW, 50, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": PROVIDER, "lock_days": 1}),
        PROVIDER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "topup-shorten")
        assert ok is True, err
        bond = _bond(session)
        assert bond.locked_until.replace(tzinfo=UTC) == BLOCK_TIME + timedelta(days=1)
        assert bond.created_at.replace(tzinfo=UTC) == datetime(2026, 1, 1, tzinfo=UTC)  # immutable anchor


def test_forged_topup_self_provider_still_applies_below_v22(tmp_path):
    """Replay compat pin: at v21 the self-provider forged top-up applied —
    the exact pre-fix #1167 behavior (v20 only bound signer==payload,
    never the persisted bond.provider)."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(BUYER, ESCROW, 1, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": BUYER, "lock_days": 7}),
        BUYER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "topup-self-v21", version=21)
        assert ok is True, err
        assert _bond(session).amount == 5001


def test_forged_release_still_applies_below_v22(tmp_path):
    """Replay compat pin: at v21 the forged release succeeded with the bond
    effect skipped — the exact pre-fix exploit behavior."""
    st = StateTransition()
    tx = _attach_sender_sig(_tx(BUYER, BUYER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), BUYER_KEY)
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "rel-forge-v21", version=21)
        assert ok is True, err
        bond = _bond(session)
        assert bond.status == "active" and bond.amount == 5000


# --- remaining matrix rows: slash exception, ordering, creation, residual --


def test_slash_by_authority_unchanged_at_v22(tmp_path):
    """Matrix 17: BOND_SLASH stays authority-gated — provider irrelevant."""
    from .test_apply_parity import AUTH, AUTH_KEY, _BOND_BURN_ADDRESS

    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(AUTH, _BOND_BURN_ADDRESS, 0, "BOND_SLASH", {"bond_id": "bond-par-1", "provider": PROVIDER, "amount": 2000}),
        AUTH_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.add(Account(chain_id=CHAIN, address=AUTH, balance=10**9, nonce=0))
        session.add(ChainParameter(chain_id=CHAIN, parameter="bond_slash_authority", value=AUTH))
        session.commit()
        ok, err = _apply(st, session, tx, "slash-ok")
        assert ok is True, err
        bond = _bond(session)
        assert bond.status == "active" and bond.amount == 3000  # 5000 - 2000, still active


def test_front_run_release_then_victim_release(tmp_path):
    """Matrix 18: attacker's forged release rejected; the real provider's
    release in the same session still succeeds."""
    st = StateTransition()
    forged = _attach_sender_sig(
        _tx(BUYER, BUYER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), BUYER_KEY
    )
    honest = _attach_sender_sig(
        _tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER}), PROVIDER_KEY
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok1, _ = _apply(st, session, forged, "rel-forge-1")
        assert ok1 is False
        ok2, err2 = _apply(st, session, honest, "rel-honest-1")
        assert ok2 is True, err2
        assert _bond(session).status == "released"


def test_new_bond_creation_ceiling_at_v22(tmp_path):
    """Matrix 20: the ceiling formula applies on the create path too —
    locked_until = min(now + lock_days, now + MAX) = now + lock_days."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(PROVIDER, ESCROW, 1000, "BOND_LOCK", {"bond_id": "bond-new", "provider": PROVIDER, "lock_days": 30}),
        PROVIDER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "lock-new")
        assert ok is True, err
        bond = _bond(session, "bond-new")
        assert bond.provider == PROVIDER
        assert bond.locked_until.replace(tzinfo=UTC) == BLOCK_TIME + timedelta(days=30)
        assert bond.created_at.replace(tzinfo=UTC) == BLOCK_TIME


def test_squatting_residual_pin_at_v22(tmp_path):
    """Matrix 22 / §7: BOND-LOCK-ID-SQUATTING residual — a caller-chosen
    bond_id is still first-come-first-served; an attacker CAN create a
    bond under a victim-picked id (as provider=themselves). Documented
    residual, no normative change."""
    st = StateTransition()
    tx = _attach_sender_sig(
        _tx(BUYER, ESCROW, 100, "BOND_LOCK", {"bond_id": "victim-picked-id", "provider": BUYER, "lock_days": 30}),
        BUYER_KEY,
    )
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        ok, err = _apply(st, session, tx, "squat-pin")
        assert ok is True, err
        bond = _bond(session, "victim-picked-id")
        assert bond.provider == BUYER  # squatter owns the id going forward


# --- admission door parity (spec §6: same verdict at the door) -------------


def _door(session: Session, monkeypatch):
    """``_validate_transaction_admission`` wired to the test DB with the
    v22 gate armed at height 1 (next block resolves version 22)."""
    from contextlib import contextmanager

    from aitbc.utils import DEFAULT_TX_FEE_UNITS
    from aitbc_chain.config import settings
    from aitbc_chain.rpc.transactions import _validate_transaction_admission

    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
    monkeypatch.setattr(settings, "state_transition_v22_height", 1)

    def submit(tx: dict) -> None:
        base: dict = {
            "from": tx["from"],
            "to": tx.get("to", tx["from"]),
            "amount": tx.get("amount", tx.get("value", 0)),
            "value": tx.get("value", tx.get("amount", 0)),
            "fee": tx.get("fee", DEFAULT_TX_FEE_UNITS),
            "nonce": tx.get("nonce", 0),
            "type": tx["type"],
            "chain_id": CHAIN,
            "payload": tx.get("payload", {}),
        }
        _validate_transaction_admission(base, None)

    return submit


def test_door_refuses_forged_release_at_v22(tmp_path, monkeypatch):
    import pytest

    st_engine = _engine(tmp_path)
    with Session(st_engine) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        submit = _door(session, monkeypatch)
        forged = _tx(BUYER, BUYER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER})
        with pytest.raises(ValueError, match="provider"):
            submit(forged)


def test_door_refuses_forged_self_provider_topup_at_v22(tmp_path, monkeypatch):
    import pytest

    st_engine = _engine(tmp_path)
    with Session(st_engine) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        submit = _door(session, monkeypatch)
        forged = _tx(BUYER, ESCROW, 100, "BOND_LOCK", {"bond_id": "bond-par-1", "provider": BUYER, "lock_days": 30})
        with pytest.raises(ValueError):
            submit(forged)


def test_door_admits_honest_release_at_v22(tmp_path, monkeypatch):
    st_engine = _engine(tmp_path)
    with Session(st_engine) as session:
        _seed_bond(session)
        _accounts(session)
        session.commit()
        submit = _door(session, monkeypatch)
        honest = _tx(PROVIDER, PROVIDER, 0, "BOND_RELEASE", {"bond_id": "bond-par-1", "provider": PROVIDER})
        submit(honest)  # no exception = admitted
