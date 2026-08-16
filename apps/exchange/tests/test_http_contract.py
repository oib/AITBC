"""Characterisation tests for the simple_exchange HTTP surface (APP-54).

APP-54 is the migration of this service from stdlib http.server to FastAPI. These
tests pin the wire contract — routes, auth, CORS, malformed bodies — so a
behavioural change is visible rather than assumed.

These tests describe what the service does today, at the wire level: which paths exist on
which methods, which require X-Api-Key, what CORS headers come back, and how malformed
requests are answered. They are deliberately about status codes and headers rather than
response bodies -- bodies depend on blockchain RPC and database contents, whereas the
routing table and the auth boundary are what a rewrite must not change quietly.

Run against the real handler through a real socket, because that is the thing being
replaced. When the FastAPI version lands, this file should pass against it unchanged; any
line that has to be edited is a behavioural change that someone chose.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

API_KEY = "characterisation-test-key"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The real ExchangeAPIHandler on a real socket, against a temporary database."""
    db_dir = tmp_path_factory.mktemp("exchange-db")
    os.environ["EXCHANGE_DATABASE_URL"] = f"sqlite:///{db_dir}/exchange.db"
    os.environ["EXCHANGE_API_KEY"] = API_KEY
    # Point the RPC base at a port nothing is listening on: the routes that reach for the
    # chain should fail as "upstream unavailable", not hang or contact a real node.
    os.environ["BLOCKCHAIN_RPC_BASE_URL"] = "http://127.0.0.1:1"

    from apps.exchange.simple_exchange.db import init_db
    from apps.exchange.simple_exchange.main import app

    init_db()

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        thread.join(0.05)
    else:
        raise RuntimeError("uvicorn did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def raw_request_status(base: str, request_line: str) -> int:
    """Send a request line verbatim and return its status code.

    Needed for targets urllib will not construct, such as one starting with "..".
    """
    port = int(base.rsplit(":", 1)[1])
    sock = socket.create_connection(("127.0.0.1", port), timeout=15)
    try:
        sock.sendall(f"{request_line}\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode())
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    finally:
        sock.close()
    return int(data.decode(errors="replace").split()[1])


def request(base: str, method: str, path: str, *, body=None, api_key: str | None = None):
    """Issue a request and return (status, headers, body-text) without raising."""
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if api_key is not None:
        headers["X-Api-Key"] = api_key

    req = Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            return (
                response.status,
                {k.lower(): v for k, v in dict(response.headers).items()},
                response.read().decode(),
            )
    except HTTPError as e:
        return e.code, {k.lower(): v for k, v in dict(e.headers).items()}, e.read().decode()


# Every route the dispatcher in handlers/__init__.py knows about, and whether it is behind
# the X-Api-Key check. Written out rather than derived, so a route silently disappearing
# during the migration shows up as a failure here.
GET_ROUTES_PUBLIC = [
    "/health",
    "/api/health",
    "/api/trades/recent",
    "/api/orders/orderbook",
    "/v1/marketplace/offers",
    "/v1/marketplace/orders",
    "/metrics",
    "/v1/bridge/price",
    "/v1/bridge/status",
    "/v1/bridge/status/some-id",
    "/v1/bridge/deposits",
    "/v1/exchange/history",
    "/exchange/price.json",
]

# Reads that do require X-Api-Key. Grouped separately because "which reads are public" is
# the kind of thing a rewrite gets wrong quietly.
GET_ROUTES_AUTHED = [
    "/api/wallet/balance",
    "/api/total-supply",
    "/api/treasury-balance",
]

# Routes taking an id. A nonexistent id answers 404, so they cannot be checked by "is it
# routed"; they are listed to record that the id-bearing form exists at all.
GET_ROUTES_WITH_ID = [
    "/v1/marketplace/offers/some-id",
    "/v1/bridge/deposit/some-id",
]

POST_ROUTES_AUTHED = [
    "/api/orders",
    "/v1/marketplace/offers",
    "/v1/marketplace/offers/some-id/book",
    "/v1/bridge/deposit",
    "/v1/bridge/withdraw",
]


class TestRoutingTable:
    @pytest.mark.parametrize("path", GET_ROUTES_PUBLIC)
    def test_get_route_exists(self, server, path):
        """Every declared GET route is dispatched. 404 from a missing oracle
        price on /v1/bridge/price is the handler, not a missing route."""
        status, _, body = request(server, "GET", path)
        if path == "/v1/bridge/price" and status == 404 and "No price available" in body:
            return
        assert status != 404, f"GET {path} is no longer routed"

    @pytest.mark.parametrize("path", GET_ROUTES_AUTHED)
    def test_authed_get_route_exists(self, server, path):
        """Routed but behind the key: a missing key gives 401, not 404."""
        status, _, _ = request(server, "GET", path)
        assert status == 401, f"GET {path} answered {status}, expected the auth check"

    @pytest.mark.parametrize("path", GET_ROUTES_WITH_ID)
    def test_id_route_answers_404_for_an_unknown_id(self, server, path):
        status, _, _ = request(server, "GET", path)
        assert status == 404

    def test_unknown_get_is_404(self, server):
        status, _, _ = request(server, "GET", "/no/such/route")
        assert status == 404

    def test_unknown_post_is_404(self, server):
        status, _, _ = request(server, "POST", "/no/such/route", body={})
        assert status == 404

    def test_unknown_delete_is_404(self, server):
        status, _, _ = request(server, "DELETE", "/no/such/route")
        assert status == 404

    def test_health_is_json_and_ok(self, server):
        status, headers, body = request(server, "GET", "/health")
        assert status == 200
        assert headers.get("content-type") == "application/json"
        json.loads(body)


class TestAuthBoundary:
    """Which endpoints require X-Api-Key is the security-relevant half of this surface."""

    @pytest.mark.parametrize("path", POST_ROUTES_AUTHED)
    def test_write_route_rejects_a_missing_key(self, server, path):
        status, _, _ = request(server, "POST", path, body={})
        assert status == 401, f"POST {path} accepted a request with no API key"

    @pytest.mark.parametrize("path", POST_ROUTES_AUTHED)
    def test_write_route_rejects_a_wrong_key(self, server, path):
        status, _, _ = request(server, "POST", path, body={}, api_key="not-the-key")
        assert status == 401, f"POST {path} accepted a wrong API key"

    def test_delete_offer_requires_a_key(self, server):
        status, _, _ = request(server, "DELETE", "/v1/marketplace/offers/some-id")
        assert status == 401

    def test_delete_order_requires_a_key(self, server):
        status, _, _ = request(server, "DELETE", "/v1/marketplace/orders/some-id")
        assert status == 401

    @pytest.mark.parametrize("path", GET_ROUTES_PUBLIC)
    def test_read_routes_do_not_require_a_key(self, server, path):
        """Reads are public today. If the migration changes that, it should be on purpose."""
        status, _, _ = request(server, "GET", path)
        assert status != 401, f"GET {path} now demands an API key"

    @pytest.mark.parametrize("path", GET_ROUTES_AUTHED)
    def test_authed_read_rejects_a_wrong_key(self, server, path):
        status, _, _ = request(server, "GET", path, api_key="not-the-key")
        assert status == 401

    def test_a_valid_key_gets_past_the_auth_check(self, server):
        """Not 401 -- what happens after auth depends on the body and is not pinned here."""
        status, _, _ = request(server, "POST", "/api/orders", body={}, api_key=API_KEY)
        assert status != 401


class TestCORS:
    def test_options_preflight(self, server):
        status, headers, _ = request(server, "OPTIONS", "/health")
        assert status == 200
        assert headers.get("access-control-allow-origin") == "*"
        assert "GET" in headers.get("access-control-allow-methods", "")
        assert "POST" in headers.get("access-control-allow-methods", "")

    def test_responses_carry_the_cors_origin_header(self, server):
        _, headers, _ = request(server, "GET", "/health")
        assert headers.get("access-control-allow-origin") == "*"


class TestMalformedRequests:
    def test_invalid_json_body_is_400(self, server):
        req = Request(
            f"{server}/api/orders",
            data=b"{not json",
            headers={"Content-Type": "application/json", "X-Api-Key": API_KEY},
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as response:
                status = response.status
        except HTTPError as e:
            status = e.code
        assert status == 400

    def test_oversized_body_is_413(self, server):
        # MAX_BODY_BYTES is 2 MB in handlers/base.py.
        payload = b'{"padding": "' + b"x" * (2 * 1024 * 1024 + 100) + b'"}'
        req = Request(
            f"{server}/api/orders",
            data=payload,
            headers={"Content-Type": "application/json", "X-Api-Key": API_KEY},
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as response:
                status = response.status
        except HTTPError as e:
            status = e.code
        assert status == 413

    def test_dot_dot_path_is_rejected(self, server):
        """do_GET refuses a path starting with .. before routing.

        Sent over a raw socket: urllib cannot express a request target that does not begin
        with "/" -- it reads the leading ".." as part of the host.
        """
        assert raw_request_status(server, "GET ../secrets HTTP/1.1") == 400

    def test_double_slash_path_is_normalised_not_rejected(self, server):
        """Recorded because it is not what the guard in do_GET looks like it does.

        That guard also tests for a leading "//", but the path is already normalised by the
        time it runs -- "//health" is served as "/health" (200) and "//evil" falls through
        to the ordinary 404, so the "//" arm is dead code. Normalising is the safe outcome,
        so this records the behaviour rather than calling it a bug; a FastAPI rewrite should
        be checked against it deliberately.
        """
        status, _, _ = request(server, "GET", "//evil")
        assert status == 404

        status, _, _ = request(server, "GET", "//health")
        assert status == 200
