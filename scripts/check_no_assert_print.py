#!/usr/bin/env python3
"""Static gate that fails on production `assert` and `print()` calls."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["aitbc", "apps", "cli", "aitbc/agent_bridge/src"]
SKIP_DIRS = {
    "tests",
    "examples",
    "scripts",
    "migrations",
    "alembic",
    "templates",
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
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


def _should_scan(path: Path) -> bool:
    parts = path.parts
    for part in parts:
        if part in SKIP_DIRS:
            return False
    if path.name.startswith("test_") or path.name.startswith("tests_"):
        return False
    return path.suffix == ".py"


def main() -> int:
    found = 0
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if not _should_scan(path):
                continue
            try:
                tree = ast.parse(path.read_text(), str(path))
            except SyntaxError:
                print(f"syntax error in {path}")
                return 2
            visitor = _AssertPrintVisitor(allow_print_in_main=True)
            visitor.visit(tree)
            for lineno, kind in visitor.violations:
                print(f"{path}:{lineno}: {kind}")
                found += 1
    if found:
        print(f"Found {found} production assert/print violation(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
