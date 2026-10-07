"""Fixture tests for scripts/ops/bridge_set_vs_consensus.py."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import bridge_set_vs_consensus as bvc  # noqa: E402

ATT = "0x19F0730A,0xE8948A55,0x5E8EA271,0x2AD555A9"


def _db(path: Path, rows: list[tuple[int, str, int, int]]) -> None:
    """rows: (id, address, epoch, is_active)."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE bridge_validators (id INTEGER PRIMARY KEY, address VARCHAR,"
        " public_key VARCHAR, epoch INTEGER, is_active BOOLEAN, registered_at DATETIME)"
    )
    con.executemany(
        "INSERT INTO bridge_validators (id,address,public_key,epoch,is_active,registered_at) VALUES (?,?,?,?,?,?)",
        [(i, a, "pk", e, f, "t") for i, a, e, f in rows],
    )
    con.commit()
    con.close()


def _run(tmp_path: Path, rows, extra_hosts=None):
    db = tmp_path / "h.db"
    _db(db, rows)
    inputs = [f"hub:{db}"] + (extra_hosts or [])
    return bvc.main(inputs + ["--validators", ATT, "--threshold", "2"])


def test_current_shape_cannot(tmp_path, capsys):
    """Registered {0x02b8, 0x7dc1} — neither is an attester."""
    rc = _run(tmp_path, [(1, "0x02b8f2c6", 0, 1), (2, "0x7dc101a8", 0, 1)])
    out = capsys.readouterr().out
    assert rc == 1 and "CANNOT" in out and "intersection=0" in out


def test_planned_pair_cannot(tmp_path, capsys):
    """{0x2aD5, 0x7dc1} — one attester of two members, threshold 2 fails."""
    rc = _run(tmp_path, [(1, "0x2ad555a9", 0, 1), (2, "0x7dc101a8", 0, 1)])
    out = capsys.readouterr().out
    assert rc == 1 and "intersection=1" in out and "CANNOT" in out


def test_four_attesters_can(tmp_path, capsys):
    rows = [(i, a, 1, 1) for i, a in enumerate(ATT.split(","), 1)]
    rc = _run(tmp_path, rows)
    out = capsys.readouterr().out
    assert rc == 0 and "CAN MEET THRESHOLD 2" in out and "intersection=4" in out


def test_latest_epoch_only_counts(tmp_path):
    """epoch-0 rows are ignored once an epoch-1 set exists."""
    rows = [
        (1, "0x02b8f2c6", 0, 1),
        (2, "0x7dc101a8", 0, 1),
        (3, "0x19f0730a", 1, 1),
        (4, "0xe8948a55", 1, 1),
    ]
    assert _run(tmp_path, rows) == 0


def test_inactive_excluded(tmp_path, capsys):
    rows = [(1, "0x19f0730a", 1, 0), (2, "0xe8948a55", 1, 0), (3, "0x7dc101a8", 1, 1)]
    rc = _run(tmp_path, rows)
    assert rc == 1 and "CANNOT" in capsys.readouterr().out


def test_json_dump_input(tmp_path, capsys):
    j = tmp_path / "rows.json"
    j.write_text(
        json.dumps(
            [
                {"address": "0x19f0730a", "is_active": 1, "epoch": 0},
                {"address": "0xe8948a55", "is_active": 1, "epoch": 1},
                {"address": "0x5e8ea271", "is_active": 1, "epoch": 1},
            ]
        )
    )
    rc = bvc.main([f"h:{j}", "--validators", ATT, "--threshold", "2"])
    out = capsys.readouterr().out
    assert rc == 0 and "intersection=2" in out


def test_error_path_returns_1(tmp_path, capsys):
    rc = bvc.main([f"missing:{tmp_path / 'nope.db'}", "--validators", ATT, "--threshold", "2"])
    assert rc == 1 and "ERROR" in capsys.readouterr().out
