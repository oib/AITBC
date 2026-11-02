"""Phase-0 test for MEMPOOL-COLUMN-TYPES-1 (#797).

``DatabaseMempool._init_table`` creates the mempool table with
``fee INTEGER`` and ``received_at REAL``. On Postgres, INTEGER tops out at
2,147,483,647 base units (~59.65 AIT at 36,000,000/AIT) — a funded sender
bidding a larger fee gets a raw DataError out of mempool.add. float4
received_at has ~128 s resolution at the current epoch, so the
eviction tie-break and evict_expired work at 2-minute granularity.

Desired behaviour (pinned here): fee is BIGINT, received_at is DOUBLE
PRECISION, a fee above 2^31 base units stores cleanly, and received_at
round-trips to the millisecond. These tests FAIL on current main against a
real Postgres — that is the bug demonstration. sqlite has no such width
limit, so the tests are postgres-marked and auto-skip without a server
(DATABASE_URL / MEMPOOL_DB_URL, else postgresql://localhost:5432/aitbc).
"""

import os
import time

import pytest
from aitbc_chain.mempool import DatabaseMempool
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.requires_postgres

CHAIN = "bc-2.test"


def _db_url() -> str:
    return os.environ.get("MEMPOOL_DB_URL") or os.environ.get("DATABASE_URL") or "postgresql://localhost:5432/aitbc"


@pytest.fixture
def pool():
    url = _db_url()
    p = DatabaseMempool(url, max_size=100, min_fee=0)
    yield p
    # scratch db only — drop the table the pool created so reruns stay clean
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS mempool"))


def _column_type(table: str, column: str) -> str:
    engine = create_engine(_db_url())
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT data_type FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
            {"t": table, "c": column},
        ).first()
    return row[0] if row else ""


class TestMempoolColumnWidths:
    def test_fee_column_is_bigint(self, pool):
        assert _column_type("mempool", "fee") == "bigint"

    def test_received_at_column_is_double_precision(self, pool):
        assert _column_type("mempool", "received_at") == "double precision"

    def test_fee_above_int32_stores(self, pool):
        """60 AIT in base units exceeds int4; the add must not raise."""
        big_fee = 2_160_000_000  # 60 AIT
        tx = {"from": "0xsender", "to": "0xrcpt", "amount": 1, "fee": big_fee, "nonce": 0, "signature": "0xsig"}
        pool.add(tx, chain_id=CHAIN)

    def test_received_at_millisecond_resolution(self, pool):
        before = time.time()
        tx = {"from": "0xsender", "to": "0xrcpt", "amount": 1, "fee": 1, "nonce": 1, "signature": "0xsig"}
        h = pool.add(tx, chain_id=CHAIN)
        after = time.time()
        engine = create_engine(_db_url())
        with engine.connect() as conn:
            stored = conn.execute(text("SELECT received_at FROM mempool WHERE tx_hash = :h"), {"h": h}).scalar()
        # float4 at the current epoch resolves to ~128 s; double precision
        # keeps the stored value within the real add window.
        assert before - 1.0 <= stored <= after + 1.0
