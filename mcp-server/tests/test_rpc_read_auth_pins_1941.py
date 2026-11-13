"""#1941 pins: post-#1936 gated /rpc reads must send auth="rpc".

The operational-read gating (verify_rpc_peer_key) 403s callers that send no
X-API-Key. These tools hit gated routes, so _http_read_tool must forward
``auth="rpc"`` to _run_http — a silent revert re-breaks them with no test
signal otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server
import aitbc_mcp_rpc_tools as rpc_tools
import aitbc_mcp_chain_tools as chain_tools

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


def test_gpu_allocations_sends_rpc_auth():
    captured, fake = _capture_auth()
    orig = mcp_server._run_http
    mcp_server._run_http = fake
    try:
        rpc_tools.get_gpu_allocations(gpu_id="gpu-1", host="hub")
    finally:
        mcp_server._run_http = orig
    assert captured["service"] == "blockchain-rpc"
    assert captured["path"] == "gpu/allocations/gpu-1"
    assert captured["auth"] == "rpc"


def test_edge_info_sends_rpc_auth():
    captured, fake = _capture_auth()
    orig = mcp_server._run_http
    mcp_server._run_http = fake
    try:
        rpc_tools.get_edge_info(node_id="edge-1", host="hub")
    finally:
        mcp_server._run_http = orig
    assert captured["path"] == "edge/info/edge-1"
    assert captured["auth"] == "rpc"


def test_ai_service_stats_sends_rpc_auth():
    captured, fake = _capture_auth()
    orig = mcp_server._run_http
    mcp_server._run_http = fake
    try:
        rpc_tools.get_ai_service_stats(host="hub")
    finally:
        mcp_server._run_http = orig
    assert captured["path"] == "ai/stats"
    assert captured["auth"] == "rpc"


def test_list_ai_jobs_onchain_sends_rpc_auth():
    captured, fake = _capture_auth()
    orig = mcp_server._run_http
    mcp_server._run_http = fake
    try:
        chain_tools.list_ai_jobs_onchain(host="hub")
    finally:
        mcp_server._run_http = orig
    assert captured["path"] == "ai/jobs"
    assert captured["auth"] == "rpc"


def test_get_ai_job_onchain_sends_rpc_auth():
    captured, fake = _capture_auth()
    orig = mcp_server._run_http
    mcp_server._run_http = fake
    try:
        chain_tools.get_ai_job_onchain(job_id="job-1", host="hub")
    finally:
        mcp_server._run_http = orig
    assert captured["path"] == "ai/job/job-1"
    assert captured["auth"] == "rpc"
