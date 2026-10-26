"""SECRET-EXCL-1 / UNPLAYABLE-TAG-1: the census generator reports
secret-excluded counts and unplayable tags correctly."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts/ops/option-coverage.py"
EXC = Path(__file__).parents[1] / "scripts/ops/option-coverage-exclusions.json"

TREE = {
    "path": ["aitbc"],
    "hidden": False,
    "deprecated": False,
    "params": [],
    "children": {
        "agent": {
            "path": ["aitbc", "agent"],
            "hidden": False,
            "deprecated": False,
            "params": [
                {"name": "format", "kind": "Option", "opts": ["--format"], "flag": True, "required": False},
                {"name": "password", "kind": "Option", "opts": ["--password"], "flag": True, "required": False},
            ],
        },
        "agent-comm": {
            "path": ["aitbc", "agent-comm"],
            "hidden": False,
            "deprecated": False,
            "params": [
                {"name": "list", "kind": "Option", "opts": ["--status"], "flag": True, "required": False},
            ],
        },
    },
}


def _run(tmp_path, exclusions=None):
    (tmp_path / "t.json").write_text(json.dumps(TREE))
    (tmp_path / "c.json").write_text(json.dumps(
        [{"scenario": "s1", "line": 1, "kind": "play", "cmd": "aitbc agent --format x", "verdict": "ok", "path": "agent"}]
    ))
    exc = tmp_path / "ex.json"
    exc.write_text(json.dumps(exclusions or {}))
    out = tmp_path / "o.md"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--tree", str(tmp_path / "t.json"),
         "--census", str(tmp_path / "c.json"), "--out", str(out), "--exclusions", str(exc)],
        check=True, capture_output=True)
    return out.read_text()


def test_secret_split(tmp_path):
    md = _run(tmp_path)
    assert "secret-value options are intentionally uncovered" in md
    assert "| `agent` | 2 | 1 | 0 | 1 | 0 | 0 |" in md


def test_unplayable(tmp_path):
    md = _run(tmp_path, {"agent-comm": {"reason": "stale-cli"}})
    assert "unplayable: stale-cli" in md
    assert "| `agent-comm` | 1 | 0 | 0 | 0 | 0 | 1 |" in md
    # every leaf keeps its heading
    assert "### `aitbc agent`" in md


def test_exclusions_file_loads():
    assert "agent-comm list" in json.loads(EXC.read_text())
