"""Deterministic fork choice in _resolve_fork and the pull-path resolver.

Rule (headers only): the push path (`import_block` -> `_resolve_fork`) decides
only a *tip race* — rival shares our head's parent and our head has no
descendants — where the lower ``(round, hash)`` wins. Anything deeper defers
to the pull path (`_resolve_fork_with_peer`), which compares branch weight in
order: distinct proposers in the segment, then segment length. A full tie
defers for one round window — the freshness gate stops the reconnected side
proposing while the majority keeps producing, so the next comparison decides
by length; ``(round, hash)`` settles the tie only if the branches are still
equal after the window. A reorg is only applied when every block
we would lose is provably empty — there is no undo for account state — and
only after the rival side has passed signature, timestamp, and proposer
schedule validation.
"""

from __future__ import annotations

import hashlib
import json
import time
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
VAL_A = "0x" + "aa" * 20
VAL_B = "0x" + "bb" * 20


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
    """import_block -> _resolve_fork: tip races only, rival validated first."""

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

    def test_rival_defers_when_we_have_descendants(self, session_factory):
        # Conflict below the tip: a single rival header cannot outweigh our
        # whole segment — the pull resolver decides on branch weight.
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
        ours5 = _mk_block(5, ours4["hash"], T0 + timedelta(seconds=190))
        _store(session_factory, ours4)
        _store(session_factory, ours5)
        # rival at height 4 — same parent, better round — but our head is 5
        rival = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="rival")

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False and result.diverged is True
        assert _heights(session_factory)[-1] == (5, ours5["hash"])
        # no inline reorg happened
        assert metrics_registry._counters.get("sync_reorgs_total") is None

    def test_rival_invalid_signature_rejected_before_reorg(self, session_factory, monkeypatch):
        # A rival that *looks* like it wins (lower round) but fails signature
        # validation must not cost us our head — the delete must not happen.
        # import_block checks the signature first; this stub passes that gate
        # and fails only when _resolve_fork re-validates, proving the fork
        # path checks before it deletes.
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
        _store(session_factory, ours4)
        rival = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="rival")

        sync = _sync(session_factory)
        sync._validate_signatures = True
        calls: list[int] = []

        def flaky_sig(block_data):
            calls.append(1)
            return (len(calls) == 1), "forged on re-check"

        monkeypatch.setattr(sync._validator, "validate_block_signature", flaky_sig)
        result = sync.import_block(rival, transactions=[])

        assert result.accepted is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert len(calls) == 2  # the fork path re-validated, then refused
        assert metrics_registry._counters.get("sync_fork_invalid_rival_total") == 1.0

    def test_rival_wrong_round_owner_rejected(self, session_factory, monkeypatch):
        # Schedule check before delete: rival claims a round that belongs to a
        # different validator — rejected even though its key would win.
        monkeypatch.setattr(sync_settings, "multi_validator_consensus_enabled", True)
        monkeypatch.setattr(sync_settings, "bridge_block_signature_required", False)
        monkeypatch.setattr(
            sync_settings, "validator_set", json.dumps([{"address": VAL_A}, {"address": VAL_B}])
        )
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), proposer=VAL_A)
        _store(session_factory, ours4)
        # height 4 round 0 belongs to sorted[0] = VAL_A; rival claims VAL_B
        rival = _mk_block(
            4, blocks[-1]["hash"], T0 + timedelta(seconds=95), proposer=VAL_B, hash_salt="rival"
        )

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_invalid_rival_total") == 1.0

    def test_rival_future_timestamp_rejected(self, session_factory):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
        _store(session_factory, ours4)
        rival = _mk_block(
            4, blocks[-1]["hash"], datetime.now(UTC) + timedelta(seconds=3600), hash_salt="rival"
        )

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])

    def test_rival_predating_parent_rejected(self, session_factory):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
        _store(session_factory, ours4)
        rival = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=30), hash_salt="rival")
        # parent block 3 sits at T0+90 — rival claims T0+30 < parent

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])

    def test_rival_bad_state_root_rolls_back_delete(self, session_factory):
        # The delete+append share one transaction: a rival that passes header
        # checks but fails _append_block's state-root comparison must leave
        # our head in place — the append's rollback undoes the staged delete.
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
        _store(session_factory, ours4)
        rival = _mk_block(
            4,
            blocks[-1]["hash"],
            T0 + timedelta(seconds=95),
            state_root="0x" + "ab" * 32,
            hash_salt="rival",
        )

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])

    def test_nonempty_tip_escalates(self, session_factory):
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), tx_count=3)
        _store(session_factory, ours4)
        rival = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="rival")

        result = _sync(session_factory).import_block(rival, transactions=[])

        assert result.accepted is False and result.diverged is True
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_reorg_unsafe_total") == 1.0


class TestPullPathForkChoice:
    """_resolve_fork_with_peer: walk-back + branch-weight comparison."""

    async def test_peer_branch_wins_and_segment_removed(self, session_factory, monkeypatch):
        # ours: ...3 -> 4(r1) -> 5 — one proposer. peer: ...3 -> 4' -> 5' -> 6'
        # — same single proposer but a longer segment: peer wins on length.
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
            assert start == end
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=5, remote_height=6) is True
        assert _heights(session_factory) == [(b["height"], b["hash"]) for b in blocks]
        assert metrics_registry._counters.get("sync_fork_choice_remote_wins_total") == 1.0

    async def test_lone_proposer_loses_to_majority_segment(self, session_factory, monkeypatch):
        # The partition case: we were isolated and produced 4@round0 and 5
        # alone. The majority produced 4'@round2 then 5', 6' with three
        # different proposers. Our lower fork-point round must NOT win.
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), proposer="lone")
        ours5 = _mk_block(5, ours4["hash"], T0 + timedelta(seconds=125), proposer="lone")
        _store(session_factory, ours4)
        _store(session_factory, ours5)
        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        # peer's 4' at round 2 (150s after parent) — worse key, more support
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=240), proposer="p1", hash_salt="p4")
        peer[5] = _mk_block(5, peer[4]["hash"], T0 + timedelta(seconds=270), proposer="p2", hash_salt="p5")
        peer[6] = _mk_block(6, peer[5]["hash"], T0 + timedelta(seconds=300), proposer="p3", hash_salt="p6")

        sync = _sync(session_factory)

        async def fake_fetch(start, end, source_url):
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=5, remote_height=6) is True
        assert _heights(session_factory) == [(b["height"], b["hash"]) for b in blocks]
        assert metrics_registry._counters.get("sync_fork_choice_remote_wins_total") == 1.0

    async def test_full_tie_defers_then_key_decides_after_window(self, session_factory, monkeypatch):
        # 1-vs-1 proposers, 1-vs-1 length: settling by (round, hash) now would
        # let a lone node's round-1 child beat the majority's round-2 child, so
        # the resolver defers for one round window. Only a tie that survives
        # the window falls back to the fork-point key.
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95))  # round 0
        _store(session_factory, ours4)
        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), hash_salt="p4")

        sync = _sync(session_factory)

        async def fake_fetch(start, end, source_url):
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)

        # First comparison defers; a re-check inside the window stays deferred.
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=4) is False
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=4) is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_choice_deferred_total") == 1.0
        assert metrics_registry._counters.get("sync_fork_choice_local_wins_total") is None
        assert metrics_registry._counters.get("sync_reorgs_total") is None

        # Window expired and branches still tied — the key settles it. Our
        # round-0 child outranks their round-1 child: local wins, no reorg.
        sync._deferred_forks[3] = time.monotonic() - 1
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=4) is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_choice_local_wins_total") == 1.0
        assert 3 not in sync._deferred_forks

    async def test_full_tie_defers_then_peer_growth_wins_by_length(self, session_factory, monkeypatch):
        # The intended tie outcome: the peer's branch produces another block
        # during the defer window, so the re-check decides by length and the
        # (round, hash) key never runs — our losing segment is removed.
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95))
        _store(session_factory, ours4)
        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), hash_salt="p4")

        sync = _sync(session_factory)

        async def fake_fetch(start, end, source_url):
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=4) is False
        assert metrics_registry._counters.get("sync_fork_choice_deferred_total") == 1.0

        peer[5] = _mk_block(5, peer[4]["hash"], T0 + timedelta(seconds=190), hash_salt="p5")
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=5) is True
        assert _heights(session_factory) == [(b["height"], b["hash"]) for b in blocks]
        assert metrics_registry._counters.get("sync_fork_choice_remote_wins_total") == 1.0
        assert metrics_registry._counters.get("sync_reorgs_total") == 1.0
        assert 3 not in sync._deferred_forks

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
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=10) is False

    async def test_nonempty_segment_escalates_on_pull(self, session_factory, monkeypatch):
        # 1v1/1v1 tie defers once; on the post-window re-check the peer's
        # round-0 child wins the key — but our losing block carries txs and
        # cannot be safely reverted, so it escalates instead of reorging.
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160), tx_count=2)
        _store(session_factory, ours4)
        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="p4")

        sync = _sync(session_factory)

        async def fake_fetch(start, end, source_url):
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=4) is False
        sync._deferred_forks[3] = time.monotonic() - 1  # expire the defer window
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=4) is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_reorg_unsafe_total") == 1.0

    async def test_peer_segment_bad_signature_no_reorg(self, session_factory, monkeypatch):
        # The peer's winning-looking segment must validate BEFORE our rows are
        # deleted — a bad signature anywhere in it refuses the reorg.
        blocks = _seed(session_factory, 4)
        ours4 = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=160))
        _store(session_factory, ours4)
        peer: dict[int, dict[str, Any]] = {b["height"]: b for b in blocks}
        peer[4] = _mk_block(4, blocks[-1]["hash"], T0 + timedelta(seconds=95), hash_salt="p4")

        sync = _sync(session_factory)
        sync._validate_signatures = True

        def bad_sig(block_data):
            return False, "forged"

        monkeypatch.setattr(sync._validator, "validate_block_signature", bad_sig)

        async def fake_fetch(start, end, source_url):
            return [peer[start]] if start in peer else []

        monkeypatch.setattr(sync, "fetch_blocks_range", fake_fetch)
        assert await sync._resolve_fork_with_peer("https://peer", local_height=4, remote_height=4) is False
        assert _heights(session_factory)[-1] == (4, ours4["hash"])
        assert metrics_registry._counters.get("sync_fork_invalid_rival_total") == 1.0
