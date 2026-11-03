"""#898: bulk_sync.sh's import counters must survive the loop.

On base the block loop ran inside a pipe subshell, so batch_imported and
batch_failed died there and every run printed "Blocks imported: 0" —
with a failed import invisible behind the success banner. The loop now
reads from process substitution and the run exits non-zero on any
failure.
"""

import json
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "sync" / "bulk_sync.sh"

pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="bulk_sync.sh missing")


def test_loop_uses_process_substitution_not_a_pipe_subshell():
    src = SCRIPT.read_text()
    assert "done < <(" in src, "counters still die in a pipe subshell"
    assert "| while read -r block" not in src


def test_run_fails_when_imports_fail_or_diff_remains_high():
    src = SCRIPT.read_text()
    assert 'if [ "$total_failed" -gt 0 ]' in src
    assert src.count("exit 1") >= 2


def _block(h, chain="test-chain"):
    return {
        "height": h,
        "hash": "0x" + f"{h:064x}",
        "parent_hash": "0x" + "00" * 32,
        "proposer": "0x" + "ab" * 20,
        "timestamp": "2026-01-01T00:00:00Z",
        "tx_count": 0,
        "chain_id": chain,
    }


class _RPC(BaseHTTPRequestHandler):
    """Tiny mock: /status, /rpc/head, /rpc/blocks-range, /rpc/importBlock."""

    state = {"local_height": 100, "accepted": True}
    genesis_port = None

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._json({"ok": True})
        elif self.path == "/rpc/head":
            side = "genesis" if self.server.server_address[1] == _RPC.genesis_port else "local"
            h = 300 if side == "genesis" else self.state["local_height"]
            self._json({"height": h})
        elif self.path.startswith("/rpc/blocks-range"):
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(self.path).query)
            start, end = int(q["start"][0]), int(q["end"][0])
            self._json({"blocks": [_block(h) for h in range(start, end + 1)]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/rpc/importBlock":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            if self.state["accepted"]:
                self.state["local_height"] = data.get("height", self.state["local_height"])
            self._json({"accepted": self.state["accepted"]})
        else:
            self._json({"error": "not found"}, 404)


def _serve(port):
    httpd = HTTPServer(("127.0.0.1", port), _RPC)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


@pytest.mark.parametrize("accepted", [True, False], ids=["ok", "refused"])
def test_counters_reach_the_report(tmp_path, accepted):
    """End-to-end with two loopback mock RPCs: counters are real and a
    refused import fails the run."""
    _RPC.state = {"local_height": 100, "accepted": accepted}
    genesis = _serve(0)
    _RPC.genesis_port = genesis.server_address[1]
    genesis_port = _RPC.genesis_port
    local = _serve(0)
    local_port = local.server_address[1]
    try:
        env = dict(
            os.environ,
            AITBC_NODE1_HOST="127.0.0.1",
            GENESIS_NODE="127.0.0.1",
            GENESIS_PORT=str(genesis_port),
            LOCAL_PORT=str(local_port),
            BULK_BATCH_SIZE="50",
            MAX_SYNC_DIFF="100",
        )
        env.pop("BLOCKCHAIN_RPC_API_KEY", None)
        result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=180)
    finally:
        genesis.shutdown()
        local.shutdown()

    out = result.stdout + result.stderr
    imported = re.search(r"Blocks imported: (\d+)", out)
    failed = re.search(r"Blocks failed: (\d+)", out)
    assert imported and failed, out
    if accepted:
        assert int(imported.group(1)) == 200, f"counters lost in the subshell: {out}"
        assert "BULK SYNC SUCCESSFUL" in out
    else:
        assert int(failed.group(1)) > 0
        assert "BULK SYNC FAILED" in out
        assert result.returncode != 0
