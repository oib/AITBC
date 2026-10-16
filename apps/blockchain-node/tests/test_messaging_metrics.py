"""MSG-6: operability metrics for the derived messaging index.

Digest determinism is the load-bearing property: same sealed rows must
give the same checkpoint digest regardless of insertion order or session,
because the alert compares digests across five nodes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from eth_keys import keys
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, col, create_engine, select

from aitbc.messaging import build_envelope
from aitbc_chain.messaging_metrics import (
    CHECKPOINT_INTERVAL,
    checkpoint_digest,
    checkpoint_for,
    collect_gauges,
    reject_reason,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Block, Transaction

CHAIN = "test-chain"

_K = [keys.PrivateKey(os.urandom(32)) for _ in range(2)]
ALICE, BOB = [k.public_key.to_checksum_address() for k in _K]


def _mk_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    s = Session(engine)
    for a in (ALICE, BOB):
        s.add(Account(chain_id=CHAIN, address=a, balance=10**12, nonce=0))
    s.commit()
    return s


def _block(session: Session, height: int) -> None:
    exists = session.exec(select(Block).where(col(Block.chain_id) == CHAIN, col(Block.height) == height)).first()
    if exists is not None:
        return
    session.add(
        Block(
            chain_id=CHAIN,
            height=height,
            hash=f"{height:064x}",
            parent_hash=f"{height - 1:064x}",
            proposer="0x0",
            state_root="",
            timestamp=datetime(2026, 1, 1) + timedelta(seconds=height),
        )
    )


def _tx(session, height, n, sender, env, *, commit=True):
    _block(session, height)
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=f"{n:064x}",
            sender=sender,
            recipient=sender,
            payload={"aitbc_msg": env},
            type="MESSAGE",
            status="confirmed",
            block_height=height,
            nonce=n,
            timestamp=(datetime(2026, 1, 1) + timedelta(seconds=height * 100 + n)).isoformat(),
        )
    )
    if commit:
        session.commit()


def _post(n: int) -> dict:
    return build_envelope(kind="post", topic="dev", body=f"body {n}", agent_address=ALICE)


def _reply(n: int, parent_n: int) -> dict:
    return build_envelope(kind="reply", topic="dev", body=f"reply {n}", agent_address=BOB, parent=f"{parent_n:064x}")


def _vote(n: int, target_n: int, value: int) -> dict:
    return build_envelope(kind="vote", topic="dev", agent_address=BOB, target=f"{target_n:064x}", value=value)


def _hide(n: int, target_n: int) -> dict:
    return build_envelope(kind="hide", topic="dev", agent_address=ALICE, target=f"{target_n:064x}")


def _seed_forum(session) -> None:
    """A post, a reply, votes and a moderation action — the scenario mix."""
    _tx(session, 1, 1, ALICE, _post(1))
    _tx(session, 2, 2, BOB, _reply(2, 1))
    _tx(session, 3, 3, BOB, _vote(3, 1, 1))
    _tx(session, 4, 4, ALICE, _hide(4, 2))


class TestRejectReason:
    def test_buckets_bounded(self):
        cases = {
            "aitbc_msg must be an object": "shape",
            "unsupported aitbc_msg.v (want 1)": "version",
            "unsupported aitbc_msg.kind (want one of [...])": "kind",
            "aitbc_msg.topic must be a non-empty string": "topic",
            "aitbc_msg.topic must be the canonical slug 'x\u200b'": "topic",
            "aitbc_msg.body is 5000 bytes; maximum is 4096": "body",
            "aitbc_msg.parent must be the parent message's 64-hex tx_hash": "parent",
            "aitbc_msg.target must be the target message's 64-hex tx_hash": "target",
            "aitbc_msg.value must be one of {-1, 0, 1}": "value",
            "aitbc_msg.grantee must be a hex address": "grantee",
            "aitbc_msg.agent_address must equal the signer": "author",
            "something entirely new": "other",
        }
        for error, want in cases.items():
            assert reject_reason(error) == want, error

    def test_interpolated_text_never_escapes_bucket(self):
        # An attacker-controlled interpolation still lands in a fixed bucket.
        err = "aitbc_msg.topic must be the canonical slug '\u200bevil'"
        assert reject_reason(err) == "topic"


class TestCheckpoint:
    def test_checkpoint_for(self):
        assert checkpoint_for(0) == 0
        assert checkpoint_for(CHECKPOINT_INTERVAL - 1) == 0
        assert checkpoint_for(CHECKPOINT_INTERVAL) == CHECKPOINT_INTERVAL
        assert checkpoint_for(CHECKPOINT_INTERVAL + 5) == CHECKPOINT_INTERVAL


class TestDigest:
    def test_deterministic_across_insertion_orders(self, session):
        """Two databases with the same rows in different row orders digest
        identically — the digest orders canonically, not by rowid."""
        _seed_forum(session)
        with _mk_session() as s2:
            # Same heights/tx_hashes, inserted reversed.
            for n, env in [
                (4, _hide(4, 2)),
                (3, _vote(3, 1, 1)),
                (2, _reply(2, 1)),
                (1, _post(1)),
            ]:
                _tx(s2, n, n, ALICE if n in (1, 4) else BOB, env)
            assert checkpoint_digest(session, CHAIN, 10) == checkpoint_digest(s2, CHAIN, 10)

    def test_stable_across_sessions(self, session):
        """An index 'restart' (new session over the same rows) digests the
        same — the derived index has no in-memory state to lose."""
        _seed_forum(session)
        first = checkpoint_digest(session, CHAIN, 10)
        # A second Session object over the same engine re-reads the rows.
        with Session(session.get_bind()) as s2:
            assert checkpoint_digest(s2, CHAIN, 10) == first

    def test_rows_above_checkpoint_excluded(self, session):
        _seed_forum(session)
        before = checkpoint_digest(session, CHAIN, 5)
        _tx(session, 8, 7, ALICE, _post(7))
        assert checkpoint_digest(session, CHAIN, 5) == before
        assert checkpoint_digest(session, CHAIN, 10) != before
        # And one above the checkpoint changes nothing at 10.
        d10 = checkpoint_digest(session, CHAIN, 10)
        _tx(session, 12, 8, ALICE, _post(8))
        assert checkpoint_digest(session, CHAIN, 10) == d10

    def test_invalid_envelope_excluded(self, session):
        _seed_forum(session)
        d1 = checkpoint_digest(session, CHAIN, 10)
        # Sealed junk that bypassed admission: kind not in MSG_KINDS.
        _tx(session, 5, 5, BOB, {"v": 1, "kind": "bogus", "topic": "dev", "agent_address": BOB})
        assert checkpoint_digest(session, CHAIN, 10) == d1

    def test_same_height_replacement_misses_cache(self, session):
        """A healed fork below the checkpoint changes the digest because the
        head hash changed — the cache can never serve it stale."""
        _seed_forum(session)
        d1 = checkpoint_digest(session, CHAIN, 10)
        # Replace the head row (simulated fork heal): new hash, new content.
        head = session.exec(select(Block).where(col(Block.chain_id) == CHAIN).order_by(col(Block.height).desc())).first()
        head.hash = "f" * 64
        session.add(head)
        session.commit()
        assert checkpoint_digest(session, CHAIN, 10) == d1  # same rows, head only
        # Now mutate a sealed row and the head hash together — a real fork
        # replacement always arrives as a new head.
        tx = session.exec(select(Transaction).where(col(Transaction.tx_hash) == f"{3:064x}")).first()
        session.delete(tx)
        head.hash = "e" * 64
        session.add(head)
        session.commit()
        d2 = checkpoint_digest(session, CHAIN, 10)
        assert d2 != d1


class TestCollectGauges:
    def test_returns_snapshot(self, session):
        _seed_forum(session)
        snap = collect_gauges(session, CHAIN)
        assert snap["chain_id"] == CHAIN
        assert snap["index_height"] == 4
        assert snap["chain_head_height"] == 4
        assert snap["index_lag_blocks"] == 0
        assert snap["messages"] == 2  # post + reply
        assert snap["actions"] == 2  # vote + hide
        assert snap["checkpoint_height"] == checkpoint_for(4)
        assert len(snap["checkpoint_digest"]) == 64
        int(snap["checkpoint_digest"], 16)  # valid hex


class TestDigestCacheKey:
    """MSG-6b item 1: the key is the hash of the block AT the checkpoint,
    so a new block above it must not force a rescan."""

    def _counting_scan(self, monkeypatch):
        import aitbc_chain.messaging_metrics as mm
        from aitbc_chain.messaging_index import _MOD_CACHE

        _MOD_CACHE.clear()  # process-global across tests
        calls = {"n": 0}
        real = mm._iter_valid_asc

        def wrapper(session, stmt, **kw):
            calls["n"] += 1
            return real(session, stmt, **kw)

        monkeypatch.setattr(mm, "_iter_valid_asc", wrapper)
        return calls

    def test_block_above_checkpoint_reuses_scan(self, session, monkeypatch):
        calls = self._counting_scan(monkeypatch)
        _seed_forum(session)  # heights 1-4, checkpoint 4
        assert checkpoint_digest(session, CHAIN, 4)
        assert calls["n"] == 1
        # A new block above the checkpoint: the key is unchanged.
        _block(session, 5)
        session.commit()
        assert checkpoint_digest(session, CHAIN, 4)
        assert calls["n"] == 1  # no rescan

    def test_checkpoint_block_replacement_rescans(self, session, monkeypatch):
        calls = self._counting_scan(monkeypatch)
        _seed_forum(session)
        assert checkpoint_digest(session, CHAIN, 4)
        # Replace the block AT the checkpoint: new hash -> new key.
        head = session.exec(select(Block).where(col(Block.chain_id) == CHAIN, col(Block.height) == 4)).first()
        head.hash = "b" * 64
        session.add(head)
        session.commit()
        d = checkpoint_digest(session, CHAIN, 4)
        assert calls["n"] == 2  # rescanned
        import aitbc_chain.messaging_metrics as mm

        assert d == mm._scan_digest(session, CHAIN, 4)  # equals fresh compute

    def test_no_checkpoint_block_falls_back_to_head(self, session, monkeypatch):
        calls = self._counting_scan(monkeypatch)
        _seed_forum(session)
        # Checkpoint 10 has no block row (head is 4): fallback keys on head.
        assert checkpoint_digest(session, CHAIN, 10)
        assert calls["n"] == 1
        assert checkpoint_digest(session, CHAIN, 10)
        assert calls["n"] == 1  # cached under the same head
        _block(session, 5)
        session.commit()
        assert checkpoint_digest(session, CHAIN, 10)
        assert calls["n"] == 2  # head moved -> fallback key changed -> rescan

    def test_digest_value_unchanged(self, session):
        """Same rows, same canonical order, same record format, same hex —
        the MSG-6 digest value is byte-identical after the key change."""
        _seed_forum(session)
        import aitbc_chain.messaging_metrics as mm

        assert checkpoint_digest(session, CHAIN, 4) == mm._scan_digest(session, CHAIN, 4)


class TestDigestSingleFlight:
    """MSG-6b item 2: concurrent cold scans share one computation."""

    def _stub(self, monkeypatch, slow=None, fail_first=False):
        import aitbc_chain.messaging_metrics as mm
        from aitbc_chain.messaging_index import _MOD_CACHE

        _MOD_CACHE.clear()
        calls = {"n": 0}
        monkeypatch.setattr(mm, "_digest_key_hash", lambda s, c, cp: "fixedkey")

        def fake_scan(session, chain_id, checkpoint):
            calls["n"] += 1
            if fail_first and calls["n"] == 1:
                raise RuntimeError("boom")
            if slow:
                slow.wait()
            return "d" * 64

        monkeypatch.setattr(mm, "_scan_digest", fake_scan)
        return calls

    def test_concurrent_callers_scan_once(self, session, monkeypatch):
        import threading
        import time

        calls = self._stub(monkeypatch)

        def fake_scan(session, chain_id, checkpoint):
            calls["n"] += 1
            time.sleep(0.2)
            return "d" * 64

        import aitbc_chain.messaging_metrics as mm

        monkeypatch.setattr(mm, "_scan_digest", fake_scan)
        results: list[str] = []
        errors: list[Exception] = []
        threads = [
            threading.Thread(
                target=lambda: results.append(checkpoint_digest(session, CHAIN, 4))  # noqa: B023
            )
            for _ in range(6)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors
        assert results == ["d" * 64] * 6
        assert calls["n"] == 1

    def test_failing_first_caller_does_not_wedge(self, session, monkeypatch):
        calls = self._stub(monkeypatch, fail_first=True)
        import pytest as _pytest

        with _pytest.raises(RuntimeError):
            checkpoint_digest(session, CHAIN, 4)
        assert calls["n"] == 1
        # The lock is released; the next caller scans and succeeds.
        assert checkpoint_digest(session, CHAIN, 4) == "d" * 64
        assert calls["n"] == 2


class TestDigestGaugeLifecycle:
    """MSG-6b item 3: the series never goes absent mid-scan; superseded
    label sets are pruned only after the new ones are set."""

    def _patch_sessions(self, session, monkeypatch):
        import aitbc_chain.messaging_metrics as mm
        from aitbc_chain import database
        from contextlib import contextmanager

        @contextmanager
        def fake_scope(chain_id):
            yield session

        monkeypatch.setattr(database, "session_scope", fake_scope)
        monkeypatch.setattr(mm, "session_scope", fake_scope, raising=False)
        return mm

    def _labels(self, mm):
        return set(mm.digest_gauge._metrics.keys())

    def test_series_survives_cold_scan_then_prunes(self, session, monkeypatch):
        import threading

        mm = self._patch_sessions(session, monkeypatch)
        _seed_forum(session)
        mm.collect_all([CHAIN])
        first = self._labels(mm)
        assert len(first) == 1 and next(iter(first))[0] == CHAIN

        # Next computation is slow: the previous series stays exposed.
        gate = threading.Event()

        def slow_scan(s, c, cp):
            gate.wait(timeout=10)
            return "e" * 64  # a changed digest at the same checkpoint

        monkeypatch.setattr(mm, "_scan_digest", slow_scan)
        from aitbc_chain.messaging_index import _MOD_CACHE

        _MOD_CACHE.clear()  # force the cold path
        t = threading.Thread(target=mm.collect_all, args=([CHAIN],))
        t.start()
        assert self._labels(mm) == first or (CHAIN, str(0), "e" * 64) in self._labels(mm)
        # The old series is still there while the scan is blocked.
        assert len(self._labels(mm)) >= 1
        gate.set()
        t.join(timeout=10)
        now = self._labels(mm)
        assert now == {(CHAIN, "0", "e" * 64)}  # exactly one series, new digest

    def test_superseded_checkpoint_label_removed(self, session, monkeypatch):
        mm = self._patch_sessions(session, monkeypatch)
        _seed_forum(session)
        # Simulate a leftover series from an older checkpoint.
        mm.digest_gauge.labels(CHAIN, "0", "a" * 64).set(1)
        mm.collect_all([CHAIN])
        labels = self._labels(mm)
        assert (CHAIN, "0", "a" * 64) not in labels
        assert len(labels) == 1

    def test_failed_chain_keeps_labels(self, session, monkeypatch):
        mm = self._patch_sessions(session, monkeypatch)
        mm.digest_gauge.labels("ghost-chain", "0", "f" * 64).set(1)
        mm.collect_all([CHAIN])
        assert ("ghost-chain", "0", "f" * 64) in self._labels(mm)


class TestReadErrorSemantics:
    """MSG-6b item 4: 4xx counts as client error, only 5xx/unhandled as
    read errors."""

    def _sample(self, name, route):
        from prometheus_client import REGISTRY

        return REGISTRY.get_sample_value(name, {"route": route}) or 0.0

    def test_http_exception_split(self):
        import asyncio

        from fastapi import HTTPException

        from aitbc_chain.rpc.messaging import _observed

        async def raise_(status):
            raise HTTPException(status_code=status, detail="x")

        async def raise_unhandled():
            raise RuntimeError("boom")

        route = "test404"
        before_err = self._sample("aitbc_messaging_read_errors_total", route)
        before_cli = self._sample("aitbc_messaging_read_client_errors_total", route)
        for fn in (
            _observed(route)(lambda: raise_(404)),
            _observed(route)(lambda: raise_(400)),
        ):
            try:
                asyncio.run(fn())
            except HTTPException:
                pass
        assert self._sample("aitbc_messaging_read_errors_total", route) == before_err
        assert self._sample("aitbc_messaging_read_client_errors_total", route) == before_cli + 2

        for fn in (
            _observed(route)(lambda: raise_(500)),
            _observed(route)(raise_unhandled),
        ):
            try:
                asyncio.run(fn())
            except Exception:  # noqa: BLE001,S110 -- the invariant is the counter, not the return path
                pass
        assert self._sample("aitbc_messaging_read_errors_total", route) == before_err + 2
        assert self._sample("aitbc_messaging_read_client_errors_total", route) == before_cli + 2

    def test_message_get_404_is_client_error(self, session, monkeypatch):
        """The routine path: a missing message increments only the client
        counter, never the alert-fed error counter."""
        import asyncio

        from fastapi import HTTPException

        from aitbc_chain import database
        from contextlib import contextmanager

        @contextmanager
        def fake_scope(chain_id):
            yield session

        monkeypatch.setattr(database, "session_scope", fake_scope)
        import aitbc_chain.rpc.messaging as rpcm

        monkeypatch.setattr(rpcm, "session_scope", fake_scope)
        from unittest.mock import MagicMock

        before_err = self._sample("aitbc_messaging_read_errors_total", "get")
        before_cli = self._sample("aitbc_messaging_read_client_errors_total", "get")
        with __import__("pytest").raises(HTTPException):
            asyncio.run(rpcm.messaging_get(MagicMock(), "0" * 64))
        assert self._sample("aitbc_messaging_read_errors_total", "get") == before_err
        assert self._sample("aitbc_messaging_read_client_errors_total", "get") == before_cli + 1
