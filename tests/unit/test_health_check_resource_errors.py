"""HEALTH-CHECK-RESOURCE-ERRORS-NOT-COUNTED-1 — disk/memory/CPU breaches
must count in TOTAL_ERRORS (exit 1), not just print."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "health_check.sh"


def _shim(tmp_path, name, body):
    f = tmp_path / "bin" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"#!/bin/bash\n{body}")
    f.chmod(0o755)
    return f


def test_resources_at_99pct_exits_1(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _shim(tmp_path, "df", 'echo "Filesystem Size Used Avail Use% Mounted on"; echo "/dev/x 100G 99G 1G 99% /"')
    _shim(
        tmp_path,
        "free",
        'echo "              total        used        free"; echo "Mem:           1000         990          10"',
    )
    _shim(tmp_path, "systemctl", 'echo ""')
    _shim(tmp_path, "curl", "exit 1")
    _shim(tmp_path, "jq", "exit 1")
    r = subprocess.run(
        ["bash", str(SCRIPT), "resources"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(bin_dir) + ":/usr/bin:/bin"},
    )
    assert r.returncode == 1, r.stdout + r.stderr


def test_each_check_returns_1_on_breach():
    body = SCRIPT.read_text()
    for fn in ("check_disk_usage", "check_system_memory", "check_resource_usage"):
        seg = body.split(f"{fn}() {{", 1)[1]
        assert "return 1" in seg or "breach=1" in seg, fn
