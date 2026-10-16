"""Tests for `aitbc transactions search` — loopback HTTP stub only.

Covers flag parsing, the at-least-one-filter requirement, the RPC path
passing sender/recipient through to /rpc/transactions, and the explorer
path refusing filters it cannot honour.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

ADDR = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"


@pytest.fixture(name="stub")
def stub_fixture():
    state: dict[str, list] = {"queries": []}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlparse(self.path)
            state["queries"].append(parse_qs(u.query))
            if u.path == "/rpc/transactions":
                body = json.dumps([{"tx_hash": "0xabc", "sender": ADDR}]).encode()
            else:
                body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}", state
    srv.shutdown()
    t.join(2)


def invoke(stub, *args):
    from aitbc_cli.commands.transactions import transactions

    base, _ = stub
    return CliRunner().invoke(transactions, ["search", "--rpc-url", base, *args])


def test_requires_at_least_one_filter(stub):
    r = invoke(stub)
    assert r.exit_code != 0 or "at least one" in r.output
    assert stub[1]["queries"] == []


def test_sender_flag_reaches_rpc(stub):
    r = invoke(stub, "--sender", ADDR)
    assert r.exit_code == 0, r.output
    assert stub[1]["queries"][-1]["sender"] == [ADDR]
    assert "0xabc" in r.output


def test_recipient_and_address_combine(stub):
    r = invoke(stub, "--address", ADDR, "--recipient", ADDR)
    assert r.exit_code == 0, r.output
    q = stub[1]["queries"][-1]
    assert q["address"] == [ADDR]
    assert q["recipient"] == [ADDR]


def test_explorer_refuses_sender_filter(stub):
    r = invoke(stub, "--sender", ADDR, "--use-explorer")
    assert "cannot filter by sender or recipient" in r.output
    assert stub[1]["queries"] == []
