"""Pin for AUDIT-EDGE-MCP-SHOW-SECRETS (#2880), MCP half.

``aitbc_system_config`` was ``read_only_hint=True`` yet exposed
``show_secrets`` — one flag turned the tool into a raw env-secret dump
with no dry_run/confirm. The param is removed; ``aitbc system config
--show-secrets`` remains a direct-CLI operator action only.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "aitbc_mcp_cli_tools.py"


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def _param_names(node: ast.FunctionDef) -> set[str]:
    return {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}


def test_system_config_has_no_show_secrets_param():
    node = _function(ast.parse(SRC.read_text()), "aitbc_system_config")
    params = _param_names(node)
    assert "show_secrets" not in params
    assert "show-secrets" not in params
    # And the body must not forward the flag either.
    body = ast.dump(node)
    assert "show-secrets" not in body and "show_secrets" not in body
