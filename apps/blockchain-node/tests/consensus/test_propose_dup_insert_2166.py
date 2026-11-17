"""#2166 — a proposer finishing a round whose block was already imported must not error.

The PBFT certificate fixes the block hash, so a peer's copy can be imported by the
sync/gossip path while this proposer is still collecting attestations. The proposer's
own insert then tripped ``UNIQUE(chain_id, hash)`` every round and logged ERROR
"Failed to propose block". Same chain+hash+height is now a benign skip; a different
hash at the same height (fork) and other integrity errors still raise.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.models import Block
from sqlmodel import Session, select

CHAIN = "bc-2"
NOW = datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None)


def _block(height=10, h="0xaaa", parent="0xp") -> Block:
    return Block(
        chain_id=CHAIN,
        height=height,
        hash=h,
        parent_hash=parent,
        proposer="0xprop",
        timestamp=NOW,
        tx_count=0,
        state_root="0x00",
        bridge_state_root="0x00",
        aux_state_root="",
        signature="sig",
    )


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()


@pytest.fixture
def session(engine):
    """``engine`` is the shared in-memory chain schema fixture (tests/conftest.py)."""
    with Session(engine) as s:
        yield s


@pytest.fixture
def proposer():
    p = object.__new__(PoAProposer)
    p._logger = logging.getLogger("test2166")
    p._config = SimpleNamespace(chain_id=CHAIN)
    p._last_proposer_id = None
    p._last_block_timestamp = None
    return p


def _import_first(session, **kw):
    """The sync/gossip importer sealed the same block before the proposer's insert."""
    session.add(_block(**kw))
    session.commit()


def test_already_imported_block_is_a_benign_skip(proposer, session, caplog):
    _import_first(session)
    with caplog.at_level(logging.INFO, logger="test2166"):
        sealed = proposer._commit_and_record_block(session, _block(), "0xprop", None, NOW)
    assert sealed is False
    assert len(session.exec(select(Block)).all()) == 1
    assert metrics_registry._counters["poa_propose_already_sealed_total"] == 1
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert "already sealed" in caplog.text


def test_session_is_usable_after_the_skip(proposer, session):
    _import_first(session)
    proposer._commit_and_record_block(session, _block(), "0xprop", None, NOW)
    session.add(_block(height=11, h="0xbbb", parent="0xaaa"))
    session.commit()
    assert [b.height for b in session.exec(select(Block).order_by(Block.height)).all()] == [10, 11]


def test_same_hash_at_a_different_height_is_not_swallowed(proposer, session):
    _import_first(session, height=10)
    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        proposer._commit_and_record_block(session, _block(height=99), "0xprop", None, NOW)
    assert "poa_propose_already_sealed_total" not in metrics_registry._counters


def test_different_hash_at_the_same_height_still_raises(proposer, session):
    """A real fork (UNIQUE chain_id+height) is never treated as 'already sealed'."""
    _import_first(session, height=10, h="0xaaa")
    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        proposer._commit_and_record_block(session, _block(height=10, h="0xother"), "0xprop", None, NOW)
    assert "poa_propose_already_sealed_total" not in metrics_registry._counters


def test_normal_commit_still_returns_true(proposer, session):
    assert proposer._commit_and_record_block(session, _block(), "0xprop", None, NOW) is True
    assert len(session.exec(select(Block)).all()) == 1
    assert "poa_propose_already_sealed_total" not in metrics_registry._counters


# --- propose path: an already-sealed block is not re-broadcast ---------------------------

from .test_proposer_watchdog import _patch_pipeline  # noqa: E402
from .test_proposer_watchdog import proposer as watchdog_proposer  # noqa: E402,F401


async def _propose_with_commit(proposer, monkeypatch, commit_result):
    _patch_pipeline(proposer, monkeypatch)
    calls = []

    async def _broadcast(*_a, **_k):
        calls.append(1)
        return True

    monkeypatch.setattr(proposer, "_commit_and_record_block", lambda *_: commit_result)
    monkeypatch.setattr(proposer, "_broadcast_block", _broadcast)
    result = await proposer._propose_block_with_watchdog(watchdog_after=5.0)
    return result, calls


@pytest.mark.asyncio
async def test_already_sealed_block_is_not_rebroadcast(watchdog_proposer, monkeypatch):  # noqa: F811
    result, broadcasts = await _propose_with_commit(watchdog_proposer, monkeypatch, False)
    assert result is True  # the block is committed; the loop waits for the next slot
    assert broadcasts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_result", [True, None])
async def test_committed_block_is_broadcast_as_before(watchdog_proposer, monkeypatch, commit_result):  # noqa: F811
    result, broadcasts = await _propose_with_commit(watchdog_proposer, monkeypatch, commit_result)
    assert result is True
    assert broadcasts == [1]
