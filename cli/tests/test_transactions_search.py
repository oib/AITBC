"""Tests for `aitbc transactions search` — loopback HTTP stub only.

Covers flag parsing, the at-least-one-filter requirement, the RPC path
passing sender/recipient through to /rpc/transactions, the explorer path
refusing filters it cannot honour, and the client-side verification that
keeps results correct against a node that has not been restarted since
the sender/recipient parameters landed (old nodes silently ignore them).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

ADDR = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"
OTHER = "0xcF171914819E9435aC5751D29c0DF313b10f8Ee3"


def _row(tx_hash: str, sender: str, recipient: str) -> dict:
    return {"tx_hash": tx_hash, "sender": sender, "recipient": recipient}


@pytest.fixture(name="stub")
def stub_fixture():
    state: dict[str, list] = {"queries": [], "rows": [_row("0xabc", ADDR, OTHER)]}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlparse(self.path)
            state["queries"].append(parse_qs(u.query))
            if u.path == "/rpc/transactions":
                # Old-node behaviour: ignore sender/recipient, return all rows.
                body = json.dumps(state["rows"]).encode()
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


def test_stale_node_rows_dropped_with_note(stub):
    # Node ignores the params and returns either-side rows (pre-restart behaviour).
    stub[1]["rows"] = [_row("0xsend", ADDR, OTHER), _row("0xrecv", OTHER, ADDR)]
    r = invoke(stub, "--sender", ADDR)
    assert r.exit_code == 0, r.output
    assert "0xsend" in r.output
    assert "0xrecv" not in r.output
    assert "did not match the filter" in r.output
    assert "limit" in r.output and "incomplete" in r.output


def test_current_node_rows_kept_without_note(stub):
    stub[1]["rows"] = [_row("0xsend", ADDR, OTHER)]
    r = invoke(stub, "--sender", ADDR)
    assert r.exit_code == 0, r.output
    assert "did not match the filter" not in r.output


def test_sender_filter_is_case_insensitive(stub):
    stub[1]["rows"] = [_row("0xsend", ADDR.lower(), OTHER)]
    r = invoke(stub, "--sender", ADDR)
    assert r.exit_code == 0, r.output
    assert "0xsend" in r.output
    assert "did not match the filter" not in r.output


def test_recipient_filter_drops_mismatches(stub):
    stub[1]["rows"] = [_row("0xsend", ADDR, OTHER), _row("0xrecv", OTHER, ADDR)]
    r = invoke(stub, "--recipient", ADDR)
    assert "0xrecv" in r.output
    assert "0xsend" not in r.output
    assert "did not match the filter" in r.output


def test_sender_and_recipient_together(stub):
    stub[1]["rows"] = [
        _row("0xa", ADDR, ADDR),
        _row("0xb", ADDR, OTHER),
        _row("0xc", OTHER, ADDR),
    ]
    r = invoke(stub, "--sender", ADDR, "--recipient", ADDR)
    assert "0xa" in r.output
    assert "0xb" not in r.output and "0xc" not in r.output
    assert "did not match the filter" in r.output
