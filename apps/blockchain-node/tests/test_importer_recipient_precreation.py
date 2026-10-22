"""FORK-1462 regression — the importer must not pre-create recipient accounts.

bc-2 forked at height 1462 when a zero-value ``GPU_MARKET`` offer addressed to
``0x0000…0000`` committed on the proposers (account root ``ffcdb1cb…``) while
every follower computed ``b4aef262…`` and rejected the block: the sequential
import path in ``sync_block_import`` created a ``balance=0, nonce=0`` account
row for the recipient before calling ``apply_transaction``, and the transition
deliberately never creates recipients for zero-value types. The proposal path
in ``consensus/poa.py`` explicitly avoids the same pre-creation (its comment:
"a proposer committed a header no other validator could reproduce").

These tests rebuild the 1462 shape on a small fixture state: each block is
constructed exactly like the proposer does — transactions applied through
``apply_transaction`` alone, then the resulting account root and committed
side-table fingerprint stamped on the header — and fed to
``ChainSync.import_block``, the follower path. The fix makes the two agree.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc_chain.base_models import Account, Block, ChainParameter
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state import side_root_shadow
from aitbc_chain.state.state_root_utils import compute_state_root_full
from aitbc_chain.state.state_transition import StateTransition, use_account_nonce_override
from aitbc_chain.sync import ChainSync
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.bridge_credit import sign_bridge_credit, sign_bridge_lock
from sqlmodel import Session, create_engine, select

CHAIN = "fork1462-fixture"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
BLOCK_VERSION = 14  # the era height 1462 was stamped under

KEY_A = "0x" + "11" * 32
KEY_BRIDGE = "0x" + "22" * 32
KEY_RECIPIENT = "0x" + "33" * 32

from aitbc.crypto.crypto import derive_ethereum_address

ADDR_A = derive_ethereum_address(KEY_A)
ADDR_BRIDGE = derive_ethereum_address(KEY_BRIDGE)
ADDR_B = derive_ethereum_address(KEY_RECIPIENT)
ADDR_NEW = derive_ethereum_address("0x" + "44" * 32)  # never seeded


@pytest.fixture()
def fixture_db(tmp_path, monkeypatch):
    """A file-backed sqlite DB with genesis + funded sender (nonce 1)."""
    monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path}/chain.db")
    chain_metadata.create_all(engine)

    @contextmanager
    def factory():
        with Session(engine) as session:
            yield session
            session.commit()

    with Session(engine) as session:
        # Sender at nonce 1, mirroring the real 1462 sender (one prior tx).
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
        session.add(ChainParameter(chain_id=CHAIN, parameter="bridge_release_authority", value=ADDR_BRIDGE, applied_height=0))
        session.flush()
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 0)).one()
        genesis.state_root = compute_state_root_full(session, CHAIN)
        session.commit()
    return engine, factory


def _signed_tx(key: str, sender_addr: str, nonce: int, tx_type: str = "TRANSFER", **extra: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": sender_addr,
        "to": extra.pop("to", ADDR_B),
        "amount": extra.pop("amount", 10),
        "fee": extra.pop("fee", DEFAULT_TX_FEE_UNITS),
        "nonce": nonce,
        "payload": extra.pop("payload", {}),
        "type": tx_type,
        "chain_id": CHAIN,
        **extra,
    }
    tx["signature"] = sign_transaction_data(tx, key)
    return tx


def _gpu_market_tx(nonce: int = 1) -> dict[str, Any]:
    """The 1462 shape: software offer, value 0, to the zero address."""
    return _signed_tx(
        KEY_A,
        ADDR_A,
        nonce,
        tx_type="GPU_MARKET",
        amount=0,
        to=ZERO_ADDRESS,
        tx_hash="0x" + "5e" * 32,
        payload={
            "action": "software_offer",
            "offer_id": "sw_offer_fixture_0001",
            "service_type": "whisper",
            "model": "base",
            "price": 0.02,
            "price_unit": "per_audio_min",
            "provider_address": ADDR_A,
            "provider_node_id": "fixture-node",
            "gpu_name": "FIXTURE GPU",
            "endpoint": "https://fixture.invalid/whisper",
            "status": "active",
        },
    )


def _bridge_lock_tx(nonce: int = 1) -> dict[str, Any]:
    tx = _signed_tx(
        KEY_A,
        ADDR_A,
        nonce,
        tx_type="BRIDGE_LOCK",
        amount=500,
        to="bridge_lock",
        tx_hash="0x" + "b1" * 32,
        payload={
            "transfer_id": "fixture-lock-1",
            "target_chain": "sep-fixture",
            "target_recipient": ADDR_B,
            "asset": "AIT",
            "eth_address": ADDR_B,
        },
    )
    tx["bridge_signature"] = sign_bridge_lock(tx, tx["tx_hash"], KEY_BRIDGE)
    return tx


def _bridge_release_tx() -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": "bridge_release",
        "to": ADDR_NEW,
        "amount": 500,
        "fee": 0,
        "nonce": 0,
        "payload": {"remote_chain": "fixture-remote", "remote_tx": "0xremote1"},
        "type": "BRIDGE_RELEASE",
        "chain_id": CHAIN,
        "tx_hash": "0x" + "b2" * 32,
    }
    tx["bridge_signature"] = sign_bridge_credit(tx, tx["tx_hash"], KEY_BRIDGE)
    return tx


def _proposer_roots(engine, txs: list[dict[str, Any]], height: int = 1) -> tuple[str | None, str]:
    """Apply exactly like the proposal path: no account pre-creation, the
    transition alone decides which rows exist. Returns (account root, aux
    fingerprint) over the post-apply state; the session is rolled back so the
    importer sees untouched fixture state."""
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


def _block(height: int, parent_hash: str, txs: list[dict[str, Any]], state_root: str, aux: str) -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": parent_hash,
        "proposer": ADDR_A,
        "timestamp": (T0 + timedelta(seconds=60 * height)).isoformat(),
        "tx_count": len(txs),
        "state_root": state_root,
        "aux_state_root": aux,
        "block_metadata": f'{{"state_transition_version": {BLOCK_VERSION}}}',
        "signature": "",
        "transactions": txs,
    }


def _accounts(session) -> dict[str, tuple[int, int]]:
    return {a.address: (a.balance, a.nonce) for a in session.exec(select(Account).where(Account.chain_id == CHAIN)).all()}


def _import_block(fixture_db, txs: list[dict[str, Any]], height: int = 1):
    engine, factory = fixture_db
    root, aux = _proposer_roots(engine, txs, height)
    block = _block(height, "0x" + "00" * 32, txs, root, aux)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(block, transactions=txs)
    return engine, result, root


def test_zero_value_gpu_market_to_zero_address_imports(fixture_db):
    """The 1462 case: a GPU_MARKET offer to 0x0 must import with the
    proposer's root — no phantom account row may be created."""
    engine, result, root = _import_block(fixture_db, [_gpu_market_tx()])
    assert result.accepted, f"block rejected: {result.reason}"
    with Session(engine) as session:
        stored = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).one()
        assert stored.state_root == root
        # The phantom row that produced the verifier root must not exist.
        assert session.get(Account, (CHAIN, ZERO_ADDRESS)) is None
        sender = session.get(Account, (CHAIN, ADDR_A))
        assert sender is not None and sender.nonce == 2


def test_message_to_new_address_leaves_no_phantom_row(fixture_db):
    """MESSAGE is zero-value too: a never-seen recipient must not appear."""
    tx = _signed_tx(KEY_A, ADDR_A, 1, tx_type="MESSAGE", amount=0, to=ADDR_NEW, tx_hash="0x" + "77" * 32)
    engine, result, root = _import_block(fixture_db, [tx])
    assert result.accepted, f"block rejected: {result.reason}"
    with Session(engine) as session:
        assert session.get(Account, (CHAIN, ADDR_NEW)) is None


def test_transfer_to_new_address_still_creates_recipient(fixture_db):
    """Regression the other way: non-zero-value apply still creates the
    recipient itself — the fix must not break first-touch transfers."""
    tx = _signed_tx(KEY_A, ADDR_A, 1, amount=123, to=ADDR_NEW, tx_hash="0x" + "78" * 32)
    engine, result, root = _import_block(fixture_db, [tx])
    assert result.accepted, f"block rejected: {result.reason}"
    with Session(engine) as session:
        recipient = session.get(Account, (CHAIN, ADDR_NEW))
        assert recipient is not None and recipient.balance == 123


def test_bridge_lock_pseudo_recipient_never_materializes(fixture_db):
    tx = _bridge_lock_tx()
    engine, result, root = _import_block(fixture_db, [tx])
    assert result.accepted, f"block rejected: {result.reason}"
    with Session(engine) as session:
        assert session.get(Account, (CHAIN, "bridge_lock")) is None


def test_bridge_release_recipient_created_and_credited(fixture_db):
    tx = _bridge_release_tx()
    engine, result, root = _import_block(fixture_db, [tx])
    assert result.accepted, f"block rejected: {result.reason}"
    with Session(engine) as session:
        recipient = session.get(Account, (CHAIN, ADDR_NEW))
        assert recipient is not None and recipient.balance == 500


@pytest.mark.parametrize(
    "tx_factory",
    [
        lambda: _gpu_market_tx(),
        lambda: _signed_tx(KEY_A, ADDR_A, 1, tx_type="MESSAGE", amount=0, to=ADDR_NEW, tx_hash="0x" + "77" * 32),
        lambda: _signed_tx(KEY_A, ADDR_A, 1, amount=123, to=ADDR_NEW, tx_hash="0x" + "78" * 32),
        lambda: _signed_tx(KEY_A, ADDR_A, 1, amount=50, to=ADDR_B, tx_hash="0x" + "79" * 32),
        lambda: _bridge_lock_tx(),
        lambda: _bridge_release_tx(),
        lambda: _signed_tx(
            KEY_A,
            ADDR_A,
            1,
            tx_type="IPFS_SUBSCRIPTION",
            amount=100,
            to=ADDR_B,
            tx_hash="0x" + "7a" * 32,
            payload={
                "island_id": "fixture-island",
                "duration_blocks": 1000,
                "quota_bytes": 1024,
                "member_address": ADDR_A,
            },
        ),
    ],
    ids=[
        "gpu_market->0x0",
        "message->new",
        "transfer->new",
        "transfer->existing",
        "bridge_lock",
        "bridge_release",
        "ipfs_subscription",
    ],
)
def test_importer_matches_proposer_root_per_type(fixture_db, tx_factory):
    """Parity sweep: for every fixture tx type the importer must accept the
    block the proposer would have committed, and the resulting account set
    must equal what apply_transaction alone produced."""
    engine, factory = fixture_db
    tx = tx_factory()
    txs = [tx]
    # Proposer-side: apply only, capture post-state + roots, roll back.
    st = StateTransition()
    with Session(engine) as session:
        data = dict(tx)
        data.setdefault("value", data.get("amount", 0))
        ok, err = st.apply_transaction(session, CHAIN, data, data["tx_hash"], block_version=BLOCK_VERSION, block_height=1)
        assert ok, f"fixture tx must apply on the proposer path: {err}"
        session.flush()
        root = compute_state_root_full(session, CHAIN)
        aux = side_root_shadow.committed_fingerprint(session.connection().connection, BLOCK_VERSION)["fingerprint"]
        want = _accounts(session)
        session.rollback()
    block = _block(1, "0x" + "00" * 32, txs, root, aux)
    sync = ChainSync(factory, chain_id=CHAIN, validate_signatures=False)
    result = sync.import_block(block, transactions=txs)
    assert result.accepted, f"{tx['type']} rejected: {result.reason}"
    with Session(engine) as session:
        assert _accounts(session) == want
