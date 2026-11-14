"""#1953 / #1941: parametrized regression pins for post-#1936 gated /rpc reads.

Operational-read gating (verify_rpc_peer_key) returns 403 without X-API-Key.
These MCP tools must pass ``auth="rpc"`` through _http_read_tool to _run_http.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server
import aitbc_mcp_chain_tools as chain_tools
import aitbc_mcp_rpc_tools as rpc_tools

mcp_server._HOSTS_CONFIG = {
    "roles": {"hub": "hub", "customer": "node0", "shop": "node2"},
    "default_host": "hub",
    "ssh_user": "",
}


def _capture_auth():
    captured: dict[str, object] = {}

    def fake(target, service, path, method, params, body, timeout, auth="none"):
        captured.update({"service": service, "path": path, "auth": auth})
        return json.dumps({"ok": True})

    return captured, fake


@pytest.mark.parametrize(
    "tool,kwargs,expected_path",
    [
        (rpc_tools.get_gpu_allocations, {"gpu_id": "gpu-1", "host": "hub"}, "gpu/allocations/gpu-1"),
        (rpc_tools.get_edge_info, {"node_id": "edge-1", "host": "hub"}, "edge/info/edge-1"),
        (rpc_tools.get_ai_service_stats, {"host": "hub"}, "ai/stats"),
        (chain_tools.list_ai_jobs_onchain, {"host": "hub"}, "ai/jobs"),
        (chain_tools.get_ai_job_onchain, {"job_id": "job-1", "host": "hub"}, "ai/job/job-1"),
    ],
    ids=[
        "get_gpu_allocations",
        "get_edge_info",
        "get_ai_service_stats",
        "list_ai_jobs_onchain",
        "get_ai_job_onchain",
    ],
)
def test_mcp_gated_read_passes_auth_rpc_to_run_http(
    tool: Callable[..., Any],
    kwargs: dict[str, str],
    expected_path: str,
) -> None:
    captured, fake = _capture_auth()
    orig = mcp_server._run_http
    mcp_server._run_http = fake
    try:
        tool(**kwargs)
    finally:
        mcp_server._run_http = orig
    assert captured["service"] == "blockchain-rpc"
    assert captured["path"] == expected_path
    assert captured["auth"] == "rpc"
