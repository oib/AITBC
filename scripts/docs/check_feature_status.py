#!/usr/bin/env python3
"""Feature-status evidence check.

A `✅` in a docs/features/*.md (or docs/FEATURES.md) status table claims a
feature shipped. That claim must be mechanically verifiable: at least one
backticked identifier in the row (a tx type, env var, CLI command, module,
class) must appear in non-docs code. Rows that fail go in
`feature-status-baseline.txt`; the baseline ratchets — new unverifiable
✅ rows fail the check.

    check_feature_status.py                    # verify against the baseline
    check_feature_status.py --write-baseline   # regenerate the baseline
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("feature-status-baseline.txt")

DOC_GLOBS = ("docs/features/*.md", "docs/FEATURES.md")

# directories whose contents count as implementation evidence
CODE_DIRS = (
    "apps/",
    "aitbc/",
    "cli/",
    "contracts/",
    "packages/",
    "scripts/",
    "mcp-server/",
    "plugins/",
)

ROW = re.compile(r"^\|.*✅.*\|$")
TOKEN = re.compile(r"`([^`\s]{2,})`")


def code_haystack() -> str:
    """All tracked code files' contents, for token lookups."""
    files = subprocess.run(
        ["git", "ls-files", "--"] + list(CODE_DIRS),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    out = []
    for rel in files:
        try:
            out.append((ROOT / rel).read_text(errors="replace"))
        except OSError:
            pass
    return "\n".join(out)


def main() -> int:
    rows: list[tuple[str, int, str]] = []  # (file, lineno, row)
    for g in DOC_GLOBS:
        for f in sorted(ROOT.glob(g)):
            for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                if ROW.match(line):
                    rows.append((f.relative_to(ROOT).as_posix(), i, line))

    tokens_of = {r: TOKEN.findall(r[2]) for r in rows}
    unique = sorted({t for toks in tokens_of.values() for t in toks})
    haystack = code_haystack()
    resolved = {t for t in unique if t in haystack}

    failures: list[str] = []
    for (rel, _ln, row), toks in zip(rows, tokens_of.values(), strict=False):
        key = f"{rel}:{row.split('|')[1].strip()}"
        if not toks:
            failures.append(f"{key}  # no evidence token in row")
        elif not any(t in resolved for t in toks):
            failures.append(f"{key}  # dead token(s): {', '.join(toks)}")

    if "--write-baseline" in sys.argv:
        BASELINE.write_text("\n".join(failures) + ("\n" if failures else ""))
        print(f"wrote {len(failures)} unverifiable rows to {BASELINE}")
        return 0

    baseline = set()
    if BASELINE.exists():
        baseline = {ln.strip() for ln in BASELINE.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")}

    new = [f for f in failures if f not in baseline]
    fixed = sorted(baseline - set(failures))
    rc = 0
    for f in new:
        print(f"UNVERIFIED ✅ ROW: {f}")
        rc = 1
    for f in fixed:
        print(f"baseline row now verifiable (remove it): {f}")
    if not new:
        print(f"feature-status check clean — {len(baseline)} known unverifiable rows, {len(rows)} ✅ rows scanned")
    else:
        print("add a backticked code identifier (tx type / env var / command) to the row,")
        print("drop the ✅, or list it in the baseline with --write-baseline")
    return rc


if __name__ == "__main__":
    sys.exit(main())
