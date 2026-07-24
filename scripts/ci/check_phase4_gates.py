#!/usr/bin/env python3
"""Phase 4 success-criteria gate checker for v0.11.0.

Reads a YAML gate definition (default: docs/releases/v0.11.0/phase4_gates.yaml)
and exits with status 0 only when every gate is marked ``status: passed`` and,
where numeric, ``current >= threshold``. Otherwise exits 1 and prints a report.

This script is intended for release-time gating and can be wired into CI as a
manual or release-triggered job.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required to run the Phase 4 gate checker") from exc


DEFAULT_GATE_FILE = Path(__file__).resolve().parents[2] / "docs" / "releases" / "v0.11.0" / "phase4_gates.yml"


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def check_gates(data: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """Return a list of (gate_name, message, passed) tuples."""
    results: list[tuple[str, str, bool]] = []
    gates = data.get("gates") or {}
    if not isinstance(gates, dict):
        results.append(("<root>", "'gates' section is missing or not a mapping", False))
        return results

    for name, gate in gates.items():
        if not isinstance(gate, dict):
            results.append((str(name), "gate entry is not a mapping", False))
            continue

        status = str(gate.get("status", "")).lower()
        threshold = _to_decimal(gate.get("threshold"))
        current = _to_decimal(gate.get("current"))

        if status == "passed":
            results.append((str(name), "status is 'passed'", True))
            continue

        if current is None:
            results.append((str(name), "no current value and status is not 'passed'", False))
            continue

        if threshold is None:
            results.append((str(name), f"current={current}, no threshold defined", False))
            continue

        if current >= threshold:
            results.append((str(name), f"current={current} meets threshold={threshold}", True))
        else:
            results.append(
                (
                    str(name),
                    f"current={current} below threshold={threshold} ({gate.get('unit', '')})",
                    False,
                )
            )

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Phase 4 success criteria gates for v0.11.0.")
    parser.add_argument(
        "--gates-file",
        type=Path,
        default=DEFAULT_GATE_FILE,
        help="Path to the phase4_gates.yaml file",
    )
    args = parser.parse_args(argv)

    gate_file: Path = args.gates_file
    if not gate_file.exists():
        print(f"ERROR: gate file not found: {gate_file}", file=sys.stderr)
        return 1

    with gate_file.open("r", encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            print(f"ERROR: invalid YAML in {gate_file}: {exc}", file=sys.stderr)
            return 1

    if not isinstance(data, dict):
        print(f"ERROR: {gate_file} does not contain a YAML mapping", file=sys.stderr)
        return 1

    version = data.get("version", "unknown")
    print(f"Phase 4 success criteria gates (v{version})")
    print(f"Source: {gate_file}")
    print("-" * 60)

    results = check_gates(data)
    passed = 0
    failed = 0
    for name, message, ok in results:
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {name}: {message}")
        if ok:
            passed += 1
        else:
            failed += 1

    print("-" * 60)
    print(f"Total: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
