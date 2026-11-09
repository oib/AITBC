"""#1322: tentative-reorg apply probe before a winning peer segment displaces ours.

Flag ``sync_fork_apply_probe_enabled`` (default OFF). The probe always rolls
back; ``apply_invalid`` vetoes the reorg, ``inconclusive`` defers it, ``ok``
lets the existing reorg path run unchanged.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.models import Block
from aitbc_chain.state.state_transition import get_state_transition
from aitbc_chain.sync import settings as sync_settings

from . import test_fork_choice as fc
from .test_fork_choice import T0, _heights, _mk_block, _seed, _store, _sync

# Fixtures shared with the fork-choice suite (assignment, not import, so the
# fixture argument names below do not shadow an imported binding).
db_engine = fc.db_engine
reset_metrics = fc.reset_metrics
round_seconds = fc.round_seconds
session_factory = fc.session_factory


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


def _fork(session_factory, monkeypatch):
    """Ours: 4,5 (one proposer); peer: 4',5',6' (longer, wins on length)."""
    blocks = _seed(session_factory, 4)
    ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
    ours5 = _mk_block(5, ours4["hash"], T0 + timedelta(seconds=190))
    _store(session_factory, ours4)
    _store(session_factory, ours5)
    peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
    peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="p4")
    peer[5] = _mk_block(5, peer[4]["hash"], T0 + timedelta(seconds=125), hash_salt="p5")
    peer[6] = _mk_block(6, peer[5]["hash"], T0 + timedelta(seconds=155), hash_salt="p6")
    sync = _sync(session_factory)

    async def fake_fetch(start, end, source_url):
        return [peer[start]] if start in peer else []

    monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
    return sync, blocks, ours4, ours5


def _stub_append(sync, monkeypatch, *, accept: bool = True, raises: bool = False):
    seen: list[int] = []

    def fake(session, block_data, transactions=None, skip_state_root_validation=False, _probe=False):
        assert _probe is True, "probe must never use the committing path"
        seen.append(block_data["height"])
        if raises:
            raise RuntimeError("boom")
        # leave a durable-looking row in the transaction: the probe must roll it back
        session.add(
            Block(
                chain_id="test-chain",
                height=block_data["height"] + 100,
                hash=f"0xprobe{block_data['height']}",
                parent_hash="0x",
                proposer="p",
                timestamp=T0,
                tx_count=0,
                state_root="0x",
            )
        )
        session.flush()
        return SimpleNamespace(accepted=accept, reason="" if accept else "exceeds remaining obligation")

    monkeypatch.setattr(sync, "_append_block", fake)
    return seen


@pytest.mark.asyncio
async def test_flag_off_does_not_probe(session_factory, monkeypatch):
    monkeypatch.setattr(sync_settings, "sync_fork_apply_probe_enabled", False)
    sync, blocks, *_ = _fork(session_factory, monkeypatch)
    seen = _stub_append(sync, monkeypatch)
    assert await sync._resolve_fork_with_peer("https://peer", 5, 6) is True
    assert seen == []


@pytest.mark.asyncio
async def test_probe_ok_lets_the_reorg_through_and_leaves_no_trace(session_factory, monkeypatch):
    monkeypatch.setattr(sync_settings, "sync_fork_apply_probe_enabled", True)
    sync, blocks, *_ = _fork(session_factory, monkeypatch)
    seen = _stub_append(sync, monkeypatch)
    assert await sync._resolve_fork_with_peer("https://peer", 5, 6) is True
    assert seen == [4, 5, 6]
    # reorg removed our 4,5; the probe's stub rows (height+100) were rolled back
    assert _heights(session_factory) == [(b["height"], b["hash"]) for b in blocks]
    assert _counter("sync_fork_probe_ok_total") == 1.0


@pytest.mark.asyncio
async def test_unappliable_peer_segment_is_vetoed_and_our_segment_kept(session_factory, monkeypatch):
    monkeypatch.setattr(sync_settings, "sync_fork_apply_probe_enabled", True)
    sync, blocks, ours4, ours5 = _fork(session_factory, monkeypatch)
    before = _heights(session_factory)
    _stub_append(sync, monkeypatch, accept=False)
    assert await sync._resolve_fork_with_peer("https://peer", 5, 6) is False
    assert _heights(session_factory) == before
    assert _counter("sync_fork_probe_apply_invalid_total") == 1.0
    assert _counter("sync_fork_choice_remote_wins_total") == 0.0


@pytest.mark.asyncio
async def test_probe_error_is_inconclusive_not_a_veto_record(session_factory, monkeypatch):
    monkeypatch.setattr(sync_settings, "sync_fork_apply_probe_enabled", True)
    sync, *_ = _fork(session_factory, monkeypatch)
    before = _heights(session_factory)
    _stub_append(sync, monkeypatch, raises=True)
    assert await sync._resolve_fork_with_peer("https://peer", 5, 6) is False
    assert _heights(session_factory) == before
    assert _counter("sync_fork_probe_inconclusive_total") == 1.0
    assert _counter("sync_fork_probe_apply_invalid_total") == 0.0


@pytest.mark.asyncio
async def test_probe_restores_the_global_replay_cache(session_factory, monkeypatch):
    monkeypatch.setattr(sync_settings, "sync_fork_apply_probe_enabled", True)
    sync, *_ = _fork(session_factory, monkeypatch)
    st = get_state_transition()
    st._processed_nonces["0xabc"] = 7
    st._processed_tx_hashes.add("0xdead")
    _stub_append(sync, monkeypatch, accept=False)
    await sync._resolve_fork_with_peer("https://peer", 5, 6)
    assert st._processed_nonces == {"0xabc": 7}
    assert st._processed_tx_hashes == {"0xdead"}
    st._processed_nonces.clear()
    st._processed_tx_hashes.clear()
