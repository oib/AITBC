"""Guard: no new silent chain-id fallbacks in aitbc_cli.

Signing paths resolve the chain id explicitly (--chain-id / CHAIN_ID /
strict probe of the submit URL) via ``resolve_chain_id`` instead of
silently defaulting. This test scans ``cli/aitbc_cli/**/*.py`` with ast
and fails on, per file:

1. any ``ait-localnet`` string literal in executable position — comments
   never reach the AST, and docstrings plus help/epilog option strings are
   excluded, so usage examples do not trip it; and
2. any ``os.getenv("CHAIN_ID", <literal>)`` / ``os.environ.get("CHAIN_ID",
   <literal>)`` whose default is a *non-empty* string literal — a silent
   non-empty default makes strict probing unreachable regardless of what
   the literal says. A ``""`` default (or no default) is allowed: an empty
   value cannot sign a transaction for a chain nobody serves.

``ALLOWLIST`` maps each file to ``(count, reason)``: the exact number of
occurrences it currently holds. A new occurrence fails; a *reduced* count
also fails (stale entries must shrink to zero and be removed, not rot).

Not covered — do not mistake this for a complete check: reads of
``config.chain_id`` / ``config.native_chain_id`` (the fields' defaults are
allowlisted here, but nothing stops a new signing caller from reading
them), and ``expected_chain_id=`` quote-binding arguments in energy/gpu
quote verification, which fail closed rather than signing wrongly.
"""

from __future__ import annotations

import ast
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parents[1] / "aitbc_cli"
LITERAL = "ait-localnet"

# Keyword arguments whose values are display text, not behaviour.
_DISPLAY_KWARGS = {"help", "epilog", "description", "short_help"}

# (occurrence count, reason) — count must match exactly or the test fails.
ALLOWLIST: dict[str, tuple[int, str]] = {
    "config.py": (2, "TODO: CLIConfig.chain_id and native_chain_id defaults feed signing callers"),
    "core/analytics.py": (3, "TODO: display/reporting defaults only"),
    "utils/genesis_reset.py": (1, "TODO: DEFAULT_CHAIN_ID for the reset tool"),
    "commands/wallet/basic.py": (1, "TODO: read-only balance display default"),
    "commands/market/__init__.py": (1, "TODO: usage-example text inside an error() message, not a default"),
}


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


def _occurrences() -> dict[str, list[tuple[int, int]]]:
    """path -> sorted (line, col) of each silent chain-id fallback."""
    found: dict[str, list[tuple[int, int]]] = {}
    for path in sorted(CLI_ROOT.rglob("*.py")):
        rel = path.relative_to(CLI_ROOT).as_posix()
        tree = ast.parse(path.read_text(), filename=rel)
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


def test_no_new_silent_chain_fallbacks():
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
        "silent chain-id fallback(s) changed — resolve via "
        "resolve_chain_id(ctx, rpc_url); or update ALLOWLIST if the change is "
        "deliberate: " + "; ".join(problems)
    )
