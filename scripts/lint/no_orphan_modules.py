#!/usr/bin/env python3
"""Guard against modules that nothing imports.

V23-102 deleted ``MarketplaceMonitor``: 280 lines of alerting that no code path could
reach, holding a module-level singleton whose ``start()`` nobody called. Deleting it
answered one module and left the class of defect untouched -- at the time of writing, 22
modules totalling 6,895 lines under ``coordinator_api`` are imported by nothing anywhere
in this repository, tests included.

Unreachable code is not free. It is read during review, searched during debugging, and
counted by every "how big is this service" question. Worse, it is *plausible*: an orphan
looks exactly like working code, so a reader who finds ``MarketplaceMonitor`` reasonably
concludes marketplace alerting exists. It did not. The alerting that shipped lived in
``MetricsCollector``, and the two disagreed about what the thresholds even meant.

**This guard does not delete anything.** It fails when a *new* orphan appears, and records
today's set in ``no_orphan_modules_baseline.json`` so that inherited debt does not turn the
tree red. The baseline may shrink and must never grow. Each entry carries a ``verdict``
saying what should happen to it, because "nothing imports it" is a reason to look, not a
reason to delete -- ``fhe_enhanced.py`` is an orphan on purpose, a stub recording that the
BFV implementation it replaced was not cryptographically secure, and deleting it would
erase a deliberate security decision.

**Why the number moves depending on who counts.** Three strictness levels are defensible
and they disagree badly:

* *Any mention anywhere* (grep the tree for the module name) is the most conservative and
  the most wrong. It counts ``modality_optimization`` as reachable because the string
  appears as a dict key in ``monitoring_dashboard.py``, and ``advanced_analytics`` because
  it appears in a privileges list. Neither is an import; neither module can execute.
* *Import graph within one package* misses cross-app imports and over-reports.
* *Import graph across every tracked file* is the one implemented here.

The importer set deliberately includes tests, examples and scripts, even though none of
them are candidates for the guard. A module reachable only from a test is still reachable,
and reporting it here would nominate for deletion the very code a test depends on.

**Known blind spot.** Imports built at runtime -- ``importlib.import_module`` on a computed
name, a ``"module:attr"`` string handed to a plugin loader -- are invisible to an AST walk.
The one dynamic shim in coordinator-api, ``services/__init__.py``, was read by hand while
writing this: it is a lazy ``__getattr__`` over a fixed four-entry map, and none of the
four are orphans. Matching module names against string literals was tried and abandoned;
it is what makes the "any mention anywhere" count wrong, and it silently exempts exactly
the modules most worth reporting. If a genuine dynamic import is added, baseline it with a
verdict that says so rather than loosening the parser.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess  # nosec B404 - used only to list tracked files via git
import sys

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).resolve().parent / "no_orphan_modules_baseline.json"

# Trees that are vendored, generated or otherwise not ours to police.
SKIP_PARTS = (
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "site-packages",
    "build",
    "dist",
    ".mypy_cache",
    "graphify-out",
)

# Where the guard looks for orphans. Everything tracked is read to build the import graph;
# only files under these prefixes can be *reported*. Kept narrow on purpose: this started
# as a coordinator-api finding, and a guard that lights up 300 entries on day one gets an
# --update-baseline and is never looked at again.
GUARDED_ROOTS = ("apps/coordinator-api/src/coordinator_api/",)

# Modules that are entrypoints by design. Nothing imports a ``main.py``; a process starts
# it. Reporting these would be reporting the architecture, not a defect.
ENTRYPOINT_NAMES = frozenset(
    {
        "__init__.py",
        "__main__.py",
        "main.py",
        "app.py",
        "conftest.py",
        "setup.py",
        "asgi.py",
        "wsgi.py",
        "env.py",  # alembic
    }
)

# Directory names whose contents are run, not imported.
ENTRYPOINT_DIR_NAMES = frozenset({"migrations", "versions", "alembic", "scripts", "bin"})

# Directories that are not candidates but *are* importers.
NON_CANDIDATE_DIR_NAMES = frozenset({"tests", "test", "examples"})


def _tracked_python_files() -> list[Path]:
    """Every tracked ``.py`` file, minus vendored trees.

    Uses ``git ls-files`` so the walk respects ``.gitignore`` -- ``apps/coordinator-api``
    carries its own ``.venv``, and walking it pulls in pip's vendored packages.
    """
    result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", "ls-files", "-z", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    files = []
    for rel in result.stdout.split("\0"):
        if not rel:
            continue
        if any(p in SKIP_PARTS for p in Path(rel).parts):
            continue
        files.append(Path(rel))
    return sorted(files)


def _imported_module_names(path: Path) -> set[str]:
    """Every module name this file could be importing, as bare identifiers.

    Dotted paths are exploded into their parts and ``from x import y`` contributes ``y``
    as well as ``x``, because ``from .services import marketplace`` imports a *module*
    named ``marketplace`` while ``from .services.marketplace import Svc`` imports a class.
    One set covers both without having to resolve the package graph, at the cost of some
    over-matching -- which errs toward calling a module reachable, the safe direction for
    a guard whose output is a deletion candidate list.
    """
    try:
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        # ``git ls-files`` reads the index, so a file deleted in the working tree but not
        # yet staged is still listed. The same crash took down no_float_money.py in
        # V23-102 on a routine deletion. It matters more here: deleting orphans is the
        # workflow this guard exists to encourage, so the hook must survive the exact
        # moment the user acts on it.
        return set()
    except (UnicodeDecodeError, SyntaxError, ValueError):
        return set()

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                names.update(node.module.split("."))
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))
    return names


def _is_candidate(path: Path) -> bool:
    """True when this file is one the guard is allowed to report."""
    posix = path.as_posix()
    if not any(posix.startswith(root) for root in GUARDED_ROOTS):
        return False
    parts = path.parts
    if any(p in NON_CANDIDATE_DIR_NAMES for p in parts):
        return False
    if any(p in ENTRYPOINT_DIR_NAMES for p in parts):
        return False
    return path.name not in ENTRYPOINT_NAMES


def _line_count(path: Path) -> int:
    try:
        return len((REPO_ROOT / path).read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def _scan() -> dict[str, int]:
    """Guarded modules whose stem appears in no other file's imports, with line counts."""
    files = _tracked_python_files()

    imported: set[str] = set()
    candidates: list[Path] = []
    for path in files:
        if _is_candidate(path):
            candidates.append(path)

    candidate_paths = {p.as_posix() for p in candidates}
    for path in files:
        # A module importing itself does not make it reachable. Nothing in this tree does
        # that today, but a self-import would otherwise hide an orphan permanently.
        if path.as_posix() in candidate_paths:
            others = _imported_module_names(path) - {path.stem}
        else:
            others = _imported_module_names(path)
        imported |= others

    return {p.as_posix(): _line_count(p) for p in candidates if p.stem not in imported}


def _load_baseline() -> dict[str, dict]:
    if not BASELINE_PATH.exists():
        return {}
    with BASELINE_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return dict(data.get("orphans", {}))


def _write_baseline(found: dict[str, int]) -> None:
    """Rewrite the baseline, preserving any verdict already recorded for a path."""
    existing = _load_baseline()
    orphans = {}
    for path in sorted(found):
        entry = {"lines": found[path]}
        prior = existing.get(path, {})
        entry["verdict"] = prior.get("verdict", "unreviewed")
        if prior.get("why"):
            entry["why"] = prior["why"]
        orphans[path] = entry

    payload = {
        "_comment": (
            "Modules under the guarded roots that nothing in this repository imports, "
            "recorded so the guard fails only on new ones. This list may shrink and must "
            "never grow. Regenerate after deleting something with: "
            "python scripts/lint/no_orphan_modules.py --update-baseline. "
            "'verdict' is the reviewed decision for each entry -- 'delete' means it is "
            "queued for removal, 'keep' means it is unreachable on purpose and 'why' says "
            "why. An entry is debt with a number attached, not an accepted state."
        ),
        "total_modules": len(orphans),
        "total_lines": sum(found.values()),
        "orphans": orphans,
    }
    with BASELINE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to match the tree. Use after deleting an orphan.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the current orphan set with line counts and exit 0.",
    )
    args = parser.parse_args()

    found = _scan()

    if args.list:
        for path, lines in sorted(found.items(), key=lambda kv: -kv[1]):
            print(f"{lines:6d}  {path}")
        print(f"\n{len(found)} modules, {sum(found.values())} lines")
        return 0

    if args.update_baseline:
        _write_baseline(found)
        print(f"baseline updated: {len(found)} orphan modules, {sum(found.values())} lines")
        return 0

    baseline = _load_baseline()
    new = sorted(set(found) - set(baseline))
    gone = sorted(set(baseline) - set(found))

    if new:
        print("modules that nothing in this repository imports:\n", file=sys.stderr)
        for path in new:
            print(f"  {found[path]:6d} lines  {path}", file=sys.stderr)
        print(
            "\nAn unreachable module is indistinguishable from a working one until someone "
            "traces its callers, so it will be read, searched and trusted. Either wire it "
            "up, delete it, or -- if it is unreachable on purpose, as a stub or an "
            "outward-facing SDK surface -- record it with a verdict:\n"
            "  python scripts/lint/no_orphan_modules.py --update-baseline",
            file=sys.stderr,
        )
        return 1

    if gone:
        # Not a failure: deleting an orphan must never turn the tree red. But a loose
        # baseline is how a shrink-only guard rots back into a decoration.
        print(f"{len(gone)} baselined orphan(s) no longer present. Tighten the baseline:")
        print("  python scripts/lint/no_orphan_modules.py --update-baseline")
        for path in gone[:10]:
            print(f"  gone: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
