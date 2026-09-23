#!/usr/bin/env python3
"""Fail if a discovered test suite is not classified for a gate.

`testpaths` in pyproject.toml lists every suite pytest collects. The Make
targets CI invokes run only some of them, and for a release cycle the gap
silently grew: exchange, wallet, market, api-gateway, trading, security
and property suites were collectable but never ran anywhere. This check pins
testpaths to scripts/ci/test_suites.py so a suite either runs in a gate or
carries a written reason it cannot.

Exits 1 listing every problem found:
  - testpaths entry missing from the classification
  - classified path that no longer exists on disk
  - path classified in two places (fast/nightly and manual overlap is fine —
    manual wins; overlapping fast+nightly is not)

Run: python3 scripts/ci/check_test_suite_parity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_suites import FAST_SUITES, MANUAL_SUITES, NIGHTLY_SUITES, REPO_ROOT, testpaths


def main() -> int:
    failures: list[str] = []

    classified = set(FAST_SUITES) | set(NIGHTLY_SUITES) | set(MANUAL_SUITES)

    for entry in testpaths():
        if entry not in classified:
            failures.append(f"{entry}: in testpaths but not classified (fast/nightly/manual)")

    for path in sorted(classified):
        if not (REPO_ROOT / path).is_dir():
            failures.append(f"{path}: classified but does not exist on disk")

    dup = set(FAST_SUITES) & set(NIGHTLY_SUITES)
    if dup:
        failures.append(f"classified as both fast and nightly: {sorted(dup)}")

    if failures:
        print("test suite parity violations:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(
        f"parity ok: {len(testpaths())} testpaths entries, "
        f"{len(FAST_SUITES)} fast, {len(NIGHTLY_SUITES)} nightly, {len(MANUAL_SUITES)} manual"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
