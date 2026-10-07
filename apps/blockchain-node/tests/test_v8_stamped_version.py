"""v8 stamped-version semantics.

Below ``state_transition_v8_height`` a block's recorded
``state_transition_version`` is proposer-controlled and trusted (pre-v8
semantics). At or above it the stamp is advisory: ``get_block_version``
always uses the height-derived version, and a mismatched or missing stamp is
logged and counted (``block_version_stamp_mismatch_total``) — never obeyed
and never rejected. ``block_metadata`` is covered by neither the block hash
nor the proposer signature, so the stamp cannot be allowed to pick the rules
a block is validated under.
"""

import hashlib
import json
import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.models import Block
from aitbc_chain.config import settings
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.rpc import blocks as rpc_blocks
from aitbc_chain.state.state_transition import (
    get_block_version,
    get_block_version_for_height,
    get_recorded_block_version,
)
from eth_account import Account as EthAccount
from sqlmodel import Session, create_engine, select

from aitbc_chain.metadata import chain_metadata

from aitbc.crypto.consensus_signing import sign_block_hash


def _hex(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test_v8_stamped_version.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    chain_metadata.create_all(engine)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(rpc_blocks, "session_scope", _session_scope)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def mock_request():
    return Mock()


@pytest.fixture
def v8_active(monkeypatch):
    """v8 advisory semantics active from height 1 (v7 off; v9–v12 pinned off so a
    baked later height never outranks v8)."""
    monkeypatch.setattr(settings, "state_transition_v8_height", 1)
    monkeypatch.setattr(settings, "state_transition_v7_height", 0)
    monkeypatch.setattr(settings, "state_transition_v9_height", None)
    monkeypatch.setattr(settings, "state_transition_v10_height", None)
    monkeypatch.setattr(settings, "state_transition_v11_height", None)
    monkeypatch.setattr(settings, "state_transition_v12_height", None)
    return settings


def _insert_genesis(engine, chain_id="chain-a") -> str:
    genesis_hash = _hex(f"{chain_id}-genesis")
    with Session(engine) as session:
        session.add(
            Block(
                chain_id=chain_id,
                height=0,
                hash=genesis_hash,
                parent_hash="0x00",
                proposer="genesis",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                tx_count=0,
            )
        )
        session.commit()
    return genesis_hash


def _signed_block(proposer, height, parent_hash, chain_id="chain-a", **overrides):
    block_hash = overrides.pop("hash", _hex(f"{chain_id}-block-{height}-{proposer.address[:8]}"))
    block_data = {
        "chain_id": chain_id,
        "height": height,
        "hash": block_hash,
        "parent_hash": parent_hash,
        "proposer": proposer.address,
        "timestamp": datetime(2026, 1, 1, 0, 1, tzinfo=UTC).isoformat(),
        "tx_count": 0,
        "signature": sign_block_hash(block_hash, proposer.key.hex()),
    }
    block_data.update(overrides)
    return block_data


def _stamped(version, **overrides):
    return {"block_metadata": json.dumps({"state_transition_version": version}), **overrides}


# --- unit level ---------------------------------------------------------------


def test_recorded_version_extraction():
    assert get_recorded_block_version({"block_metadata": '{"state_transition_version": 7}'}) == 7
    assert get_recorded_block_version({"block_metadata": {"state_transition_version": 5}}) == 5
    assert get_recorded_block_version({"block_metadata": None}) is None
    assert get_recorded_block_version({"block_metadata": "{not json"}) is None
    assert get_recorded_block_version({"block_metadata": "{}"}) is None
    assert get_recorded_block_version({}) is None


def test_for_height_returns_8_above_v8(v8_active):
    assert get_block_version_for_height(0) == 2
    assert get_block_version_for_height(1) == 8
    assert get_block_version_for_height(99999) == 8


def test_below_v8_stamp_wins(v8_active):
    """Pre-v8 semantics are untouched: the recorded version governs."""
    assert get_block_version({"block_metadata": '{"state_transition_version": 5}'}, height=0) == 5
    assert get_block_version({"block_metadata": '{"state_transition_version": 1}'}, height=0) == 1


def test_at_v8_height_derived_version_wins(v8_active):
    """At/above v8 the recorded stamp is ignored entirely — matching or not."""
    assert get_block_version(_stamped(8), height=1) == 8
    assert get_block_version(_stamped(7), height=1) == 8  # stale stamp: ignored
    assert get_block_version(_stamped(1), height=50) == 8  # downgraded stamp: ignored
    assert get_block_version({}, height=1) == 8  # unstamped: tolerated
    assert get_block_version({"block_metadata": "{bad json"}, height=1) == 8


def test_mismatch_logs_and_counts(v8_active, caplog):
    metrics_registry.reset()
    with caplog.at_level(logging.WARNING, logger="aitbc_chain.state.state_transition"):
        assert get_block_version(_stamped(7), height=10) == 8
    assert metrics_registry._counters.get("block_version_stamp_mismatch_total") == 1
    assert any("state_transition_version=7" in r.message and "height requires 8" in r.message for r in caplog.records)


def test_matching_stamp_no_warning(v8_active, caplog):
    metrics_registry.reset()
    with caplog.at_level(logging.WARNING, logger="aitbc_chain.state.state_transition"):
        assert get_block_version(_stamped(8), height=10) == 8
    assert metrics_registry._counters.get("block_version_stamp_mismatch_total") is None
    assert not caplog.records


def test_below_v8_mismatch_silent(v8_active, caplog):
    """Below activation a wrong stamp governs silently — that is the pre-v8
    behavior this fleet replayed to 24800 without a single mismatch."""
    metrics_registry.reset()
    with caplog.at_level(logging.WARNING, logger="aitbc_chain.state.state_transition"):
        assert get_block_version(_stamped(3), height=0) == 3
    assert metrics_registry._counters.get("block_version_stamp_mismatch_total") is None


# --- through the import path ---------------------------------------------------


@pytest.mark.asyncio
async def test_import_correct_stamp_accepted(isolated_engine, mock_request, v8_active):
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    result = await rpc_blocks.import_block(mock_request, _signed_block(proposer, 1, genesis_hash, **_stamped(8)))

    assert result["success"] is True
    assert result["accepted"] is True
    with Session(isolated_engine) as session:
        block = session.exec(select(Block).where(Block.height == 1)).first()
    assert block is not None
    assert json.loads(block.block_metadata)["state_transition_version"] == 8


@pytest.mark.asyncio
async def test_import_stale_stamp_tolerated(isolated_engine, mock_request, v8_active):
    """A block stamped v7 at a v8 height imports and validates under v8 —
    the stamp can no longer downgrade the rules, so it is no longer fatal."""
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    result = await rpc_blocks.import_block(mock_request, _signed_block(proposer, 1, genesis_hash, **_stamped(7)))

    assert result["success"] is True
    assert result["accepted"] is True


@pytest.mark.asyncio
async def test_import_unstamped_tolerated(isolated_engine, mock_request, v8_active):
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    result = await rpc_blocks.import_block(mock_request, _signed_block(proposer, 1, genesis_hash))

    assert result["success"] is True
    assert result["accepted"] is True


@pytest.mark.asyncio
async def test_import_stamp_governs_below_activation(isolated_engine, mock_request, monkeypatch):
    """Pre-activation the stamp stays authoritative: a block stamped 5 is
    validated under v5 exactly as before."""
    monkeypatch.setattr(settings, "state_transition_v8_height", 100)
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    result = await rpc_blocks.import_block(mock_request, _signed_block(proposer, 1, genesis_hash, **_stamped(5)))

    assert result["success"] is True
