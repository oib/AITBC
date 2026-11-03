"""CACHE-MONITOR-MEMORY-THRESHOLD-DEAD-1 — ALERT_THRESHOLD=90 must gate:
990 of 1000 bytes logs ALERT and exits non-zero."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "cache-monitor.sh"


def _redis_shim(tmp_path, used):
    f = tmp_path / "redis-cli"
    f.write_text(
        "#!/bin/bash\n"
        'case "$2" in\n'
        f' memory) echo "used_memory_human:0.98K"; echo "used_memory_peak_human:1K"; echo "used_memory:{used}";;\n'
        ' config) echo "maxmemory"; echo "1000";;\n'
        ' stats) echo "keyspace_hits:1"; echo "keyspace_misses:0";;\n'
        ' keyspace) echo "db0:keys=1";;\n'
        "esac\n"
        "exit 0\n"
    )
    f.chmod(0o755)


def test_990_of_1000_alerts(tmp_path):
    _redis_shim(tmp_path, 990)
    r = subprocess.run(
        ["bash", "-c", f"source {SCRIPT}; check_redis_memory"],
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path) + ":/usr/bin:/bin"},
    )
    assert "ALERT" in r.stdout + r.stderr
    assert r.returncode == 1
