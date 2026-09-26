"""v8 stamped-version gate.

Below ``state_transition_v8_height`` a block's recorded
``state_transition_version`` is proposer-controlled and trusted (pre-v8
semantics). At or above it, import rejects a block whose recorded version
differs from ``get_block_version_for_height(height)`` — or that records none.
"""

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.models import Block
from aitbc_chain.config import settings
from aitbc_chain.rpc import blocks as rpc_blocks
from aitbc_chain.state.state_transition import (
    get_block_version_for_height,
    get_recorded_block_version,
    validate_recorded_version,
)
from eth_account import Account as EthAccount
from fastapi import HTTPException
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
    """v8 gate active from height 1 (and v7 far above the test heights)."""
    monkeypatch.setattr(settings, "state_transition_v8_height", 1)
    monkeypatch.setattr(settings, "state_transition_v7_height", 0)
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


def test_validate_lenient_when_disabled():
    assert validate_recorded_version({"block_metadata": '{"state_transition_version": 1}'}, 50000) == (True, "")
    assert validate_recorded_version({}, 50000) == (True, "")


def test_validate_lenient_below_activation(v8_active):
    # v8 activates at height 1; height 0 keeps the pre-v8 semantics.
    assert validate_recorded_version({}, 0) == (True, "")
    assert validate_recorded_version({"block_metadata": '{"state_transition_version": 3}'}, 0) == (True, "")


def test_validate_rejects_mismatch_and_unstamped(v8_active):
    ok, reason = validate_recorded_version(_stamped(7), 1)
    assert not ok and "7" in reason and "8" in reason
    ok, reason = validate_recorded_version({}, 5)
    assert not ok and "no state_transition_version" in reason
    ok, reason = validate_recorded_version(_stamped(9), 5)
    assert not ok
    assert validate_recorded_version(_stamped(8), 5) == (True, "")


# --- through the import path ---------------------------------------------------


@pytest.mark.asyncio
async def test_import_stamps_v8_accepted(isolated_engine, mock_request, v8_active):
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    result = await rpc_blocks.import_block(
        mock_request, _signed_block(proposer, 1, genesis_hash, **_stamped(8))
    )

    assert result["success"] is True
    assert result["accepted"] is True
    with Session(isolated_engine) as session:
        block = session.exec(select(Block).where(Block.height == 1)).first()
    assert block is not None
    assert json.loads(block.block_metadata)["state_transition_version"] == 8


@pytest.mark.asyncio
async def test_import_older_stamp_rejected(isolated_engine, mock_request, v8_active):
    """A proposer stamping v7 at a v8 height must be refused."""
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    with pytest.raises(HTTPException) as exc_info:
        await rpc_blocks.import_block(
            mock_request, _signed_block(proposer, 1, genesis_hash, **_stamped(7))
        )
    assert exc_info.value.status_code == 400

    with Session(isolated_engine) as session:
        assert session.exec(select(Block).where(Block.height == 1)).first() is None


@pytest.mark.asyncio
async def test_import_unstamped_rejected(isolated_engine, mock_request, v8_active):
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    with pytest.raises(HTTPException) as exc_info:
        await rpc_blocks.import_block(mock_request, _signed_block(proposer, 1, genesis_hash))
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_import_stale_stamp_lenient_below_activation(isolated_engine, mock_request, monkeypatch):
    """Pre-activation the stamp stays proposer-controlled: a block stamped 5
    below the v8 height imports exactly as before."""
    monkeypatch.setattr(settings, "state_transition_v8_height", 100)
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    result = await rpc_blocks.import_block(
        mock_request, _signed_block(proposer, 1, genesis_hash, **_stamped(5))
    )

    assert result["success"] is True
