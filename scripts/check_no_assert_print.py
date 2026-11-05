#!/usr/bin/env python3
"""Static gate that fails on production `assert` and `print()` calls."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "ci" / "assert-print-baseline.txt"
# Directories that are never production service code. Compared against the
# path *relative to ROOT* — matching on absolute parts used to let a checkout
# living under e.g. /x/tests/ or /x/venv/ disable the whole gate.
SKIP_DIRS = {
    "tests",
    "test",
    "examples",
    "example",
    "scripts",
    "migrations",
    "alembic",
    "templates",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "site-packages",
    "node_modules",
    ".git",
    "data",
    "docs",
    "tasks",
    "contracts",
    "website",
    ".github",
    ".gitea",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _is_main_guard(node: ast.AST) -> bool:
    """Return True if node is ``if __name__ == "__main__":``."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


class _AssertPrintVisitor(ast.NodeVisitor):
    def __init__(self, *, allow_print_in_main: bool) -> None:
        self.allow_print_in_main = allow_print_in_main
        self.main_guard = False
        self.violations: list[tuple[int, str]] = []

    def visit_If(self, node: ast.If) -> None:
        if _is_main_guard(node):
            old = self.main_guard
            self.main_guard = True
            for stmt in node.body:
                self.visit(stmt)
            self.main_guard = old
            for stmt in node.orelse:
                self.visit(stmt)
        else:
            self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.violations.append((node.lineno, "assert"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            if not (self.allow_print_in_main and self.main_guard):
                self.violations.append((node.lineno, "print()"))
        self.generic_visit(node)


def _should_scan(rel: Path) -> bool:
    # Compare parts *relative to ROOT*: testing the absolute path meant a
    # checkout living under e.g. /x/tests/ or /x/venv/ scanned nothing at all.
    for part in rel.parts:
        if part in SKIP_DIRS:
            return False
    if rel.name.startswith("test_") or rel.name.startswith("tests_"):
        return False
    return rel.suffix == ".py"


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        try:
            rel_path = path.relative_to(ROOT)
        except ValueError:
            continue
        if _should_scan(rel_path):
            files.append(path)
    return sorted(files)


def _scan() -> tuple[dict[str, int], list[str]]:
    """Return (violations per file, error lines)."""
    per_file: dict[str, int] = {}
    errors: list[str] = []
    for path in _iter_python_files():
        try:
            tree = ast.parse(path.read_text(), str(path))
        except SyntaxError:
            errors.append(f"syntax error in {path}")
            continue
        visitor = _AssertPrintVisitor(allow_print_in_main=True)
        visitor.visit(tree)
        if visitor.violations:
            rel = path.relative_to(ROOT).as_posix()
            per_file[rel] = per_file.get(rel, 0) + len(visitor.violations)
    return per_file, errors


def _read_baseline() -> dict[str, int]:
    baseline: dict[str, int] = {}
    if not BASELINE.is_file():
        return baseline
    for line in BASELINE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        count_s, _, path = line.partition(" ")
        try:
            baseline[path.strip()] = int(count_s)
        except ValueError:
            continue
    return baseline


def main(argv: list[str]) -> int:
    if "--update" in argv:
        per_file, errors = _scan()
        for err in errors:
            print(err)
        lines = [f"{count:6d} {path}" for path, count in sorted(per_file.items())]
        BASELINE.write_text("\n".join(lines) + ("\n" if lines else ""))
        print(f"baseline updated: {BASELINE} ({sum(per_file.values())} violations in {len(per_file)} files)")
        return 1 if errors else 0

    per_file, errors = _scan()
    for err in errors:
        print(err)
    if errors:
        return 2

    baseline = _read_baseline()
    new_violations = {p: c for p, c in per_file.items() if c > baseline.get(p, 0)}
    if new_violations:
        total = 0
        for path in sorted(new_violations):
            count = per_file[path]
            allowed = baseline.get(path, 0)
            total += count - allowed
            print(f"{path}: {count} assert/print violation(s) (baseline allows {allowed})")
        print(f"Found {total} new production assert/print violation(s)")
        return 1

    remaining = sum(baseline.values()) - sum(min(c, baseline[p]) for p, c in per_file.items() if p in baseline)
    print(f"OK: no new assert/print violations ({sum(per_file.values())} known, baseline {remaining} stale entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
