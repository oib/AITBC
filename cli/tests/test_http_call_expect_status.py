"""TOOL-1: ``aitbc http call --expect-status`` and structured non-2xx output.

The tests run a real local HTTP server so the full ``AITBCHTTPClient`` path
(session, raise_for_status, NetworkError wrapping) executes — nothing mocks
the client.  The RateLimitError/CircuitBreakerOpenError catches use a real
client subclass that raises the real exception type from ``get``.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from click.testing import CliRunner

from aitbc.exceptions import CircuitBreakerOpenError, RateLimitError
from aitbc_cli.commands import http as http_module
from aitbc_cli.commands.http import call_http
from aitbc_cli.utils.http_client import AITBCHTTPClient


class _Handler(BaseHTTPRequestHandler):
    """401 for /needs-auth, 404 for everything else — both JSON detail bodies."""

    def _reply(self, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/needs-auth"):
            self._reply(401, "Missing API key")
        else:
            self._reply(404, f"no route {self.path}")

    def do_POST(self) -> None:
        self.do_GET()

    def log_message(self, *args: Any) -> None:  # keep test output quiet
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, url, *args):
    return runner.invoke(
        call_http,
        ["svc", *args, "--url", url],
        obj={"output_format": "json"},
    )


class TestExpectStatus:
    def test_expected_404_returns_structured_output(self, runner, server):
        result = _invoke(runner, server, "missing/route", "--expect-status", "404")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["status"] == 404
        assert "no route" in payload["detail"]

    def test_expected_401_returns_detail(self, runner, server):
        result = _invoke(runner, server, "needs-auth", "--expect-status", "401")
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload == {"status": 401, "detail": "Missing API key"}

    def test_expect_status_is_repeatable(self, runner, server):
        result = _invoke(runner, server, "needs-auth", "--expect-status", "401", "--expect-status", "404")
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["status"] == 401

    def test_status_not_in_expected_set_still_errors(self, runner, server):
        result = _invoke(runner, server, "needs-auth", "--expect-status", "404")
        assert result.exit_code != 0
        assert "HTTP 401" in result.output


class TestPlainNon2xx:
    def test_404_renders_one_line(self, runner, server):
        result = _invoke(runner, server, "missing/route")
        assert result.exit_code != 0
        assert "HTTP 404 from svc/missing/route: no route /missing/route" in result.output

    def test_401_renders_detail(self, runner, server):
        result = _invoke(runner, server, "needs-auth")
        assert result.exit_code != 0
        assert "HTTP 401 from svc/needs-auth: Missing API key" in result.output

    def test_no_traceback(self, runner, server):
        result = _invoke(runner, server, "missing/route")
        assert "Traceback" not in result.output


class _RateLimitedClient(AITBCHTTPClient):
    """Real client whose limiter trips on the first request."""

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        raise RateLimitError("client-side rate limit exceeded")


class _OpenCircuitClient(AITBCHTTPClient):
    def get(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        raise CircuitBreakerOpenError("circuit breaker open")


class TestClientRaisedErrors:
    """RateLimitError/CircuitBreakerOpenError bypass NetworkError wrapping."""

    def test_rate_limit_is_clean_error(self, runner, server, monkeypatch):
        monkeypatch.setattr(http_module, "AITBCHTTPClient", _RateLimitedClient)
        result = _invoke(runner, server, "missing/route")
        assert result.exit_code != 0
        assert "RateLimitError calling svc/missing/route" in result.output
        assert "Traceback" not in result.output

    def test_circuit_breaker_is_clean_error(self, runner, server, monkeypatch):
        monkeypatch.setattr(http_module, "AITBCHTTPClient", _OpenCircuitClient)
        result = _invoke(runner, server, "missing/route")
        assert result.exit_code != 0
        assert "CircuitBreakerOpenError calling svc/missing/route" in result.output
        assert "Traceback" not in result.output
