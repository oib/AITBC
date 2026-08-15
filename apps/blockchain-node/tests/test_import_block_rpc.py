"""Regression tests for v0.18.0 B1 — import_block RPC validation.

The RPC endpoint must route through the same validation as peer sync
(signature, parent linkage, state root) and must never delete an existing
block: a conflicting hash/height is a 409.
"""

import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.models import Block
from aitbc_chain.rpc import blocks as rpc_blocks
from eth_account import Account as EthAccount
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from aitbc.crypto.consensus_signing import sign_block_hash


def _hex(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test_import_block_rpc.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SQLModel.metadata.create_all(engine)

    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    # session_scope is imported into rpc.blocks from ..database — patch it there
    # (the ChainSync session factory closes over the module global).
    monkeypatch.setattr(rpc_blocks, "session_scope", _session_scope)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def mock_request():
    return Mock()


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


@pytest.mark.asyncio
async def test_import_valid_signed_block(isolated_engine, mock_request):
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()

    result = await rpc_blocks.import_block(mock_request, _signed_block(proposer, 1, genesis_hash))

    assert result["success"] is True
    assert result["accepted"] is True
    with Session(isolated_engine) as session:
        block = session.exec(select(Block).where(Block.chain_id == "chain-a", Block.height == 1)).first()
    assert block is not None
    assert block.proposer == proposer.address


@pytest.mark.asyncio
async def test_import_unsigned_block_rejected(isolated_engine, mock_request):
    """Bogus proposer with no signature must be rejected (fail closed)."""
    genesis_hash = _insert_genesis(isolated_engine)
    block_data = _signed_block(EthAccount.create(), 1, genesis_hash)
    block_data["signature"] = ""

    with pytest.raises(HTTPException) as exc_info:
        await rpc_blocks.import_block(mock_request, block_data)
    assert exc_info.value.status_code == 400

    with Session(isolated_engine) as session:
        assert session.exec(select(Block).where(Block.height == 1)).first() is None


@pytest.mark.asyncio
async def test_import_forged_signature_rejected(isolated_engine, mock_request):
    """A block signed by an impostor key claiming another proposer is rejected."""
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()
    impostor = EthAccount.create()
    block_data = _signed_block(proposer, 1, genesis_hash)
    block_data["signature"] = sign_block_hash(block_data["hash"], impostor.key.hex())

    with pytest.raises(HTTPException) as exc_info:
        await rpc_blocks.import_block(mock_request, block_data)
    assert exc_info.value.status_code == 400
    assert "signature" in exc_info.value.detail.lower()

    with Session(isolated_engine) as session:
        assert session.exec(select(Block).where(Block.height == 1)).first() is None


@pytest.mark.asyncio
async def test_import_bogus_state_root_rejected(isolated_engine, mock_request):
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()
    block_data = _signed_block(proposer, 1, genesis_hash, state_root="0x" + "11" * 32)

    with pytest.raises(HTTPException) as exc_info:
        await rpc_blocks.import_block(mock_request, block_data)
    assert exc_info.value.status_code == 400
    assert "state root" in exc_info.value.detail.lower()

    with Session(isolated_engine) as session:
        assert session.exec(select(Block).where(Block.height == 1)).first() is None


@pytest.mark.asyncio
async def test_import_unknown_parent_rejected(isolated_engine, mock_request):
    _insert_genesis(isolated_engine)
    proposer = EthAccount.create()
    block_data = _signed_block(proposer, 1, _hex("no-such-parent"))

    with pytest.raises(HTTPException) as exc_info:
        await rpc_blocks.import_block(mock_request, block_data)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_conflicting_height_is_409_never_delete(isolated_engine, mock_request):
    """Same height, different hash: 409 and the original block survives."""
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()
    original = _signed_block(proposer, 1, genesis_hash)
    result = await rpc_blocks.import_block(mock_request, original)
    assert result["success"] is True

    replacement = _signed_block(proposer, 1, genesis_hash, hash=_hex("replacement-block-1"))
    with pytest.raises(HTTPException) as exc_info:
        await rpc_blocks.import_block(mock_request, replacement)
    assert exc_info.value.status_code == 409

    with Session(isolated_engine) as session:
        block = session.exec(select(Block).where(Block.chain_id == "chain-a", Block.height == 1)).first()
    assert block is not None
    assert block.hash == original["hash"]


@pytest.mark.asyncio
async def test_conflicting_hash_elsewhere_is_409_never_delete(isolated_engine, mock_request):
    """Same hash at a different height: 409 and the original block survives.

    This is the v0.18.0 regression: the old code deleted the existing row.
    """
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()
    first = _signed_block(proposer, 1, genesis_hash)
    await rpc_blocks.import_block(mock_request, first)
    second = _signed_block(proposer, 2, first["hash"])
    await rpc_blocks.import_block(mock_request, second)

    # Re-import the height-1 hash at height 3 (parent = height-2 block).
    squatter = _signed_block(proposer, 3, second["hash"], hash=first["hash"])
    with pytest.raises(HTTPException) as exc_info:
        await rpc_blocks.import_block(mock_request, squatter)
    assert exc_info.value.status_code == 409

    with Session(isolated_engine) as session:
        block = session.exec(select(Block).where(Block.chain_id == "chain-a", Block.height == 1)).first()
        assert block is not None
        assert block.hash == first["hash"]
        assert session.exec(select(Block).where(Block.chain_id == "chain-a", Block.height == 3)).first() is None


@pytest.mark.asyncio
async def test_idempotent_reimport_same_block(isolated_engine, mock_request):
    genesis_hash = _insert_genesis(isolated_engine)
    proposer = EthAccount.create()
    block_data = _signed_block(proposer, 1, genesis_hash)
    first = await rpc_blocks.import_block(mock_request, block_data)
    assert first["success"] is True

    again = await rpc_blocks.import_block(mock_request, dict(block_data))
    assert again["success"] is True
    assert again["block_hash"] == block_data["hash"]
