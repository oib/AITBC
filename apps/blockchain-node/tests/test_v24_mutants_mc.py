"""#1314 MC1–MC7 composition-mutant legs (Gitea #1314 comment 22629, A's
INTEGRATED VERIFY PLAN §2; MC5 amended per c22767/c22828 — adjacent and
gap-2 legs at v>=22, not a ">=2 gap" window).

Each leg composes the #1307 v23 ``session.refresh`` sites with the #1314
v24 mechanisms (ParitySession expire-on-write, ``read_current_account``
authoritative scalar reads, R2 Transaction-row flush) and pins the
interaction — mutants are expressed with ``monkeypatch``/explicit sequence
reproduction rather than source edits, per the task constraints.

Per-V-site exposure table (MC2 deliverable — which sites #1307's
sender-only ``session.refresh`` incidentally heals vs which still diverge
once the #1314 layers are removed):

| V-site | account read | #1307 refresh covers it? | MC2 result |
|---|---|---|---|
| V1 escrow custody (state_transition.py:2205/:2250/:2733/:2780) | per-job escrow ``_escrow_address(job_id)`` | NO — non-sender account, refresh only ever touches ``sender_account`` | statically exposed (not run — needs full escrow-lock fixture) |
| V2 executor funding (:671) | governance executor candidates | NO — non-sender | statically exposed |
| V3 bond escrow (:436, ``bond_tx_verdict``) | ``_BOND_ESCROW_ADDRESS`` | NO | EMPIRICAL: exposed — verdict passes on the stale ORM 5000 where the authoritative read refuses at 4000 |
| V4 sender reads (:1968 BRIDGE_LOCK balance, :2026 nonce/balance) | tx sender | PARTIAL — the v23 tail ``flush+refresh`` (:2948-2949) heals the *retained sender object*, so a same-sender follow-up tx is masked; a recipient-turned-sender is NOT (no refresh ever touches it) and the v24 ``elif >= 23`` refresh branches are bypassed at block_version>=24 | EMPIRICAL: same-sender masked, ping-pong exposed |
| V5 proposer pre-check (poa.py ~:2861) | sender via ``account_map``/``read_current_account`` | NO — proposer path has no #1307 refresh site | statically exposed |

MC3 note: the precedence rule (boundary flush+refresh BEFORE any #1314
authoritative read) is simulated by reproducing the reordered sequence
in-test — a real source reorder was not required and none was made.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from aitbc_chain.base_models import Account, Bond, ChainParameter
from aitbc_chain.base_models import Transaction as ChainTransaction
from aitbc_chain.database import ParitySession, PROD_SESSION_KWARGS, prod_parity_sessionmaker
from aitbc_chain.state import state_transition as st_mod
from aitbc_chain.state.authoritative_reads import (
    prepare_account_for_orm_write,
    read_current_account,
)
from aitbc_chain.state.bridge_credit import sign_bridge_credit, sign_bridge_lock
from aitbc_chain.state.state_transition import StateTransition, bond_tx_verdict
from aitbc_chain.v24_rules import v24_rules_active

from .test_apply_parity import (
    _BOND_BURN_ADDRESS,
    _BOND_ESCROW_ADDRESS,
    AUTH_KEY,
    BUYER,
    BUYER_KEY,
    CHAIN,
    HEIGHT,
    PROVIDER,
    _attach_sender_sig,
    _hash,
    _new_engine,
    _seed_common,
    _tx,
)
from .test_tx_nonce_per_block_invariants import (
    ADDR_R,
    ADDR_S,
    AMT,
    BALANCE0,
    CHAIN as NCHAIN,
    FEE,
    KEY_R,
    NONCE0,
    _account_scalars,
    _apply,
    _bridge_lock_tx,
    _make_db,
    _signed_tx,
)
from .test_v24_authoritative_reads import (
    BLOCK_TIME,
    _engine,
    _pin_escrow_then_drop_balance,
    _release_verdict,
)

V24 = 24
MC_TS = datetime(2026, 11, 6, tzinfo=UTC)


def _seed_bond_parity(session: Session) -> None:
    """``_seed_bond`` variant that works under ``autoflush=False`` prod-parity
    sessions: the shared helper's ``session.get`` relies on autoflush to see
    the just-added escrow row, so this version flushes explicitly first.
    Same rows, same values."""
    session.add(Account(chain_id=CHAIN, address=_BOND_ESCROW_ADDRESS, balance=0, nonce=0))
    session.add(Account(chain_id=CHAIN, address=_BOND_BURN_ADDRESS, balance=0, nonce=0))
    session.add(
        Bond(
            chain_id=CHAIN,
            bond_id="bond-par-1",
            provider=PROVIDER,
            amount=5000,
            locked_until=datetime(2020, 1, 1, tzinfo=UTC),
            status="active",
            created_tx_hash=_hash("bond-lock", "bond-par-1"),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    session.flush()
    esc = session.get(Account, (CHAIN, _BOND_ESCROW_ADDRESS))
    assert esc is not None
    esc.balance = 5000
    session.flush()


# ---------------------------------------------------------------------------
# shared mutant machinery
# ---------------------------------------------------------------------------


def _orm_account_shim(session: Session, chain_id: str, address: str) -> tuple[int | None, int, bool]:
    """Pre-#1314 read semantics for ``read_current_account`` call sites.

    Every v24 call site was a ``session.get(Account, ...)`` + attribute read
    before layer 2 existed; this shim reproduces exactly that — including
    serving whatever the (possibly stale) identity map holds.
    """
    acct = session.get(Account, (chain_id, address))
    if acct is None:
        return None, 0, False
    return acct.balance, acct.nonce or 0, True


@pytest.fixture()
def layer1_expire_disabled(monkeypatch):
    """MC1/MC2 mutant: ParitySession expire-on-write becomes a no-op.

    Everything else — ``v24_rules_active`` context, ``read_current_account``,
    the #1307 refresh sites — stays live, so any surviving pin proves it does
    not secretly depend on Layer-1 identity-map expiry.
    """
    monkeypatch.setattr(ParitySession, "_expire_written_tables", lambda self, tables: None)


@pytest.fixture()
def pre1314_world(layer1_expire_disabled, monkeypatch):
    """MC2 mutant: the pre-#1314 world at block_version>=24 — no expire-on-
    write AND no authoritative scalar reads. Only the #1307 ``session.refresh``
    sites remain as freshness mechanisms. Used to measure which V-sites that
    refresh incidentally heals (the masking check)."""
    monkeypatch.setattr(st_mod, "read_current_account", _orm_account_shim)


# ---------------------------------------------------------------------------
# MC1 — expire-on-write removed; #1307 pins must still pass (equivalent mutant
# expected: the pins ride on V4 reads + the v23 tail refresh, not on expire)
# ---------------------------------------------------------------------------


def test_mc1_expire_disabled_mutant_is_observable(tmp_path, layer1_expire_disabled):
    """Sanity: with ``_expire_written_tables`` no-op'd, a clean identity-map
    instance is NOT expired by a raw write even inside the v24 context —
    otherwise the MC1 legs below would be vacuous."""
    engine = _engine(tmp_path)
    addr = "0xmc1acct"
    with prod_parity_sessionmaker(bind=engine)() as session:
        session.add(Account(chain_id=CHAIN, address=addr, balance=100, nonce=0))
        session.commit()
        obj = session.get(Account, (CHAIN, addr))
        assert obj is not None and obj.balance == 100
        with v24_rules_active():
            session.execute(
                text("UPDATE account SET balance = :b WHERE chain_id = :c AND address = :a"),
                {"b": 200, "c": CHAIN, "a": addr},
            )
        # Mutant active: no expiry -> the retained object still serves 100.
        assert obj.balance == 100
        session.rollback()


def test_mc1_p1_same_sender_pair_passes_at_v24_without_expire(tmp_path, layer1_expire_disabled):
    """#1307 T5/P1 shape at block_version=24: two sequential same-sender txs.

    With expire-on-write disabled the second tx still validates — the v24
    ``read_current_account`` sender read (V4) sees the raw-SQL post-tx1 row
    and the v23 tail ``flush+refresh`` keeps the retained object authoritative.
    A failure here would be a kill: a hidden dependency on Layer-1."""
    engine, _factory = _make_db(tmp_path / "mc1-p1.db")
    st = StateTransition()
    with prod_parity_sessionmaker(bind=engine)() as session:
        # _make_db seeds under its own chain id (NCHAIN).
        retained = session.get(Account, (NCHAIN, ADDR_S))
        assert retained is not None and retained.nonce == NONCE0

        ok1, err1 = _apply(st, session, _signed_tx(NONCE0, AMT, label="mc1-p1-a"), version=V24)
        assert ok1, err1
        ok2, err2 = _apply(st, session, _signed_tx(NONCE0 + 1, AMT, label="mc1-p1-b"), version=V24)
        assert ok2, f"second same-sender tx rejected without expire-on-write: {err2}"
        session.flush()
        assert _account_scalars(session) == (NONCE0 + 2, BALANCE0 - 2 * (AMT + FEE))
        assert retained.nonce == NONCE0 + 2
        assert retained.balance == BALANCE0 - 2 * (AMT + FEE)
        session.rollback()


def test_mc1_p2_recipient_sender_ping_pong_passes_at_v24_without_expire(tmp_path, layer1_expire_disabled):
    """#1307 M2/P2 shape at v24: S->R credit then R->S spend, twice.

    The recipient-turned-sender reads ride on V4 ``read_current_account`` —
    no identity-map freshness needed — so the pin holds with expire disabled."""
    engine, _factory = _make_db(tmp_path / "mc1-p2.db")
    st = StateTransition()
    with prod_parity_sessionmaker(bind=engine)() as session:
        s_obj = session.get(Account, (NCHAIN, ADDR_S))
        r_obj = session.get(Account, (NCHAIN, ADDR_R))
        assert s_obj is not None and r_obj is not None

        txs = [
            _signed_tx(NONCE0, 5_000_000, label="mc1-p2-s1"),
            _signed_tx(0, 1_000_000, label="mc1-p2-r1", key=KEY_R, sender=ADDR_R, recipient=ADDR_S),
            _signed_tx(NONCE0 + 1, 1_000, label="mc1-p2-s2"),
            _signed_tx(1, 1_000, label="mc1-p2-r2", key=KEY_R, sender=ADDR_R, recipient=ADDR_S),
        ]
        for tx in txs:
            ok, err = _apply(st, session, tx, version=V24)
            assert ok, f"{tx['tx_hash']}: {err}"
            session.flush()
        assert _account_scalars(session) == (NONCE0 + 2, BALANCE0 - 4_000_000 - 2 * FEE)
        assert _account_scalars(session, ADDR_R) == (2, 4_000_000 - 2 * FEE)
        session.rollback()


def test_mc1_bridge_lock_pair_rejected_at_v24_without_expire(tmp_path, layer1_expire_disabled):
    """#1307 M1 shape at v24: same-sender BRIDGE_LOCK pair. The first lock
    early-returns before the tail refresh, so its raw debit leaves the sender
    object stale — the second lock's rejection can ONLY come from the v24
    authoritative balance read (V4), not from refresh or expire."""
    engine, _factory = _make_db(tmp_path / "mc1-bridge.db")
    st = StateTransition()
    with prod_parity_sessionmaker(bind=engine)() as session:
        session.add(
            ChainParameter(
                chain_id=NCHAIN,
                parameter="bridge_release_authority",
                value=ADDR_S,
                applied_height=None,
            )
        )
        session.flush()
        s_obj = session.get(Account, (NCHAIN, ADDR_S))
        assert s_obj is not None

        lock1 = _bridge_lock_tx(transfer_id="mc1-lock-1", amount=BALANCE0 - FEE - 100, label="mc1-lock-1")
        lock2 = _bridge_lock_tx(transfer_id="mc1-lock-2", amount=1, label="mc1-lock-2", nonce=NONCE0 + 1)

        ok, err = _apply(st, session, lock1, version=V24)
        assert ok, err
        session.flush()
        assert _account_scalars(session) == (NONCE0 + 1, 100)
        # The retained object is stale here (BRIDGE_LOCK early-returns before
        # the tail refresh, and the mutant disabled expire-on-write) — it
        # still serves the pre-lock values while the DB row moved on.
        assert s_obj.balance == BALANCE0 and s_obj.nonce == NONCE0

        ok2, err2 = _apply(st, session, lock2, version=V24)
        assert not ok2, f"second lock must reject on the post-first balance: {err2}"
        assert "Insufficient balance" in err2
        session.flush()
        assert _account_scalars(session) == (NONCE0 + 1, 100)
        session.rollback()


# ---------------------------------------------------------------------------
# MC2 — masking check: pre-#1314 world (no expire, ORM-shim reads) at v24.
# Which V-sites does the surviving #1307 refresh incidentally heal?
# ---------------------------------------------------------------------------


def test_mc2_v4_same_sender_masked_by_tail_refresh(tmp_path, pre1314_world):
    """V4 sender reads, same-sender pair: MASKED. The v23 tail
    ``flush+refresh`` at the end of tx1 reloads the retained sender object,
    so tx2's (shimmed, ORM-shaped) read already sees post-tx1 state — the
    pin passes even with both #1314 layers removed."""
    engine, _factory = _make_db(tmp_path / "mc2-same.db")
    st = StateTransition()
    with prod_parity_sessionmaker(bind=engine)() as session:
        retained = session.get(Account, (NCHAIN, ADDR_S))
        assert retained is not None
        ok1, err1 = _apply(st, session, _signed_tx(NONCE0, AMT, label="mc2-sa"), version=V24)
        assert ok1, err1
        ok2, err2 = _apply(st, session, _signed_tx(NONCE0 + 1, AMT, label="mc2-sb"), version=V24)
        assert ok2, f"unexpected: same-sender pair should be masked by tail refresh: {err2}"
        session.flush()
        assert _account_scalars(session) == (NONCE0 + 2, BALANCE0 - 2 * (AMT + FEE))
        session.rollback()


def test_mc2_v4_ping_pong_exposed_without_layer2(tmp_path, pre1314_world):
    """V4 sender reads, recipient->sender: EXPOSED. The credited recipient's
    ORM object is never refreshed (#1307 refreshes senders only) and the v24
    ``elif >= 23`` refresh branches are bypassed at block_version=24, so the
    shimmed read serves the stale pre-credit balance and the tx is rejected —
    the masking is partial, not coverage."""
    engine, _factory = _make_db(tmp_path / "mc2-pingpong.db")
    st = StateTransition()
    with prod_parity_sessionmaker(bind=engine)() as session:
        s_obj = session.get(Account, (NCHAIN, ADDR_S))
        r_obj = session.get(Account, (NCHAIN, ADDR_R))
        assert s_obj is not None and r_obj is not None

        tx1 = _signed_tx(NONCE0, 5_000_000, label="mc2-pp-s1")
        tx2 = _signed_tx(0, 1_000_000, label="mc2-pp-r1", key=KEY_R, sender=ADDR_R, recipient=ADDR_S)

        ok1, err1 = _apply(st, session, tx1, version=V24)
        assert ok1, err1
        session.flush()
        # DB truth vs stale ORM object — the divergence the shim exposes.
        assert _account_scalars(session, ADDR_R) == (0, 5_000_000)
        assert r_obj.balance == 0

        ok2, err2 = _apply(st, session, tx2, version=V24)
        assert not ok2, "expected stale-balance rejection without layer 2"
        assert "Insufficient balance" in err2
        session.rollback()


def test_mc2_v3_bond_escrow_verdict_exposed_without_layer2(tmp_path, pre1314_world):
    """V3 bond-escrow verdict: EXPOSED. ``bond_tx_verdict`` at v24 with the
    authoritative read shimmed falls back to the pinned stale ORM object
    (5000) and returns None where the real read refuses (4000 < 5000).
    #1307's sender refresh never touches the bond escrow account."""
    engine = _engine(tmp_path)
    with prod_parity_sessionmaker(bind=engine)() as session:
        _seed_bond_parity(session)
        session.commit()
        pinned = _pin_escrow_then_drop_balance(session)
        err = bond_tx_verdict(
            session,
            CHAIN,
            "BOND_RELEASE",
            {"bond_id": "bond-par-1", "provider": PROVIDER},
            PROVIDER,
            PROVIDER,
            0,
            block_version=V24,
            block_time=BLOCK_TIME,
        )
        assert err is None, f"expected stale-pass divergence, got refusal: {err}"
        assert pinned.balance == 5000
        session.rollback()


def test_mc2_v3_control_authoritative_read_refuses(tmp_path):
    """Control leg (no mutant): the same fixture with layer 2 live refuses —
    isolates that the divergence above is caused by the removed read, not by
    the fixture."""
    engine = _engine(tmp_path)
    with prod_parity_sessionmaker(bind=engine)() as session:
        _seed_bond_parity(session)
        session.commit()
        _pin_escrow_then_drop_balance(session)
        err = _release_verdict(session, V24)
        assert err is not None and "escrow balance 4000" in err
        session.rollback()


# ---------------------------------------------------------------------------
# MC3 — precedence: authoritative read BEFORE the boundary flush+refresh must
# diverge; correct order (flush -> refresh -> read) converges. Simulated by
# reproducing the reordered sequence in-test (no source reorder needed).
# ---------------------------------------------------------------------------


def _seed_mc3_account(engine, balance: int = 1000) -> None:
    with prod_parity_sessionmaker(bind=engine)() as session:
        session.add(Account(chain_id=CHAIN, address="0xmc3acct", balance=balance, nonce=0))
        session.commit()


def test_mc3_read_before_boundary_flush_refresh_loses_pending_write(tmp_path):
    """Wrong order — ``read_current_account`` hoisted ABOVE the #1307-style
    ``flush -> refresh`` boundary on a session carrying a pending ORM write:

    * the scalar read sees pre-flush DB state (the +777 mint residue is
      invisible — raw SELECT does not consult dirty attributes);
    * the subsequent ``session.refresh`` then DISCARDS the pending write
      (verified semantics under ``autoflush=False``: refresh reloads DB
      state over dirty attributes — the #1307 M5 pin's premise).

    Net effect: the pending +777 is silently lost and the boundary read
    returned a value that never matched any committed state. The correct
    order (flush -> refresh -> read) preserves and observes it."""
    # _engine derives the db filename from the directory; use two subdirs.
    (Path(tmp_path) / "wrong").mkdir()
    (Path(tmp_path) / "right").mkdir()
    engine_wrong = _engine(Path(tmp_path) / "wrong")
    engine_right = _engine(Path(tmp_path) / "right")
    _seed_mc3_account(engine_wrong)
    _seed_mc3_account(engine_right)

    # --- wrong order: read_current_account BEFORE flush+refresh ---
    with prod_parity_sessionmaker(bind=engine_wrong)() as session:
        acct = session.get(Account, (CHAIN, "0xmc3acct"))
        assert acct is not None
        acct.balance += 777  # pending ORM residue (receipt-mint shape, #1307 M5)
        early_bal, _n, _e = read_current_account(session, CHAIN, "0xmc3acct")
        session.refresh(acct)  # boundary refresh runs AFTER the authoritative read
        session.flush()
        session.commit()
        wrong_committed = acct.balance
    assert early_bal == 1000  # scalar read never saw the pending +777
    assert wrong_committed == 1000  # refresh discarded it — divergence

    # --- correct order: flush -> refresh -> read ---
    with prod_parity_sessionmaker(bind=engine_right)() as session:
        acct = session.get(Account, (CHAIN, "0xmc3acct"))
        assert acct is not None
        acct.balance += 777
        session.flush()  # persist pending ORM write first (the #1307 tail order)
        session.refresh(acct)
        late_bal, _n2, _e2 = read_current_account(session, CHAIN, "0xmc3acct")
        session.commit()
        right_committed = acct.balance
    assert late_bal == 1777
    assert right_committed == 1777
    assert wrong_committed != right_committed


# ---------------------------------------------------------------------------
# MC4 — refresh on a detached post-rollback object raises; v24 boundary
# checks must not depend on refresh reachability (Q6 residue class).
# ---------------------------------------------------------------------------


def test_mc4_refresh_detached_raises_but_v24_reads_converge(tmp_path):
    """Post-rollback residue shapes: an expunged object and an object added
    inside a rolled-back savepoint (``apply_transaction_guarded`` expunges
    ORM objects added inside on rollback) are both detached — ``session.refresh``
    raises ``InvalidRequestError`` on them. The v24 boundary machinery
    (``read_current_account``, ``prepare_account_for_ORM_write``,
    ``bond_tx_verdict``) never touches the detached reference and still
    returns authoritative state."""
    engine = _engine(tmp_path)
    with prod_parity_sessionmaker(bind=engine)() as session:
        _seed_bond_parity(session)
        session.commit()
        pinned = _pin_escrow_then_drop_balance(session)  # ORM 5000 vs DB 4000

        # Residue shape 1: expunged (detached) persistent object.
        session.expunge(pinned)
        with pytest.raises(InvalidRequestError):
            session.refresh(pinned)

        # Residue shape 2: object added inside a savepoint that rolled back —
        # mirrors apply_transaction_guarded's snapshot restore.
        sp = session.begin_nested()
        ghost = Account(chain_id=CHAIN, address="0xmc4ghost", balance=1, nonce=0)
        session.add(ghost)
        session.flush()
        sp.rollback()
        assert ghost not in session
        with pytest.raises(InvalidRequestError):
            session.refresh(ghost)

        # v24 boundary verdict does not need refresh reachability: the
        # authoritative scalar read still refuses on the real 4000.
        err = _release_verdict(session, V24)
        assert err is not None and "escrow balance 4000" in err
        bal, _nonce, exists = read_current_account(session, CHAIN, _BOND_ESCROW_ADDRESS)
        assert (bal, exists) == (4000, True)
        session.rollback()


def test_mc4_boundary_helpers_ignore_detached_residue(tmp_path):
    """``read_current_account`` and ``prepare_account_for_ORM_write`` on a
    session carrying detached residue return authoritative values — the
    v24 checks are scalar/identity-map based, never refresh-reachability
    based."""
    engine = _engine(tmp_path)
    addr = "0xmc4acct"
    with prod_parity_sessionmaker(bind=engine)() as session:
        session.add(Account(chain_id=CHAIN, address=addr, balance=321, nonce=4))
        session.commit()
        obj = session.get(Account, (CHAIN, addr))
        assert obj is not None
        session.expunge(obj)
        with pytest.raises(InvalidRequestError):
            session.refresh(obj)

        bal, nonce, exists = read_current_account(session, CHAIN, addr)
        assert (bal, nonce, exists) == (321, 4, True)
        prep = prepare_account_for_orm_write(session, CHAIN, addr)
        assert prep is not None and prep.balance == 321 and prep.nonce == 4
        session.rollback()


# ---------------------------------------------------------------------------
# MC5 — R2 Transaction-row flush x #1307 refresh interaction.
# BRIDGE_LOCK -> BRIDGE_REFUND same block: the refund's v6 lock binding reads
# the LOCK's Transaction row; R2's add+flush (v>=24) is what makes it visible
# on the proposer schedule. The earlier TRANSFER exercises the v23 tail
# refresh — the two mechanisms must not interfere.
# ---------------------------------------------------------------------------


def _mc5_lock_tx(label: str, amount: int, nonce: int = 0) -> dict[str, Any]:
    """Authority-signed BRIDGE_LOCK on the parity chain (BUYER sender)."""
    tx = _tx(
        BUYER,
        "bridge_lock",
        amount,
        "BRIDGE_LOCK",
        {
            "transfer_id": label,
            "target_chain": "ait-side",
            "target_recipient": PROVIDER,
            "asset": "AIT",
            "amount": amount,
        },
    )
    # Sender signature first, tx_hash after — the _bridge_lock_tx convention:
    # the signed projection excludes tx_hash, which is bound separately.
    _attach_sender_sig(tx, BUYER_KEY)
    tx["tx_hash"] = _hash("mc5-lock", label)
    tx["bridge_signature"] = sign_bridge_lock(tx, tx["tx_hash"], AUTH_KEY)
    return tx


def _mc5_refund_tx(lock_hash: str, label: str) -> dict[str, Any]:
    """Authority-signed BRIDGE_REFUND naming ``lock_hash`` (pseudo-sender)."""
    tx: dict[str, Any] = {
        "from": "bridge_refund",
        "to": BUYER,
        "amount": 9000,
        "value": 9000,
        "fee": 0,
        "nonce": 0,
        "type": "BRIDGE_REFUND",
        "chain_id": CHAIN,
        "tx_hash": _hash("mc5-refund", label),
        "signature": "",
        "payload": {"transfer_id": "xfer-par-1", "asset": "AIT", "lock_tx_hash": lock_hash},
    }
    tx["lock_tx_hash"] = lock_hash
    tx["payload"]["bridge_signature"] = sign_bridge_credit(tx, tx["tx_hash"], AUTH_KEY)
    return tx


def _mc5_transfer_tx(label: str) -> dict[str, Any]:
    tx = _tx(BUYER, PROVIDER, 100, "TRANSFER")
    _attach_sender_sig(tx, BUYER_KEY)
    tx["tx_hash"] = _hash("mc5-transfer", label)
    return tx


def _mc5_add_tx_row(session: Session, tx: dict[str, Any], *, height: int) -> None:
    """Reproduce the proposer's per-tx Transaction-row insert verbatim
    (poa.py ~:2959-2978): raw ``from``/``to``, envelope copy, sealed
    ``block_height``/``status='confirmed'`` — the row ``_refund_lock_record``
    resolves."""
    payload = tx.get("payload")
    session.add(
        ChainTransaction(
            chain_id=CHAIN,
            tx_hash=tx["tx_hash"],
            sender=tx.get("from", ""),
            recipient=tx.get("to", ""),
            payload=payload if isinstance(payload, dict) else {},
            envelope=dict(tx),
            value=tx.get("amount", tx.get("value", 0)),
            fee=tx.get("fee", 0),
            nonce=tx.get("nonce", 0),
            timestamp=MC_TS.isoformat(),
            block_height=height,
            status="confirmed",
            type=(tx.get("type") or "TRANSFER").upper(),
        )
    )


def _mc5_seed(engine) -> None:
    with Session(engine) as s:
        _seed_common(s)
        s.commit()


def _mc5_account(engine, address: str) -> tuple[int, int]:
    with Session(engine) as s:
        row = s.execute(
            text("SELECT nonce, balance FROM account WHERE chain_id = :c AND address = :a"),
            {"c": CHAIN, "a": address},
        ).one()
        return int(row[0]), int(row[1])


def _mc5_apply(st: StateTransition, session: Session, tx: dict[str, Any], version: int):
    data = dict(tx)
    data.setdefault("value", data.get("amount", 0))
    return st.apply_transaction_guarded(
        session, CHAIN, data, tx["tx_hash"], block_version=version, block_height=HEIGHT, block_time=MC_TS
    )


def test_mc5_r2_flush_makes_same_block_lock_visible_to_refund_v24(tmp_path):
    """Adjacent LOCK->REFUND at v24 with the R2 add+flush schedule: the
    TRANSFER first exercises the v23 tail ``flush+refresh``; the LOCK's
    Transaction row is added AND flushed before the REFUND's apply, so its
    v6 lock binding resolves. All three apply; account state is exact."""
    engine = _new_engine(tmp_path, "mc5-flush")
    _mc5_seed(engine)
    st = StateTransition()
    transfer = _mc5_transfer_tx("t1")
    lock = _mc5_lock_tx("xfer-mc5-1", 9000)
    refund = _mc5_refund_tx(lock["tx_hash"], "r1")

    with prod_parity_sessionmaker(bind=engine)() as session:
        ok, err = _mc5_apply(st, session, transfer, V24)
        assert ok, f"transfer: {err}"  # hits the >=23 tail flush+refresh
        ok, err = _mc5_apply(st, session, lock, V24)
        assert ok, f"lock: {err}"
        _mc5_add_tx_row(session, lock, height=HEIGHT)
        session.flush()  # #1314 R2: v>=24 explicit flush
        ok, err = _mc5_apply(st, session, refund, V24)
        assert ok, f"refund must see the flushed same-block lock row: {err}"
        session.commit()

    # BUYER: -100-fee (transfer) -(9000+fee) (lock) +9000 (refund credit),
    # nonce +1 per sender-debit path (transfer + lock).
    nonce, bal = _mc5_account(engine, BUYER)
    assert nonce == 2
    assert bal == 10_000_000 - 100 - 2 * FEE
    assert _mc5_account(engine, PROVIDER) == (0, 10_000_000 + 100)


def test_mc5_without_row_visibility_refund_rejected_then_recovers(tmp_path):
    """Control/mutant leg: same sequence but the LOCK's Transaction row is
    NEVER added before the REFUND (the pre-R2 proposer schedule — rows were
    collected and inserted only after the whole tx loop). The refund's v6
    binding finds no sealed BRIDGE_LOCK and is rejected; adding+flushing the
    row afterwards makes the identical envelope apply — proving the flush
    schedule, not the tx content, was the divergence."""
    engine = _new_engine(tmp_path, "mc5-deferred")
    _mc5_seed(engine)
    st = StateTransition()
    transfer = _mc5_transfer_tx("t1")
    lock = _mc5_lock_tx("xfer-mc5-2", 9000)
    refund = _mc5_refund_tx(lock["tx_hash"], "r1")

    with prod_parity_sessionmaker(bind=engine)() as session:
        ok, err = _mc5_apply(st, session, transfer, V24)
        assert ok, err
        ok, err = _mc5_apply(st, session, lock, V24)
        assert ok, err
        # No Transaction row added — proposer pre-R2 shape.
        ok, err = _mc5_apply(st, session, refund, V24)
        assert not ok, "refund must not resolve a lock row that was never written"
        assert "sealed BRIDGE_LOCK" in err

        # Recovery: once the row lands (next block's schedule / R2 flush),
        # the identical envelope applies.
        _mc5_add_tx_row(session, lock, height=HEIGHT)
        session.flush()
        ok, err = _mc5_apply(st, session, refund, V24)
        assert ok, f"refund retry after row visibility: {err}"
        session.commit()

    nonce, bal = _mc5_account(engine, BUYER)
    assert (nonce, bal) == (2, 10_000_000 - 100 - 2 * FEE)


def test_mc5_pending_row_visible_via_nested_flush_at_v22(tmp_path):
    """v22/v23 window leg (c22775 amendment): below the v24 R2 gate the
    importer/proposer schedule leaves the Transaction row PENDING — but at
    v>=22 ``apply_transaction_guarded``'s ``begin_nested`` flushes it before
    the refund's validate, so the adjacent case still resolves. Pins that
    the R2 flush does not change pre-v24 semantics."""
    engine = _new_engine(tmp_path, "mc5-v22")
    _mc5_seed(engine)
    st = StateTransition()
    transfer = _mc5_transfer_tx("t1")
    lock = _mc5_lock_tx("xfer-mc5-3", 9000)
    refund = _mc5_refund_tx(lock["tx_hash"], "r1")

    with prod_parity_sessionmaker(bind=engine)() as session:
        ok, err = _mc5_apply(st, session, transfer, 22)
        assert ok, err
        ok, err = _mc5_apply(st, session, lock, 22)
        assert ok, err
        _mc5_add_tx_row(session, lock, height=HEIGHT)  # pending — no v24 flush
        ok, err = _mc5_apply(st, session, refund, 22)
        assert ok, f"v22 nested-savepoint flush must surface the pending lock row: {err}"
        session.commit()

    nonce, bal = _mc5_account(engine, BUYER)
    assert (nonce, bal) == (2, 10_000_000 - 100 - 2 * FEE)


def test_mc5_below_v22_pending_row_stays_invisible_legacy(tmp_path):
    """Below-v22 control: ``apply_transaction_guarded`` delegates without a
    savepoint, so nothing flushes the pending Transaction row before the
    refund's validate — the lock binding fails closed exactly as legacy
    replay expects. Pins that v24 rules (and the R2 flush) do not leak
    below their gates."""
    engine = _new_engine(tmp_path, "mc5-v21")
    _mc5_seed(engine)
    st = StateTransition()
    transfer = _mc5_transfer_tx("t1")
    lock = _mc5_lock_tx("xfer-mc5-4", 9000)
    refund = _mc5_refund_tx(lock["tx_hash"], "r1")

    with prod_parity_sessionmaker(bind=engine)() as session:
        ok, err = _mc5_apply(st, session, transfer, 21)
        assert ok, err
        ok, err = _mc5_apply(st, session, lock, 21)
        assert ok, err
        _mc5_add_tx_row(session, lock, height=HEIGHT)  # pending, never flushed
        ok, err = _mc5_apply(st, session, refund, 21)
        assert not ok, "v21 must keep the legacy invisible-row refusal"
        assert "sealed BRIDGE_LOCK" in err
        session.rollback()


# ---------------------------------------------------------------------------
# MC6 — golden-engine session-config parity: refresh behaves identically
# under prod-parity config vs a divergent sessionmaker, and the golden
# engine's open_session is pinned to prod_parity_sessionmaker.
# ---------------------------------------------------------------------------


def test_mc6_golden_engine_uses_prod_parity_sessionmaker():
    """Source pin: ``tests/golden/engine.py::open_session`` must construct
    sessions via ``prod_parity_sessionmaker`` — the #1314 parity fix. A
    divergent config (autoflush/expire_on_commit defaults) is exactly the
    masking class the golden corpus re-record had to eliminate."""
    from .golden import engine as golden_engine

    src = inspect.getsource(golden_engine.open_session)
    assert "prod_parity_sessionmaker" in src, (
        "golden engine open_session no longer uses prod_parity_sessionmaker — session-config parity with production is broken"
    )
    assert PROD_SESSION_KWARGS["autoflush"] is False
    assert PROD_SESSION_KWARGS["expire_on_commit"] is False
    assert PROD_SESSION_KWARGS["class_"] is ParitySession


def test_mc6_refresh_converges_across_session_configs(tmp_path):
    """Functional leg: the #1307 ``session.refresh`` reload yields identical
    post-write values under the prod-parity sessionmaker and a divergent
    default sessionmaker — refresh is config-independent — while the
    *unrefreshed* reads diverge (expire_on_commit=False retains stale attrs
    across commit; the divergent config expires them). This is why the pins
    must run on prod-parity sessions to mean anything."""
    engine = _engine(tmp_path)
    addr = "0xmc6acct"
    with prod_parity_sessionmaker(bind=engine)() as session:
        session.add(Account(chain_id=CHAIN, address=addr, balance=100, nonce=0))
        session.commit()

    results = {}
    for tag, maker in (
        ("prod", prod_parity_sessionmaker(bind=engine)),
        ("divergent", sessionmaker(bind=engine)),
    ):
        with maker() as session:
            obj = session.get(Account, (CHAIN, addr))
            assert obj is not None and obj.balance == 100
            session.execute(
                text("UPDATE account SET balance = :b WHERE chain_id = :c AND address = :a"),
                {"b": 200, "c": CHAIN, "a": addr},
            )
            # Unrefreshed read: BOTH configs serve the stale identity-map
            # value here (plain Session has no expire-on-write either).
            stale = obj.balance
            session.refresh(obj)
            fresh = obj.balance
            session.rollback()
        results[tag] = (stale, fresh)

    assert results["prod"] == results["divergent"] == (100, 200)

    # Commit-boundary divergence the prod config deliberately keeps: after
    # commit, expire_on_commit=False retains attributes (stale window), the
    # divergent config expires them. refresh converges both to DB truth.
    with prod_parity_sessionmaker(bind=engine)() as session:
        obj = session.get(Account, (CHAIN, addr))
        assert obj is not None
        session.execute(
            text("UPDATE account SET balance = :b WHERE chain_id = :c AND address = :a"),
            {"b": 300, "c": CHAIN, "a": addr},
        )
        session.commit()
        prod_post_commit = obj.balance  # stale: expire_on_commit=False, no v24 ctx
        session.refresh(obj)
        assert obj.balance == 300
        session.rollback()
    with sessionmaker(bind=engine)() as session:
        obj = session.get(Account, (CHAIN, addr))
        assert obj is not None
        session.execute(
            text("UPDATE account SET balance = :b WHERE chain_id = :c AND address = :a"),
            {"b": 400, "c": CHAIN, "a": addr},
        )
        session.commit()
        div_post_commit = obj.balance  # expire_on_commit=True -> already 400
        session.rollback()
    # The configs genuinely diverge pre-refresh: prod retains the pre-write
    # attribute (100) across commit; the divergent session reloaded (400).
    assert prod_post_commit == 100
    assert div_post_commit == 400


# ---------------------------------------------------------------------------
# MC7 — v23-unarmed control: identical discriminating legs below block_version
# 24 preserve legacy/stale behavior — the v24 rules do not leak.
# ---------------------------------------------------------------------------


def test_mc7_expire_inert_outside_v24_context(tmp_path):
    """ParitySession expire-on-write is gated on ``v24_rules_is_active()``:
    the same raw write outside the v24 context leaves the clean instance
    stale (legacy), inside the context it expires (v24). One session, both
    halves — proves the gate, not just the mechanism."""
    engine = _engine(tmp_path)
    addr = "0xmc7acct"
    with prod_parity_sessionmaker(bind=engine)() as session:
        session.add(Account(chain_id=CHAIN, address=addr, balance=100, nonce=0))
        session.commit()
        obj = session.get(Account, (CHAIN, addr))
        assert obj is not None

        # Outside v24 context: no expiry — legacy stale read preserved.
        session.execute(
            text("UPDATE account SET balance = :b WHERE chain_id = :c AND address = :a"),
            {"b": 200, "c": CHAIN, "a": addr},
        )
        assert obj.balance == 100

        # Inside v24 context: expire fires — next access reloads DB truth.
        with v24_rules_active():
            session.execute(
                text("UPDATE account SET balance = :b WHERE chain_id = :c AND address = :a"),
                {"b": 300, "c": CHAIN, "a": addr},
            )
        assert obj.balance == 300
        session.rollback()


def test_mc7_v22_same_sender_stale_rejection_preserved(tmp_path):
    """v22 control on the prod-parity session: the same retained-session
    second-tx shape keeps the historical ``Invalid nonce`` rejection — no
    v23 refresh, no v24 reads."""
    engine, _factory = _make_db(tmp_path / "mc7-v22.db")
    st = StateTransition()
    with prod_parity_sessionmaker(bind=engine)() as session:
        retained = session.get(Account, (NCHAIN, ADDR_S))
        assert retained is not None
        ok1, err1 = _apply(st, session, _signed_tx(NONCE0, AMT, label="mc7-v22-a"), version=22)
        assert ok1, err1
        ok2, err2 = _apply(st, session, _signed_tx(NONCE0 + 1, AMT, label="mc7-v22-b"), version=22)
        assert not ok2, "v22 must keep the pre-fix stale-read rejection"
        assert "Invalid nonce" in err2
        session.rollback()


def test_mc7_v22_ping_pong_stale_rejection_preserved(tmp_path):
    """v22 ping-pong control: the credited recipient's stale balance rejects
    its next outbound tx — the pre-v23/v24 divergence window is pinned, not
    fixed."""
    engine, _factory = _make_db(tmp_path / "mc7-v22pp.db")
    st = StateTransition()
    with prod_parity_sessionmaker(bind=engine)() as session:
        s_obj = session.get(Account, (NCHAIN, ADDR_S))
        r_obj = session.get(Account, (NCHAIN, ADDR_R))
        assert s_obj is not None and r_obj is not None
        tx1 = _signed_tx(NONCE0, 5_000_000, label="mc7-v22pp-s1")
        tx2 = _signed_tx(0, 1_000_000, label="mc7-v22pp-r1", key=KEY_R, sender=ADDR_R, recipient=ADDR_S)
        ok1, err1 = _apply(st, session, tx1, version=22)
        assert ok1, err1
        session.flush()
        assert r_obj.balance == 0  # stale: no refresh below v23
        ok2, err2 = _apply(st, session, tx2, version=22)
        assert not ok2, "v22 must keep the stale-recipient rejection"
        assert "Insufficient balance" in err2
        session.rollback()


def test_mc7_v23_bond_verdict_keeps_orm_divergence(tmp_path):
    """v23 control: the same stale-escrow fixture at block_version=23 keeps
    the pre-v24 ORM verdict (passes on stale 5000) — the authoritative read
    is gated >=24 and does not leak into replayed v23 history."""
    engine = _engine(tmp_path)
    with prod_parity_sessionmaker(bind=engine)() as session:
        _seed_bond_parity(session)
        session.commit()
        pinned = _pin_escrow_then_drop_balance(session)
        assert _release_verdict(session, 23) is None
        assert pinned.balance == 5000
        session.rollback()
