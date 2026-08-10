#!/usr/bin/env python3
"""Fail when a directory's package-manager artifacts disagree with each other.

V23-27a was CI auditing a lockfile it never installed from. `contracts/` tracked
`package-lock.json`, but the workflows ran `pnpm install`, which ignored it, resolved fresh
every run, and installed a tree no lockfile described. `npm audit` measured the tracked file;
the tree under test was something else. The advisory counts were real numbers about the wrong
tree.

V23-28 fixed the workflows it found and wrote the reasoning into `contracts/.npmrc`. What it
could not fix is the shape of the mistake, which is that **the evidence is invisible**. A
stray `pnpm-lock.yaml` sitting in `contracts/` is untracked, so `git status` is the only thing
that shows it, and for most of this repo's history a blanket `*.yaml` rule in `.gitignore`
hid it from even that -- V23-28 found the file exactly that way. Nothing failed. Nothing
could fail.

So this check walks the **working tree**, not `git ls-files`. An ignored or untracked
lockfile is precisely the case worth catching; a check that only reads tracked files would
have passed on every day of the window that produced V23-27a.

Three rules, all of them about a directory contradicting itself:

1. Two package managers' artifacts in one directory. Whichever one CI runs, the other
   lockfile is a description of a tree nobody installs -- and it is the one auditors read.
2. A lockfile that contradicts the directory's own `packageManager` field. `contracts/`
   declares `npm@11.16.0`; a `pnpm-lock.yaml` there is a second opinion with no owner.
3. A `pnpm-workspace.yaml` underneath another one. pnpm resolves its workspace root by
   walking *up* to the nearest `pnpm-workspace.yaml`, so a nested file silently demotes the
   real root: `packages/web/` carried one, and `pnpm install` there built `web` as a
   standalone root with an `overrides` shim instead of as a member of `packages/`. Same
   defect as the other two -- an install that succeeds while describing the wrong tree.

Run with `--list` to print what was found without failing, which is the honest way to check
that the rules still match reality after a directory changes package managers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Artifacts that name the package manager that produced them. `pnpm-workspace.yaml` counts:
# it is pnpm-only configuration, and in pnpm 10+ it is where `overrides` and build allowances
# live, so its presence in an npm directory is a claim that pnpm runs there.
ARTIFACT_MANAGERS = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "pnpm-workspace.yaml": "pnpm",
    "yarn.lock": "yarn",
    "bun.lockb": "bun",
    "bun.lock": "bun",
}

# Trees that are not this repository's source: vendored dependencies, nested repo copies, and
# generated output. CLAUDE.md's search-scope guard names most of these for the same reason.
SKIP_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "graphify-out",
    "tmp",
    "__pycache__",
    "artifacts",
    "cache",
}

# Relative paths pruned wholesale: the worktree pool is a set of nested checkouts, and
# harness/claude is the inert shipped-harness source, not code that runs here.
SKIP_PATHS = {
    Path(".claude/worktrees"),
    Path("harness/claude"),
}


def _walk_dirs(root: Path):
    """Yield every source directory under root, pruning vendored and generated trees."""
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        rel = here.relative_to(root)

        if any(rel == skip or skip in rel.parents for skip in SKIP_PATHS):
            dirnames[:] = []
            continue

        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        yield rel, set(filenames)


def _declared_manager(directory: Path) -> str | None:
    """Return the manager named by package.json's `packageManager`, if it declares one."""
    manifest = directory / "package.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    declared = data.get("packageManager")
    if not isinstance(declared, str) or not declared:
        return None
    # "npm@11.16.0" -> "npm"; a leading @ would mean a scoped name, which is not a manager.
    return declared.lstrip("@").split("@", 1)[0] or None


def _collect(root: Path) -> tuple[dict[Path, dict[str, str]], list[Path]]:
    """Return per-directory {artifact: manager} plus every directory holding a pnpm workspace."""
    found: dict[Path, dict[str, str]] = {}
    workspaces: list[Path] = []

    for rel, filenames in _walk_dirs(root):
        artifacts = {name: ARTIFACT_MANAGERS[name] for name in sorted(filenames) if name in ARTIFACT_MANAGERS}
        if artifacts:
            found[rel] = artifacts
        if "pnpm-workspace.yaml" in filenames:
            workspaces.append(rel)

    return found, workspaces


def _describe(rel: Path, artifacts: dict[str, str]) -> str:
    prefix = "" if str(rel) == "." else f"{rel}/"
    return ", ".join(f"{prefix}{name} ({manager})" for name, manager in artifacts.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check package-manager artifacts for disagreement.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to scan (default: repo root)")
    parser.add_argument("--list", action="store_true", help="print what was found and exit 0")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    found, workspaces = _collect(root)

    if args.list:
        for rel in sorted(found):
            declared = _declared_manager(root / rel) or "-"
            print(f"{rel}/  declares={declared}  {_describe(rel, found[rel])}")
        return 0

    problems: list[str] = []

    for rel in sorted(found):
        artifacts = found[rel]
        managers = set(artifacts.values())
        declared = _declared_manager(root / rel)

        if len(managers) > 1:
            problems.append(
                f"{rel}/: artifacts from {len(managers)} package managers -- {_describe(rel, artifacts)}\n"
                f"    Only one of these describes the tree that gets installed. The others are\n"
                f"    unowned second opinions, and audits read whichever they find first."
            )
        elif declared and declared not in managers:
            stray = _describe(rel, artifacts)
            problems.append(
                f"{rel}/: package.json declares packageManager={declared}, but the directory holds {stray}\n"
                f"    Install with {declared}, or change the declaration -- not both."
            )

    for rel in sorted(workspaces):
        ancestors = [other for other in workspaces if other != rel and other in rel.parents]
        if ancestors:
            outer = sorted(ancestors)[-1]
            problems.append(
                f"{rel}/pnpm-workspace.yaml: nested inside the workspace rooted at {outer}/\n"
                f"    pnpm walks up to the nearest pnpm-workspace.yaml, so running pnpm in\n"
                f"    {rel}/ builds it as a standalone root and ignores {outer}/pnpm-lock.yaml."
            )

    if problems:
        print("Package-manager artifacts disagree:\n")
        for problem in problems:
            print(f"  {problem}\n")
        print(
            "  This is the V23-27a shape: an install that succeeds while describing a tree\n"
            "  nobody runs. Delete the artifacts belonging to the manager this directory does\n"
            "  not use -- see contracts/.npmrc for how that was settled there.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
