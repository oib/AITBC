"""CONSENSUS-STATE-001 / #1169 — rejected-tx account isolation at v22.

Before the fix, ``sync_block_import`` pre-created the sender ``Account``
before ``apply_transaction`` ran validation: a tx that validate/apply
rejected still left a committed phantom account row (balance 0, nonce 0),
so importer state diverged from the proposer (which never pre-creates)
and from any node replaying without the pre-insert.

At ``block_version >= 22`` the pre-apply sender insert is gone —
``apply_transaction`` owns account creation on its success paths only.
Pre-v22 the legacy insert is pinned unchanged for replay identity.

Harness mirrors ``test_aux_root_volatile_eras.py``: proposer-side roots
are computed over clean state, the block is fed to ``ChainSync.import_block``.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account, Block
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state import side_root_shadow
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition
from aitbc_chain.sync import ChainSync
from sqlmodel import Session, create_engine, select

CHAIN = "acct-iso-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)

KEY_A = "0x" + "11" * 32
KEY_C = "0x" + "44" * 32

from aitbc.crypto.crypto import derive_ethereum_address

ADDR_A = derive_ethereum_address(KEY_A)
ADDR_B = derive_ethereum_address("0x" + "33" * 32)
ADDR_C = derive_ethereum_address(KEY_C)  # deliberately NO account — the phantom candidate


@pytest.fixture()
def fixture_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=0))
        session.add(Account(chain_id=CHAIN, address=ADDR_B, balance=0, nonce=0))
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


def _tx(
    sender: str,
    key: str,
    to: str,
    amount: int,
    nonce: int,
    tx_type: str,
    tx_hash: str,
    payload=None,
    fee: int = DEFAULT_TX_FEE_UNITS,
) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": sender,
        "to": to,
        "amount": amount,
        "fee": fee,
        "nonce": nonce,
        "payload": payload or {},
        "type": tx_type,
        "chain_id": CHAIN,
        "tx_hash": tx_hash,
    }
    tx["signature"] = sign_transaction_data(tx, key)
    return tx


def _roots_after_apply(
    engine, txs: list[dict[str, Any]], version: int, *, precreate: set[str] | None = None, height: int = 1
) -> tuple[str | None, str]:
    """Simulate the importer outcome on clean state: optional legacy sender
    pre-creation, then apply each tx (success or failure), read roots, roll back."""
    st = StateTransition()
    with Session(engine) as session:
        for addr in precreate or set():
            session.add(Account(chain_id=CHAIN, address=addr, balance=0, nonce=0))
        for tx in txs:
            data = dict(tx)
            data.setdefault("value", data.get("amount", 0))
            st.apply_transaction(session, CHAIN, data, data["tx_hash"], block_version=version, block_height=height)
        session.flush()
        root = compute_state_root_full(session, CHAIN)
        aux = side_root_shadow.committed_fingerprint(session.connection().connection, version)["fingerprint"]
        session.rollback()
    return root, aux


def _block(
    txs: list[dict[str, Any]],
    state_root: str | None,
    aux: str | None,
    version: int,
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
        "proposer": ADDR_A,
        "timestamp": timestamp,
        "tx_count": len(txs),
        "state_root": state_root,
        "aux_state_root": aux,
        "block_metadata": f'{{"state_transition_version": {version}}}',
        "signature": "",
        "transactions": txs,
    }
    # v20+: the delivered tx list must hash to the block hash (#1064) —
    # stamp it exactly like a proposer would.
    from aitbc_chain.consensus.block_hash import compute_block_hash

    block["hash"] = compute_block_hash(
        CHAIN,
        height,
        block["parent_hash"],
        timestamp,
        [str(tx.get("tx_hash", "")) for tx in txs],
        ADDR_A,
        state_root,
        None,
        aux,
    )
    return block


def _import(engine, factory, txs, version, *, precreate=None, height=1, parent_hash="0x" + "00" * 32):
    root, aux = _roots_after_apply(engine, txs, version, precreate=precreate, height=height)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    return sync.import_block(_block(txs, root, aux, version, height=height, parent_hash=parent_hash), transactions=txs)


def _account(engine, address: str) -> Account | None:
    with Session(engine) as session:
        return session.get(Account, (CHAIN, address))


def _tx_status(engine, tx_hash: str) -> str | None:
    from aitbc_chain.base_models import Transaction as ChainTransaction

    with Session(engine) as session:
        row = session.exec(
            select(ChainTransaction).where(ChainTransaction.chain_id == CHAIN, ChainTransaction.tx_hash == tx_hash)
        ).first()
        return row.status if row else None


# --- the defect ------------------------------------------------------------


def test_v22_rejected_tx_leaves_no_phantom_account(fixture_db):
    """A sealed v22 block carrying a tx from a nonexistent sender imports,
    the tx records failed, and NO account row appears for the sender."""
    engine, factory = fixture_db
    failing = _tx(ADDR_C, KEY_C, ADDR_B, 10, 0, "TRANSFER", "0x" + "c1" * 32)
    result = _import(engine, factory, [failing], 22)
    assert result.accepted, f"v22 block must import: {result.reason}"
    assert _account(engine, ADDR_C) is None, "phantom sender account committed at v22"
    assert _tx_status(engine, failing["tx_hash"]) == "failed"


def test_v21_legacy_phantom_account_pinned(fixture_db):
    """Replay pin: below v22 the pre-apply sender insert still runs — the
    phantom account is the historical (defective) behavior, preserved
    byte-for-byte."""
    engine, factory = fixture_db
    failing = _tx(ADDR_C, KEY_C, ADDR_B, 10, 0, "TRANSFER", "0x" + "c2" * 32)
    result = _import(engine, factory, [failing], 21, precreate={ADDR_C})
    assert result.accepted, f"v21 block must import: {result.reason}"
    acct = _account(engine, ADDR_C)
    assert acct is not None and acct.balance == 0 and acct.nonce == 0


# --- intra-block account creation stays valid -------------------------------


def test_v22_intrablock_pay_then_spend(fixture_db):
    """tx1 pays a fresh address; tx2 spends from it later in the SAME v22
    block — account creation on the success path is preserved."""
    engine, factory = fixture_db
    pay = _tx(ADDR_A, KEY_A, ADDR_C, 500_000, 0, "TRANSFER", "0x" + "d1" * 32)
    spend = _tx(ADDR_C, KEY_C, ADDR_A, 400, 0, "TRANSFER", "0x" + "d2" * 32)
    result = _import(engine, factory, [pay, spend], 22)
    assert result.accepted, f"v22 intra-block block must import: {result.reason}"
    acct = _account(engine, ADDR_C)
    assert acct is not None, "recipient account must exist after successful credit"
    # 500000 in - (400 + fee) out
    assert acct.balance == 500_000 - 400 - DEFAULT_TX_FEE_UNITS
    assert _tx_status(engine, spend["tx_hash"]) == "confirmed"


def test_v22_mixed_block_failed_tx_no_phantom(fixture_db):
    """A valid tx followed by a rejected tx in one v22 block: the valid
    state lands, the rejected sender leaves no account."""
    engine, factory = fixture_db
    good = _tx(ADDR_A, KEY_A, ADDR_B, 500, 0, "TRANSFER", "0x" + "e1" * 32)
    bad = _tx(ADDR_C, KEY_C, ADDR_B, 10, 0, "TRANSFER", "0x" + "e2" * 32)
    result = _import(engine, factory, [good, bad], 22)
    assert result.accepted, f"v22 mixed block must import: {result.reason}"
    assert _account(engine, ADDR_C) is None
    assert _tx_status(engine, good["tx_hash"]) == "confirmed"
    assert _tx_status(engine, bad["tx_hash"]) == "failed"


# --- validate_transaction read-only at v22 ---------------------------------


def test_v22_validate_is_read_only_for_liquidity(tmp_path):
    """LIQUIDITY_DEPOSIT from an unknown sender: validate must fail AND
    create no account rows (previously the ensures ran pre-verdict)."""
    engine = create_engine(f"sqlite:///{tmp_path}/ro.db")
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        st = StateTransition()
        before = len(session.exec(select(Account)).all())
        tx = _tx(
            ADDR_C,
            KEY_C,
            ADDR_B,
            100,
            0,
            "LIQUIDITY_DEPOSIT",
            "0x" + "f1" * 32,
            {"pool_id": "main", "lock_days": 7},
        )
        ok, _err = st.validate_transaction(session, CHAIN, tx, tx["tx_hash"], block_version=22, block_height=1)
        assert ok is False
        after = session.exec(select(Account)).all()
        assert len(after) == before, f"validate created accounts at v22: {[a.address for a in after]}"


def test_v21_validate_still_ensures_for_replay(tmp_path):
    """Pre-v22 pin: the liquidity ensure still runs below v22 (replay
    identity) — the account row appears during validation."""
    engine = create_engine(f"sqlite:///{tmp_path}/ro21.db")
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        st = StateTransition()
        tx = _tx(
            ADDR_C,
            KEY_C,
            ADDR_B,
            100,
            0,
            "LIQUIDITY_DEPOSIT",
            "0x" + "f2" * 32,
            {"pool_id": "main", "lock_days": 7},
        )
        ok, _err = st.validate_transaction(session, CHAIN, tx, tx["tx_hash"], block_version=21, block_height=1)
        assert ok is False  # still rejected (no balance) — but the row was ensured
        assert session.get(Account, (CHAIN, ADDR_C)) is not None


# --- R1 completion: virtual (0,0) sender reads at v22 ------------------------
#
# The ratified contract (consensus-state-001-v22-contract.md §3/F4,
# implementation-review-checklist.md §3) requires a missing sender Account
# to read as virtual balance=0/nonce=0 — identical outcomes to the pre-v22
# importer pre-create — with the row materializing only on apply success.
# dd8f81fe9 removed the phantom on rejection but kept "Sender account not
# found" rejection, which silently became R2. These tests pin R1.

KEY_B = "0x" + "33" * 32


def test_v22_validate_virtual_sender_reads(tmp_path):
    """Core R1 pin: validate_transaction at v22 treats a missing sender as
    (0,0) — a zero-cost tx validates TRUE while creating no Account row."""
    engine = create_engine(f"sqlite:///{tmp_path}/virt.db")
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        st = StateTransition()
        tx = _tx(ADDR_C, KEY_C, ADDR_B, 0, 0, "TRANSFER", "0x" + "a1" * 32, fee=0)
        ok, err = st.validate_transaction(session, CHAIN, tx, tx["tx_hash"], block_version=22, block_height=1)
        assert ok, f"zero-cost unknown-sender tx must validate at v22: {err}"
        assert session.get(Account, (CHAIN, ADDR_C)) is None, "validate must stay read-only"


def test_v22_zero_cost_unknown_sender_import_succeeds(fixture_db):
    """R1: a sealed v22 block carrying a zero-cost tx from a never-seen
    sender imports, applies, and materializes the account at nonce=1 —
    the same committed outcome v21 produced via the phantom row."""
    engine, factory = fixture_db
    tx = _tx(ADDR_C, KEY_C, ADDR_B, 0, 0, "TRANSFER", "0x" + "a2" * 32, fee=0)
    result = _import(engine, factory, [tx], 22)
    assert result.accepted, f"v22 zero-cost unknown-sender block must import: {result.reason}"
    acct = _account(engine, ADDR_C)
    assert acct is not None, "apply success must materialize the sender account"
    assert acct.nonce == 1 and acct.balance == 0
    assert _tx_status(engine, tx["tx_hash"]) == "confirmed"


def test_v21_zero_cost_unknown_sender_import_succeeds(fixture_db):
    """Historical pin: the same tx at v21 succeeds through the legacy
    pre-create path with the identical resulting account (nonce=1)."""
    engine, factory = fixture_db
    tx = _tx(ADDR_C, KEY_C, ADDR_B, 0, 0, "TRANSFER", "0x" + "a3" * 32, fee=0)
    result = _import(engine, factory, [tx], 21, precreate={ADDR_C})
    assert result.accepted, f"v21 zero-cost unknown-sender block must import: {result.reason}"
    acct = _account(engine, ADDR_C)
    assert acct is not None and acct.nonce == 1 and acct.balance == 0


def test_v22_unknown_sender_positive_value_rejected(fixture_db):
    """R1: virtual balance 0 cannot cover a positive cost — rejected, no row."""
    engine, factory = fixture_db
    tx = _tx(ADDR_C, KEY_C, ADDR_B, 10, 0, "TRANSFER", "0x" + "a4" * 32, fee=0)
    result = _import(engine, factory, [tx], 22)
    assert result.accepted, f"block must import: {result.reason}"
    assert _account(engine, ADDR_C) is None
    assert _tx_status(engine, tx["tx_hash"]) == "failed"


def test_v22_unknown_sender_invalid_nonce_rejected(fixture_db):
    """R1: virtual nonce is 0 — a tx carrying nonce=5 fails the nonce
    check with no account row."""
    engine, factory = fixture_db
    tx = _tx(ADDR_C, KEY_C, ADDR_B, 0, 5, "TRANSFER", "0x" + "a5" * 32, fee=0)
    result = _import(engine, factory, [tx], 22)
    assert result.accepted, f"block must import: {result.reason}"
    assert _account(engine, ADDR_C) is None
    assert _tx_status(engine, tx["tx_hash"]) == "failed"


def test_v22_unknown_sender_bad_signature_rejected(fixture_db):
    """R1: a tx claiming ADDR_C but signed by KEY_A fails signature
    verification before any account logic — no row."""
    engine, factory = fixture_db
    tx = _tx(ADDR_C, KEY_A, ADDR_B, 0, 0, "TRANSFER", "0x" + "a6" * 32, fee=0)
    result = _import(engine, factory, [tx], 22)
    assert result.accepted, f"block must import: {result.reason}"
    assert _account(engine, ADDR_C) is None
    assert _tx_status(engine, tx["tx_hash"]) == "failed"


def test_v22_existing_sender_zero_cost_succeeds(fixture_db):
    """R1: an existing zero-balance sender's zero-cost tx still succeeds —
    virtual reads only apply when the row is absent."""
    engine, factory = fixture_db
    tx = _tx(ADDR_B, KEY_B, ADDR_A, 0, 0, "TRANSFER", "0x" + "a7" * 32, fee=0)
    result = _import(engine, factory, [tx], 22)
    assert result.accepted, f"v22 existing-sender zero-cost block must import: {result.reason}"
    acct = _account(engine, ADDR_B)
    assert acct is not None and acct.nonce == 1 and acct.balance == 0
    assert _tx_status(engine, tx["tx_hash"]) == "confirmed"


def test_v22_proposer_includes_zero_cost_unknown_sender(fixture_db, monkeypatch):
    """R1a proposer parity: _process_txs_sequential must not skip a valid
    zero-cost tx whose sender is absent from account_map — it applies it
    and the account materializes, matching the importer outcome."""
    from types import SimpleNamespace

    from aitbc_chain.config import settings
    from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig

    engine, factory = fixture_db
    monkeypatch.setattr(settings, "state_transition_v22_height", 1)
    tx = _tx(ADDR_C, KEY_C, ADDR_B, 0, 0, "TRANSFER", "0x" + "a8" * 32, fee=0)
    pending = SimpleNamespace(tx_hash=tx["tx_hash"], content=dict(tx))
    config = ProposerConfig(
        chain_id=CHAIN,
        proposer_id=ADDR_A,
        interval_seconds=5,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )

    @contextmanager
    def session_factory():
        with Session(engine) as session:
            yield session
            session.commit()

    proposer = PoAProposer(config=config, session_factory=session_factory)
    with Session(engine) as session:
        processed, _changed, ok = proposer._process_txs_sequential(
            session,
            [pending],
            {},  # account_map: sender unknown — the R1 case
            {},
            next_height=1,
            timestamp=T0 + timedelta(seconds=60),
        )
        assert ok, "proposer must process the tx, not abort the block"
        assert [t.tx_hash for t in processed] == [tx["tx_hash"]]
        acct = session.get(Account, (CHAIN, ADDR_C))
        assert acct is not None and acct.nonce == 1 and acct.balance == 0
        session.commit()
    # Importer agreement is pinned by
    # test_v22_zero_cost_unknown_sender_import_succeeds: same tx shape,
    # same resulting account (nonce=1, balance=0).


def test_v22_validate_ipfs_subscription_read_only(tmp_path):
    """T14: IPFS_SUBSCRIPTION validate at v22 creates no recipient or
    sender rows even though the pre-v22 code ensured the treasury."""
    engine = create_engine(f"sqlite:///{tmp_path}/ipfs.db")
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=0))
        st = StateTransition()
        before = {a.address for a in session.exec(select(Account)).all()}
        tx = _tx(
            ADDR_A,
            KEY_A,
            ADDR_B,
            100,
            0,
            "IPFS_SUBSCRIPTION",
            "0x" + "b1" * 32,
            {"months": 1},
        )
        st.validate_transaction(session, CHAIN, tx, tx["tx_hash"], block_version=22, block_height=1)
        after = {a.address for a in session.exec(select(Account)).all()}
        assert after == before, f"validate created accounts at v22: {after - before}"


def test_v22_activation_boundary_across_heights(fixture_db):
    """T17: a v21 block followed by a v22 block in one chain — the v21
    segment keeps phantom semantics, the v22 segment applies virtual
    reads. The zero-cost unknown-sender tx only succeeds post-activation."""
    engine, factory = fixture_db
    # Height 1 @ v21: rejected tx leaves the historical phantom row.
    bad21 = _tx(ADDR_C, KEY_C, ADDR_B, 10, 0, "TRANSFER", "0x" + "c3" * 32)
    r1 = _import(engine, factory, [bad21], 21, precreate={ADDR_C}, height=1)
    assert r1.accepted, f"v21 block must import: {r1.reason}"
    assert _account(engine, ADDR_C) is not None, "v21 phantom semantics must be preserved"

    # Height 2 @ v22: a DIFFERENT fresh sender's zero-cost tx succeeds via
    # virtual reads and materializes at nonce=1.
    ghost_key = "0x" + "55" * 32
    ghost = derive_ethereum_address(ghost_key)
    good22 = _tx(ghost, ghost_key, ADDR_B, 0, 0, "TRANSFER", "0x" + "c4" * 32, fee=0)
    r2 = _import(engine, factory, [good22], 22, height=2, parent_hash=r1.block_hash or "")
    assert r2.accepted, f"v22 block must import: {r2.reason}"
    acct = _account(engine, ghost)
    assert acct is not None and acct.nonce == 1 and acct.balance == 0
