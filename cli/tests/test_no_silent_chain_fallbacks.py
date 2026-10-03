"""Guard: no new ``ait-localnet`` literals in signing-capable code.

Task 5/8/10/12 made signing paths resolve the chain id explicitly
(--chain-id / CHAIN_ID / strict probe of the submit URL) instead of
silently defaulting to ``ait-localnet``. This test fails if a new literal
appears outside the allowlist, and fails if an allowlisted file no longer
contains the literal (stale entries must be removed, not left to rot).

Comments never reach the AST; docstrings and help/epilog option strings
are excluded by construction, so usage examples do not need allowlisting.
"""

from __future__ import annotations

import ast
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parents[1] / "aitbc_cli"
LITERAL = "ait-localnet"

# Keyword arguments whose values are display text, not behaviour.
_DISPLAY_KWARGS = {"help", "epilog", "description", "short_help"}

ALLOWLIST: dict[str, str] = {
    "config.py": "TODO: CLIConfig.chain_id and native_chain_id defaults feed signing callers",
    "commands/agent_sdk.py": "TODO: register/verify/submit fall back to ait-localnet on probe failure",
    "commands/operations.py": "TODO: ops signing paths fall back to ait-localnet on probe failure",
    "commands/wallet/basic.py": "TODO: read-only balance display default",
    "commands/market/__init__.py": "TODO: usage-example text inside an error() message, not a default",
    "core/analytics.py": "TODO: display/reporting defaults only",
    "utils/genesis_reset.py": "TODO: DEFAULT_CHAIN_ID for the reset tool",
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


def _occurrences() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted(CLI_ROOT.rglob("*.py")):
        rel = path.relative_to(CLI_ROOT).as_posix()
        tree = ast.parse(path.read_text(), filename=rel)
        skip = _docstring_ids(tree) | _display_kwarg_ids(tree)
        lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and LITERAL in node.value
            and id(node) not in skip
        ]
        if lines:
            found[rel] = lines
    return found


def test_no_new_ait_localnet_literals():
    found = _occurrences()
    violations = {path: lines for path, lines in found.items() if path not in ALLOWLIST}
    assert not violations, (
        "new 'ait-localnet' literal(s) outside the allowlist — resolve the "
        "chain id via resolve_chain_id(ctx, rpc_url) instead: "
        + "; ".join(f"{p}:{lines}" for p, lines in sorted(violations.items()))
    )


def test_allowlist_not_stale():
    found = _occurrences()
    stale = [path for path in ALLOWLIST if path not in found]
    assert not stale, (
        "allowlisted file(s) no longer contain 'ait-localnet' — remove the "
        f"allowlist entr{'y' if len(stale) == 1 else 'ies'}: {stale}"
    )
