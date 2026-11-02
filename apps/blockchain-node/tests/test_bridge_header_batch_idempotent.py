"""#828: mirroring a header another process already stored is not an error.

``_store_header_batch`` checked for an existing (chain_id, height) and then
INSERTed in a second statement. A second process mirroring the same newest header
(another ``--workers`` process, or the island unit) stored it in between, the commit
died on ``uix_bridge_block_chain_height`` and the whole batch rolled back, logging
``Failed to store bridge header batch ... height=None`` every few minutes. These tests
run against a file-backed sqlite database, where two connections really do interleave.
"""

from __future__ import annotations

import logging
import threading

import pytest
from sqlalchemy import event, text
from sqlmodel import Session, create_engine, select

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import BridgeBlockHeader

CHAIN_ID = "chain-a"
PROPOSER = "0x" + "11" * 20


def _header(height: int, hash_: str | None = None) -> dict:
    return {"height": height, "hash": hash_ or f"0x{height:064x}", "proposer": PROPOSER}


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}", connect_args={"timeout": 30})
    chain_metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def bridge(engine):
    return CrossChainBridge(lambda: Session(engine))


def _rows(engine) -> dict[int, BridgeBlockHeader]:
    with Session(engine) as session:
        found = session.exec(select(BridgeBlockHeader).where(BridgeBlockHeader.chain_id == CHAIN_ID)).all()
    return {row.height: row for row in found}


def test_header_stored_by_someone_else_mid_batch_is_skipped_not_fatal(bridge, engine):
    """The other process commits height 10 after our existence check for it, before our INSERT of it.

    The hook fires on this batch's first INSERT, before this connection has written
    anything (and so before it holds sqlite's write lock): that is the window the old
    check-then-insert left open, and the only moment a second connection can commit.
    Height 10 is the header being inserted, so its existence check has already said no.
    """
    fired = []

    @event.listens_for(engine, "before_cursor_execute")
    def _other_process_wins(conn, cursor, statement, parameters, context, executemany):
        if fired or not statement.lstrip().upper().startswith("INSERT INTO BRIDGE_BLOCK_HEADER"):
            return
        fired.append(True)
        other = create_engine(str(engine.url), connect_args={"timeout": 30})
        with other.begin() as raw:
            raw.execute(
                text(
                    "INSERT INTO bridge_block_header (chain_id, height, hash, parent_hash, proposer, state_root,"
                    " bridge_state_root, signature, timestamp, finality_confirmed, confirmation_count)"
                    " VALUES (:c, 10, '0xother', '0x00', :p, '', '', '', '2026-01-01 00:00:00', 0, 0)"
                ),
                {"c": CHAIN_ID, "p": PROPOSER},
            )
        other.dispose()

    stored = bridge._store_header_batch(CHAIN_ID, [_header(h) for h in range(10, 15)])

    assert fired, "the race was never injected"
    rows = _rows(engine)
    assert sorted(rows) == [10, 11, 12, 13, 14]  # the old code rolled the whole batch back
    assert stored == 4  # counted only what this call inserted
    assert rows[10].hash == "0xother"  # the winner's row is left alone


def test_two_writers_on_the_same_batch_both_finish_and_store_each_height_once(bridge, engine):
    headers = [_header(h) for h in range(200)]
    errors: list[BaseException] = []
    stored: list[int] = []
    start = threading.Barrier(2)

    def _writer() -> None:
        mine = CrossChainBridge(lambda: Session(engine))
        try:
            start.wait()
            stored.append(mine._store_header_batch(CHAIN_ID, headers))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_writer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert sorted(_rows(engine)) == list(range(200))
    assert sum(stored) == 200  # every height was inserted by exactly one of them


def test_the_same_batch_twice_stores_nothing_the_second_time(bridge, engine):
    headers = [_header(h) for h in range(5)]
    assert bridge._store_header_batch(CHAIN_ID, headers) == 5
    before = {h: (r.confirmation_count, r.finality_confirmed) for h, r in _rows(engine).items()}

    assert bridge._store_header_batch(CHAIN_ID, headers) == 0

    assert {h: (r.confirmation_count, r.finality_confirmed) for h, r in _rows(engine).items()} == before


def test_insert_once_reports_whether_it_inserted(bridge, engine):
    with Session(engine) as session:
        first = BridgeBlockHeader(chain_id=CHAIN_ID, height=1, hash="0xa", parent_hash="0x0", proposer=PROPOSER, state_root="")
        again = BridgeBlockHeader(chain_id=CHAIN_ID, height=1, hash="0xb", parent_hash="0x0", proposer=PROPOSER, state_root="")
        assert bridge._insert_header_once(session, first) is True
        assert bridge._insert_header_once(session, again) is False
        session.commit()
    rows = _rows(engine)
    assert list(rows) == [1] and rows[1].hash == "0xa"


def test_a_real_store_failure_names_the_batch_not_just_none(bridge, caplog):
    def _boom(chain_id, pending):
        raise RuntimeError("disk gone")

    bridge._store_header_batch = _boom  # type: ignore[method-assign]
    pending = [_header(h) for h in range(10, 15)]
    with caplog.at_level(logging.ERROR):
        assert bridge._flush_header_batch(CHAIN_ID, pending, None) is False
    assert "height=None (batch 10..14, 5 headers)" in caplog.text


def test_insert_once_falls_back_to_a_plain_add_on_other_dialects(bridge, monkeypatch):
    class _Dialect:
        name = "mysql"

    class _Bind:
        dialect = _Dialect()

    class _Session:
        added: list = []

        def get_bind(self):
            return _Bind()

        def add(self, row):
            self.added.append(row)

    session = _Session()
    row = BridgeBlockHeader(chain_id=CHAIN_ID, height=1, hash="0xa", parent_hash="0x0", proposer=PROPOSER, state_root="")
    assert bridge._insert_header_once(session, row) is True
    assert session.added == [row]
