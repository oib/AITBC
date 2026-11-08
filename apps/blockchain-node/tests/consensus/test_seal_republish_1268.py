"""#1268 Phase 1, item 3: re-publish an unconfirmed seal until a child exists
or a peer serves it. Flag off schedules nothing."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.models import Block
from sqlmodel import Session, create_engine

CHAIN = "test-chain"
SEAL = "0xseal"
PAYLOAD = {"chain_id": CHAIN, "height": 100, "hash": SEAL}


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


def _block(h: int, hash_: str, parent: str) -> Block:
    return Block(
        chain_id=CHAIN,
        height=h,
        hash=hash_,
        parent_hash=parent,
        proposer="p",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        tx_count=0,
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    metrics_registry.reset()
    eng = create_engine(f"sqlite:///{tmp_path / 'sr.db'}")
    chain_metadata.create_all(eng)
    config = ProposerConfig(
        chain_id=CHAIN, proposer_id="n", interval_seconds=1, max_block_size_bytes=1000, max_txs_per_block=10
    )
    proposer = PoAProposer(config=config, session_factory=lambda: Session(eng))
    broker = AsyncMock()
    locate = AsyncMock(return_value=None)
    monkeypatch.setattr(poa_module, "gossip_broker", broker)
    monkeypatch.setattr(poa_module, "locate_voted_block", locate)
    monkeypatch.setattr(settings, "seal_republish_enabled", True)
    monkeypatch.setattr(settings, "seal_republish_interval_seconds", 1.0)
    monkeypatch.setattr(settings, "seal_republish_max_seconds", 30.0)
    yield proposer, eng, broker, locate
    eng.dispose()
    metrics_registry.reset()


def _put(eng, *blocks) -> None:
    with Session(eng) as s:
        for b in blocks:
            s.add(b)
        s.commit()


@pytest.mark.asyncio
async def test_flag_off_schedules_nothing(env, monkeypatch):
    proposer, *_ = env
    monkeypatch.setattr(settings, "seal_republish_enabled", False)
    proposer._schedule_seal_republish("blocks.x", PAYLOAD)
    assert not proposer._republish_tasks


@pytest.mark.asyncio
async def test_unconfirmed_seal_is_republished_until_stopped(env):
    proposer, eng, broker, _ = env
    _put(eng, _block(100, SEAL, "0xparent"))
    proposer._schedule_seal_republish("blocks.x", PAYLOAD)
    assert len(proposer._republish_tasks) == 1
    await asyncio.sleep(2.3)
    proposer._stop_event.set()
    await asyncio.gather(*proposer._republish_tasks, return_exceptions=True)
    assert broker.publish.await_count >= 2
    assert broker.publish.await_args.args == ("blocks.x", PAYLOAD)
    assert _counter("seal_republished_total") >= 2


@pytest.mark.asyncio
async def test_a_child_settles_the_seal(env):
    proposer, eng, broker, _ = env
    _put(eng, _block(100, SEAL, "0xparent"), _block(101, "0xchild", SEAL))
    await proposer._republish_seal("blocks.x", PAYLOAD)
    broker.publish.assert_not_awaited()
    assert _counter("seal_republish_settled_total") == 1


@pytest.mark.asyncio
async def test_a_replaced_seal_is_never_republished(env):
    proposer, eng, broker, _ = env
    _put(eng, _block(100, "0xrival", "0xparent"))
    await proposer._republish_seal("blocks.x", PAYLOAD)
    broker.publish.assert_not_awaited()
    assert _counter("seal_republish_settled_total") == 1


@pytest.mark.asyncio
async def test_a_serving_peer_ends_the_republish(env):
    proposer, eng, broker, locate = env
    _put(eng, _block(100, SEAL, "0xparent"))
    locate.return_value = "https://peer1.example"
    await proposer._republish_seal("blocks.x", PAYLOAD)
    broker.publish.assert_not_awaited()
    assert _counter("seal_republish_peer_serves_total") == 1
    assert locate.await_args.args == (CHAIN, 100, {SEAL})


@pytest.mark.asyncio
async def test_gives_up_after_the_budget(env, monkeypatch):
    proposer, eng, broker, _ = env
    monkeypatch.setattr(settings, "seal_republish_max_seconds", 0.5)
    _put(eng, _block(100, SEAL, "0xparent"))
    await proposer._republish_seal("blocks.x", PAYLOAD)
    assert _counter("seal_republish_gave_up_total") == 1


@pytest.mark.asyncio
async def test_failed_publish_is_retried_not_fatal(env):
    proposer, eng, broker, _ = env
    _put(eng, _block(100, SEAL, "0xparent"))
    broker.publish.side_effect = [RuntimeError("redis down"), None, None]
    proposer._schedule_seal_republish("blocks.x", PAYLOAD)
    await asyncio.sleep(2.3)
    proposer._stop_event.set()
    await asyncio.gather(*proposer._republish_tasks, return_exceptions=True)
    assert broker.publish.await_count >= 2
