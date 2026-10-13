"""
Tests for `aitbc eth transfers` — loopback HTTP stubs only.

No network, no keys, no wallet files: a threaded http.server on
127.0.0.1 plays both the Blockscout API (GET /api/v2/...) and the
JSON-RPC endpoint (POST /). Covers pagination, re-run dedupe, the
nonce cross-check, the Sepolia-only refusal, internal transfers, and
failed-transaction gas accounting.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

ADDR = "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"
OTHER = "0x09362894C18f7CbCdb85b124ef4c8F63DEC09B32"
SEPOLIA = hex(11155111)


def _tx(
    hash_: str,
    frm: str,
    to: str | None,
    value: int,
    *,
    status="ok",
    nonce=0,
    block=1000,
    gas_used=21000,
    gas_price=10**9,
    method="transfer",
    ts="2026-10-13T10:00:00.000000Z",
    created=None,
):
    return {
        "hash": hash_,
        "nonce": nonce,
        "block_number": block,
        "timestamp": ts,
        "status": status,
        "value": str(value),
        "gas_used": str(gas_used),
        "gas_price": str(gas_price),
        "method": method,
        "from": {"hash": frm},
        "to": {"hash": to} if to else None,
        "created_contract": {"hash": created} if created else None,
    }


def _internal(tx_hash: str, frm: str, to: str, value: int, *, index=0, success=True):
    return {
        "transaction_hash": tx_hash,
        "index": index,
        "type": "call",
        "value": str(value),
        "success": success,
        "block": 1000,
        "timestamp": "2026-10-13T10:00:01.000000Z",
        "from": {"hash": frm},
        "to": {"hash": to},
    }


def _route_get(state, path):
    """Explorer API responses for one GET, or None -> 404."""
    u = urlparse(path)
    q = parse_qs(u.query)
    if "/internal-transactions" in u.path:
        return {"items": state["internal"], "next_page_params": None}
    if "/transactions" not in u.path:
        return None
    direction = q.get("filter", ["to"])[0]
    pool = state["txs_to"] if direction == "to" else state["txs_from"]
    if state["paged"] and "cursor" not in q:
        return {"items": pool[:1], "next_page_params": {"cursor": "2"}}
    return {"items": pool[1:] if state["paged"] else pool, "next_page_params": None}


def _route_post(state, req):
    """JSON-RPC response for one POST."""
    m, p = req.get("method"), req.get("params") or []
    result = None
    if m == "eth_chainId":
        result = state["chain_id"]
    elif m == "eth_getTransactionCount":
        result = hex(state["nonces"].get(str(p[0]).lower(), 0))
    elif m == "eth_getBalance":
        result = hex(state["balances"].get(str(p[0]).lower(), 0))
    if result is None:
        return {"jsonrpc": "2.0", "id": req.get("id"), "error": {"message": "unsupported"}}
    return {"jsonrpc": "2.0", "id": req.get("id"), "result": result}


def make_state(**kw):
    state = {
        "chain_id": SEPOLIA,
        "nonces": {ADDR.lower(): 0},
        "balances": {ADDR.lower(): 0},
        "txs_to": [],
        "txs_from": [],
        "internal": [],
        "paged": False,
    }
    state.update(kw)
    return state


@pytest.fixture
def stub():
    """Loopback stub; yields (base_url, state). state may be mutated per test."""
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


def test_happy_path_net_equals_balance(stub):
    base, st = stub
    st["txs_to"] = [_tx("0xaaa", OTHER, ADDR, 3 * 10**18)]
    st["txs_from"] = [_tx("0xbbb", ADDR, OTHER, 10**18, nonce=0)]
    st["nonces"][ADDR.lower()] = 1
    st["balances"][ADDR.lower()] = 2 * 10**18 - 21000 * 10**9
    r = invoke(stub, "--no-log", "--address", ADDR)
    assert r.exit_code == 0, r.output
    assert "yes" in r.output
    assert "nonce" not in r.output.lower() or "cross-check" not in r.output


def test_pagination(stub):
    base, st = stub
    st["paged"] = True
    st["txs_from"] = [
        _tx("0xaaa", ADDR, OTHER, 0, nonce=0),
        _tx("0xbbb", ADDR, OTHER, 0, nonce=1),
    ]
    st["nonces"][ADDR.lower()] = 2
    r = invoke(stub, "--no-log", "--address", ADDR)
    assert r.exit_code == 0, r.output
    assert "0xaaa" in r.output and "0xbbb" in r.output


def test_dedupe_second_run_appends_nothing(stub, tmp_path):
    base, st = stub
    st["txs_to"] = [_tx("0xaaa", OTHER, ADDR, 10**18)]
    st["balances"][ADDR.lower()] = 10**18
    log = str(tmp_path / "t.jsonl")
    r1 = invoke(stub, "--address", ADDR, "--log", log)
    assert r1.exit_code == 0, r1.output
    lines1 = open(log).read().strip().splitlines()
    assert len(lines1) == 1
    r2 = invoke(stub, "--address", ADDR, "--log", log)
    assert r2.exit_code == 0, r2.output
    assert "+0 rows" in r2.output
    assert open(log).read().strip().splitlines() == lines1


def test_nonce_mismatch_warns_and_exits(stub, tmp_path):
    base, st = stub
    st["txs_from"] = [_tx("0xbbb", ADDR, OTHER, 10**18, nonce=0)]
    st["nonces"][ADDR.lower()] = 7  # explorer says 1, RPC says 7
    log = str(tmp_path / "t.jsonl")
    r = invoke(stub, "--address", ADDR, "--log", log)
    assert r.exit_code == 1
    assert "nonce" in r.output.lower()
    assert "1 outgoing transactions but RPC nonce is 7" in r.output
    assert len(open(log).read().strip().splitlines()) == 1  # consistent rows still logged


def test_non_sepolia_refused(stub, tmp_path):
    base, st = stub
    st["chain_id"] = hex(1)
    log = str(tmp_path / "t.jsonl")
    r = invoke(stub, "--address", ADDR, "--log", log)
    assert r.exit_code != 0
    assert "non-Sepolia" in r.output
    assert not (tmp_path / "t.jsonl").exists()


def test_internal_transfers(stub):
    base, st = stub
    st["internal"] = [_internal("0xccc", OTHER, ADDR, 5 * 10**17)]
    st["balances"][ADDR.lower()] = 5 * 10**17
    r = invoke(stub, "--no-log", "--address", ADDR)
    assert r.exit_code == 0, r.output
    assert "int" in r.output
    assert "0.5" in r.output


def test_failed_tx_counts_gas_only(stub):
    base, st = stub
    st["txs_from"] = [_tx("0xddd", ADDR, OTHER, 10**18, status="error", nonce=0, gas_used=21000, gas_price=10**9)]
    st["nonces"][ADDR.lower()] = 1
    st["balances"][ADDR.lower()] = 10**18 - 21000 * 10**9  # pre-funded 1 ETH, lost only gas
    st["txs_to"] = [_tx("0xaaa", OTHER, ADDR, 10**18)]
    r = invoke(stub, "--no-log", "--address", ADDR)
    assert r.exit_code == 0, r.output
    assert "failed" in r.output
    assert "yes" in r.output  # net = 1 - gas, matches balance


def test_label_resolution(stub):
    r = invoke(stub, "--no-log", "--address", "bridge")
    assert r.exit_code == 0, r.output
    assert "bridge" in r.output
