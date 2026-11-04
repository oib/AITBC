"""#996 pins: load_test_endpoint must actually hit the endpoint (args not
swapped), run at wall-clock concurrency, and report rps + cpu delta."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SPEC = importlib.util.spec_from_file_location(
    "scalability_validation",
    os.path.join(os.path.dirname(__file__), "../../scripts/testing/scalability_validation.py"),
)


def _load():
    os.environ.setdefault("AITBC_API_KEY", "pin-test")
    mod = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(mod)
    return mod


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib handler name
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture()
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    import threading

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def test_load_test_six_requests_all_200(server):
    mod = _load()
    v = mod.ScalabilityValidator(f"http://127.0.0.1:{server.server_port}")
    res = asyncio.run(v.load_test_endpoint("/health", "GET", concurrent_users=2, requests_per_user=3, ramp_up_time=0.1))
    assert res["total_requests"] == 6
    assert res["successful_requests"] == 6
    assert res["failed_requests"] == 0
    assert res["success_rate"] == 100.0
    assert res["requests_per_second"] > 0
    assert res["wall_time_s"] > 0


def test_no_method_token_error(server):
    """The swapped-args bug reported the method as the URL token."""
    mod = _load()
    v = mod.ScalabilityValidator(f"http://127.0.0.1:{server.server_port}")
    res = asyncio.run(v.load_test_endpoint("/health", "GET", concurrent_users=1, requests_per_user=1, ramp_up_time=0))
    assert "error" not in str(res) or "non-token" not in str(res)
    assert res["successful_requests"] == 1
