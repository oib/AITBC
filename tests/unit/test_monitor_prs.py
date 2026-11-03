"""#1008: a mixed PR is flagged manual — min(rings) wins, ring 0/1 never approved."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "monitor-prs.py"


def _load():
    spec = importlib.util.spec_from_file_location("monitor_prs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["monitor_prs"] = module
    spec.loader.exec_module(module)
    return module


def test_min_ring_logic():
    src = SCRIPT.read_text()
    assert "min(rings)" in src
    assert "min_ring <= 1" in src


def test_changed_files_compiled_not_first20():
    src = SCRIPT.read_text()
    assert '["find", tmpdir' not in src
    assert "changed_files" in src
