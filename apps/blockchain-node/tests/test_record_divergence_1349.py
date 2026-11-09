"""#1349 RL-1 — record-layer nonce/envelope divergence legs (L0–L2 + verdict memo).

E's corrected divergence model (c23423-24, verified line-by-line c23533-34):
the importer rewrites ``tx_data["nonce"]`` to the live account nonce BEFORE
apply whenever ``use_account_nonce_override`` holds (``sync_block_import.py:815-816``).
NEW ``transaction`` rows then store the OVERRIDDEN nonce and an envelope
snapshot taken after the rewrite (``:845-853``); EXISTING rows are upgraded
in place touching only ``block_height`` + ``status`` (``:864-870``), keeping
their original envelope/nonce. Same unsigned tx -> stored record differs
node-to-node depending on whether a row pre-existed.

Public RPC admission of unsigned txs is closed (every submit endpoint is
signature-gated; the V23-90 exemption is dead — c23563-64), so these legs
drive ``ChainSync.import_block`` directly: no RPC, importer-direct, exactly
the surface E's consumer audit targets.

Sessions use a prod-parity sessionmaker (``autoflush=False,
expire_on_commit=False`` — identical to ``database.py:483-484``) per the
#1314 package convention; plain ``Session(engine)`` would not reproduce
the pending-visibility semantics this record layer sits inside. When the
shared ``prod_parity_session`` factory lands with #1314 these fixtures
should migrate to it.

L3 verdict memo lives in each test's docstring; the ledger post carries
the consolidated LATENT-vs-LIVE table.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from aitbc_chain.base_models import Account, Block, ChainParameter, Transaction
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state import side_root_shadow
from aitbc_chain.state.block_deltas import _tx_payloads_at
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition, use_account_nonce_override
from aitbc_chain.sync import ChainSync
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.bridge_credit import sign_bridge_lock
from sqlmodel import Session, create_engine, select
from sqlalchemy.orm import sessionmaker

CHAIN = "rl1-1349-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
BLOCK_VERSION = 23  # current armed version — v8+ height rules do not apply at fixture heights

KEY_A = "0x" + "11" * 32
KEY_B = "0x" + "33" * 32
KEY_BRIDGE = "0x" + "22" * 32
ADDR_A = derive_ethereum_address(KEY_A)
ADDR_B = derive_ethereum_address(KEY_B)
ADDR_NEW = derive_ethereum_address("0x" + "44" * 32)

TX_HASH = "0x" + "c1" * 32


def _prod_parity_sessionmaker(engine):
    """Mirror of ``database.py:483-484`` — the production session config.

    ``autoflush=False`` + ``expire_on_commit=False`` is the whole point:
    plain ``Session(engine)`` autoflushes pending rows, which would mask
    exactly the visibility semantics the importer depends on.
    """
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, expire_on_commit=False)


def _make_db(tmp_path, name: str):
    """Fresh chain store + prod-parity factory, seeded like the proposer
    fixtures (genesis account set + bridge_release_authority parameter)."""
    db_path = tmp_path / name / "chain.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    chain_metadata.create_all(engine)
    sm = _prod_parity_sessionmaker(engine)

    @contextmanager
    def factory():
        with sm() as session:
            yield session
            session.commit()

    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=ADDR_A, balance=10**9, nonce=1))
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
        session.add(
            ChainParameter(
                chain_id=CHAIN,
                parameter="bridge_release_authority",
                value=derive_ethereum_address(KEY_BRIDGE),
                applied_height=0,
            )
        )
        session.flush()
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 0)).one()
        genesis.state_root = compute_state_root_full(session, CHAIN)
        session.commit()
    return engine, factory


def _bridge_lock_tx(recorded_nonce: int, bridge_sign_nonce: int) -> dict[str, Any]:
    """BRIDGE_LOCK whose ``bridge_signature`` is computed over
    ``bridge_sign_nonce`` while the row records ``recorded_nonce``.

    The authority signature covers the semantic message INCLUDING nonce
    (``bridge_lock_message`` projects ``tx_data["nonce"]``). The importer
    rewrites ``tx_data["nonce"]`` to the live account nonce before apply
    whenever ``use_account_nonce_override`` holds — so for an UNSIGNED lock
    the signature must cover the POST-override value (account nonce=1) or
    apply fails verification. For a SIGNED lock the override never fires
    and the signature covers the recorded nonce.
    """
    tx: dict[str, Any] = {
        "from": ADDR_A,
        "to": "bridge_lock",
        "amount": 500,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": recorded_nonce,
        "payload": {
            "transfer_id": "rl1-1349-lock-1",
            "target_chain": "sep-fixture",
            "target_recipient": ADDR_B,
            "asset": "AIT",
            "eth_address": ADDR_B,
        },
        "type": "BRIDGE_LOCK",
        "chain_id": CHAIN,
        "tx_hash": TX_HASH,
    }
    sign_tx = dict(tx)
    sign_tx["nonce"] = bridge_sign_nonce
    tx["bridge_signature"] = sign_bridge_lock(sign_tx, tx["tx_hash"], KEY_BRIDGE)
    return tx


def _unsigned_bridge_lock_tx() -> dict[str, Any]:
    """Unsigned (no top-level signature) BRIDGE_LOCK inside
    ``V9_UNSIGNED_ALLOWED_TX_TYPES`` — applies unsigned at every v9+
    version. Records nonce=0 while the account nonce is 1, so the
    importer's override rewrite is observable in stored columns; the
    bridge authority signed over the post-override nonce (1), which is
    what apply will verify against."""
    return _bridge_lock_tx(recorded_nonce=0, bridge_sign_nonce=1)


def _proposer_roots(engine, txs: list[dict[str, Any]], height: int = 1) -> tuple[str, str]:
    """Apply like the proposal path and return (account root, aux
    fingerprint); rolls back so the importer sees untouched fixture state."""
    st = StateTransition()
    with Session(engine) as session:
        for tx in txs:
            data = dict(tx)
            data.setdefault("value", data.get("amount", 0))
            sender = session.get(Account, (CHAIN, data.get("from", "")))
            if sender is not None and use_account_nonce_override(data, BLOCK_VERSION):
                data["nonce"] = sender.nonce
            ok, err = st.apply_transaction(
                session,
                CHAIN,
                data,
                data["tx_hash"],
                block_version=BLOCK_VERSION,
                block_height=height,
            )
            assert ok, f"fixture tx must apply on the proposer path: {err}"
        session.flush()
        root = compute_state_root_full(session, CHAIN)
        aux = side_root_shadow.committed_fingerprint(session.connection().connection, BLOCK_VERSION)["fingerprint"]
        session.rollback()
    return root, aux


def _block(height: int, txs: list[dict[str, Any]], state_root: str, aux: str) -> dict[str, Any]:
    from aitbc_chain.consensus.block_hash import compute_block_hash

    timestamp = (T0 + timedelta(seconds=60 * height)).isoformat()
    # v20+ gate (sync_block_import.py:518): the delivered tx list must hash
    # to the block hash — compute it the same way the proposer does.
    block_hash = compute_block_hash(
        CHAIN,
        height,
        "0x" + "00" * 32,
        timestamp,
        [str(tx.get("tx_hash", "")) for tx in txs],
        ADDR_A,
        state_root,
        "",
        aux,
    )
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": block_hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": ADDR_A,
        "timestamp": timestamp,
        "tx_count": len(txs),
        "state_root": state_root,
        "aux_state_root": aux,
        "block_metadata": f'{{"state_transition_version": {BLOCK_VERSION}}}',
        "signature": "",
        "transactions": txs,
    }


def _import(fixture, txs: list[dict[str, Any]], height: int = 1):
    engine, factory = fixture
    root, aux = _proposer_roots(engine, txs, height)
    block = _block(height, txs, root, aux)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    return engine, sync.import_block(block, transactions=txs), root


def _stored_tx(engine) -> Transaction:
    with Session(engine) as session:
        return session.exec(select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.tx_hash == TX_HASH)).one()


def _seed_rejected_row(engine, tx: dict[str, Any]) -> None:
    """Pre-existing ``transaction`` row as a pending/rejected writeback
    would leave it: ORIGINAL (un-overridden) nonce + envelope snapshot,
    status rejected, never sealed (block_height NULL)."""
    with Session(engine) as session:
        session.add(
            Transaction(
                chain_id=CHAIN,
                tx_hash=TX_HASH,
                block_height=None,
                sender=tx["from"],
                recipient=tx["to"],
                payload=tx.get("payload", {}),
                envelope=dict(tx),
                type=tx["type"],
                value=tx.get("amount", 0),
                fee=tx.get("fee", 0),
                nonce=tx["nonce"],
                status="rejected",
            )
        )
        session.commit()


# ---------------------------------------------------------------- L0


def test_l0_unsigned_tx_admitted_importer_direct(tmp_path):
    """L0 — importer-direct admission probe (no RPC; public submit is
    signature-gated closed per c23563-64).

    An unsigned BRIDGE_LOCK at the current armed version (v23 stamp)
    imports cleanly and writes a ``transaction`` row — the override-eligible
    class is reachable on the live import path today.
    """
    fixture = _make_db(tmp_path, "l0")
    tx = _unsigned_bridge_lock_tx()
    assert "signature" not in tx and "sig" not in tx
    engine, result, _root = _import(fixture, [tx])
    assert result.accepted, f"unsigned BRIDGE_LOCK rejected at v{BLOCK_VERSION}: {result.reason}"
    row = _stored_tx(engine)
    assert row.status == "confirmed"
    assert row.block_height == 1


# ---------------------------------------------------------------- L1


def test_l1_record_divergence_preexisting_vs_clean(tmp_path):
    """L1 — THE core divergence: same unsigned tx, node-A with a
    pre-existing (rejected-writeback) row vs node-B clean.

    Expected per E's model: node-A keeps ORIGINAL nonce=0 + original
    envelope; node-B stores OVERRIDDEN nonce=1 (live account nonce) +
    post-rewrite envelope. State roots identical — divergence is
    record-layer only, exactly the RL-1 class.
    """
    tx = _unsigned_bridge_lock_tx()

    eng_a, fac_a = _make_db(tmp_path, "nodeA")
    _seed_rejected_row(eng_a, tx)
    eng_b, fac_b = _make_db(tmp_path, "nodeB")

    engine_a, result_a, root_a = _import((eng_a, fac_a), [tx])
    engine_b, result_b, root_b = _import((eng_b, fac_b), [dict(tx)])
    assert result_a.accepted and result_b.accepted

    row_a = _stored_tx(engine_a)
    row_b = _stored_tx(engine_b)

    # State layer converges — same block, same root.
    assert root_a == root_b

    # Record layer diverges.
    assert row_a.nonce == 0, f"pre-existing row should keep original nonce, got {row_a.nonce}"
    assert row_b.nonce == 1, f"clean node should store overridden nonce=account nonce(1), got {row_b.nonce}"
    env_a = row_a.envelope or {}
    env_b = row_b.envelope or {}
    assert env_a.get("nonce") == 0
    assert env_b.get("nonce") == 1
    assert env_a != env_b


def test_l1_control_signed_tx_no_divergence(tmp_path):
    """L1 control — a SIGNED tx shows no divergence: the override does not
    fire (envelope nonce is authoritative at v7+), so both nodes store the
    same record regardless of pre-existing rows."""
    tx = _bridge_lock_tx(recorded_nonce=0, bridge_sign_nonce=0)
    tx["signature"] = sign_transaction_data(tx, KEY_A)

    eng_a, fac_a = _make_db(tmp_path, "ctrlA")
    _seed_rejected_row(eng_a, tx)
    eng_b, fac_b = _make_db(tmp_path, "ctrlB")

    engine_a, result_a, _ = _import((eng_a, fac_a), [tx])
    engine_b, result_b, _ = _import((eng_b, fac_b), [dict(tx)])
    assert result_a.accepted and result_b.accepted

    row_a = _stored_tx(engine_a)
    row_b = _stored_tx(engine_b)
    assert row_a.nonce == row_b.nonce == 0
    assert (row_a.envelope or {}).get("nonce") == (row_b.envelope or {}).get("nonce") == 0


# ---------------------------------------------------------------- L2


def test_l2_consumers_see_divergent_record(tmp_path):
    """L2 — consumer exposure: the divergent stored columns reach the
    reorg-requeue reader (``block_deltas._tx_payloads_at``) verbatim, and
    ``rpc/sync.py:export_chain`` serves ``Transaction.envelope`` to peers
    unchanged (``:146`` — pass-through, asserted by code cite + identical
    select shape here).

    LATENT-vs-LIVE read: peer state-sync serve is a propagation vector
    (LIVE for record dissemination); requeue re-apply re-derives the nonce
    via the same override, so apply-outcome impact is LATENT for this tx
    class. Digest normalization (``DIGEST_JSON_DROP_KEYS``) covers
    tx_hash/value/chain_id/falsy-signature spellings but NOT nonce content
    — the divergent field is outside the normalized set.
    """
    tx = _unsigned_bridge_lock_tx()
    eng_a, fac_a = _make_db(tmp_path, "cA")
    _seed_rejected_row(eng_a, tx)
    eng_b, fac_b = _make_db(tmp_path, "cB")
    engine_a, result_a, _ = _import((eng_a, fac_a), [tx])
    engine_b, result_b, _ = _import((eng_b, fac_b), [dict(tx)])
    assert result_a.accepted and result_b.accepted

    with Session(engine_a) as sa, Session(engine_b) as sb:
        pay_a = _tx_payloads_at(sa, CHAIN, 1)
        pay_b = _tx_payloads_at(sb, CHAIN, 1)
    assert len(pay_a) == len(pay_b) == 1
    assert pay_a[0].get("nonce") == 0
    assert pay_b[0].get("nonce") == 1
    # The requeue payload IS the stored envelope — divergence propagates.
    assert pay_a[0] != pay_b[0]
