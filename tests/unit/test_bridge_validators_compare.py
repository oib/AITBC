"""Fixture tests for scripts/ops/bridge_validators_compare.py."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import bridge_validators_compare as cmp  # noqa: E402


def _db(path: Path, rows: list[tuple[int, str, int]]) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE bridge_validators (id INTEGER PRIMARY KEY, address VARCHAR,"
        " public_key VARCHAR, epoch INTEGER, is_active BOOLEAN, registered_at DATETIME)"
    )
    con.executemany(
        "INSERT INTO bridge_validators (id,address,public_key,epoch,is_active,registered_at) VALUES (?,?,?,?,?,?)",
        [(i, a, "pk", 0, f, "t") for i, a, f in rows],
    )
    con.commit()
    con.close()


R = [(1, "0x02B8F2C6", 1), (2, "0x7DC101A8", 1), (3, "0x43641CA2", 0)]


def test_match_identical_active_sets(tmp_path, capsys):
    a = tmp_path / "a.db"
    _db(a, R)
    b = tmp_path / "b.db"
    _db(b, R[:2])
    assert cmp.main([f"hub:{a}", f"node0:{b}"]) == 0
    out = capsys.readouterr().out
    assert "MATCH" in out and "active=2" in out and "rows=3" in out and "rows=2" in out


def test_differ_on_active_set(tmp_path, capsys):
    a = tmp_path / "a.db"
    _db(a, R)
    c = tmp_path / "c.db"
    _db(c, [(1, "0x2AD555A9", 1)])
    assert cmp.main([f"hub:{a}", f"hub1:{c}"]) == 1
    assert "DIFFER" in capsys.readouterr().out


def test_case_insensitive_address_compare(tmp_path):
    a = tmp_path / "a.db"
    _db(a, [(1, "0x02B8F2C6", 1)])
    b = tmp_path / "b.db"
    _db(b, [(1, "0x02b8f2c6", 1)])
    assert cmp.main([f"x:{a}", f"y:{b}"]) == 0


def test_inactive_rows_do_not_differ(tmp_path):
    a = tmp_path / "a.db"
    _db(a, R)
    b = tmp_path / "b.db"
    _db(b, R[:2] + [(4, "0xDEADBEEF", 0)])
    assert cmp.main([f"x:{a}", f"y:{b}"]) == 0


def test_empty_table_differs(tmp_path, capsys):
    a = tmp_path / "a.db"
    _db(a, R[:2])
    e = tmp_path / "e.db"
    _db(e, [])
    assert cmp.main([f"hub:{a}", f"hub1:{e}"]) == 1
    assert "active=0" in capsys.readouterr().out


def test_json_dump_input(tmp_path):
    a = tmp_path / "a.db"
    _db(a, R[:2])
    j = tmp_path / "j.json"
    j.write_text(json.dumps([{"address": "0x02b8f2c6", "is_active": 1}, {"address": "0x7dc101a8", "is_active": 1}]))
    assert cmp.main([f"hub:{a}", f"node0:{j}"]) == 0


def test_error_path_returns_1(tmp_path, capsys):
    assert cmp.main([f"missing:{tmp_path / 'nope.db'}"]) == 1
    assert "ERROR" in capsys.readouterr().out
