"""Pin for AUDIT-EDGE-MCP-EXPORT-WRITE (#2879).

``aitbc_blockchain_monitor`` and ``aitbc_monitor_metrics`` are
``read_only_hint=True`` tools, but their ``export``/``export_path`` params
forwarded ``--export <path>`` to the CLI, which runs ``open(path, 'w')``
as root over SSH — an arbitrary remote file write disguised as a read.
The params are removed; export stays available on the CLI itself and on
the gated (destructive_hint + dry_run/confirm) generated export tools.

Pure-AST pin: parses the shipped source so it gates the committed schema,
not an import-time view.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "aitbc_mcp_cli_tools.py"

# Params that let a caller aim a write at a remote filesystem path.
_FILE_WRITE_PARAMS = {"export", "export_path", "output_file", "output", "destination"}


def _read_only_tools(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Map function name -> node for every @mcp.tool(read_only_hint=True) def."""
    out: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not (isinstance(deco, ast.Call) and getattr(deco.func, "attr", "") == "tool"):
                continue
            for kw in deco.keywords:
                if kw.arg != "annotations" or not isinstance(kw.value, ast.Call):
                    continue
                if any(
                    k.arg == "read_only_hint" and isinstance(k.value, ast.Constant) and k.value.value is True
                    for k in kw.value.keywords
                ):
                    out[node.name] = node
    return out


def _param_names(node: ast.FunctionDef) -> set[str]:
    return {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}


def test_fixed_tools_have_no_file_write_params():
    tree = ast.parse(SRC.read_text())
    tools = _read_only_tools(tree)
    for name in ("aitbc_blockchain_monitor", "aitbc_monitor_metrics"):
        assert name in tools, f"{name} missing or no longer read_only_hint"
        leaked = _param_names(tools[name]) & _FILE_WRITE_PARAMS
        assert not leaked, f"{name} exposes file-write param(s) {leaked} on a read_only_hint tool"


def test_no_read_only_tool_exposes_file_write_params():
    """Sweep: the #2879 defect class must not exist on ANY read_only tool."""
    tree = ast.parse(SRC.read_text())
    offenders = {
        name: sorted(_param_names(node) & _FILE_WRITE_PARAMS)
        for name, node in _read_only_tools(tree).items()
        if _param_names(node) & _FILE_WRITE_PARAMS
    }
    assert offenders == {}, f"read_only tools with file-write params: {offenders}"
