"""Tests for scripts/ops/rebuild-escrows.py (SD-1 read-only reconciliation proof).

Each test builds a small chain.db fixture in a temp dir — block, transaction,
escrow and account tables with the columns the tool selects — and runs the
script's ``main()`` against it. The safety-critical test is
``TestReadOnly``: the tool must be incapable of opening the database writable.
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
SCRIPT = REPO_ROOT / "scripts" / "ops" / "rebuild-escrows.py"
CHAIN = "ait-test"

BUYER = "0x" + "11" * 20
PROVIDER = "0x" + "22" * 20
BUYER2 = "0x" + "33" * 20
PROVIDER2 = "0x" + "44" * 20


def _load():
    spec = importlib.util.spec_from_file_location("rebuild_escrows", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rebuild_escrows"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


def _escrow_addr(job_id: str) -> str:
    return to_checksum_address("0x" + keccak(f"aitbc.escrow.{job_id}".encode()).hex()[:40])


def _mk_db(path: Path) -> sqlite3.Connection:
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


def _block(conn, height, meta_version=12, ts=None):
    conn.execute(
        "INSERT INTO block VALUES (?,?,?,?,?,?)",
        (
            CHAIN,
            height,
            f"0xblock{height:04d}",
            f"0xblock{height - 1:04d}" if height else "0x" + "0" * 64,
            ts or f"2026-10-0{1 + height // 10} 0{height % 10}:00:00.000000",
            json.dumps({"state_transition_version": meta_version}),
        ),
    )


def _tx(conn, n, height, type_, job_id, value, sender, recipient, payload_extra=None):
    payload = {"action": EXPECTED_ACTIONS[type_], "job_id": job_id, **(payload_extra or {})}
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


EXPECTED_ACTIONS = {
    "ESCROW_LOCK": "escrow_lock",
    "ESCROW_RELEASE": "escrow_release",
    "ESCROW_REFUND": "escrow_refund",
    "ESCROW_FEE_SWEEP": "escrow_fee_sweep",
}

ESCROW_COLS = (
    "job_id, chain_id, buyer, provider, amount, status, created_at, released_at, refunded_at,"
    " lock_tx_hash, job_tx_hash, release_tx_hash, refund_tx_hash, released_amount, refunded_amount,"
    " billed_legs, protected, energy_quote_snapshot, energy_quote_id, energy_quote_digest,"
    " energy_settlement_route, energy_settlement_asset, energy_settlement_unit_scale,"
    " energy_net_floor_units, energy_provider_credit_units, energy_fee_basis_points"
)


def _row(conn, job_id, **over):
    base = {
        "job_id": job_id,
        "chain_id": CHAIN,
        "buyer": None,
        "provider": None,
        "amount": 0,
        "status": "locked",
        "created_at": None,
        "released_at": None,
        "refunded_at": None,
        "lock_tx_hash": None,
        "job_tx_hash": None,
        "release_tx_hash": None,
        "refund_tx_hash": None,
        "released_amount": None,
        "refunded_amount": None,
        "billed_legs": None,
        "protected": 0,
        "energy_quote_snapshot": None,
        "energy_quote_id": None,
        "energy_quote_digest": None,
        "energy_settlement_route": None,
        "energy_settlement_asset": None,
        "energy_settlement_unit_scale": None,
        "energy_net_floor_units": None,
        "energy_provider_credit_units": None,
        "energy_fee_basis_points": None,
    }
    base.update(over)
    cols = [c.strip() for c in ESCROW_COLS.split(",")]
    conn.execute(
        f"INSERT INTO escrow ({ESCROW_COLS}) VALUES ({','.join('?' for _ in cols)})",
        [base[c] for c in cols],
    )


def _account(conn, address, balance=0):
    conn.execute("INSERT INTO account VALUES (?,?,?)", (CHAIN, address, balance))


def _canon(addr):
    return to_checksum_address(addr.lower())


def _build_fixture(path: Path) -> Path:
    """Five jobs: released+change, refund-only, missing row, field mismatch,
    orphan row — plus a mempool leg that must be ignored."""
    conn = _mk_db(path)
    for h in range(10):
        _block(conn, h)
    # jobA: released with buyer-change leg (metered settlement, either order).
    _tx(conn, 1, 1, "ESCROW_LOCK", "job-AAAA0001", 1000, BUYER, _escrow_addr("job-AAAA0001"), {"provider": PROVIDER})
    _tx(conn, 2, 4, "ESCROW_REFUND", "job-AAAA0001", 400, PROVIDER2, BUYER)  # change mined first
    _tx(conn, 3, 5, "ESCROW_RELEASE", "job-AAAA0001", 600, PROVIDER2, PROVIDER)
    # jobB: refund-only.
    _tx(conn, 4, 2, "ESCROW_LOCK", "job-BBBB0002", 500, BUYER2, _escrow_addr("job-BBBB0002"), {"provider": PROVIDER2})
    _tx(conn, 5, 6, "ESCROW_REFUND", "job-BBBB0002", 500, PROVIDER2, BUYER2)
    # jobC: locked, no escrow row written (the crash-between-submit-and-row case).
    _tx(conn, 6, 3, "ESCROW_LOCK", "job-CCCC0003", 700, BUYER, _escrow_addr("job-CCCC0003"), {"provider": PROVIDER})
    # jobD: locked, row exists but amount disagrees with the chain.
    _tx(conn, 7, 7, "ESCROW_LOCK", "job-DDDD0004", 800, BUYER, _escrow_addr("job-DDDD0004"), {"provider": PROVIDER})
    # jobE: orphan escrow row — no sealed lock anywhere.
    # jobF: mempool-only lock — must not be counted (block_height NULL).
    conn.execute(
        'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?)',
        (
            8,
            CHAIN,
            "0xtx0008",
            None,
            BUYER,
            PROVIDER,
            json.dumps({"action": "escrow_lock", "job_id": "job-FFFF0006", "provider": PROVIDER}),
            "2026-10-01 00:00:00.000000",
            999,
            "ESCROW_LOCK",
        ),
    )

    # Stored rows: A and B fully correct, D with wrong amount, E an orphan.
    _row(
        conn,
        "job-AAAA0001",
        buyer=_canon(BUYER),
        provider=_canon(PROVIDER),
        amount=1000,
        status="released",
        released_amount=600,
        refunded_amount=400,
        lock_tx_hash="0xtx0001",
        release_tx_hash="0xtx0003",
        refund_tx_hash="0xtx0002",
    )
    _row(
        conn,
        "job-BBBB0002",
        buyer=_canon(BUYER2),
        provider=_canon(PROVIDER2),
        amount=500,
        status="refunded",
        released_amount=0,
        refunded_amount=500,
        lock_tx_hash="0xtx0004",
        refund_tx_hash="0xtx0005",
    )
    _row(conn, "job-DDDD0004", buyer=_canon(BUYER), provider=_canon(PROVIDER), amount=801, lock_tx_hash="0xtx0007")
    _row(conn, "job-EEEE0005", buyer=_canon(BUYER), provider=_canon(PROVIDER), amount=42)

    # Accounts: parties for G4, custody balances for G3 (v12 lock stamps).
    for addr in (BUYER, PROVIDER, BUYER2, PROVIDER2):
        _account(conn, _canon(addr))
    _account(conn, _escrow_addr("job-AAAA0001"), 0)
    _account(conn, _escrow_addr("job-BBBB0002"), 0)
    _account(conn, _escrow_addr("job-CCCC0003"), 700)
    _account(conn, _escrow_addr("job-DDDD0004"), 800)
    conn.commit()
    conn.close()
    return path


class TestReadOnly:
    """The safety property: no code path can write to the database."""

    def test_connect_ro_refuses_writes(self, tool, tmp_path):
        db = _mk_db(tmp_path / "chain.db")
        db.commit()
        db.close()
        conn = tool._connect_ro(str(tmp_path / "chain.db"))
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("CREATE TABLE rogue (x INTEGER)")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("INSERT INTO escrow (job_id) VALUES ('x')")
        conn.close()

    def test_connect_ro_honors_wal(self, tool, tmp_path):
        """Plain mode=ro (not immutable=1) must see rows living only in the
        WAL — a live node's newest commits sit there uncheckpointed."""
        writer = _mk_db(tmp_path / "chain.db")
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO escrow (job_id, chain_id) VALUES ('job-wal', ?)", (CHAIN,))
        writer.commit()
        try:
            assert (tmp_path / "chain.db-wal").exists(), "fixture must hold uncheckpointed WAL pages"
            conn = tool._connect_ro(str(tmp_path / "chain.db"))
            assert conn.execute("SELECT COUNT(*) FROM escrow").fetchone()[0] == 1
            conn.close()
        finally:
            writer.close()

    def test_script_has_no_write_flags(self, tool):
        # argparse exposes exactly the three documented options.
        with pytest.raises(SystemExit) as exc:
            tool.main(["--help"])
        assert exc.value.code == 0

    def test_write_flags_are_rejected(self, tool, tmp_path):
        db = _mk_db(tmp_path / "chain.db")
        db.commit()
        db.close()
        # argparse must not accept any mutation request — exit 2 = usage error.
        for flag in ("--write", "--apply", "--fix", "--repair"):
            with pytest.raises(SystemExit) as exc:
                tool.main(["--db", str(tmp_path / "chain.db"), flag])
            assert exc.value.code == 2
        src = SCRIPT.read_text()
        for banned in ("mode=rw", "mode=rwc"):
            assert banned not in src

    def test_help_states_read_only(self, tool, capsys):
        with pytest.raises(SystemExit):
            tool.main(["--help"])
        assert "READ-ONLY" in capsys.readouterr().out.upper()


class TestReconcile:
    def test_fixture_reports_all_divergence_classes(self, tool, tmp_path, capsys):
        db = _build_fixture(tmp_path / "chain.db")
        code = tool.main(["--db", str(db)])
        out = capsys.readouterr().out
        assert code == 1  # divergent state — proof red
        assert "sealed_locks=4" in out  # mempool-only job-F lock excluded
        assert "jobs=4" in out
        assert "rows=4" in out
        assert "missing=1" in out and "job-CCCC0003" in out
        assert "orphans=1" in out and "job-EEEE0005" in out
        assert "field=amount" in out and "job-DDDD0004" in out
        assert "R5: FAIL" in out
        assert "G2: FAIL" in out

    def test_clean_db_exits_zero(self, tool, tmp_path, capsys):
        path = tmp_path / "chain.db"
        conn = _mk_db(path)
        for h in range(6):
            _block(conn, h)
        _tx(conn, 1, 1, "ESCROW_LOCK", "job-11110001", 1000, BUYER, _escrow_addr("job-11110001"), {"provider": PROVIDER})
        _tx(conn, 2, 3, "ESCROW_RELEASE", "job-11110001", 600, PROVIDER2, PROVIDER)
        _tx(conn, 3, 4, "ESCROW_REFUND", "job-11110001", 400, PROVIDER2, BUYER)
        _row(
            conn,
            "job-11110001",
            buyer=_canon(BUYER),
            provider=_canon(PROVIDER),
            amount=1000,
            status="released",
            released_amount=600,
            refunded_amount=400,
            lock_tx_hash="0xtx0001",
            release_tx_hash="0xtx0002",
            refund_tx_hash="0xtx0003",
        )
        for addr in (BUYER, PROVIDER, PROVIDER2):
            _account(conn, _canon(addr))
        _account(conn, _escrow_addr("job-11110001"), 0)
        conn.commit()
        conn.close()
        assert tool.main(["--db", str(path)]) == 0
        out = capsys.readouterr().out
        assert "proof: CLEAN" in out
        for check in ("R1", "R2", "R3", "R4", "R5", "G1", "G2", "G3", "G4"):
            assert f"  {check}: PASS" in out

    def test_r1_orphan_settlement_leg(self, tool, tmp_path, capsys):
        path = tmp_path / "chain.db"
        conn = _mk_db(path)
        _block(conn, 1)
        _block(conn, 2)
        _tx(conn, 1, 1, "ESCROW_LOCK", "job-00000001", 100, BUYER, _escrow_addr("job-00000001"), {"provider": PROVIDER})
        _tx(conn, 2, 2, "ESCROW_RELEASE", "job-NOLOCK99", 50, PROVIDER2, PROVIDER)
        _row(conn, "job-00000001", buyer=_canon(BUYER), provider=_canon(PROVIDER), amount=100, lock_tx_hash="0xtx0001")
        for addr in (BUYER, PROVIDER):
            _account(conn, _canon(addr))
        _account(conn, _escrow_addr("job-00000001"), 100)
        conn.commit()
        conn.close()
        assert tool.main(["--db", str(path)]) == 1
        out = capsys.readouterr().out
        assert "R1: FAIL" in out

    def test_legacy_escrow_schema_without_new_columns(self, tool, tmp_path, capsys):
        """A chain.db whose escrow table predates billed_legs/energy_* must not crash."""
        path = tmp_path / "chain.db"
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT, parent_hash TEXT,
                                timestamp TEXT, block_metadata TEXT);
            CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, chain_id TEXT, tx_hash TEXT,
                                        block_height INTEGER, sender TEXT, recipient TEXT,
                                        payload TEXT, created_at TEXT, value INTEGER, type TEXT);
            CREATE TABLE escrow (job_id TEXT PRIMARY KEY, chain_id TEXT, buyer TEXT,
                                 provider TEXT, amount INTEGER, status TEXT, created_at TEXT,
                                 lock_tx_hash TEXT);
            CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER);
            """
        )
        conn.execute(
            "INSERT INTO block VALUES (?,?,?,?,?,?)",
            (CHAIN, 1, "0xblock0001", "0x0", "2026-10-01 00:00:00.000000", "{}"),
        )
        conn.execute(
            'INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?)',
            (
                1,
                CHAIN,
                "0xtx0001",
                1,
                BUYER,
                PROVIDER,
                json.dumps({"action": "escrow_lock", "job_id": "job-OLD00001", "provider": PROVIDER}),
                "2026-10-01 00:00:00.000000",
                100,
                "ESCROW_LOCK",
            ),
        )
        conn.execute(
            "INSERT INTO escrow (job_id, chain_id, buyer, provider, amount, status, lock_tx_hash) VALUES (?,?,?,?,?,?,?)",
            ("job-OLD00001", CHAIN, _canon(BUYER), _canon(PROVIDER), 100, "locked", "0xtx0001"),
        )
        for addr in (BUYER, PROVIDER):
            conn.execute("INSERT INTO account VALUES (?,?,?)", (CHAIN, _canon(addr), 0))
        conn.commit()
        conn.close()
        assert tool.main(["--db", str(path)]) == 0
        assert "proof: CLEAN" in capsys.readouterr().out

    def test_job_id_filter_scopes_the_proof(self, tool, tmp_path, capsys):
        db = _build_fixture(tmp_path / "chain.db")
        code = tool.main(["--db", str(db), "--job-id", "job-AAAA0001"])
        out = capsys.readouterr().out
        assert code == 0
        assert "jobs=1" in out and "proof: CLEAN" in out


class TestWritePlan:
    """--plan: the write-phase dry run (SD-1). Lists classes only — the tool
    still has no write path; the plan is what an operator-approved write
    phase would do."""

    def test_plan_lists_per_class_actions(self, tool, tmp_path, capsys):
        db = _build_fixture(tmp_path / "chain.db")
        code = tool.main(["--db", str(db), "--plan"])
        out = capsys.readouterr().out
        assert code == 1  # divergent state — proof red
        assert "write-phase dry run" in out
        # job-C has no escrow row → step-1 INSERT with derived values.
        assert "INSERT" in out and "CCCC" in out
        # job-D's conflict is field=amount — not the deferred-residue class,
        # so it lands in manual review, never in the update list.
        assert "manual review" in out and "DDDD" in out
        # job-E's orphan row is report-only, never repaired.
        assert "report-only" in out
        assert "unchanged rows" in out

    def test_plan_deferred_residue_is_the_only_update_class(self, tool, tmp_path):
        """Stored billed-net while the deferred-residue leg also sealed:
        released_amount stored < derived on release-shaped fields only —
        the single conflict shape the write phase may UPDATE."""
        conn = _mk_db(tmp_path / "chain.db")
        for h in range(6):
            _block(conn, h)
        _tx(
            conn,
            1,
            1,
            "ESCROW_LOCK",
            "job-RESIDUE1",
            1000,
            BUYER,
            _escrow_addr("job-RESIDUE1"),
            {"provider": PROVIDER},
        )
        _tx(conn, 2, 2, "ESCROW_RELEASE", "job-RESIDUE1", 975, PROVIDER2, PROVIDER)
        _tx(conn, 3, 3, "ESCROW_RELEASE", "job-RESIDUE1", 25, PROVIDER2, PROVIDER)
        _row(
            conn,
            "job-RESIDUE1",
            buyer=_canon(BUYER),
            provider=_canon(PROVIDER),
            amount=1000,
            status="released",
            released_amount=975,
            lock_tx_hash="0xtx0001",
            release_tx_hash="0xtx0002",
        )
        for addr in (BUYER, PROVIDER, PROVIDER2):
            _account(conn, _canon(addr))
        _account(conn, _escrow_addr("job-RESIDUE1"), 0)
        conn.commit()
        conn.close()
        db = tmp_path / "chain.db"
        code = tool.main(["--db", str(db), "--plan", "--report", str(tmp_path / "r.json")])
        plan = json.loads((tmp_path / "r.json").read_text())["write_plan"]
        assert code == 1  # the conflict is still an R5 failure
        assert plan["manual_review"] == []
        assert len(plan["update"]) == 1
        item = plan["update"][0]
        assert item["class"] == "deferred-residue" and item["job_id"] == "job-RESIDUE1"
        upd = {s["field"]: s for s in item["set"]}
        assert upd["released_amount"]["stored"] == 975
        assert upd["released_amount"]["derived"] == 1000

    def test_plan_aborts_on_r2_double_settlement(self, tool, tmp_path, capsys):
        """R2 is stop-and-escalate: the plan prints ABORT and no steps."""
        conn = _mk_db(tmp_path / "chain.db")
        for h in range(4):
            _block(conn, h)
        _tx(
            conn,
            1,
            1,
            "ESCROW_LOCK",
            "job-DOUBLE01",
            100,
            BUYER,
            _escrow_addr("job-DOUBLE01"),
            {"provider": PROVIDER},
        )
        _tx(conn, 2, 2, "ESCROW_RELEASE", "job-DOUBLE01", 80, PROVIDER2, PROVIDER)
        _tx(conn, 3, 3, "ESCROW_RELEASE", "job-DOUBLE01", 80, PROVIDER2, PROVIDER)
        conn.commit()
        conn.close()
        db = tmp_path / "chain.db"
        code = tool.main(["--db", str(db), "--plan", "--report", str(tmp_path / "r.json")])
        out = capsys.readouterr().out
        plan = json.loads((tmp_path / "r.json").read_text())["write_plan"]
        assert code == 1
        assert plan["abort"] and "R2" in plan["abort"][0]
        assert "ABORT" in out
        # An abort means no write steps are ever listed for this host.
        assert "step 1" not in out

    def test_plan_flag_changes_no_report_fields(self, tool, tmp_path):
        """--plan is presentation only: the underlying report is identical."""
        db = _build_fixture(tmp_path / "chain.db")
        tool.main(["--db", str(db), "--report", str(tmp_path / "plain.json")])
        tool.main(["--db", str(db), "--plan", "--report", str(tmp_path / "plan.json")])
        plain = json.loads((tmp_path / "plain.json").read_text())
        with_plan = json.loads((tmp_path / "plan.json").read_text())
        assert with_plan.pop("write_plan")  # present and non-empty
        assert with_plan == plain
