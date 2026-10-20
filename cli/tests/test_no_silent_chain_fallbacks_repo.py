"""Guard: no silent chain-id fallbacks in app sources and ops scripts.

Repo-wide sibling of ``test_no_silent_chain_fallbacks.py`` (which scans
``cli/aitbc_cli``). Same rules, wider scope:

- ``apps/*/src/**/*.py`` — every service's packaged source;
- ``apps/*/*.py`` — top-level app modules such as the blockchain
  explorer's ``main.py`` and ``chain_client.py``;
- ``scripts/**/*.py`` — ops and utility scripts.

It fails on, per file:

1. any ``ait-localnet`` string literal in executable position — comments
   never reach the AST, and docstrings plus help/description option
   strings are excluded, so usage examples do not trip it; and
2. any ``os.getenv("CHAIN_ID", <literal>)`` / ``os.environ.get("CHAIN_ID",
   <literal>)`` whose default is a *non-empty* string literal.

``ALLOWLIST`` maps each remaining file to ``(count, reason)``. It must
shrink to zero: entries are removed as their sites are resolved, and a
stale entry fails the test.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LITERAL = "ait-localnet"

_DISPLAY_KWARGS = {"help", "epilog", "description", "short_help"}

# (occurrence count, reason) — count must match exactly or the test fails.
ALLOWLIST: dict[str, tuple[int, str]] = {}


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            ids.add(id(body[0].value))
    return ids


def _display_kwarg_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in _DISPLAY_KWARGS:
            ids.update(id(sub) for sub in ast.walk(node.value))
    return ids


def _is_chain_id_getenv(node: ast.AST) -> ast.Constant | None:
    """Return the non-empty literal default of a ``getenv("CHAIN_ID", <lit>)`` call."""
    if not isinstance(node, ast.Call) or len(node.args) < 2 or not isinstance(node.func, ast.Attribute):
        return None
    func = node.func
    is_os_getenv = func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os"
    is_environ_get = (
        func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )
    if not (is_os_getenv or is_environ_get):
        return None
    first, default = node.args[0], node.args[1]
    if (
        isinstance(first, ast.Constant)
        and first.value == "CHAIN_ID"
        and isinstance(default, ast.Constant)
        and isinstance(default.value, str)
        and default.value != ""
    ):
        return default
    return None


def _scanned_paths() -> list[Path]:
    paths: list[Path] = []
    paths += REPO_ROOT.glob("apps/*/src/**/*.py")
    paths += REPO_ROOT.glob("apps/*/*.py")
    paths += REPO_ROOT.glob("scripts/**/*.py")
    return sorted(set(paths))


def _occurrences() -> dict[str, list[tuple[int, int]]]:
    """path -> sorted (line, col) of each silent chain-id fallback."""
    found: dict[str, list[tuple[int, int]]] = {}
    for path in _scanned_paths():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(), filename=rel)
        except SyntaxError:
            continue
        skip = _docstring_ids(tree) | _display_kwarg_ids(tree)
        positions: set[tuple[int, int]] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and LITERAL in node.value:
                if id(node) not in skip:
                    positions.add((node.lineno, node.col_offset))
            default = _is_chain_id_getenv(node)
            if default is not None:
                positions.add((default.lineno, default.col_offset))
        if positions:
            found[rel] = sorted(positions)
    return found


def test_no_new_silent_chain_fallbacks_repo():
    found = _occurrences()
    problems: list[str] = []
    for path, positions in sorted(found.items()):
        allowed = ALLOWLIST.get(path)
        if allowed is None:
            problems.append(f"{path}: {positions} — not allowlisted")
        elif len(positions) != allowed[0]:
            problems.append(f"{path}: {positions} — allowlist says {allowed[0]}")
    for path, (count, _reason) in ALLOWLIST.items():
        if path not in found:
            problems.append(f"{path}: allowlist entry stale (expected {count}, none found)")
    assert not problems, (
        "silent chain-id fallback(s) in app sources or scripts — resolve via "
        "aitbc.utils.chain_id.resolve_chain_id; or update ALLOWLIST if the "
        "change is deliberate: " + "; ".join(problems)
    )
