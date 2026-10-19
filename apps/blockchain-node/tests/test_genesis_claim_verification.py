"""Bootstrap-time verification of genesis claims (V-5).

``_ensure_genesis_block`` wrote whatever hash and state_root a genesis file or the
(removed) RPC bootstrap claimed, and every fleet genesis.json turned out to be an abandoned
pre-migration stub — a fresh node would write the wrong block 0 and only notice
when the next synced block failed its parent_hash check. ``_verify_genesis_claims``
recomputes the allocation state root (the same ``StateManager.update_account``
path ``compute_state_root_full`` uses) and the canonical block hash *before* the
block row or any account is committed, so a corrupted or stale genesis is refused
with a clear message and an untouched database.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.models import Block
from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie, StateManager
from sqlmodel import Session, create_engine, select

from aitbc_chain.metadata import chain_metadata

CHAIN_ID = "ait-test.example.net"
TIMESTAMP = "2026-08-12T10:55:15.216243+00:00"

ALLOC_A = {"address": "0xF5A930bBC90c15dB0bbf28f8485D18eEf24c3F43", "balance": 36_000_000_000_000_000, "nonce": 0}
ALLOC_B = {"address": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F", "balance": 1, "nonce": 0}


def _alloc_root(allocations) -> str:
    state = StateManager()
    for alloc in allocations:
        state.update_account(str(alloc["address"]), int(alloc["balance"]), int(alloc.get("nonce", 0)))
    return "0x" + state.get_root().hex()


def _empty_bridge_root() -> str:
    return "0x" + MerklePatriciaTrie().get_root().hex()


def _make_genesis(allocations, *, root=None, block_hash=None, timestamp=TIMESTAMP) -> dict:
    """A genesis file whose claims recompute, unless a caller overrides them.

    The shape mirrors the fleet's real files: claims live under ``block`` and
    allocations sit at the top level.
    """
    claimed_root = root if root is not None else _alloc_root(allocations)
    claimed_hash = (
        block_hash
        if block_hash is not None
        else compute_block_hash(
            CHAIN_ID,
            0,
            "0x00",
            datetime.fromisoformat(timestamp),
            [],
            "genesis",
            state_root=claimed_root,
            bridge_state_root=_empty_bridge_root(),
        )
    )
    return {
        "chain_id": CHAIN_ID,
        "block": {
            "height": 0,
            "hash": claimed_hash,
            "parent_hash": "0x00",
            "proposer": "genesis",
            "timestamp": timestamp,
            "tx_count": 0,
            "chain_id": CHAIN_ID,
            "state_root": claimed_root,
        },
        "allocations": allocations,
    }


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}", echo=False)
    chain_metadata.create_all(engine)

    @contextmanager
    def _factory():
        with Session(engine) as session:
            yield session

    try:
        yield _factory
    finally:
        engine.dispose()


def _proposer(session_factory) -> PoAProposer:
    """A proposer wired to an empty DB."""
    config = ProposerConfig(
        chain_id=CHAIN_ID,
        proposer_id="",
        interval_seconds=5,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )
    return PoAProposer(config=config, session_factory=session_factory)


def _patch_file(*, genesis_file: dict | None):
    return patch.object(
        PoAProposer,
        "_load_genesis_data_from_file",
        lambda self: genesis_file,
    )


def _genesis_block(session_factory) -> Block | None:
    with session_factory() as session:
        return session.exec(select(Block).where(Block.chain_id == CHAIN_ID).where(Block.height == 0)).first()


async def test_self_consistent_genesis_file_bootstraps(session_factory) -> None:
    node = _proposer(session_factory)
    file_patch = _patch_file(genesis_file=_make_genesis([ALLOC_A, ALLOC_B]))
    with file_patch:
        await node._ensure_genesis_block()

    genesis = _genesis_block(session_factory)
    assert genesis is not None
    assert genesis.state_root == _alloc_root([ALLOC_A, ALLOC_B])
    with session_factory() as session:
        from aitbc_chain.models import Account

        accounts = session.exec(select(Account).where(Account.chain_id == CHAIN_ID)).all()
    assert len(accounts) == 2


async def test_wrong_state_root_is_refused_and_writes_nothing(session_factory) -> None:
    node = _proposer(session_factory)
    file_patch = _patch_file(genesis_file=_make_genesis([ALLOC_A], root="0x00"))
    with file_patch:
        with pytest.raises(RuntimeError, match="state_root mismatch"):
            await node._ensure_genesis_block()

    assert _genesis_block(session_factory) is None
    with session_factory() as session:
        from aitbc_chain.models import Account

        assert session.exec(select(Account).where(Account.chain_id == CHAIN_ID)).all() == []


async def test_wrong_block_hash_is_refused_and_writes_nothing(session_factory) -> None:
    node = _proposer(session_factory)
    file_patch = _patch_file(genesis_file=_make_genesis([ALLOC_A], block_hash="0x" + "ab" * 32))
    with file_patch:
        with pytest.raises(RuntimeError, match="hash mismatch"):
            await node._ensure_genesis_block()

    assert _genesis_block(session_factory) is None


async def test_empty_allocations_must_claim_the_empty_root(session_factory) -> None:
    # An empty set is refused when it claims a root it cannot produce —
    # the pre-migration stub shape. A self-consistent empty genesis still
    # passes, so a brand-new island that allocates nothing is not broken.
    node = _proposer(session_factory)
    file_patch = _patch_file(genesis_file=_make_genesis([], root="0x" + "11" * 32))
    with file_patch:
        with pytest.raises(RuntimeError, match="state_root mismatch"):
            await node._ensure_genesis_block()
    assert _genesis_block(session_factory) is None

    node2 = _proposer(session_factory)
    file_patch = _patch_file(genesis_file=_make_genesis([]))
    with file_patch:
        await node2._ensure_genesis_block()
    genesis = _genesis_block(session_factory)
    assert genesis is not None
    assert genesis.state_root == _alloc_root([])


async def test_duplicated_allocation_address_is_refused(session_factory) -> None:
    dup = {"address": ALLOC_A["address"].lower(), "balance": 5, "nonce": 0}
    node = _proposer(session_factory)
    file_patch = _patch_file(genesis_file=_make_genesis([ALLOC_A, dup]))
    with file_patch:
        with pytest.raises(RuntimeError, match="duplicated allocation"):
            await node._ensure_genesis_block()
    assert _genesis_block(session_factory) is None


async def test_missing_file_refuses_without_any_rpc_call(session_factory) -> None:
    """RPC genesis bootstrap is removed: no file means a loud refusal, an
    untouched database, and zero network traffic — a partial RPC payload
    (no timestamp, parameters or bridge validators) can never be seeded."""
    node = _proposer(session_factory)
    fetch = AsyncMock(side_effect=AssertionError("genesis RPC must not be called"))
    with (
        _patch_file(genesis_file=None),
        patch("aitbc_chain.consensus.poa.SharedHttpClient.get", fetch),
        pytest.raises(RuntimeError, match="agent/genesis.json"),
    ):
        await node._ensure_genesis_block()

    fetch.assert_not_called()
    assert _genesis_block(session_factory) is None
    with session_factory() as session:
        from aitbc_chain.base_models import ChainParameter
        from aitbc_chain.cross_chain.bridge_validator import BridgeValidator
        from aitbc_chain.models import Account

        assert session.exec(select(Account).where(Account.chain_id == CHAIN_ID)).all() == []
        assert session.exec(select(ChainParameter).where(ChainParameter.chain_id == CHAIN_ID)).all() == []
        assert session.exec(select(BridgeValidator).where(BridgeValidator.chain_id == CHAIN_ID)).all() == []
