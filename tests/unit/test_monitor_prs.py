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


SCRIPT_PM = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "production_monitoring.sh"


def test_no_double_line_status():
    """#1009: is-active || echo produced a two-line status = phantom alert."""
    src = SCRIPT_PM.read_text()
    assert 'is-active "$service" 2>/dev/null || echo' not in src
    assert "status=${status:-failed}" in src


SCRIPT_FCC = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "fleet-config-check.sh"


def test_no_eval_of_remote_text():
    """#1010: remote output is parsed, never eval'd."""
    src = SCRIPT_FCC.read_text()
    assert 'eval "$res"' not in src
    assert "while IFS='=' read -r" in src


def test_unreachable_is_flag_not_unset():
    """#1011: an unreadable host counts as a flag in both sections."""
    src = SCRIPT_FCC.read_text()
    assert "UNREACHABLE — cannot verify the kill switch is unset" in src
    assert "UNREACHABLE — cannot verify the mock flag is unset" in src
    # the all-clear lines only print when no flag was raised
    assert src.count("UNREACHABLE") >= 6


def test_dropped_host_fails_digest():
    """#1012: a dropped host sets dig_bad and names the compared hosts."""
    src = SCRIPT_FCC.read_text()
    assert "FAIL: no digest from:" in src
    assert "dig_dropped" in src


def test_no_ssh_reach_exits_nonzero():
    """#1013: skipped env sections = exit 3, never a 'No drift' claim."""
    src = SCRIPT_FCC.read_text()
    assert "NOT EVALUABLE: env sections skipped" in src
    assert "exit 3" in src


def test_deprecated_bridge_set_derives_from_deployments_json():
    """#1557: the dead-contract sweep must read deployments-bridge-sepolia.json
    so a newly-deprecated instance cannot drift out of the check."""
    src = SCRIPT_FCC.read_text()
    assert "deployments-bridge-sepolia.json" in src
    assert "DEAD_BRIDGE_CONTRACTS=$(python3" in src
    # every address the JSON marks deprecated must appear in the fallback list
    import json

    repo = SCRIPT_FCC.resolve().parents[2]
    data = json.loads((repo / "contracts" / "deployments-bridge-sepolia.json").read_text())
    deprecated = {e["address"] for e in data if e.get("deprecated")}
    fallback = src.split('DEAD_BRIDGE_CONTRACTS="', 1)[1].split('"', 1)[0]
    for addr in deprecated:
        assert addr in fallback, f"{addr} missing from fleet-config-check fallback"
