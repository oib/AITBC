"""#1307 — same-sender sequential-tx invariants at ``block_version >= 23``.

Root cause pinned here: ``apply_transaction`` debits the sender and bumps
its nonce with raw ``UPDATE account ...`` SQL, which bypasses SQLAlchemy's
identity map. The retained ``Account`` object keeps its pre-update
attributes, so a second same-sender tx applied later in the same session
(a proposer block, an import block) read the stale nonce and was rejected
``Invalid nonce`` even though its signed envelope was correct. The fix
reloads the sender row at the two validation read sites and before the
per-block diagnostic nonce cache is recorded — gated to ``>= 23``. The
v22 control at the bottom pins that the stale read still applies below
the gate.

Cases follow the #1307 spec (c21379) T1-T10 plus a v22 control and a
success-tail failure pin. All applies run the sequential path — the
parallel path is version-capped at v8 and unreachable at v23.

Scope note: the refresh is gated to ``block_version >= 23``. ``<= 22``
apply outcomes are preserved byte-for-byte; ``>= 23`` same-session apply
outcomes change by design (that is the fix), and whether sealed v23
history requires replay/activation adjudication is an AD question this
change does not settle.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine, select

from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Block
from aitbc_chain.base_models import Transaction as ChainTransaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state import side_root_shadow
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import (
    StateTransition,
    get_state_transition,
    use_account_nonce_override,
)
from aitbc_chain.sync import ChainSync

CHAIN = "nonce-inv-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
VERSION = 23

KEY_S = "0x" + "11" * 32
ADDR_S = derive_ethereum_address(KEY_S)
ADDR_R = derive_ethereum_address("0x" + "33" * 32)

NONCE0 = 5
BALANCE0 = 10**9
FEE = DEFAULT_TX_FEE_UNITS
AMT = 100


def _tx_hash(label: str) -> str:
    return "0x" + hashlib.sha256(label.encode()).hexdigest()


def _signed_tx(
    nonce: int,
    amount: int,
    *,
    fee: int = FEE,
    tx_type: str = "TRANSFER",
    payload: dict[str, Any] | None = None,
    label: str = "tx",
) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": ADDR_S,
        "to": ADDR_R,
        "amount": amount,
        "fee": fee,
        "nonce": nonce,
        "payload": payload or {},
        "type": tx_type,
        "chain_id": CHAIN,
        "tx_hash": _tx_hash(f"{label}-{nonce}-{amount}-{fee}-{tx_type}"),
    }
    tx["signature"] = sign_transaction_data(tx, KEY_S)
    return tx


def _apply_data(tx: dict[str, Any]) -> dict[str, Any]:
    """Caller-side ``amount`` -> ``value`` normalisation, as the proposer and
    importer both do before ``apply_transaction_guarded``."""
    data = dict(tx)
    data.setdefault("value", data.get("amount", 0))
    return data


def _apply(st: StateTransition, session: Session, tx: dict[str, Any], *, version: int = VERSION, height: int = 1):
    data = _apply_data(tx)
    return st.apply_transaction_guarded(session, CHAIN, data, data["tx_hash"], block_version=version, block_height=height)


def _make_db(db_path) -> tuple:
    engine = create_engine(f"sqlite:///{db_path}")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_S, balance=BALANCE0, nonce=NONCE0))
        session.add(Account(chain_id=CHAIN, address=ADDR_R, balance=0, nonce=0))
        session.add(
            Block(
                chain_id=CHAIN,
                height=0,
                hash="0x" + "00" * 32,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=T0,
                tx_count=0,
            )
        )
        session.flush()
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 0)).one()
        genesis.state_root = compute_state_root_full(session, CHAIN)
        session.commit()
    return engine, factory


@pytest.fixture()
def fixture_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    return _make_db(tmp_path / "chain.db")


def _account_scalars(session: Session, address: str = ADDR_S) -> tuple[int, int]:
    """Raw scalar read — DB truth inside the open transaction, bypassing the
    ORM identity map entirely."""
    row = session.execute(
        text("SELECT nonce, balance FROM account WHERE chain_id = :c AND address = :a"),
        {"c": CHAIN, "a": address},
    ).one()
    return int(row[0]), int(row[1])


def _account(engine, address: str = ADDR_S) -> Account | None:
    with Session(engine) as session:
        return session.get(Account, (CHAIN, address))


def _tx_status(engine, tx_hash: str) -> str | None:
    with Session(engine) as session:
        row = session.exec(
            select(ChainTransaction).where(ChainTransaction.chain_id == CHAIN, ChainTransaction.tx_hash == tx_hash)
        ).first()
        return row.status if row else None


def _roots_after_apply(engine, txs: list[dict[str, Any]], version: int = VERSION, *, height: int = 1):
    """Proposer-side root computation on clean state: apply each tx, read
    roots, roll back — mirrors the test_account_isolation_v22 harness."""
    st = StateTransition()
    with Session(engine) as session:
        for tx in txs:
            st.apply_transaction_guarded(
                session, CHAIN, _apply_data(tx), tx["tx_hash"], block_version=version, block_height=height
            )
        session.flush()
        root = compute_state_root_full(session, CHAIN)
        aux = side_root_shadow.committed_fingerprint(session.connection().connection, version)["fingerprint"]
        session.rollback()
    return root, aux


def _block(
    txs: list[dict[str, Any]],
    state_root: str | None,
    aux: str | None,
    version: int = VERSION,
    *,
    height: int = 1,
    parent_hash: str = "0x" + "00" * 32,
) -> dict[str, Any]:
    timestamp = (T0 + timedelta(seconds=60 * height)).isoformat()
    block: dict[str, Any] = {
        "chain_id": CHAIN,
        "height": height,
        "hash": "",
        "parent_hash": parent_hash,
        "proposer": ADDR_S,
        "timestamp": timestamp,
        "tx_count": len(txs),
        "state_root": state_root,
        "aux_state_root": aux,
        "block_metadata": f'{{"state_transition_version": {version}}}',
        "signature": "",
        "transactions": txs,
    }
    # v20+: the delivered tx list must hash to the block hash (#1064).
    from aitbc_chain.consensus.block_hash import compute_block_hash

    block["hash"] = compute_block_hash(
        CHAIN,
        height,
        block["parent_hash"],
        timestamp,
        [str(tx.get("tx_hash", "")) for tx in txs],
        ADDR_S,
        state_root,
        None,
        aux,
    )
    return block


def _import(engine, factory, txs, version: int = VERSION, *, height: int = 1, parent_hash: str = "0x" + "00" * 32):
    root, aux = _roots_after_apply(engine, txs, version, height=height)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    return sync.import_block(_block(txs, root, aux, version, height=height, parent_hash=parent_hash), transactions=txs)


# --- T1: valid sequential nonces accepted ---------------------------------


def test_t1_sequential_nonces_apply_and_confirm(fixture_db):
    """Nonces N..N+2 from one sender all apply in a single session; the
    sealed-block import path confirms every tx row."""
    engine, factory = fixture_db
    txs = [_signed_tx(NONCE0 + i, AMT + i, label=f"t1-{i}") for i in range(3)]

    st = StateTransition()
    with Session(engine) as session:
        for tx in txs:
            ok, err = _apply(st, session, tx)
            assert ok, f"{tx['tx_hash']}: {err}"
        session.rollback()  # keep the DB clean for the real import leg

    result = _import(engine, factory, txs, VERSION)
    assert result.accepted, f"v23 block must import: {result.reason}"

    acct = _account(engine)
    assert acct is not None
    assert acct.nonce == NONCE0 + 3
    expected_balance = BALANCE0 - sum(int(t["amount"]) + int(t["fee"]) for t in txs)
    assert acct.balance == expected_balance
    for tx in txs:
        assert _tx_status(engine, tx["tx_hash"]) == "confirmed"


# --- T2: nonce gap rejected -------------------------------------------------


def test_t2_nonce_gap_rejected_zero_delta(fixture_db):
    """Nonce N applies; N+2 is rejected ``Invalid nonce`` and leaves zero
    mutation inside the savepoint."""
    engine, _factory = fixture_db
    st = StateTransition()
    tx_ok = _signed_tx(NONCE0, AMT, label="t2-ok")
    tx_gap = _signed_tx(NONCE0 + 2, AMT, label="t2-gap")

    with Session(engine) as session:
        ok, err = _apply(st, session, tx_ok)
        assert ok, err
        ok2, err2 = _apply(st, session, tx_gap)
        assert not ok2, "gap nonce must be rejected"
        assert "Invalid nonce" in err2
        session.flush()
        # Exactly the tx_ok outcome — the rejected tx mutated nothing.
        assert _account_scalars(session) == (NONCE0 + 1, BALANCE0 - (AMT + FEE))
        assert _account_scalars(session, ADDR_R) == (0, AMT)
        assert tx_gap["tx_hash"] not in st._processed_tx_hashes


# --- T3: duplicate nonce rejected -------------------------------------------


def test_t3_duplicate_nonce_second_rejected(fixture_db):
    """Two DIFFERENT txs carrying the same signed nonce: the first applies,
    the second is rejected — no same-nonce double-apply inside a block."""
    engine, _factory = fixture_db
    st = StateTransition()
    tx_a = _signed_tx(NONCE0, AMT, label="t3-a")
    tx_b = _signed_tx(NONCE0, AMT + 50, label="t3-b")  # same nonce, distinct hash/value

    with Session(engine) as session:
        ok_a, err_a = _apply(st, session, tx_a)
        assert ok_a, err_a
        ok_b, err_b = _apply(st, session, tx_b)
        assert not ok_b
        assert "Invalid nonce" in err_b
        assert str(NONCE0 + 1) in err_b and str(NONCE0) in err_b
        session.flush()
        assert _account_scalars(session) == (NONCE0 + 1, BALANCE0 - (AMT + FEE))
        assert _account_scalars(session, ADDR_R) == (0, AMT)  # tx_b's larger credit never landed


# --- T4: balance correctness, independent -----------------------------------


def test_t4_balance_boundary_never_negative(fixture_db):
    """Nonces always correct; balance covers exactly two of three txs. The
    third is rejected on balance and the account never goes negative —
    asserted via raw scalar SELECT, not the ORM."""
    engine, _factory = fixture_db
    st = StateTransition()
    cost = AMT + FEE

    with Session(engine) as session:
        session.execute(
            text("UPDATE account SET balance = :b WHERE chain_id = :c AND address = :a"),
            {"b": 2 * cost, "c": CHAIN, "a": ADDR_S},
        )
        session.flush()
        txs = [_signed_tx(NONCE0 + i, AMT, label=f"t4-{i}") for i in range(3)]
        results = [_apply(st, session, tx) for tx in txs]
        assert results[0][0] and results[1][0], results
        assert not results[2][0], "third tx must fail on balance"
        assert "Insufficient balance" in results[2][1]
        session.flush()
        nonce, balance = _account_scalars(session)
        assert nonce == NONCE0 + 2
        assert balance == 0  # exact — never negative
        assert _account_scalars(session, ADDR_R) == (0, 2 * AMT)


# --- T5: stale-ORM regression pin (the bug itself) ---------------------------


def test_t5_stale_orm_retained_session_second_tx(fixture_db):
    """A retained ``Account`` object (mirroring the proposer's per-block
    ``account_map``) must not hide the raw-SQL nonce/balance updates from
    the next same-sender tx. Fails on unfixed code with
    ``expected NONCE0, got NONCE0+1``."""
    engine, _factory = fixture_db
    st = StateTransition()

    with Session(engine) as session:
        retained = session.get(Account, (CHAIN, ADDR_S))  # preload the identity map
        assert retained is not None and retained.nonce == NONCE0

        ok1, err1 = _apply(st, session, _signed_tx(NONCE0, AMT, label="t5-a"))
        assert ok1, err1

        ok2, err2 = _apply(st, session, _signed_tx(NONCE0 + 1, AMT, label="t5-b"))
        assert ok2, f"second same-sender tx rejected on a stale ORM read: {err2}"

        session.flush()
        assert _account_scalars(session) == (NONCE0 + 2, BALANCE0 - 2 * (AMT + FEE))
        # The retained object itself carries authoritative values — callers
        # holding it across the block see the same state the DB has.
        assert retained.nonce == NONCE0 + 2
        assert retained.balance == BALANCE0 - 2 * (AMT + FEE)


# --- T6: session reuse across a block boundary -------------------------------


def test_t6_commit_reset_cache_next_block(fixture_db):
    """Same Session: apply block-h txs, commit, reset the per-block caches,
    then block-h+1 txs validate against committed state — no leakage."""
    engine, _factory = fixture_db
    st = StateTransition()

    with Session(engine) as session:
        ok, err = _apply(st, session, _signed_tx(NONCE0, AMT, label="t6-a"), height=1)
        assert ok, err
        session.commit()

        st.reset_processed_cache()
        assert st.get_processed_nonces() == {}
        assert st._processed_tx_hashes == set()

        ok2, err2 = _apply(st, session, _signed_tx(NONCE0 + 1, AMT, label="t6-b"), height=2)
        assert ok2, err2
        session.commit()

    acct = _account(engine)
    assert acct is not None
    assert (acct.nonce, acct.balance) == (NONCE0 + 2, BALANCE0 - 2 * (AMT + FEE))


# --- T7: handler exception -> savepoint rollback ------------------------------


def test_t7_handler_exception_rolls_back_cleanly(fixture_db, monkeypatch):
    """A late-apply handler raising after the raw debit must roll the tx
    back to its savepoint: tx1 intact, tx2 zero mutation, ORM attributes
    agree with scalar DB truth, and no phantom cache entries."""
    engine, _factory = fixture_db
    st = StateTransition()

    def _boom(self, session, chain_id, tx_data, tx_hash, sender_addr):
        raise RuntimeError("t7 injected handler failure")

    monkeypatch.setattr(StateTransition, "_handle_ipfs_subscription", _boom)

    tx1 = _signed_tx(NONCE0, AMT, label="t7-a")
    tx2 = _signed_tx(
        NONCE0 + 1,
        50,
        tx_type="IPFS_SUBSCRIPTION",
        payload={"island_id": "isl-t7", "duration_blocks": 10, "quota_bytes": 100},
        label="t7-b",
    )

    with Session(engine) as session:
        ok1, err1 = _apply(st, session, tx1)
        assert ok1, err1

        with pytest.raises(RuntimeError, match="t7 injected handler failure"):
            _apply(st, session, tx2)

        session.flush()
        # tx1-only outcome: sender debited once, nonce advanced once.
        assert _account_scalars(session) == (NONCE0 + 1, BALANCE0 - (AMT + FEE))
        assert _account_scalars(session, ADDR_R) == (0, AMT)  # tx2's credit rolled back
        # The retained ORM object agrees with the row — no phantom increment.
        acct = session.get(Account, (CHAIN, ADDR_S))
        assert acct is not None
        assert acct.nonce == NONCE0 + 1
        assert acct.balance == BALANCE0 - (AMT + FEE)
        # No phantom caches for the failed tx; the nonce cache still holds
        # the authoritative post-tx1 next-expected nonce.
        assert tx2["tx_hash"] not in st._processed_tx_hashes
        assert st._processed_nonces.get(ADDR_S) == NONCE0 + 1


# --- success-tail refresh failure: no phantom cache ----------------------------


def test_success_tail_refresh_raise_no_phantom_cache(fixture_db, monkeypatch):
    """If the >=23 tail ``session.refresh`` raises after the raw debit, the
    guarded savepoint rolls the tx back — and because the cache writes now
    run AFTER the refresh, no processed-hash/nonce residue survives for
    the failed tx while tx1's entries stay intact."""
    engine, _factory = fixture_db
    st = StateTransition()
    tx1 = _signed_tx(NONCE0, AMT, label="t11-a")
    tx2 = _signed_tx(NONCE0 + 1, AMT, label="t11-b")

    with Session(engine) as session:
        ok1, err1 = _apply(st, session, tx1)
        assert ok1, err1

        sender_obj = session.get(Account, (CHAIN, ADDR_S))
        assert sender_obj is not None
        real_refresh = Session.refresh
        sender_refreshes: list[Any] = []

        def flaky_refresh(self, target, *args, **kwargs):
            if target is sender_obj:
                sender_refreshes.append(target)
                # tx2's first sender refresh is the validation read (must
                # succeed); the second is the success-tail reload (raise).
                if len(sender_refreshes) >= 2:
                    raise RuntimeError("t11 injected tail refresh failure")
            return real_refresh(self, target, *args, **kwargs)

        monkeypatch.setattr(Session, "refresh", flaky_refresh)

        with pytest.raises(RuntimeError, match="t11 injected tail refresh failure"):
            _apply(st, session, tx2)

        assert len(sender_refreshes) == 2  # validate read + attempted tail
        session.flush()
        # tx2 rolled back to its savepoint: DB shows the tx1-only outcome.
        assert _account_scalars(session) == (NONCE0 + 1, BALANCE0 - (AMT + FEE))
        assert _account_scalars(session, ADDR_R) == (0, AMT)
        # No phantom cache entries for tx2; tx1's entries intact.
        tx1_data = _apply_data(tx1)
        tx2_data = _apply_data(tx2)
        assert tx1_data["tx_hash"] in st._processed_tx_hashes
        assert tx2_data["tx_hash"] not in st._processed_tx_hashes
        assert st._processed_nonces.get(ADDR_S) == NONCE0 + 1


# --- T8: v7+ envelope nonce is real at v23 ------------------------------------


def test_t8_wrong_signed_nonce_rejected_v23(fixture_db):
    """A signed tx carrying nonce N+5 against account nonce N is rejected —
    and the nonce-override rewrite stays OFF at v23, so the check is real."""
    engine, _factory = fixture_db
    st = StateTransition()
    tx = _signed_tx(NONCE0 + 5, AMT, label="t8")
    assert use_account_nonce_override(tx, VERSION) is False

    with Session(engine) as session:
        ok, err = _apply(st, session, tx)
        assert not ok
        assert "Invalid nonce" in err
        session.flush()
        assert _account_scalars(session) == (NONCE0, BALANCE0)
        assert _account_scalars(session, ADDR_R) == (0, 0)


# --- T9: rejected tx recoverable after the gap closes -------------------------


def test_t9_rejected_tx_retryable_after_gap_closes(fixture_db, monkeypatch):
    """Actual recoverable semantics (the #712 family the dedup code
    documents), exercised at both boundaries:

    Phase A — in-session: a tx rejected on a nonce gap leaves no
    processed-hash entry and no persisted row, so the IDENTICAL envelope
    applies once the gap closes.

    Phase B — the persisted ``status='rejected'``, ``block_height=None``
    writeback the proposer makes for a drained refusal (#669,
    ``poa._persist_rejected_txs``): the identical hash+envelope resubmitted
    through the REAL ``_process_txs_sequential`` path re-applies once the
    gap closes and flips THE SAME row to ``confirmed`` — rejection is a
    verdict, not a terminal state, for unsealed txs. This pins that the
    fix does not change replay/resubmission admission."""
    engine, factory = fixture_db
    st = StateTransition()
    tx_a = _signed_tx(NONCE0, AMT, label="t9-a")
    tx_b = _signed_tx(NONCE0 + 2, AMT, label="t9-b")  # gap: expected NONCE0+1
    tx_c = _signed_tx(NONCE0 + 1, AMT, label="t9-c")  # fills the gap

    # --- Phase A: no persisted row, identical in-session retry ---
    with Session(engine) as session:
        for tx in (tx_a, tx_b, tx_c):
            ok, err = _apply(st, session, tx)
            if tx is tx_b:
                assert not ok and "Invalid nonce" in err
            else:
                assert ok, f"{tx['tx_hash']}: {err}"

        # Identical retry — same envelope, same tx_hash.
        ok_b, err_b = _apply(st, session, tx_b)
        assert ok_b, f"rejected tx not recoverable after the gap closed: {err_b}"

        session.flush()
        assert _account_scalars(session) == (NONCE0 + 3, BALANCE0 - 3 * (AMT + FEE))
        assert _account_scalars(session, ADDR_R) == (0, 3 * AMT)
    # Session closed without commit — Phase B starts from clean state.

    # --- Phase B: persisted rejected row + real proposer resubmission ---
    from aitbc_chain.config import settings
    from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig

    tx_a2 = _signed_tx(NONCE0, AMT, label="t9b-a")
    tx_b2 = _signed_tx(NONCE0 + 2, AMT, label="t9b-b")
    tx_c2 = _signed_tx(NONCE0 + 1, AMT, label="t9b-c")
    st2 = StateTransition()

    with Session(engine) as session:
        ok_a2, err_a2 = _apply(st2, session, tx_a2)
        assert ok_a2, err_a2
        ok_b2, err_b2 = _apply(st2, session, tx_b2)
        assert not ok_b2 and "Invalid nonce" in err_b2
        # Mirror poa._persist_rejected_txs verbatim: terminal rejected
        # writeback, block_height=None — service state, not sealed ledger.
        session.add(
            ChainTransaction(
                chain_id=CHAIN,
                tx_hash=tx_b2["tx_hash"],
                sender=tx_b2["from"],
                recipient=tx_b2["to"],
                payload=tx_b2["payload"],
                envelope=dict(tx_b2),
                value=tx_b2["amount"],
                fee=tx_b2["fee"],
                nonce=tx_b2["nonce"],
                timestamp=None,
                block_height=None,
                status="rejected",
                type="TRANSFER",
                tx_metadata=json.dumps(
                    {
                        "rejected_reason": err_b2,
                        "rejected_at_height": 1,
                        "rejected_at": T0.isoformat(),
                    }
                ),
            )
        )
        ok_c2, err_c2 = _apply(st2, session, tx_c2)  # fills the gap
        assert ok_c2, err_c2
        session.commit()

    # Pre-resubmission truth: the row sits rejected, unsealed.
    assert _tx_status(engine, tx_b2["tx_hash"]) == "rejected"

    # Resubmit the identical envelope through the REAL proposer path.
    monkeypatch.setattr(settings, "state_transition_v23_height", 1)
    proposer = PoAProposer(
        config=ProposerConfig(
            chain_id=CHAIN, proposer_id=ADDR_S, interval_seconds=5, max_block_size_bytes=1_000_000, max_txs_per_block=100
        ),
        session_factory=factory,
    )
    get_state_transition().reset_processed_cache()
    with Session(engine) as session:
        account_map = {a.address: a for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()}
        # The rejected row has block_height=None → existing_tx_map skips it
        # (production builds the map from non-None heights only).
        existing_tx_map: dict[str, int] = {}
        pending = [SimpleNamespace(tx_hash=tx_b2["tx_hash"], content=dict(tx_b2))]
        rejected: list[tuple[Any, str]] = []
        processed, _changed, ok = proposer._process_txs_sequential(
            session,
            pending,
            account_map,
            existing_tx_map,
            next_height=2,
            timestamp=T0 + timedelta(seconds=120),
            rejected=rejected,
        )
        assert ok, f"proposer aborted: {rejected}"
        assert len(processed) == 1 and not rejected
        session.flush()
        # THE SAME row flips to confirmed — no duplicate, no fake claim.
        rows = session.exec(
            select(ChainTransaction).where(ChainTransaction.chain_id == CHAIN, ChainTransaction.tx_hash == tx_b2["tx_hash"])
        ).all()
        assert len(rows) == 1
        assert rows[0].status == "confirmed" and rows[0].block_height == 2
        assert _account_scalars(session) == (NONCE0 + 3, BALANCE0 - 3 * (AMT + FEE))
        session.commit()

    assert _tx_status(engine, tx_b2["tx_hash"]) == "confirmed"
    acct = _account(engine)
    assert acct is not None
    assert (acct.nonce, acct.balance) == (NONCE0 + 3, BALANCE0 - 3 * (AMT + FEE))


# --- T10: proposer vs importer parity ----------------------------------------


def test_t10_proposer_and_importer_converge(fixture_db, tmp_path, monkeypatch):
    """The REAL proposer path (``PoAProposer._process_txs_sequential``) and
    the REAL importer (``ChainSync.import_block``) on isolated DBs must
    produce identical account state and identical state/aux roots — the
    'every caller' claim of the refresh fix."""
    from aitbc_chain.config import settings
    from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig

    engine_p, _factory_p = fixture_db
    engine_i, factory_i = _make_db(tmp_path / "chain-i.db")
    txs = [_signed_tx(NONCE0 + i, AMT + i, label=f"t10-{i}") for i in range(3)]

    # --- proposer side ---
    monkeypatch.setattr(settings, "state_transition_v23_height", 1)
    proposer = PoAProposer(
        config=ProposerConfig(
            chain_id=CHAIN, proposer_id=ADDR_S, interval_seconds=5, max_block_size_bytes=1_000_000, max_txs_per_block=100
        ),
        session_factory=_factory_p,
    )
    get_state_transition().reset_processed_cache()
    with Session(engine_p) as session:
        account_map = {a.address: a for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()}
        rejected: list[tuple[Any, str]] = []
        pending = [SimpleNamespace(tx_hash=t["tx_hash"], content=dict(t)) for t in txs]
        processed, _changed, ok = proposer._process_txs_sequential(
            session,
            pending,
            account_map,
            {},
            next_height=1,
            timestamp=T0 + timedelta(seconds=60),
            rejected=rejected,
        )
        assert ok, f"proposer aborted the block: {rejected}"
        assert len(processed) == 3 and not rejected
        session.flush()
        root_p = compute_state_root_full(session, CHAIN)
        aux_p = side_root_shadow.committed_fingerprint(session.connection().connection, VERSION)["fingerprint"]
        snap_p = _account_scalars(session)
        # The retained object the proposer held in account_map carries the
        # authoritative post-block nonce — the fix's caller-visible effect.
        assert session.get(Account, (CHAIN, ADDR_S)).nonce == NONCE0 + 3
        session.commit()

    # --- importer side: same txs as a sealed v23 block on a second DB ---
    sync = ChainSync(factory_i, chain_id=CHAIN, validate_signatures=False)
    block = _block(txs, root_p, aux_p, VERSION, height=1)
    result = sync.import_block(block, transactions=txs)
    assert result.accepted, f"importer rejected the block: {result.reason}"

    with Session(engine_i) as session:
        snap_i = _account_scalars(session)
        stored = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
        root_i = compute_state_root_full(session, CHAIN)
        aux_i = side_root_shadow.committed_fingerprint(session.connection().connection, VERSION)["fingerprint"]

    assert snap_p == snap_i, f"account divergence: proposer={snap_p} importer={snap_i}"
    assert root_i == root_p, f"recomputed importer root {root_i} != proposer root {root_p}"
    assert stored.state_root == root_p
    assert aux_i == aux_p


# --- v22 control: <=22 semantics untouched -----------------------------------


def test_v22_retained_session_second_tx_still_rejected(fixture_db):
    """Control: the same retained-session shape at v22 keeps the historical
    stale-read rejection — the refresh is gated to >=23 and must not leak
    into replayed history."""
    engine, _factory = fixture_db
    st = StateTransition()

    with Session(engine) as session:
        retained = session.get(Account, (CHAIN, ADDR_S))
        assert retained is not None

        ok1, err1 = _apply(st, session, _signed_tx(NONCE0, AMT, label="v22-a"), version=22)
        assert ok1, err1

        ok2, err2 = _apply(st, session, _signed_tx(NONCE0 + 1, AMT, label="v22-b"), version=22)
        assert not ok2, "v22 must keep the pre-fix rejection semantics"
        assert "Invalid nonce" in err2
