"""Tests for scripts/ops/escrow-repair.py — the SD-1 flag-gated writer.

The safety properties under test: ``snapshot`` never writes to the source
(opened mode=ro + query_only); ``apply`` defaults to a dry run; ``--write``
refuses paths under the live data dir without ``--allow-live-path``; and the
apply step performs exactly the proof's plan — class-1 inserts, class-2
deferred-residue updates, orphan archive into escrow_orphan — and nothing
else.
"""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

pytest.importorskip("eth_utils")
from eth_utils import keccak, to_checksum_address  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "escrow-repair.py"
CHAIN = "ait-test"

BUYER = "0x" + "11" * 20
PROVIDER = "0x" + "22" * 20


def _load():
    spec = importlib.util.spec_from_file_location("escrow_repair", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["escrow_repair"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


@pytest.fixture(scope="module")
def reb():
    return sys.modules["rebuild_escrows"]


def _canon(addr: str) -> str:
    return to_checksum_address(addr)


def _escrow_addr(job_id: str) -> str:
    return to_checksum_address("0x" + keccak(f"aitbc.escrow.{job_id}".encode()).hex()[:40])


def _mk_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE block (
            chain_id TEXT, height INTEGER, hash TEXT, parent_hash TEXT,
            timestamp TEXT, block_metadata TEXT
        );
        CREATE TABLE "transaction" (
            id INTEGER PRIMARY KEY, chain_id TEXT, tx_hash TEXT, block_height INTEGER,
            sender TEXT, recipient TEXT, payload TEXT, created_at TEXT,
            value INTEGER, type TEXT
        );
        CREATE TABLE escrow (
            job_id TEXT PRIMARY KEY, chain_id TEXT, buyer TEXT, provider TEXT,
            amount INTEGER, status TEXT, created_at TEXT, released_at TEXT, refunded_at TEXT,
            lock_tx_hash TEXT, job_tx_hash TEXT, release_tx_hash TEXT, refund_tx_hash TEXT,
            released_amount INTEGER, refunded_amount INTEGER, billed_legs TEXT,
            protected INTEGER, energy_quote_snapshot TEXT, energy_quote_id TEXT,
            energy_quote_digest TEXT, energy_settlement_route TEXT, energy_settlement_asset TEXT,
            energy_settlement_unit_scale INTEGER, energy_net_floor_units INTEGER,
            energy_provider_credit_units INTEGER, energy_fee_basis_points INTEGER
        );
        CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER);
        """
    )
    return conn


def _block(conn, height, ts=None):
    conn.execute(
        "INSERT INTO block VALUES (?,?,?,?,?,?)",
        (
            CHAIN,
            height,
            f"0xblock{height:04d}",
            f"0xblock{height - 1:04d}" if height else "0x" + "0" * 64,
            ts or f"2026-10-01 0{height}:00:00.000000",
            json.dumps({"state_transition_version": 12}),
        ),
    )


def _tx(conn, n, height, type_, job_id, value, sender, recipient, payload_extra=None):
    payload = {"action": f"{type_.lower()}", "job_id": job_id, **(payload_extra or {})}
    conn.execute(
        'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?)',
        (
            n,
            CHAIN,
            f"0xtx{n:04d}",
            height,
            sender,
            recipient,
            json.dumps(payload),
            "2026-10-01 00:00:00.000000",
            value,
            type_,
        ),
    )


def _row(conn, job_id, **kw):
    cols = {
        "chain_id": CHAIN,
        "buyer": _canon(BUYER),
        "provider": _canon(PROVIDER),
        "amount": 1000,
        "status": "locked",
        "created_at": "2026-10-01 00:00:00",
    }
    cols["job_id"] = job_id
    cols.update(kw)
    names = ", ".join(cols)
    conn.execute(f"INSERT INTO escrow ({names}) VALUES ({', '.join('?' * len(cols))})", tuple(cols.values()))


def _build_fixture(path: Path) -> Path:
    """job-KEEP: stored row stopped at the first of two release legs
    (deferred residue). job-MISSING: sealed lock, no row. job-ORPHAN:
    stored row, no sealed lock."""
    conn = _mk_db(path)
    for h in range(6):
        _block(conn, h)
    _tx(conn, 1, 1, "ESCROW_LOCK", "job-KEEP00001", 1000, BUYER, _escrow_addr("job-KEEP00001"), {"provider": PROVIDER})
    _tx(conn, 2, 2, "ESCROW_RELEASE", "job-KEEP00001", 600, PROVIDER, PROVIDER)
    _tx(conn, 3, 3, "ESCROW_RELEASE", "job-KEEP00001", 400, PROVIDER, PROVIDER)
    _tx(conn, 4, 4, "ESCROW_LOCK", "job-MISSING1", 700, BUYER, _escrow_addr("job-MISSING1"), {"provider": PROVIDER})
    _row(
        conn,
        "job-KEEP00001",
        status="released",
        released_amount=600,  # stale: second leg (400) never reached the row
        release_tx_hash="0xtx0002",
        lock_tx_hash="0xtx0001",
        job_tx_hash="0xlocalabc",
        billed_legs="[600]",
    )
    _row(conn, "job-ORPHAN001", status="locked", job_tx_hash="0xlocaldef")
    conn.commit()
    conn.close()
    return path


def _escrow_row(conn, job_id):
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM escrow WHERE job_id = ?", (job_id,)).fetchone()


class TestSnapshot:
    def test_snapshot_copies_and_checksums(self, tool, tmp_path):
        src = _build_fixture(tmp_path / "src" / "chain.db")
        info = tool.snapshot_db(Path(src), tmp_path / "copy")
        dst = tmp_path / "copy" / "chain.db"
        assert dst.is_file()
        assert oct((tmp_path / "copy").stat().st_mode & 0o777) == "0o700"
        assert info["src_sha256"] != info["dst_sha256"]  # different bytes, both recorded
        conn = sqlite3.connect(dst)
        assert conn.execute("SELECT COUNT(*) FROM escrow").fetchone()[0] == 2
        conn.close()

    def test_snapshot_source_stays_readonly(self, tool, tmp_path):
        src = _build_fixture(tmp_path / "src2" / "chain.db")
        tool.snapshot_db(Path(src), tmp_path / "copy2")
        conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
        assert conn.execute("SELECT COUNT(*) FROM escrow").fetchone()[0] == 2
        conn.close()


class TestApplyGate:
    def test_apply_without_write_is_dry_run(self, tool, tmp_path, capsys):
        db = _build_fixture(tmp_path / "chain.db")
        rc = tool.main(["apply", "--db", str(db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "DRY RUN" in out
        conn = sqlite3.connect(db)
        assert conn.execute("SELECT released_amount FROM escrow WHERE job_id='job-KEEP00001'").fetchone()[0] == 600
        conn.close()

    def test_write_refuses_live_path(self, tool, tmp_path, monkeypatch, capsys):
        live = tmp_path / "var" / "lib" / "aitbc"
        db = _build_fixture(live / "chain.db")
        monkeypatch.setattr(tool, "LIVE_DATA_DIR", live.resolve())
        rc = tool.main(["apply", "--db", str(db), "--write"])
        assert rc == 2
        assert "refusing" in capsys.readouterr().err
        conn = sqlite3.connect(db)
        assert conn.execute("SELECT released_amount FROM escrow WHERE job_id='job-KEEP00001'").fetchone()[0] == 600
        conn.close()

    def test_write_under_live_path_needs_allow_flag(self, tool, tmp_path, monkeypatch):
        live = tmp_path / "var" / "lib" / "aitbc"
        db = _build_fixture(live / "chain.db")
        monkeypatch.setattr(tool, "LIVE_DATA_DIR", live.resolve())
        rc = tool.main(["apply", "--db", str(db), "--write", "--allow-live-path"])
        assert rc == 0  # gate exists; the flag opens it deliberately


class TestApplyWrites:
    def test_apply_performs_all_three_classes(self, tool, tmp_path, capsys):
        db = _build_fixture(tmp_path / "chain.db")
        rc = tool.main(["apply", "--db", str(db), "--write"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "insert: 1" in out and "update: 1" in out and "archive: 1" in out

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row

        # class 2: deferred residue caught up to both sealed legs
        keep = _escrow_row(conn, "job-KEEP00001")
        assert keep["released_amount"] == 1000
        assert keep["release_tx_hash"] == "0xtx0003"
        assert keep["job_tx_hash"] == "0xlocalabc"  # non-derivable fields untouched
        assert keep["billed_legs"] == "[600]"

        # class 1: missing row inserted from the sealed lock
        miss = _escrow_row(conn, "job-MISSING1")
        assert miss is not None
        assert miss["amount"] == 700
        assert miss["status"] == "locked"
        assert miss["lock_tx_hash"] == "0xtx0004"
        assert miss["protected"] == 0
        assert miss["job_tx_hash"] is None

        # class 3: orphan moved, not deleted
        assert _escrow_row(conn, "job-ORPHAN001") is None
        orphan = conn.execute("SELECT * FROM escrow_orphan WHERE job_id='job-ORPHAN001'").fetchone()
        assert orphan is not None
        assert orphan["job_tx_hash"] == "0xlocaldef"  # RPC-era field preserved
        assert orphan["archived_reason"] == "no sealed lock leg"
        conn.close()

    def test_apply_proof_rerun_is_clean(self, tool, tmp_path, capsys):
        db = _build_fixture(tmp_path / "chain.db")
        tool.main(["apply", "--db", str(db), "--write"])
        out = capsys.readouterr().out
        assert '"insert": 0' not in out  # human text, not json
        assert "after:" in out
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        reb = sys.modules["rebuild_escrows"]
        report, _ = reb.reconcile(conn)
        plan = reb._build_write_plan(report)
        conn.close()
        assert plan["insert"] == [] and plan["update"] == [] and plan["manual_review"] == []
        assert plan["report_only"] == []

    def test_apply_blocked_by_abort(self, tool, reb, tmp_path):
        """A fresh (unreviewed) double-settlement aborts apply even on a copy."""
        path = tmp_path / "chain.db"
        conn = _mk_db(path)
        _block(conn, 0)
        _block(conn, 1)
        _block(conn, 2)
        _tx(conn, 1, 1, "ESCROW_LOCK", "job-DOUBLE99", 360000, BUYER, _escrow_addr("job-DOUBLE99"), {"provider": PROVIDER})
        _tx(conn, 2, 2, "ESCROW_RELEASE", "job-DOUBLE99", 351000, PROVIDER, PROVIDER)
        _tx(conn, 3, 2, "ESCROW_RELEASE", "job-DOUBLE99", 351000, PROVIDER, PROVIDER)
        conn.commit()
        conn.close()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        report, _ = reb.reconcile(conn)
        plan = reb._build_write_plan(report)
        assert plan["abort"], "expected an R2 abort on the fixture"
        with pytest.raises(SystemExit):
            tool.apply_plan(conn, report, plan)
        conn.close()
