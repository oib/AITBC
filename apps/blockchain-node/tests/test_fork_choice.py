"""Deterministic fork choice in _resolve_fork and the pull-path resolver.

Rule (headers only): lower proposer round wins; ties break on lower block
hash. The push path (`import_block` -> `_resolve_fork`) can only decide when
the rival block shares our block's parent; the pull path
(`_resolve_fork_with_peer`) walks back to the common ancestor and compares
the two children of the fork point. A reorg is only applied when every block
we would lose is provably empty — there is no undo for account state.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.models import Block
from aitbc_chain.sync import ChainSync
from aitbc_chain.sync import settings as sync_settings
from sqlmodel import Session, create_engine, select

from aitbc_chain.metadata import chain_metadata

CHAIN = "test-chain"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


@pytest.fixture(autouse=True)
def round_seconds(monkeypatch):
    monkeypatch.setattr(sync_settings, "consensus_proposer_round_seconds", 60)


@pytest.fixture
def db_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fork.db'}", echo=False)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    @contextmanager
    def _factory():
        with Session(db_engine) as session:
            yield session

    return _factory


def _hash(*parts: object) -> str:
    return "0x" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _mk_block(
    height: int,
    parent_hash: str,
    ts: datetime,
    *,
    proposer: str = "proposer-a",
    tx_count: int = 0,
    state_root: str | None = None,
    hash_salt: object = "",
) -> dict[str, Any]:
    """A block dict (import payload) AND the hash it would be stored under."""
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": _hash(height, parent_hash, ts.isoformat(), hash_salt),
        "parent_hash": parent_hash,
        "proposer": proposer,
        "timestamp": ts.isoformat(),
        "tx_count": tx_count,
        "state_root": state_root,
    }


def _store(session_factory, block: dict[str, Any]) -> None:
    with session_factory() as session:
        session.add(
            Block(
                chain_id=CHAIN,
                height=block["height"],
                hash=block["hash"],
                parent_hash=block["parent_hash"],
                proposer=block["proposer"],
                timestamp=datetime.fromisoformat(block["timestamp"]),
                tx_count=block["tx_count"],
                state_root=block["state_root"],
            )
        )
        session.commit()


def _seed(session_factory, heights: int, *, start_ts: datetime = T0, step: int = 30) -> list[dict[str, Any]]:
    """Seed `heights` empty blocks, `step` seconds apart (round stays 0)."""
    blocks: list[dict[str, Any]] = []
    parent = "0x00"
    for h in range(heights):
        b = _mk_block(h, parent, start_ts + timedelta(seconds=step * h), state_root="0xstate")
        _store(session_factory, b)
        blocks.append(b)
        parent = b["hash"]
    return blocks


def _sync(session_factory) -> ChainSync:
    return ChainSync(session_factory, chain_id=CHAIN, validate_signatures=False)


def _heights(session_factory) -> list[tuple[int, str]]:
    with session_factory() as session:
        return [(b.height, b.hash) for b in session.exec(select(Block).order_by(Block.height)).all()]


class TestPushPathForkChoice:
    """import_block -> _resolve_fork with the rival block in hand."""

    def test_rival_lower_round_reorgs_us(self, session_factory):
        # our head 4 at round 1 (70s after parent); rival 4 at round 0 (5s).
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
        _store(session_factory, ours4)
        rival = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="rival")

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is True and result.reorged is True
        assert _heights(session_factory)[-1] == (4, rival["hash"])

    def test_rival_higher_round_rejected(self, session_factory):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95))
        _store(session_factory, ours4)
        rival = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), hash_salt="rival")

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False and result.diverged is True
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_choice_local_wins_total") == 1.0

    def test_same_round_lower_hash_wins(self, session_factory):
        blocks = _seed(session_factory, 4)
        ts = T0 + timedelta(seconds=95)
        ours4 = _mk_block(4, blocks[-1]["hash"], ts)
        rival = _mk_block(4, blocks[-1]["hash"], ts, hash_salt="rival")
        _store(session_factory, ours4)

        result = _sync(session_factory).import_block(rival, transactions=[])

        winner = min(ours4["hash"], rival["hash"])
        expected_accepted = rival["hash"] == winner
        assert result.accepted is expected_accepted
        assert _heights(session_factory)[-1] == (4, winner)

    def test_different_parent_is_undecidable(self, session_factory):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95))
        _store(session_factory, ours4)
        # rival descends from a different parent — its round is not derivable
        rival = _mk_block(4, "0xdeadbeef" + "0" * 56, T0 + timedelta(seconds=95), hash_salt="r")

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False and result.diverged is True
        assert _heights(session_factory)[-1] == (4, ours4["hash"])

    def test_nonempty_losing_segment_escalates(self, session_factory):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), tx_count=3)
        _store(session_factory, ours4)
        rival = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="rival")

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False and result.diverged is True
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_reorg_unsafe_total") == 1.0

    def test_reorg_depth_limit(self, session_factory):
        blocks = _seed(session_factory, 4, step=200)  # ours3 lands at T0+600, round 3
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=860))
        _store(session_factory, ours4)
        sync = _sync(session_factory)
        sync._max_reorg_depth = 1
        # rival at height 3 wins on round (10 s after the shared parent 2)
        rival3 = _mk_block(3, blocks[2]["hash"], T0 + timedelta(seconds=410), hash_salt="r3")
        result = sync.import_block(rival3, transactions=[])
        # removing heights 3..4 = 2 blocks > max_reorg_depth 1
        assert result.accepted is False
        assert metrics_registry._counters.get("sync_reorg_rejected_total") == 1.0


class TestPullPathForkChoice:
    """_resolve_fork_with_peer: walk-back to ancestor + fork-point compare."""

    async def test_peer_branch_wins_and_segment_removed(self, session_factory, monkeypatch):
        # ours: ...3 -> 4(r1) -> 5(r0-on-4). peer: ...3 -> 4'(r0) -> 5' -> 6'
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
        ours5 = _mk_block(5, ours4["hash"], T0 + timedelta(seconds=190))
        _store(session_factory, ours4)
        _store(session_factory, ours5)
        # peer shares the ancestor chain 0..3 and diverges at 4
        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="p4")
        peer[5] = _mk_block(5, peer[4]["hash"], T0 + timedelta(seconds=125), hash_salt="p5")
        peer[6] = _mk_block(6, peer[5]["hash"], T0 + timedelta(seconds=155), hash_salt="p6")

        sync = _sync(session_factory)

        async def fake_fetch(start, end, source_url):
            assert start == end
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=5) is True
        assert _heights(session_factory) == [(b["height"], b["hash"]) for b in blocks]
        assert metrics_registry._counters.get("sync_fork_choice_remote_wins_total") == 1.0

    async def test_our_branch_wins_peer_stays(self, session_factory, monkeypatch):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95))  # round 0
        _store(session_factory, ours4)
        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), hash_salt="p4")

        sync = _sync(session_factory)

        async def fake_fetch(start, end, source_url):
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4) is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_choice_local_wins_total") == 1.0

    async def test_no_common_ancestor_within_window(self, session_factory, monkeypatch):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95))
        _store(session_factory, ours4)
        sync = _sync(session_factory)

        async def fake_fetch(start, end, source_url):
            # peer chain disagrees at every height we hold
            return [{"hash": f"0xpeer{start}", "height": start, "timestamp": T0.isoformat()}]

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        monkeypatch.setattr(sync, "_max_reorg_depth", 2)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4) is False

    async def test_nonempty_segment_escalates_on_pull(self, session_factory, monkeypatch):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), tx_count=2)
        _store(session_factory, ours4)
        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="p4")

        sync = _sync(session_factory)

        async def fake_fetch(start, end, source_url):
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4) is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_reorg_unsafe_total") == 1.0
