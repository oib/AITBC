"""Every long-running aitbc service unit carries the OOM-protection knobs.

Hub's 3906 MB container ate three system-wide OOM kills on 22 Oct 2026 —
user@0 slice plus aitbc-coordinator-api and aitbc-blockchain-rpc — because
no unit ranked its own OOM score and most carried no memory ceiling at
all. The fix is unit-file configuration, so this is a source scan like
``test_service_file_logging_is_enabled.py``: importing service code to
check a directive would pull in the whole platform for one line.

Rules, applied to every ``*.service`` under ``apps/`` and ``scripts/``
that is a long-running unit (``Restart=on-failure`` and NOT
``Type=oneshot`` — oneshots never restart, so their knobs are dead
config; ``aitbc-recovery.service`` is the example):

1. ``OOMScoreAdjust=`` absent. 486f25e03 stripped it from every unit:
   hub is an unprivileged LXC where the score is inert, so the lint now
   guards against the dead key creeping back in.
2. ``MemoryMax=`` implies ``MemoryHigh=``, and High < Max — the soft
   throttle must sit under the hard cap or it never fires.
3. ``RestartSec=`` present — a restart delay exists so an OOM-killed
   unit does not re-enter the same spike instantly.

Value parsing accepts systemd's ``K``/``M``/``G``/``T`` byte suffixes;
``infinity`` and percentages are not used in this tree and would fail
loudly here rather than parse wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
UNIT_GLOBS = ("apps/**/*.service", "scripts/**/*.service")

_SUFFIX = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40}


def _units() -> list[Path]:
    files: list[Path] = []
    for pattern in UNIT_GLOBS:
        files.extend(REPO.glob(pattern))
    return sorted(files)


def _section_service(path: Path) -> dict[str, str]:
    """Directive -> value for the [Service] section only."""
    values: dict[str, str] = {}
    in_service = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_service = line == "[Service]"
            continue
        if in_service and "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    return values


def _bytes(val: str) -> int:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([KMGT]?)", val)
    if not m:
        raise ValueError(f"unparseable systemd size: {val!r}")
    return int(float(m.group(1)) * _SUFFIX.get(m.group(2), 1))


def _long_running(path: Path) -> bool:
    svc = _section_service(path)
    return svc.get("Restart") == "on-failure" and svc.get("Type") != "oneshot"


LONG_RUNNING = [p for p in _units() if _long_running(p)]


def test_scan_finds_long_running_units() -> None:
    # Guard against a silent empty scan: hub alone runs ~20 of these.
    assert len(LONG_RUNNING) >= 20, f"expected >=20 long-running units, found {len(LONG_RUNNING)}"


@pytest.mark.parametrize("path", LONG_RUNNING, ids=lambda p: p.name)
def test_oom_score_adjust_stays_absent(path: Path) -> None:
    val = _section_service(path).get("OOMScoreAdjust")
    assert val is None, f"{path.name}: OOMScoreAdjust={val} re-added — inert on unprivileged LXC (486f25e03)"


@pytest.mark.parametrize("path", LONG_RUNNING, ids=lambda p: p.name)
def test_memory_high_below_memory_max(path: Path) -> None:
    svc = _section_service(path)
    if "MemoryMax" not in svc:
        return  # uncapped services get their caps from the Phase-0 table
    assert "MemoryHigh" in svc, f"{path.name}: MemoryMax={svc['MemoryMax']} without MemoryHigh"
    hi, mx = _bytes(svc["MemoryHigh"]), _bytes(svc["MemoryMax"])
    assert hi < mx, f"{path.name}: MemoryHigh={svc['MemoryHigh']} not below MemoryMax={svc['MemoryMax']}"


@pytest.mark.parametrize("path", LONG_RUNNING, ids=lambda p: p.name)
def test_restart_sec_present(path: Path) -> None:
    val = _section_service(path).get("RestartSec")
    assert val is not None, f"{path.name}: long-running unit lacks RestartSec"
    assert int(val.rstrip("s")) >= 5, f"{path.name}: RestartSec={val} below 5s"
