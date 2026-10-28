"""Shared ACT-1 activation (V-2 + V-3 + V-4) at height 46,100.

Pins the armed defaults and the pre-activation identity: below H the block
hash preimage, the stamped state-transition version, and every apply rule are
byte-identical to the pre-activation chain. At H the block header commits the
13-table side-table root as ``aux_state_root`` (V-3) and a BRIDGE_LOCK with no
derivable leaf data is refused (V-4); v13's governance binding (V-2) is already
covered by test_governance_v13_binding.py.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.base_models import Account, Block, ChainParameter
from aitbc_chain.config import SHARED_ACTIVATION_HEIGHT, V13_HEIGHT_NOT_ARMED, settings
from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.database import chain_metadata
from aitbc_chain.state.side_root_shadow import committed_fingerprint
from aitbc_chain.state.state_transition import StateTransition, get_block_version_for_height

H = SHARED_ACTIVATION_HEIGHT
CHAIN = "ait-test"
AUTH_KEY = "0x" + "66" * 32
SENDER = "0x" + "ab" * 20


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _isolate_ladder_above_v14(monkeypatch):
    """v17 is code-pinned at 8900 — below this file's H-era heights — so the
    default ladder answers 17 everywhere these tests probe. Park the rungs
    above v14 (v16/v17/v18) so the tests exercise only the v13–v15 rungs they
    assert on; a test may still arm v15 itself via monkeypatch."""
    monkeypatch.setattr(settings, "state_transition_v16_height", None)
    monkeypatch.setattr(settings, "state_transition_v17_height", None)
    monkeypatch.setattr(settings, "state_transition_v18_height", None)


# --- The shared height and the version ladder ---------------------------------


def test_shared_height_defaults_to_46100():
    """The operator's 12 Oct decision is pinned: both thresholds arm at H."""
    assert SHARED_ACTIVATION_HEIGHT == 46100
    assert settings.state_transition_v13_height == H
    assert settings.state_transition_v14_height == H


def test_version_boundary_at_h():
    """Below H the stamped version stays 12; at H the v14 rung applies."""
    assert get_block_version_for_height(H - 1) == 12
    assert get_block_version_for_height(H) == 14
    # v14 shadows v13 on the ladder at the same armed height — far-future
    # heights stamp 14, not 13.
    assert get_block_version_for_height(V13_HEIGHT_NOT_ARMED) == 14


def test_v13_rung_when_armed_before_v14(monkeypatch):
    """A STOP-rule split (v13 armed below v14) still produces version 13
    blocks in the gap — the ladder keeps both rungs."""
    monkeypatch.setattr(settings, "state_transition_v13_height", H - 100)
    monkeypatch.setattr(settings, "state_transition_v14_height", H)
    assert get_block_version_for_height(H - 101) == 12
    assert get_block_version_for_height(H - 100) == 13
    assert get_block_version_for_height(H - 1) == 13
    assert get_block_version_for_height(H) == 14


def test_v15_rung_unarmed_by_default():
    """EDGE-REG-CONSENSUS-1: the committed-set change sits behind
    state_transition_v15_height, which is None until the operator pins a
    fleet activation height — nothing changes while it is unset."""
    assert settings.state_transition_v15_height is None
    assert get_block_version_for_height(H) == 14
    assert get_block_version_for_height(H + 10_000_000) == 14


def test_v15_rung_when_armed(monkeypatch):
    """Pinning the height stamps 15 from the boundary on; below it the
    ladder is unchanged."""
    monkeypatch.setattr(settings, "state_transition_v15_height", H + 1000)
    assert get_block_version_for_height(H) == 14
    assert get_block_version_for_height(H + 999) == 14
    assert get_block_version_for_height(H + 1000) == 15
    assert get_block_version_for_height(H + 1001) == 15


def test_v15_fingerprint_excludes_edge_registration(session):
    """The same database fingerprints differently at v14 vs v15 only via
    edge_node_registration — the table a local RPC write can still touch."""
    from aitbc_chain.state.gpu_resources import EdgeNodeRegistration

    session.add(Account(chain_id=CHAIN, address="0x" + "11" * 20, balance=5, nonce=0))
    session.add(EdgeNodeRegistration(chain_id=CHAIN, node_id="n1", endpoint="http://x", registered_by="0x" + "22" * 20))
    session.commit()
    conn = session.connection().connection
    fp14 = committed_fingerprint(conn, 14)
    fp15 = committed_fingerprint(conn, 15)
    assert fp14["fingerprint"] != fp15["fingerprint"]
    assert "edge_node_registration" in fp14["tables"]
    assert "edge_node_registration" not in fp15["tables"]
    # deleting the row changes v14 but cannot touch v15 — the table is out
    # of its digest set entirely
    session.query(EdgeNodeRegistration).delete()
    session.commit()
    conn = session.connection().connection
    assert committed_fingerprint(conn, 15)["fingerprint"] == fp15["fingerprint"]
    assert committed_fingerprint(conn, 14)["fingerprint"] != fp14["fingerprint"]


# --- The hash: aux is a new preimage term only when set -------------------------


def test_hash_preimage_unchanged_without_aux():
    """Absent/empty aux reproduces the literal pre-v14 formula."""
    ts = "2026-10-13T18:00:00+00:00"
    preimage = f"chain|100|0xpar|{ts}|a|b|prop|0xsr|0xbr".encode()
    expected = "0x" + hashlib.sha256(preimage).hexdigest()
    assert compute_block_hash("chain", 100, "0xpar", ts, ["a", "b"], "prop", "0xsr", "0xbr") == expected
    assert compute_block_hash("chain", 100, "0xpar", ts, ["a", "b"], "prop", "0xsr", "0xbr", None) == expected
    # The import/attestation path passes "" for missing aux — same preimage.
    assert compute_block_hash("chain", 100, "0xpar", ts, ["a", "b"], "prop", "0xsr", "0xbr", "") == expected


def test_hash_binds_aux_when_set():
    base = compute_block_hash("chain", H, "0xpar", "t", [], "prop", "0xsr", "0xbr")
    auxed = compute_block_hash("chain", H, "0xpar", "t", [], "prop", "0xsr", "0xbr", "abcd0123")
    assert auxed != base
    assert auxed == compute_block_hash("chain", H, "0xpar", "t", [], "prop", "0xsr", "0xbr", "abcd0123")


# --- The header field ---------------------------------------------------------


def test_block_aux_field_roundtrip(session):
    """The column exists and round-trips the 16-hex fingerprint."""
    block = Block(
        chain_id=CHAIN,
        height=H,
        hash="0x" + "aa" * 32,
        parent_hash="0x" + "00" * 32,
        proposer="0x" + "bb" * 20,
        tx_count=0,
        aux_state_root="abcd0123cafebabe",
    )
    session.add(block)
    session.commit()
    assert session.exec(select(Block).where(Block.height == H)).one().aux_state_root == "abcd0123cafebabe"


def test_block_aux_field_null_pre_v14(session):
    block = Block(
        chain_id=CHAIN,
        height=H - 1,
        hash="0x" + "cc" * 32,
        parent_hash="0x" + "00" * 32,
        proposer="0x" + "bb" * 20,
        tx_count=0,
    )
    session.add(block)
    session.commit()
    assert session.exec(select(Block).where(Block.height == H - 1)).one().aux_state_root is None


def test_committed_fingerprint_is_deterministic(session):
    """The same fingerprint both sides of the seal/import path compare."""
    session.add(Account(chain_id=CHAIN, address="0x" + "11" * 20, balance=5, nonce=0))
    session.commit()
    conn = session.connection().connection
    fp1 = committed_fingerprint(conn)["fingerprint"]
    fp2 = committed_fingerprint(conn)["fingerprint"]
    assert fp1 == fp2 and len(fp1) == 16


# --- V-4: the guard becomes a refusal at v14 -----------------------------------


def _seed_lock_state(session):
    from aitbc.crypto.crypto import derive_ethereum_address

    session.add(
        ChainParameter(
            chain_id=CHAIN,
            parameter="bridge_release_authority",
            value=derive_ethereum_address(AUTH_KEY),
        )
    )
    session.add(Account(chain_id=CHAIN, address=SENDER, balance=1_000_000, nonce=0))
    session.commit()


def _bridge_lock(leaf_fields: dict | None, *, envelope_leaf: bool = False) -> tuple[dict, str]:
    from aitbc_chain.state.bridge_credit import sign_bridge_lock

    tx_hash = "0x" + "ab" * 32
    lock = {
        "chain_id": CHAIN,
        "type": "BRIDGE_LOCK",
        "from": SENDER,
        "to": "bridge_lock",
        "amount": 10,
        "fee": 1,
        "nonce": 0,
        "tx_hash": tx_hash,
        "payload": dict(leaf_fields) if leaf_fields and not envelope_leaf else {},
    }
    if leaf_fields and envelope_leaf:
        # GAP-47 shape: leaf fields live on the signed envelope top level.
        lock.update(leaf_fields)
    lock["bridge_signature"] = sign_bridge_lock(lock, tx_hash, AUTH_KEY)
    return lock, tx_hash


def _validate(session, lock, tx_hash, block_version):
    return StateTransition().validate_transaction(session, CHAIN, lock, tx_hash, block_version=block_version, block_height=H)


def test_v14_refuses_lock_without_leaf_data(session):
    _seed_lock_state(session)
    lock, tx_hash = _bridge_lock(None)
    ok, msg = _validate(session, lock, tx_hash, block_version=14)
    assert not ok
    assert "no derivable leaf data" in msg


def test_v14_accepts_lock_with_payload_leaf(session):
    _seed_lock_state(session)
    lock, tx_hash = _bridge_lock({"transfer_id": "t1", "amount": 10, "target_chain": "other"})
    ok, msg = _validate(session, lock, tx_hash, block_version=14)
    assert ok, msg


def test_v14_accepts_lock_with_envelope_leaf(session):
    _seed_lock_state(session)
    lock, tx_hash = _bridge_lock({"transfer_id": "t1", "amount": 10, "target_chain": "other"}, envelope_leaf=True)
    ok, msg = _validate(session, lock, tx_hash, block_version=14)
    assert ok, msg


def test_pre_v14_unreadable_lock_still_validates(session):
    """Grandfathering: below the shared height the same lock passes — the
    dry-run guard only counts it."""
    _seed_lock_state(session)
    lock, tx_hash = _bridge_lock(None)
    ok, msg = _validate(session, lock, tx_hash, block_version=13)
    assert ok, msg
