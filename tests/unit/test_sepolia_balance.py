"""Tests for scripts/ops/sepolia_balance.py (ETH-1).

A real loopback ``http.server`` stubs the JSON-RPC endpoint — no network,
no keys, no environment reads.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import sepolia_balance as sb  # noqa: E402

ADDR_A = "0x" + "11" * 20
ADDR_B = "0x" + "22" * 20


class _RpcStub(BaseHTTPRequestHandler):
    """Answers eth_getBalance / eth_getTransactionCount from a canned map."""

    responses: dict = {}
    seen: list = []
    seen_agents: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.__class__.seen.append(body)
        self.__class__.seen_agents.append(self.headers.get("User-Agent"))
        method = body["method"]
        key = (method, body["params"][0])
        result = self.__class__.responses.get(key, "0x0")
        payload = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):  # silence
        pass


@pytest.fixture()
def rpc_server():
    _RpcStub.responses = {
        ("eth_getBalance", ADDR_A): hex(2 * 10**18 + 5 * 10**17),  # 2.5 ETH
        ("eth_getTransactionCount", ADDR_A): "0x3",
        ("eth_getBalance", ADDR_B): "0x0",
        ("eth_getTransactionCount", ADDR_B): "0x0",
    }
    _RpcStub.seen = []
    _RpcStub.seen_agents = []
    server = HTTPServer(("127.0.0.1", 0), _RpcStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)


def test_balance_and_nonce_per_address(rpc_server):
    row = sb.query_address(rpc_server, ADDR_A)
    assert row["balance_wei"] == 2_500_000_000_000_000_000
    assert row["balance_eth"] == "2.5"
    assert row["nonce"] == 3


def test_both_calls_use_latest_block_tag(rpc_server):
    sb.query_address(rpc_server, ADDR_B)
    methods = {(c["method"], c["params"][1]) for c in _RpcStub.seen}
    assert methods == {
        ("eth_getBalance", "latest"),
        ("eth_getTransactionCount", "latest"),
    }


def test_sends_descriptive_user_agent(rpc_server):
    # public RPC endpoints 403 urllib's default "Python-urllib/*" agent
    sb.query_address(rpc_server, ADDR_B)
    assert _RpcStub.seen_agents
    assert all(agent == sb.USER_AGENT for agent in _RpcStub.seen_agents)
    assert not sb.USER_AGENT.startswith("Python-urllib")


def test_main_table_output(rpc_server, capsys):
    rc = sb.main(["--rpc-url", rpc_server, ADDR_A, ADDR_B])
    out = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert out[0] == f"{ADDR_A}  2.5 ETH  nonce=3"
    assert out[1] == f"{ADDR_B}  0 ETH  nonce=0"


def test_main_json_output(rpc_server, capsys):
    rc = sb.main(["--rpc-url", rpc_server, "--json", ADDR_A])
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert rows == [
        {
            "address": ADDR_A,
            "balance_wei": 2_500_000_000_000_000_000,
            "balance_eth": "2.5",
            "nonce": 3,
        }
    ]


def test_invalid_address_rejected_without_rpc_call(rpc_server, capsys):
    rc = sb.main(["--rpc-url", rpc_server, "not-an-address", ADDR_A])
    err = capsys.readouterr().err
    assert rc == 1
    assert "not-an-address" in err
    assert "not a 0x + 40-hex address" in err
    # only the valid address hit the wire
    assert all(c["params"][0] == ADDR_A for c in _RpcStub.seen)


def test_rpc_error_row_exits_1_but_others_print(rpc_server, capsys):
    class _ErrStub(_RpcStub):
        responses = {}
        seen = []

        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            raw = json.dumps({"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32000, "message": "boom"}}).encode()
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = HTTPServer(("127.0.0.1", 0), _ErrStub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        rc = sb.main(["--rpc-url", f"http://127.0.0.1:{server.server_port}", ADDR_A, ADDR_B])
    finally:
        server.shutdown()
    # both rows fail -> exit 1, error text carries the RPC message
    captured = capsys.readouterr()
    assert rc == 1
    assert "boom" in captured.err


def test_refuses_non_http_rpc_url():
    with pytest.raises(SystemExit) as excinfo:
        sb.main(["--rpc-url", "ftp://example", ADDR_A])
    assert "must be http(s)" in str(excinfo.value)
