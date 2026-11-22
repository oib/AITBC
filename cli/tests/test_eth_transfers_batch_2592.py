"""#2592: `aitbc eth transfers` batch must (a) continue past one wallet's
explorer failure — rc=1 at the end, other wallets still output+logged —
and (b) exclude rows from a nonce-mismatched wallet from the log.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

ADDR1 = "0x" + "11" * 20
ADDR2 = "0x" + "22" * 20
SEPOLIA = hex(11155111)


def _tx(hash_, frm, to, value, *, status="ok", nonce=0, block=1000):
    return {
        "hash": hash_,
        "nonce": nonce,
        "block_number": block,
        "timestamp": "2026-10-13T10:00:00.000000Z",
        "status": status,
        "value": str(value),
        "gas_used": "21000",
        "gas_price": str(10**9),
        "method": "transfer",
        "from": {"hash": frm},
        "to": {"hash": to} if to else None,
    }


def make_state():
    return {
        # explorer-down wallets: their /api/v2 paths 404 -> ExplorerError
        "down": set(),
        "wallets": {
            ADDR1.lower(): {
                "txs_to": [_tx("0xaaa", "0x" + "99" * 20, ADDR1, 10**18)],
                "txs_from": [],
                "internal": [],
                "nonce": 0,
                "balance": 10**18,
            },
            ADDR2.lower(): {
                "txs_to": [],
                "txs_from": [_tx("0xbbb", ADDR2, "0x" + "88" * 20, 5 * 10**17, nonce=0)],
                "internal": [],
                "nonce": 1,
                "balance": 5 * 10**17,
            },
        },
    }


def _wallet_for(state, addr):
    return state["wallets"].get(addr.lower(), {"txs_to": [], "txs_from": [], "internal": [], "nonce": 0, "balance": 0})


def _route_get(state, path):
    u = urlparse(path)
    addr = None
    for part in u.path.split("/"):
        if part.startswith("0x") and len(part) == 42:
            addr = part.lower()
            break
    if addr is None or addr in state["down"]:
        return None  # -> 404
    w = _wallet_for(state, addr)
    if "/internal-transactions" in u.path:
        return {"items": w["internal"], "next_page_params": None}
    if "/transactions" in u.path:
        direction = parse_qs(u.query).get("filter", ["to"])[0]
        return {"items": w[f"txs_{direction}"], "next_page_params": None}
    return None


def _route_post(state, req):
    m, p = req.get("method"), req.get("params") or []
    addr = str(p[0]).lower() if p else ""
    w = _wallet_for(state, addr)
    if m == "eth_chainId":
        result = SEPOLIA
    elif m == "eth_getTransactionCount":
        result = hex(w["nonce"])
    elif m == "eth_getBalance":
        result = hex(w["balance"])
    else:
        return {"jsonrpc": "2.0", "id": req.get("id"), "error": {"message": "unsupported"}}
    return {"jsonrpc": "2.0", "id": req.get("id"), "result": result}


@pytest.fixture
def stub():
    state = make_state()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            obj = _route_get(state, self.path)
            if obj is None:
                self.send_response(404)
                self.end_headers()
            else:
                self._send(obj)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            self._send(_route_post(state, req))

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}", state
    srv.shutdown()
    t.join(2)


def invoke(stub, *args):
    from aitbc_cli.commands.eth import eth

    base, _ = stub
    return CliRunner().invoke(eth, ["transfers", "--explorer-url", base, "--rpc-url", base, *args])


def test_one_wallet_explorer_failure_continues_batch(stub, tmp_path):
    base, st = stub
    st["down"].add(ADDR1.lower())
    log = str(tmp_path / "t.jsonl")
    r = invoke(stub, ADDR1, ADDR2, "--log", log)
    assert r.exit_code == 1
    # the healthy wallet's rows still made it to output and the log
    assert "0xbbb" in r.output
    lines = [json.loads(line) for line in open(log)]
    assert any(row["tx_hash"] == "0xbbb" for row in lines)
    assert not any(row["tx_hash"] == "0xaaa" for row in lines)


def test_nonce_mismatch_excludes_rows_from_log(stub, tmp_path):
    base, st = stub
    # ADDR2 shows 1 outgoing tx but RPC nonce is 1 — consistent.
    # Force a mismatch: explorer shows 1 out tx, nonce says 5.
    st["wallets"][ADDR2.lower()]["nonce"] = 5
    log = str(tmp_path / "t.jsonl")
    r = invoke(stub, ADDR1, ADDR2, "--log", log)
    assert r.exit_code == 1
    assert "nonce" in r.output.lower()
    # ADDR1 (consistent, incoming only, nonce 0 == 0 out) still logged;
    # ADDR2's outgoing row must NOT be in the log.
    lines = [json.loads(line) for line in open(log)] if __import__("os").path.exists(log) else []
    assert not any(row["tx_hash"] == "0xbbb" for row in lines)
    assert any(row["tx_hash"] == "0xaaa" for row in lines)
