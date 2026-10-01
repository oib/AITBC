"""Confirmation counts stop at ``bridge_confirmation_count_cap``; nothing a decision reads moves.

Every new header used to bump every earlier header's ``confirmation_count``, a rewrite of the whole
``bridge_block_header`` table once per block: 22,267 rows, 12.5 MiB, ~3,200 WAL frames per block on every
node (2026-10-01), 99.8% of the frames a block writes and growing with chain height. A count above the deepest
requirement is never read, so counting now stops at a cap that is never below ``bridge_finality_blocks`` or
``bridge_min_confirmations``. ``test_bridge_confirmation_bump_equivalence.py`` still pins the values below
the cap against the row loop; this file pins what is new.
"""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc_chain.config import settings
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.cross_chain.bridge_finality import BridgeFinalityMixin
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import BridgeBlockHeader

CHAIN_ID = "chain-a"
CAP = 10


def _header(height: int, **overrides: Any) -> dict[str, Any]:
    return {
        "chain_id": CHAIN_ID,
        "height": height,
        "hash": f"0x{height:064x}",
        "parent_hash": f"0x{max(0, height - 1):064x}",
        "proposer": "0x" + "11" * 20,
        "state_root": f"0xstate{height}",
        "bridge_state_root": f"0xbridge{height}",
        "signature": "",
        **overrides,
    }


def _increment_confirmations_by_loop(self: Any, chain_id: str, new_height: int, session: Any) -> None:
    """The original per-row implementation, as the reference for what the capped bump must still write."""
    earlier = session.exec(
        select(BridgeBlockHeader).where(BridgeBlockHeader.chain_id == chain_id, BridgeBlockHeader.height < new_height)
    ).all()
    for h in earlier:
        h.confirmation_count += 1
        session.add(h)
        self._update_finality(chain_id, h, session, commit=False)
    if earlier:
        session.commit()


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    chain_metadata.drop_all(engine)
    engine.dispose()


def _configure(monkeypatch, *, release_enabled: bool) -> None:
    monkeypatch.setattr(settings, "bridge_confirmation_count_cap", CAP)
    monkeypatch.setattr(settings, "bridge_release_enabled", release_enabled)


@pytest.fixture(params=[True, False], ids=["release-fence-up", "release-fence-down"])
def capped(request, monkeypatch):
    """Cap of 10, with the release fence up (the fleet: counts start at 0) and down (dev networks)."""
    _configure(monkeypatch, release_enabled=request.param)


@pytest.fixture
def capped_fence_down(monkeypatch):
    """The cases that hand the bridge their own counts exist only while the release fence is down."""
    _configure(monkeypatch, release_enabled=False)


def _table(engine) -> dict[int, tuple[int, bool]]:
    with Session(engine) as session:
        rows = session.exec(
            select(BridgeBlockHeader).where(BridgeBlockHeader.chain_id == CHAIN_ID).order_by(BridgeBlockHeader.height)  # type: ignore[arg-type]
        ).all()
        return {r.height: (r.confirmation_count, r.finality_confirmed) for r in rows}


def test_default_cap_is_deep_enough_for_any_realistic_depth() -> None:
    """The reported depth stays accurate far beyond the 6 the node itself requires."""
    assert settings.bridge_confirmation_count_cap >= 100
    assert settings.bridge_confirmation_count_cap >= max(settings.bridge_finality_blocks, settings.bridge_min_confirmations)


def test_counts_stop_at_the_cap(engine, capped) -> None:
    bridge = CrossChainBridge(lambda: Session(engine))
    for height in range(40):
        bridge.store_block_header(_header(height))
    table = _table(engine)
    assert {h: count for h, (count, _final) in table.items()} == {h: min(39 - h, CAP) for h in range(40)}
    assert {h for h, (_count, final) in table.items() if final} == set(range(34)), "final = at least 6 deep"


def test_capped_bump_matches_the_row_loop_up_to_the_cap(engine, capped) -> None:
    payloads = [_header(h) for h in range(40)]
    live_bridge = CrossChainBridge(lambda: Session(engine))
    for payload in payloads:
        live_bridge.store_block_header(dict(payload))
    live = _table(engine)

    reference_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(reference_engine)
    try:
        with patch.object(BridgeFinalityMixin, "_increment_confirmations", _increment_confirmations_by_loop):
            reference_bridge = CrossChainBridge(lambda: Session(reference_engine))
            for payload in payloads:
                reference_bridge.store_block_header(dict(payload))
        reference = _table(reference_engine)
    finally:
        chain_metadata.drop_all(reference_engine)
        reference_engine.dispose()

    assert live == {h: (min(count, CAP), final) for h, (count, final) in reference.items()}


def test_per_block_writes_are_bounded_by_the_cap(engine, capped) -> None:
    """The point of the change: rows rewritten per block no longer grow with the table."""
    bridge = CrossChainBridge(lambda: Session(engine))
    bumped_rows: list[int] = []

    @event.listens_for(engine, "after_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]
        if statement.startswith("UPDATE bridge_block_header SET confirmation_count"):
            bumped_rows.append(cursor.rowcount)

    for height in range(60):
        bridge.store_block_header(_header(height))
    assert bumped_rows[-1] == CAP, "the 60th header must not rewrite the 59 rows below it"
    assert max(bumped_rows) <= CAP


def test_rows_already_past_the_cap_keep_their_count(engine, capped_fence_down) -> None:
    bridge = CrossChainBridge(lambda: Session(engine))
    bridge.store_block_header(_header(0, confirmation_count=500))
    for height in range(1, 6):
        bridge.store_block_header(_header(height))
    assert _table(engine)[0][0] == 500


def test_finality_flag_is_set_even_when_nothing_is_bumped(engine, capped_fence_down) -> None:
    """A row past the cap but still unflagged (caller-supplied counts, release fence down) must still be flagged."""
    bridge = CrossChainBridge(lambda: Session(engine))
    bridge.store_block_header(_header(0, confirmation_count=50, finality_confirmed=False))
    bridge.store_block_header(_header(1))
    assert _table(engine)[0] == (50, True)


def test_finality_decisions_are_unchanged_for_old_headers(engine, capped) -> None:
    bridge = CrossChainBridge(lambda: Session(engine))
    for height in range(40):
        bridge.store_block_header(_header(height))
    oldest = bridge._get_block_header(CHAIN_ID, 0)
    assert oldest is not None and oldest.confirmation_count == CAP
    assert bridge._check_finality_for_transfer(oldest, 1)  # small: needs bridge_min_confirmations
    assert bridge._check_finality_for_transfer(oldest, 10**9)  # large: needs bridge_finality_blocks


def test_the_cap_never_sits_below_the_deepest_requirement(engine, monkeypatch) -> None:
    """A cap configured below bridge_min_confirmations must not strand small transfers."""
    monkeypatch.setattr(settings, "bridge_confirmation_count_cap", 3)
    monkeypatch.setattr(settings, "bridge_min_confirmations", 8)
    bridge = CrossChainBridge(lambda: Session(engine))
    for height in range(20):
        bridge.store_block_header(_header(height))
    oldest = bridge._get_block_header(CHAIN_ID, 0)
    assert oldest is not None and oldest.confirmation_count == 8
    assert bridge._check_finality_for_transfer(oldest, 1)


def test_the_sqlite_update_reports_rows_changed() -> None:
    """Guards the write-bound test: it reads cursor.rowcount, which sqlite3 must fill in for an UPDATE."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t(a INTEGER)")
    con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(5)])
    assert con.execute("UPDATE t SET a = a + 1 WHERE a < 3").rowcount == 3
