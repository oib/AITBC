"""The unlanded-settlement exporter: ``scripts/monitoring/escrow-settlements-textfile.py``.

S-8 remedy 3. ``release_escrow``/``refund_escrow`` mark a row terminal at RPC
acceptance; a settlement dropped at production then serves a dead hash forever
(15 such rows exist fleet-wide, invisible for weeks). The exporter reads each
local chain.db read-only, counts rows whose stored settlement hash is absent
from the sealed ``transaction`` table past the age threshold, and writes a
node_exporter textfile that ``aitbc_rules.yml`` alerts on.

The fixtures carry the 15 known dead rows from
``TOPOLOGY/2026-10-03-escrow-residue-unlanded-release.md`` (job-id prefixes are
what that audit published) plus landed/in-flight controls.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
import stat
import time
from pathlib import Path

import pytest

MONITORING = Path(__file__).resolve().parents[2] / "scripts" / "monitoring"

_spec = importlib.util.spec_from_file_location("escrow_settlements_textfile", MONITORING / "escrow-settlements-textfile.py")
assert _spec is not None and _spec.loader is not None
exporter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exporter)

NOW = time.time()
# int(NOW): %f round-trip can land the stored ts a fraction of a µs after the
# requested epoch and flip int(age) below 100000; integer OLD renders exactly.
OLD = int(NOW) - 100_000  # every known dead row is far past the 900s threshold


def _ts(epoch: float) -> str:
    """SQLAlchemy's sqlite DATETIME render: 'YYYY-MM-DD HH:MM:SS.ffffff' (naive UTC)."""
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


# The 15 unlanded settlements from the residue audit: (job id, kind, dead hash).
# Hub rows are published as 8-char prefixes; node0 sw_job_ipfs rows by their
# time suffix -- the fixture ids embed exactly what the audit names.
DEAD_RELEASES = [
    ("6cf24981", "release"),  # hub v2, lock block 1550
    ("52e476db", "release"),  # hub v2, lock block 1570
    ("544d1132", "release"),  # hub v2, lock block 1609
    ("82dd7c59", "release"),  # hub v2, lock block 1636
    ("abfe8833", "release"),  # hub v3, lock block 7224
    ("f05ada69", "release"),  # hub v3, lock block 7306
    ("5f6ebf5f", "release"),  # hub — lock AND release never landed
    ("sw_job_ipfs_20260911094410_dead", "release"),  # node0 v2
    ("sw_job_ipfs_20260911094553_dead", "release"),  # node0 v2
    ("sw_job_ipfs_20260911101737_dead", "release"),  # node0 v2
    ("sw_job_20260914200636_207d09b8", "release"),  # node0 v3
    ("sw_job_20260914200706_88d364d9", "release"),  # node0 v3
    ("sw_job_20260914200726_a558bd8a", "release"),  # node0 v3
]
DEAD_REFUNDS = [
    ("sw_job_ipfs_20260911095909_dead", "refund"),  # node0 v2, lock block 2426
    ("sw_job_ipfs_20260911101750_dead", "refund"),  # node0 v2, lock block 2445
]
KNOWN_DEAD = DEAD_RELEASES + DEAD_REFUNDS


def _make_db(path: Path, rows: list[tuple], landed: list[str] | None = None) -> Path:
    """A minimal chain.db: the escrow + transaction columns the check reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE escrow (job_id TEXT PRIMARY KEY, status TEXT, release_tx_hash TEXT, "
        "refund_tx_hash TEXT, released_at TEXT, refunded_at TEXT)"
    )
    conn.execute("CREATE TABLE 'transaction' (tx_hash TEXT, type TEXT, payload TEXT)")
    conn.executemany(
        "INSERT INTO escrow (job_id, status, release_tx_hash, refund_tx_hash, released_at, refunded_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.executemany("INSERT INTO 'transaction' (tx_hash) VALUES (?)", [(h,) for h in (landed or [])])
    conn.commit()
    conn.close()
    return path


def _dead_row(job_id: str, kind: str) -> tuple:
    dead_hash = f"0xdead{job_id[-4:]}"
    if kind == "release":
        return (job_id, "released", dead_hash, None, _ts(OLD), None)
    return (job_id, "refunded", None, dead_hash, None, _ts(OLD))


@pytest.fixture
def fleet_db(tmp_path) -> Path:
    """A chain.db carrying all 15 known dead rows."""
    return _make_db(
        tmp_path / "data" / "ait-test" / "chain.db",
        [_dead_row(job_id, kind) for job_id, kind in KNOWN_DEAD],
    )


class TestParseSettledAt:
    @pytest.mark.parametrize(
        "raw",
        [
            "2026-09-10 19:19:58.790000",  # the SQLAlchemy space form
            "2026-09-10T19:19:58.790000",  # ISO T form
            "2026-09-10T19:19:58.790000Z",  # Z suffix
            "2026-09-10T19:19:58+00:00",  # explicit offset
        ],
    )
    def test_known_forms_parse(self, raw):
        assert exporter.parse_settled_at(raw) is not None

    @pytest.mark.parametrize("raw", [None, "", "  ", "yesterday", 12345, "2026-13-40 99:99:99"])
    def test_unusable_forms_are_none(self, raw):
        assert exporter.parse_settled_at(raw) is None


class TestUnlandedRows:
    def _check(self, db: Path, now: float = NOW, max_age: float = 900.0):
        return exporter.read_db(str(db), now, max_age)

    def test_all_15_known_dead_rows_flag(self, fleet_db):
        violations = self._check(fleet_db)
        assert violations is not None
        flagged = {(v.job_id, v.kind) for v in violations}
        assert flagged == set(KNOWN_DEAD)

    def test_landed_settlement_is_not_a_violation(self, tmp_path):
        db = _make_db(
            tmp_path / "chain.db",
            [("job-ok", "released", "0xlanded", None, _ts(OLD), None)],
            landed=["0xlanded"],
        )
        assert self._check(db) == []

    def test_in_flight_settlement_is_not_a_violation(self, tmp_path):
        """A marked row younger than the threshold is settling, not dead."""
        db = _make_db(
            tmp_path / "chain.db",
            [("job-fresh", "released", "0xnewhash", None, _ts(NOW - 60), None)],
        )
        assert self._check(db) == []

    def test_locked_row_is_not_checked(self, tmp_path):
        db = _make_db(tmp_path / "chain.db", [("job-open", "locked", None, None, None, None)])
        assert self._check(db) == []

    def test_missing_hash_flags_immediately_for_old_rows(self, tmp_path):
        """A settled row with no stored hash can never verify — it is a violation."""
        db = _make_db(tmp_path / "chain.db", [("job-nohash", "released", None, None, _ts(OLD), None)])
        violations = self._check(db)
        assert [v.job_id for v in violations] == ["job-nohash"]

    def test_missing_timestamp_flags_immediately(self, tmp_path):
        """A terminal claim with no timestamp cannot age out — flag it now."""
        db = _make_db(tmp_path / "chain.db", [("job-notime", "released", "0xabsent", None, None, None)])
        violations = self._check(db)
        assert [v.job_id for v in violations] == ["job-notime"]

    def test_threshold_env_scales_the_age_gate(self, tmp_path):
        db = _make_db(tmp_path / "chain.db", [("job-edge", "released", "0xabsent", None, _ts(NOW - 100), None)])
        assert self._check(db, max_age=900.0) == []
        assert [v.job_id for v in self._check(db, max_age=60.0)] == ["job-edge"]

    def test_refund_and_release_legs_are_checked_independently(self, tmp_path):
        """A row marked both ways flags the leg whose hash is missing."""
        db = _make_db(
            tmp_path / "chain.db",
            [("job-both", "released", "0xlanded", "0xabsent", _ts(OLD), _ts(OLD))],
            landed=["0xlanded"],
        )
        violations = self._check(db)
        assert [(v.job_id, v.kind) for v in violations] == [("job-both", "refund")]

    def test_stored_refund_hash_claims_the_leg_on_a_released_row(self, tmp_path):
        """The live blind spot: node0's metered rows are status='released' with
        refunded_at NULL but carry a dead refund_tx_hash — the stored hash is
        itself a claim and must flag even without a refund mark."""
        db = _make_db(
            tmp_path / "chain.db",
            [("job-metered", "released", "0xlanded", "0xdeadrefund", _ts(OLD), None)],
            landed=["0xlanded"],
        )
        violations = self._check(db)
        assert [(v.job_id, v.kind) for v in violations] == [("job-metered", "refund")]

    def test_stored_release_hash_claims_the_leg_on_a_refunded_row(self, tmp_path):
        """Symmetric blind spot: a release hash on a refund-marked row."""
        db = _make_db(
            tmp_path / "chain.db",
            [("job-metered2", "refunded", "0xdeadrel", "0xlanded", None, _ts(OLD))],
            landed=["0xlanded"],
        )
        violations = self._check(db)
        assert [(v.job_id, v.kind) for v in violations] == [("job-metered2", "release")]

    def test_hash_only_row_is_a_claim_with_illegible_age(self, tmp_path):
        """A stored hash with no status or timestamp is still a settlement
        claim; its unparseable age cannot hide an unsealed hash."""
        db = _make_db(
            tmp_path / "chain.db",
            [("job-hashonly", "locked", None, "0xdeadrefund", None, None)],
        )
        violations = self._check(db)
        assert [(v.job_id, v.kind) for v in violations] == [("job-hashonly", "refund")]

    def test_sealed_second_leg_hash_is_not_a_violation(self, tmp_path):
        """Hash-claims-leg must not flag the healed two-leg rows: both stored
        hashes sealed means clean, regardless of the missing refunded_at."""
        db = _make_db(
            tmp_path / "chain.db",
            [("job-healed", "released", "0xrel", "0xref", _ts(OLD), None)],
            landed=["0xrel", "0xref"],
        )
        assert self._check(db) == []

    def test_unreadable_db_is_failure_not_clear(self, tmp_path):
        db = tmp_path / "chain.db"
        db.write_text("not sqlite")
        assert exporter.read_db(str(db), NOW, 900.0) is None

    def test_missing_escrow_table_is_failure_not_clear(self, tmp_path):
        """A DB without the table cannot prove 'all clear' — it failed the check."""
        db = tmp_path / "chain.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE 'transaction' (tx_hash TEXT)")
        conn.commit()
        conn.close()
        assert exporter.read_db(str(db), NOW, 900.0) is None


class TestRender:
    def test_metrics_cover_count_detail_oldest_and_health(self, fleet_db):
        results = {str(fleet_db): exporter.read_db(str(fleet_db), NOW, 900.0)}
        text = exporter.render(results, now=NOW)
        assert f"aitbc_escrow_unlanded_settlements {len(KNOWN_DEAD)}" in text
        for job_id, kind in KNOWN_DEAD:
            assert f'aitbc_escrow_unlanded_settlement{{job_id="{job_id}",kind="{kind}"}} 1' in text
        assert "aitbc_escrow_unlanded_settlement_oldest_seconds 100000" in text
        assert 'aitbc_escrow_settlement_scrape_success{db="' + str(fleet_db) + '"} 1' in text
        assert f"aitbc_escrow_settlement_scrape_timestamp_seconds {int(NOW)}" in text
        assert text.endswith("\n")

    def test_clean_db_renders_zero_violations(self, tmp_path):
        db = _make_db(tmp_path / "chain.db", [("job-ok", "released", "0xlanded", None, _ts(OLD), None)], landed=["0xlanded"])
        text = exporter.render({str(db): exporter.read_db(str(db), NOW, 900.0)}, now=NOW)
        assert "aitbc_escrow_unlanded_settlements 0" in text
        assert "aitbc_escrow_unlanded_settlement{" not in text
        assert "aitbc_escrow_unlanded_settlement_oldest_seconds 0" in text

    def test_job_id_in_a_label_cannot_break_exposition(self):
        text = exporter.render(
            {"/db": [exporter.Violation(job_id='evil"\nname', kind="release", age_seconds=1.0)]},
            now=NOW,
        )
        lines = [line for line in text.splitlines() if line.startswith("aitbc_escrow_unlanded_settlement{")]
        assert len(lines) == 1 and 'evil\\"\\nname' in lines[0]


class TestMain:
    def _env(self, monkeypatch, tmp_path, db_path: Path | None = None):
        monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path / "out"))
        (tmp_path / "out").mkdir()
        if db_path is not None:
            monkeypatch.setenv("AITBC_CHAIN_DB", str(db_path))
        else:
            monkeypatch.delenv("AITBC_CHAIN_DB", raising=False)
            monkeypatch.setenv("AITBC_DATA_DIR", str(tmp_path))

    def test_writes_metrics_and_exits_0(self, fleet_db, tmp_path, monkeypatch):
        self._env(monkeypatch, tmp_path, fleet_db)
        assert exporter.main() == 0
        text = (tmp_path / "out" / exporter.OUTPUT_NAME).read_text()
        assert f"aitbc_escrow_unlanded_settlements {len(KNOWN_DEAD)}" in text

    def test_glob_scans_data_dir_when_no_explicit_db(self, fleet_db, tmp_path, monkeypatch):
        """AITBC_DATA_DIR is the parent of data/: the fixture is data/ait-test/chain.db."""
        self._env(monkeypatch, tmp_path, db_path=None)
        assert exporter.main() == 0
        text = (tmp_path / "out" / exporter.OUTPUT_NAME).read_text()
        assert f"aitbc_escrow_unlanded_settlements {len(KNOWN_DEAD)}" in text

    def test_multiple_dbs_union_their_violations(self, tmp_path, monkeypatch):
        db1 = _make_db(tmp_path / "data" / "c1" / "chain.db", [_dead_row("job-a", "release")])
        db2 = _make_db(tmp_path / "data" / "c2" / "chain.db", [_dead_row("job-b", "refund")])
        self._env(monkeypatch, tmp_path, db_path=None)
        assert exporter.main() == 0
        text = (tmp_path / "out" / exporter.OUTPUT_NAME).read_text()
        assert "aitbc_escrow_unlanded_settlements 2" in text
        assert 'db="' + str(db1) + '"' in text and 'db="' + str(db2) + '"' in text

    def test_failed_db_exits_1_but_still_writes(self, tmp_path, monkeypatch):
        db = tmp_path / "data" / "bad" / "chain.db"
        db.parent.mkdir(parents=True)
        db.write_text("not sqlite")
        self._env(monkeypatch, tmp_path, db_path=None)
        assert exporter.main() == 1
        text = (tmp_path / "out" / exporter.OUTPUT_NAME).read_text()
        assert 'aitbc_escrow_settlement_scrape_success{db="' + str(db) + '"} 0' in text

    def test_no_db_found_exits_2_but_still_writes(self, tmp_path, monkeypatch, capsys):
        """No chain.db is a failed check, not silence: the textfile must still
        carry a failing scrape_success so the alert has a series to fire on."""
        self._env(monkeypatch, tmp_path, db_path=None)
        assert exporter.main() == 2
        assert "no chain.db" in capsys.readouterr().err
        text = (tmp_path / "out" / exporter.OUTPUT_NAME).read_text()
        assert 'aitbc_escrow_settlement_scrape_success{db="none"} 0' in text
        assert "aitbc_escrow_settlement_scrape_timestamp_seconds" in text

    def test_bad_threshold_exits_2(self, fleet_db, tmp_path, monkeypatch, capsys):
        self._env(monkeypatch, tmp_path, fleet_db)
        monkeypatch.setenv("AITBC_ESCROW_SETTLEMENT_MAX_AGE_SECONDS", "whenever")
        assert exporter.main() == 2


class TestWriteAtomic:
    def test_writes_world_readable_file_and_leaves_no_temp_file(self, tmp_path):
        exporter.write_atomic(str(tmp_path), "first\n")
        exporter.write_atomic(str(tmp_path), "second\n")
        target = tmp_path / exporter.OUTPUT_NAME
        assert target.read_text() == "second\n"
        assert stat.S_IMODE(target.stat().st_mode) == 0o644
        assert [p.name for p in tmp_path.iterdir()] == [exporter.OUTPUT_NAME]

    def test_failed_write_keeps_the_previous_file(self, tmp_path, monkeypatch):
        exporter.write_atomic(str(tmp_path), "good\n")

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(exporter.os, "replace", boom)
        with pytest.raises(OSError):
            exporter.write_atomic(str(tmp_path), "bad\n")
        assert (tmp_path / exporter.OUTPUT_NAME).read_text() == "good\n"
        assert [p.name for p in tmp_path.iterdir()] == [exporter.OUTPUT_NAME]


class TestFilesAgree:
    """The rules, the script and the unit files have to name the same things."""

    def test_every_metric_the_rules_use_is_emitted(self):
        rules = (MONITORING / "aitbc_rules.yml").read_text()
        used = set(re.findall(r"\baitbc_escrow_[a-z_]+", rules))
        assert used, "the rules no longer read the escrow settlement series"
        emitted = set(
            re.findall(
                r"\baitbc_escrow_[a-z_]+",
                exporter.render({"/db": [exporter.Violation(job_id="j", kind="release", age_seconds=1.0)]}, now=1),
            )
        )
        assert used <= emitted, used - emitted

    def test_unit_runs_the_script_from_the_repo_and_writes_the_textfile_dir(self):
        unit = (MONITORING / "aitbc-escrow-settlements.service").read_text()
        assert "/opt/aitbc/scripts/monitoring/escrow-settlements-textfile.py" in unit
        assert os.access(MONITORING / "escrow-settlements-textfile.py", os.X_OK)
        directory = re.search(r"^Environment=AITBC_TEXTFILE_DIR=(\S+)$", unit, re.M).group(1)
        assert f"ReadWritePaths={directory}" in unit

    def test_timer_fires_minutely_on_the_service(self):
        timer = (MONITORING / "aitbc-escrow-settlements.timer").read_text()
        assert "OnCalendar=minutely" in timer
        assert "Unit=aitbc-escrow-settlements.service" in timer

    def test_alert_rules_are_in_the_shared_file_not_hub_only(self):
        """Per-host escrow rows need per-host coverage: rules belong with every
        host's rule loadout, not the hub-only file (the T35 lesson, inverted)."""
        shared = (MONITORING / "aitbc_rules.yml").read_text()
        hub = (MONITORING / "aitbc_hub_rules.yml").read_text()
        assert "EscrowSettlementUnlanded" in shared
        assert "EscrowSettlement" not in hub

    def _escrow_alert_bodies(self) -> list[str]:
        """The text of each ``- alert: EscrowSettlement*`` block, comments stripped."""
        rules = (MONITORING / "aitbc_rules.yml").read_text()
        alerts = re.split(r"\n\s*- alert: ", rules)
        return [
            "\n".join(line for line in a.splitlines() if not line.lstrip().startswith("#"))
            for a in alerts
            if a.startswith("EscrowSettlement")
        ]

    def test_escrow_alerts_do_not_use_absent(self):
        """absent() has no instance label and, under per-host evaluation, fires
        on every host that lacks the timer — the T35 mechanism in miniature."""
        bodies = self._escrow_alert_bodies()
        assert len(bodies) >= 2, bodies
        assert all("absent(" not in body for body in bodies)

    def test_unreadable_db_fires_an_alert_not_an_all_clear(self):
        """scrape_success 0 means the count is untrustworthy, not zero."""
        bodies = self._escrow_alert_bodies()
        assert any(re.search(r"aitbc_escrow_settlement_scrape_success\s*==\s*0", body) for body in bodies), (
            "no alert reads scrape_success — a broken DB would resolve as all-clear"
        )
