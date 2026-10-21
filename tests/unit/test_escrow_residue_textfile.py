"""Fixture tests for escrow-residue-textfile.py write_atomic (ATTEST-PROM-MODE-1).

Same mkstemp-without-chmod class as the attestation exporter: the .prom
landed 0600, unreadable to node-exporter (user prometheus)."""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exporter = _load("escrow_residue_textfile", REPO / "scripts/monitoring/escrow-residue-textfile.py")


def test_write_atomic_world_readable(tmp_path):
    exporter.write_atomic(str(tmp_path), "metric 1\n")
    out = tmp_path / exporter.OUTPUT_NAME
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o644
    assert out.read_text() == "metric 1\n"


def test_write_atomic_rename_failure_leaves_target_and_no_litter(tmp_path, monkeypatch):
    target = tmp_path / exporter.OUTPUT_NAME
    target.write_text("old\n")
    monkeypatch.setattr(exporter.os, "rename", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    try:
        exporter.write_atomic(str(tmp_path), "new\n")
        raise AssertionError("expected OSError")
    except OSError:
        pass
    assert target.read_text() == "old\n"
    assert list(tmp_path.glob(".aitbc_escrow_residue.*.tmp")) == []


def test_write_atomic_write_failure_no_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter.os, "fdopen", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    try:
        exporter.write_atomic(str(tmp_path), "x\n")
        raise AssertionError("expected OSError")
    except OSError:
        pass
    assert not (tmp_path / exporter.OUTPUT_NAME).exists()
    assert list(tmp_path.glob(".aitbc_escrow_residue.*.tmp")) == []
