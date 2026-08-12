"""The proposer signature must survive a sync hop.

A block is signed once, by its proposer, at production time. Every node that
receives it afterwards authenticates the proposer from that signature -- so the
field has to survive being serialised out of one node and imported into the
next. It did not:

  - ``get_blocks_range`` -- the endpoint peer sync pulls from -- built a
    seven-field dict and left ``signature`` out.
  - ``get_block`` did the same, in both the response and the header it seeded
    the cache with.
  - ``sync_block_import`` validated ``block_data["signature"]`` and then
    constructed the ``Block`` row without it.

Each of those is individually invisible: every field the caller asked about was
present and correct. Together they meant a signed chain became unsigned the
moment it crossed an RPC boundary, and a follower validating fail-closed could
never import anything. The deployed follower sat at height 93,274 for nine days
with 12,287 blocks of backlog, logging "Unsigned block and no trusted proposer
set configured" once per block per retry.

The existing import tests asserted ``block.proposer`` after a successful import
and stopped there, which is why three separate drops of the field went
unnoticed. These tests assert on the signature specifically, and the last one
asserts on the property that actually matters: export -> import -> export leaves
a signature that still verifies against the original proposer.
"""

import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from aitbc_chain.block_cache import get_block_header_cache
from aitbc_chain.models import Block
from aitbc_chain.rpc import blocks as rpc_blocks
from eth_account import Account as EthAccount
from sqlmodel import Session, SQLModel, create_engine, select

from aitbc.crypto.consensus_signing import sign_block_hash, verify_block_signature

CHAIN = "chain-sig"


def _hex(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


def _engine_for(tmp_path, name):
    engine = create_engine(f"sqlite:///{tmp_path / name}", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _scope_for(engine):
    @contextmanager
    def _session_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    return _session_scope


@pytest.fixture
def node_a(tmp_path, monkeypatch):
    """A node that produced its own signed chain."""
    engine = _engine_for(tmp_path, "node_a.db")
    monkeypatch.setattr(rpc_blocks, "session_scope", _scope_for(engine))
    # The header cache is a process-wide singleton, so a height cached by one
    # test would be served to the next one.
    get_block_header_cache().clear()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def mock_request():
    return Mock()


def _produce_signed_block(engine, proposer, height, parent_hash):
    """Write a block the way consensus/poa.py does -- signature included."""
    block_hash = _hex(f"{CHAIN}-{height}")
    signature = sign_block_hash(block_hash, proposer.key.hex())
    with Session(engine) as session:
        session.add(
            Block(
                chain_id=CHAIN,
                height=height,
                hash=block_hash,
                parent_hash=parent_hash,
                proposer=proposer.address,
                timestamp=datetime(2026, 1, 1, 0, height, tzinfo=UTC),
                tx_count=0,
                state_root=None,
                signature=signature,
            )
        )
        session.commit()
    return block_hash, signature


def _genesis(engine):
    genesis_hash = _hex(f"{CHAIN}-genesis")
    with Session(engine) as session:
        session.add(
            Block(
                chain_id=CHAIN,
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


@pytest.mark.asyncio
async def test_blocks_range_serves_the_signature(node_a, mock_request):
    """The endpoint peer sync pulls from must carry what peer sync validates."""
    genesis_hash = _genesis(node_a)
    proposer = EthAccount.create()
    block_hash, signature = _produce_signed_block(node_a, proposer, 1, genesis_hash)

    result = await rpc_blocks.get_blocks_range(mock_request, start=1, end=1, chain_id=CHAIN)

    (served,) = result["blocks"]
    assert served["signature"] == signature
    assert verify_block_signature(block_hash, served["signature"], proposer.address)


@pytest.mark.asyncio
async def test_get_block_serves_the_signature(node_a, mock_request):
    genesis_hash = _genesis(node_a)
    proposer = EthAccount.create()
    block_hash, signature = _produce_signed_block(node_a, proposer, 1, genesis_hash)

    served = await rpc_blocks.get_block(mock_request, height=1, chain_id=CHAIN)

    assert served["signature"] == signature
    assert verify_block_signature(block_hash, served["signature"], proposer.address)


@pytest.mark.asyncio
async def test_cached_and_uncached_headers_agree(node_a, mock_request):
    """A field present on a cache miss and absent on a hit is worse than absent.

    ``get_block`` seeds the header cache with its own dict. If that dict omits
    the signature, the first read after a restart carries it and every read
    afterwards does not -- an intermittent failure that depends on process
    uptime.
    """
    genesis_hash = _genesis(node_a)
    proposer = EthAccount.create()
    _produce_signed_block(node_a, proposer, 1, genesis_hash)

    first = await rpc_blocks.get_block(mock_request, height=1, chain_id=CHAIN)
    second = await rpc_blocks.get_block(mock_request, height=1, chain_id=CHAIN)

    assert first["signature"] == second["signature"]
    assert set(first) == set(second)


@pytest.mark.asyncio
async def test_signature_survives_a_sync_hop(node_a, tmp_path, monkeypatch, mock_request):
    """Export from A, import into B, export from B: still verifiable.

    This is the property the deployed network needed and did not have. Node B
    stands in for a follower: it never saw the proposer's key and can only
    authenticate the block from what node A sent it.
    """
    genesis_hash = _genesis(node_a)
    proposer = EthAccount.create()
    block_hash, signature = _produce_signed_block(node_a, proposer, 1, genesis_hash)

    exported = (await rpc_blocks.get_blocks_range(mock_request, start=1, end=1, chain_id=CHAIN))["blocks"][0]
    exported["chain_id"] = CHAIN

    node_b = _engine_for(tmp_path, "node_b.db")
    try:
        monkeypatch.setattr(rpc_blocks, "session_scope", _scope_for(node_b))
        _genesis(node_b)

        result = await rpc_blocks.import_block(mock_request, dict(exported))
        assert result["accepted"] is True

        # Stored, not merely checked in flight.
        with Session(node_b) as session:
            stored = session.exec(select(Block).where(Block.chain_id == CHAIN, Block.height == 1)).first()
        assert stored is not None
        assert stored.signature == signature, "node B validated the signature and then discarded it"

        # And re-servable, so a third node can authenticate the block from B.
        reexported = (await rpc_blocks.get_blocks_range(mock_request, start=1, end=1, chain_id=CHAIN))["blocks"][0]
        assert verify_block_signature(block_hash, reexported["signature"], proposer.address)
    finally:
        node_b.dispose()
