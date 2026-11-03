"""ENV-WATCH-EMPTY-VALUE-PRESENT-1 — an empty or blanked assignment must
report 0: systemd EnvironmentFile stacking makes the LAST assignment win."""

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("env_watch", REPO / "scripts" / "monitoring" / "env-watch-textfile.py")
envw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(envw)


def _scan(tmp_path, files):
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    return envw.scan_entries([("svc", "VAR", [str(tmp_path / n) for n in files])])[0]


def test_empty_value_reports_0(tmp_path):
    assert _scan(tmp_path, {"a.env": "VAR=\n"})[("svc", "VAR")] == 0


def test_late_blank_wins(tmp_path):
    assert _scan(tmp_path, {"a.env": "VAR=x\n", "b.env": "VAR=\n"})[("svc", "VAR")] == 0


def test_real_value_reports_1(tmp_path):
    assert _scan(tmp_path, {"a.env": "VAR=\n", "b.env": "VAR=x\n"})[("svc", "VAR")] == 1
