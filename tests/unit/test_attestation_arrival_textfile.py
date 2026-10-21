"""Fixture tests for attestation-arrival-textfile.py (MON-1)."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import stat
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exporter = _load("attestation_arrival_textfile", REPO / "scripts/monitoring/attestation-arrival-textfile.py")

NOW = 1_800_000_000.0
A, B, C, D = "0xAA", "0xBB", "0xCC", "0xDD"


def _block(con, height, proposer, attesting):
    meta = attesting if isinstance(attesting, str) else json.dumps({"attestations": attesting})
    con.execute(
        "INSERT INTO block VALUES (?,?,?,?)",
        (height, proposer, f"2026-09-01 00:{height:02d}:00", meta),
    )


def _atts(*validators):
    return [{"validator": v, "signature": "0xsig"} for v in validators]


def _db(tmp_path: Path) -> Path:
    """Chain fixture: four validators, thirteen blocks covering every edge case."""
    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE block (height INTEGER PRIMARY KEY, proposer TEXT, timestamp TEXT, block_metadata TEXT)")
    _block(con, 1, A, _atts(B, C, D))  # all present
    _block(con, 2, B, _atts(A, C, D))  # all present
    _block(con, 3, C, _atts(A, B, D))  # all present
    _block(con, 4, D, _atts(A, B, C))  # all present
    _block(con, 5, A, _atts(B, D))  # C missing
    _block(con, 6, B, _atts(A, C, C, D))  # C duplicated — counts once
    _block(con, 7, C, _atts(A, B, C, D))  # proposer's own entry ignored
    _block(con, 8, D, "not json{{")  # malformed — all remote missing
    _block(con, 9, D, _atts(A, B, C))  # all present
    _block(con, 10, A, _atts(B, C))  # D missing
    _block(con, 11, D, _atts(A, B, C))  # D proposed — streak skips it
    _block(con, 12, B, _atts(A, C))  # D missing
    _block(con, 13, C, _atts(A, B))  # D missing
    con.commit()
    con.close()
    return db


def _stats(db: Path, window: int = 200, validators=None):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return exporter.arrival_stats(con, window, validators)
    finally:
        con.close()


def test_totals_and_share(tmp_path):
    s = _stats(_db(tmp_path))
    assert s.window_blocks == 13
    assert s.validators == (A, B, C, D)
    assert s.head_height == 13
    assert s.expected_remote_total == 39
    assert s.arrived_remote_total == 32
    assert abs(s.arrival_share - 32 / 39) < 1e-9
    assert s.short_blocks == 5  # h5, h8, h10, h12, h13


def test_missed_per_validator(tmp_path):
    s = _stats(_db(tmp_path))
    assert s.missed_blocks == {A: 1, B: 1, C: 2, D: 3}  # h8 hits A,B,C; h5 C; h10,h12,h13 D


def test_consecutive_missed_streak(tmp_path):
    s = _stats(_db(tmp_path))
    # D: h13 miss, h12 miss, h11 skipped (D proposed), h10 miss -> 3
    assert s.consecutive_missed[D] == 3
    assert s.consecutive_missed[A] == 0
    assert s.consecutive_missed[B] == 0
    assert s.consecutive_missed[C] == 0


def test_window_limits_blocks(tmp_path):
    s = _stats(_db(tmp_path), window=4)
    assert s.window_blocks == 4
    assert s.head_height == 13


def test_validators_override_narrows_set(tmp_path):
    s = _stats(_db(tmp_path), validators=[A, B, C])
    assert s.validators == (A, B, C)
    assert s.expected_remote_total == 30  # 9 in-set-proposer blocks x2 + 4 D blocks x3
    assert s.arrived_remote_total == 26  # malformed h8 (A,B,C) + C still missing on h5
    assert s.missed_blocks == {A: 1, B: 1, C: 2}
    assert s.short_blocks == 2


def test_render_exact_lines(tmp_path):
    db = _db(tmp_path)
    s = _stats(db)
    text = exporter.render({"/db/chain.db": s}, now=NOW)
    assert 'aitbc_attestation_scrape_success{db="/db/chain.db"} 1' in text
    assert 'aitbc_attestation_window_blocks{db="/db/chain.db"} 13' in text
    assert 'aitbc_attestation_validators{db="/db/chain.db"} 4' in text
    assert 'aitbc_attestation_head_height{db="/db/chain.db"} 13' in text
    assert 'aitbc_attestation_expected_remote_total{db="/db/chain.db"} 39' in text
    assert 'aitbc_attestation_arrived_remote_total{db="/db/chain.db"} 32' in text
    assert f'aitbc_attestation_arrival_share{{db="/db/chain.db"}} {repr(round(32 / 39, 6))}' in text
    assert 'aitbc_attestation_short_blocks{db="/db/chain.db"} 5' in text
    assert 'aitbc_attestation_missed_blocks{db="/db/chain.db",validator="0xDD"} 3' in text
    assert 'aitbc_attestation_consecutive_missed{db="/db/chain.db",validator="0xDD"} 3' in text
    assert 'aitbc_attestation_missed_blocks{db="/db/chain.db",validator="0xAA"} 1' in text
    assert 'aitbc_attestation_consecutive_missed{db="/db/chain.db",validator="0xAA"} 0' in text
    assert f"aitbc_attestation_scrape_timestamp_seconds {int(NOW)}" in text


def test_render_marks_failed_db():
    text = exporter.render({"/good/chain.db": None, "/bad/chain.db": None}, now=NOW)
    assert 'aitbc_attestation_scrape_success{db="/bad/chain.db"} 0' in text
    assert 'aitbc_attestation_scrape_success{db="/good/chain.db"} 0' in text
    assert text.count("aitbc_attestation_arrival_share{") == 0


def test_missing_block_table_is_failure(tmp_path):
    db = tmp_path / "empty.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE other (id INTEGER)")
    con.commit()
    con.close()
    assert exporter.read_db(str(db), 200, None) is None


def test_unopenable_db_is_failure(tmp_path):
    assert exporter.read_db(str(tmp_path / "nonexistent" / "chain.db"), 200, None) is None


def test_empty_set_share_is_one(tmp_path):
    db = tmp_path / "one.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE block (height INTEGER PRIMARY KEY, proposer TEXT, timestamp TEXT, block_metadata TEXT)")
    _block(con, 1, A, _atts())
    con.commit()
    con.close()
    s = _stats(db, validators=[A])
    assert s.expected_remote_total == 0
    assert s.arrival_share == 1.0


def test_main_writes_prom(tmp_path, monkeypatch):
    db = _db(tmp_path)
    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setenv("AITBC_CHAIN_DB", str(db))
    monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(outdir))
    assert exporter.main() == 0
    text = (outdir / "aitbc_attestation_arrival.prom").read_text()
    assert 'aitbc_attestation_scrape_success{db="' + str(db) + '"} 1' in text


def test_write_atomic_world_readable(tmp_path):
    """node-exporter runs as user prometheus — mkstemp's 0600 would hide the
    file and blind every alert reading it. The writer must chmod 0644."""
    exporter.write_atomic(str(tmp_path), "metric 1\n")
    out = tmp_path / exporter.OUTPUT_NAME
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o644
    assert out.read_text() == "metric 1\n"


def test_write_atomic_rename_failure_leaves_target_and_no_litter(tmp_path, monkeypatch):
    """A failed rename must not clobber the existing .prom or drop the temp."""
    target = tmp_path / exporter.OUTPUT_NAME
    target.write_text("old\n")
    monkeypatch.setattr(exporter.os, "rename", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    try:
        exporter.write_atomic(str(tmp_path), "new\n")
        raise AssertionError("expected OSError")
    except OSError:
        pass
    assert target.read_text() == "old\n"
    assert list(tmp_path.glob(".aitbc_attestation_arrival.*.tmp")) == []


def test_write_atomic_write_failure_no_partial(tmp_path, monkeypatch):
    """A failed write must leave no partial target and no temp litter."""
    monkeypatch.setattr(exporter.os, "fdopen", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    try:
        exporter.write_atomic(str(tmp_path), "x\n")
        raise AssertionError("expected OSError")
    except OSError:
        pass
    assert not (tmp_path / exporter.OUTPUT_NAME).exists()
    assert list(tmp_path.glob(".aitbc_attestation_arrival.*.tmp")) == []


def test_silent_validator_crosses_alert_thresholds(tmp_path):
    """The M6 case the rules exist for: one validator missing every owed
    attestation. The rendered series must cross BOTH loaded thresholds —
    consecutive_missed >= 20 (AttestationValidatorSilent) and
    arrival_share < 0.97 (AttestationArrivalDegraded) — or the alerts
    would still be blind with the exporter running."""
    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE block (height INTEGER PRIMARY KEY, proposer TEXT, timestamp TEXT, block_metadata TEXT)")
    vs = [A, B, C, D]
    for h in range(1, 30):
        proposer = vs[h % 4]
        _block(con, h, proposer, _atts(*[v for v in vs if v not in (proposer, D)]))
    con.commit()
    con.close()
    s = _stats(db)
    # D proposed h4..h28 (7 blocks) and missed the other 22 owed — an
    # unbroken silence from the head.
    assert s.consecutive_missed[D] >= 20
    assert s.arrival_share < 0.97
    text = exporter.render({str(db): s}, now=NOW)
    label = f'{{db="{db}",validator="0xDD"}}'
    assert f"aitbc_attestation_consecutive_missed{label} {s.consecutive_missed[D]}" in text
    assert "aitbc_attestation_arrival_share{" in text


def test_fresh_chain_no_alert(tmp_path):
    """Cut-day shape: a young bc-2 with a handful of well-attested blocks
    must not fire anything — share stays 1.0 and every streak is zero."""
    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE block (height INTEGER PRIMARY KEY, proposer TEXT, timestamp TEXT, block_metadata TEXT)")
    vs = [A, B, C, D]
    for h in range(1, 4):
        proposer = vs[h % 4]
        _block(con, h, proposer, _atts(*[v for v in vs if v != proposer]))
    con.commit()
    con.close()
    s = _stats(db)
    assert s.arrival_share == 1.0
    assert all(v == 0 for v in s.consecutive_missed.values())
    assert all(v == 0 for v in s.missed_blocks.values())


def _db_with_genesis(tmp_path: Path, produced: int = 25) -> Path:
    """bc-2 shape: height 0 is the file-loaded genesis row (proposer
    "genesis", no attestations list), heights 1..N are produced blocks."""
    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE block (height INTEGER PRIMARY KEY, proposer TEXT, timestamp TEXT, block_metadata TEXT)")
    _block(con, 0, "genesis", json.dumps({"allocations": []}))
    vs = [A, B, C, D]
    for h in range(1, produced + 1):
        proposer = vs[h % 4]
        _block(con, h, proposer, _atts(*[v for v in vs if v != proposer]))
    con.commit()
    con.close()
    return db


def test_genesis_pseudo_proposer_owes_nothing(tmp_path):
    """The genesis row must never enter the validator set: on bc-2 its
    block 0 sits inside the window, so a derived "genesis" validator would
    miss every owed block and export consecutive_missed == head height —
    AttestationValidatorSilent would false-fire on every host."""
    s = _stats(_db_with_genesis(tmp_path))
    assert s.window_blocks == 26  # genesis row still counted as examined
    assert s.head_height == 25
    assert "genesis" not in s.validators
    assert s.validators == (A, B, C, D)
    assert s.expected_remote_total == 25 * 3  # block 0 owes nothing
    assert s.arrival_share == 1.0
    assert s.missed_blocks == {A: 0, B: 0, C: 0, D: 0}
    assert all(v == 0 for v in s.consecutive_missed.values())


def test_genesis_pseudo_proposer_not_in_render(tmp_path):
    db = _db_with_genesis(tmp_path)
    text = exporter.render({str(db): _stats(db)}, now=NOW)
    assert 'validator="genesis"' not in text


def test_genesis_filtered_from_pinned_set(tmp_path):
    """A pinned AITBC_ATTESTATION_VALIDATORS carrying "genesis" is cleaned
    the same way — the pseudo-proposer owes nothing however it arrives."""
    s = _stats(_db_with_genesis(tmp_path), validators=["genesis", A, B, C, D])
    assert s.validators == (A, B, C, D)
    assert "genesis" not in s.missed_blocks


def test_genesis_only_chain_still_reports(tmp_path):
    """A bare genesis row (pre-C5 shape) yields an empty validator set and
    share 1.0 rather than a phantom silent validator."""
    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE block (height INTEGER PRIMARY KEY, proposer TEXT, timestamp TEXT, block_metadata TEXT)")
    _block(con, 0, "genesis", json.dumps({"allocations": []}))
    con.commit()
    con.close()
    s = _stats(db)
    assert s.head_height == 0
    assert s.validators == ()
    assert s.expected_remote_total == 0
    assert s.arrival_share == 1.0
