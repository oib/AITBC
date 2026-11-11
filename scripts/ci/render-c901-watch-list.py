#!/usr/bin/env python3
"""Render C901 / except-ratchet reviewer watch-list (#1517).

Regenerate committed markdown:
  PYTHON=/opt/aitbc/venv/bin/python scripts/ci/render-c901-watch-list.py \\
    > scripts/ci/c901-watch-list.md
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
C901_BASELINE = REPO_ROOT / "scripts/ci/c901-baseline.txt"
EXCEPT_BASELINE = REPO_ROOT / "scripts/ci/except-baseline.txt"
COMPLEX_RE = re.compile(r"is too complex \((\d+) > 10\)")
FUNC_RE = re.compile(r"`([^`]+)` is too complex")


def _repo_python() -> str:
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts/ci/repo-python.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() or sys.executable


def _load_baseline(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not path.is_file():
        return counts
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            counts[parts[1]] = int(parts[0])
    return counts


def _ruff_c901(python: str) -> list[dict]:
    proc = subprocess.run(
        [python, "-m", "ruff", "check", ".", "--select", "C901", "--output-format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise SystemExit(f"ruff C901 scan failed (rc={proc.returncode}): {proc.stderr[:500]}")
    return json.loads(proc.stdout or "[]")


def _rel_path(filename: str) -> str:
    path = Path(filename)
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return filename


def _parse_finding(item: dict) -> tuple[str, str, int, int] | None:
    message = item.get("message", "")
    m_comp = COMPLEX_RE.search(message)
    m_func = FUNC_RE.search(message)
    if not m_comp or not m_func:
        return None
    loc = item.get("location") or {}
    return (
        _rel_path(item.get("filename", "")),
        m_func.group(1),
        int(loc.get("row") or 0),
        int(m_comp.group(1)),
    )


def main() -> int:
    python = _repo_python()
    c901_base = _load_baseline(C901_BASELINE)
    except_base = _load_baseline(EXCEPT_BASELINE)

    findings: list[tuple[str, str, int, int]] = []
    for raw in _ruff_c901(python):
        parsed = _parse_finding(raw)
        if parsed:
            findings.append(parsed)

    # Tier 1: low complexity in files already at their baseline ceiling (headroom 0–1).
    tier1: list[str] = []
    for path, func, line, complexity in sorted(findings, key=lambda t: (t[3], t[0], t[1])):
        base = c901_base.get(path, 0)
        if base < 3:
            continue
        if complexity not in (11, 12, 13):
            continue
        tier1.append(f"- `{path}` `{func}` @ {line} (complexity {complexity}, baseline {base})")

    # Tier 2: highest per-file C901 baseline counts (at ceiling).
    tier2 = sorted(c901_base.items(), key=lambda kv: (-kv[1], kv[0]))[:20]

    # Tier 3: far over threshold — ratchet only blocks new functions, not growth inside.
    tier3: list[str] = []
    for path, func, line, complexity in sorted(findings, key=lambda t: -t[3])[:25]:
        if complexity >= 20:
            tier3.append(f"- `{path}` `{func}` @ {line} (complexity {complexity})")

    by_pkg: dict[str, int] = defaultdict(int)
    for path, _f, _l, _c in findings:
        top = path.split("/", 1)[0] if "/" in path else path
        by_pkg[top] += 1

    except_top = sorted(except_base.items(), key=lambda kv: (-kv[1], kv[0]))[:15]

    lines = [
        "# C901 / except-ratchet watch-list",
        "",
        "Machine-regenerated reference for reviewers (#1517). **Do not edit by hand** —",
        "run `scripts/ci/render-c901-watch-list.py > scripts/ci/c901-watch-list.md`.",
        "",
        "## Gates",
        "",
        "- **C901:** `scripts/ci/check-c901-ratchet.sh` (pre-push hook `c901-complexity-ratchet`)",
        "- **BLE001/S110:** `scripts/ci/check-except-ratchet.sh` (pre-push hook `except-ratchet`)",
        f"- Baseline files: {len(c901_base)} C901 files, {len(except_base)} except files",
        "",
        "## Tier 1 — brushing complexity 11–12 in hot files",
        "",
        "Extract a helper before adding branches to these functions.",
        "",
        *tier1[:40],
        "",
        "## Tier 2 — highest C901 baseline counts (per-file ceiling)",
        "",
        *[f"- `{path}`: {count}" for path, count in tier2],
        "",
        "## Tier 3 — deep complexity (ratchet-blind to in-function growth)",
        "",
        *tier3,
        "",
        "## C901 volume by top-level path",
        "",
        *[f"- `{pkg}`: {count}" for pkg, count in sorted(by_pkg.items(), key=lambda kv: -kv[1])[:12]],
        "",
        "## Except baseline hotspots (BLE001/S110)",
        "",
        *[f"- `{path}`: {count}" for path, count in except_top],
        "",
    ]
    sys.stdout.write("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
