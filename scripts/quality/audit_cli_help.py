#!/usr/bin/env python3
"""Audit all ``aitbc`` CLI --help output and print a 10/10 score.

Run from the repo root with the venv active:

    python scripts/quality/audit_cli_help.py

Add ``--fail-under 100`` to exit non-zero unless the score is perfect.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = REPO_ROOT / "cli"

# cli/aitbc_cli is an editable install in the venv, but the source tree may not
# be on sys.path if the script is invoked directly.  Be safe.
if str(CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(CLI_ROOT))

from aitbc_cli.core.main import cli
from aitbc_cli.utils.help_quality import walk_commands, score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit with non-zero status if the score is below this value.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a human report.",
    )
    parser.add_argument(
        "--show-failures",
        type=int,
        default=20,
        metavar="N",
        help="Print the first N failing commands.",
    )
    args = parser.parse_args()

    results = walk_commands(cli)
    report = score(results, min_desc_words=6)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print("AITBC CLI --help audit")
    print(f"  Total commands : {report['total']}")
    print(f"  Passing        : {report['ok']}")
    print(f"  Score          : {report['score']:.2f} / 100")
    print()

    failures = report["failures"]
    if failures:
        print(f"Top {args.show_failures} failing commands:")
        for a in failures[: args.show_failures]:
            print(f"  - {a['path']}")
            for issue in a["issues"]:
                print(f"      * {issue}")

    if args.fail_under is not None and report["score"] < args.fail_under:
        print(f"\nFAIL: score {report['score']:.2f} is below {args.fail_under}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
