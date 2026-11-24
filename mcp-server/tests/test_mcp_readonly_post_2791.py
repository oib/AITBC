"""AUDIT-EDGE pin: #2791 — POST tools must not carry read_only_hint.

Nine tools call _run_http(method='POST') directly, skipping
call_aitbc_http's GET-only confirm gate, yet were annotated
read_only_hint=True — MCP clients auto-approve them. State-changing or
expensive endpoints (zk proof generation up to 300s, liquidity/bridge
builds) were reachable with zero confirmation. They are now explicitly
read_only_hint=False.
"""

import ast
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parents[1]

_TARGETS = {
    "aitbc_mcp_zk_tools.py": ["generate_zk_proof", "verify_zk_proof", "verify_zk_job_receipt"],
    "aitbc_mcp_liquidity_tools.py": ["build_liquidity_deposit", "build_liquidity_withdraw", "build_liquidity_claim"],
    "aitbc_mcp_rpc_tools_bridge.py": [
        "get_eth_bridge_deposit_instructions",
        "eth_bridge_withdraw_estimate",
        "eth_bridge_withdraw_build",
    ],
}


def _decorator_for(path: Path, fn_name: str) -> str:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            for dec in node.decorator_list:
                return ast.get_source_segment(path.read_text(), dec) or ""
    raise AssertionError(f"{fn_name} not found in {path.name}")


def test_post_tools_are_not_read_only_hint() -> None:
    for filename, names in _TARGETS.items():
        path = MCP_SERVER_DIR / filename
        for name in names:
            dec = _decorator_for(path, name)
            assert "read_only_hint=True" not in dec, f"{name} still claims read-only on a POST endpoint"
            assert "read_only_hint=False" in dec, f"{name} should be explicitly read_only_hint=False"
