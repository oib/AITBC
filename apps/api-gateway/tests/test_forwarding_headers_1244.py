"""#1244 pins: the gateway stamps the caller identity, it never forwards it.

``_strip_hop_by_hop`` used to pass a client's own ``X-Real-IP`` /
``X-Forwarded-For`` to the upstream verbatim, where the shared rate limiter
trusted them (any loopback peer, i.e. the gateway, is a trusted proxy). The
gateway now overwrites ``X-Real-IP`` with the address it observed and
overwrites ``X-Forwarded-For`` with that same address — the client-supplied
chain is dropped entirely (#1177 operator ruling: overwrite, never
append/forward verbatim).
"""

from __future__ import annotations

import api_gateway.main as gw
from aitbc.rate_limiting import _client_ip_for_rate_limit
from starlette.requests import Request


def _request(peer: str | None, headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 50000) if peer else None,
            "query_string": b"",
        }
    )


def _upstream_view(headers: dict[str, str]) -> Request:
    """What the service behind the gateway sees: the gateway (loopback) is the peer."""
    return _request("127.0.0.1", headers)


def _forward(request: Request) -> dict[str, str]:
    out = gw._strip_hop_by_hop(request.headers)
    gw._stamp_forwarding_headers(out, request)
    return out


def test_client_supplied_x_real_ip_is_replaced_with_the_observed_peer():
    spoof = _request("203.0.113.9", {"X-Real-IP": "198.51.100.1"})
    out = _forward(spoof)
    assert out["x-real-ip"] == "203.0.113.9"
    assert "198.51.100.1" not in out["x-real-ip"]


def test_direct_caller_cannot_choose_its_upstream_identity():
    """The sandbox repro: XFF ``10.1.1.1, 198.51.100.55`` arrived upstream as
    ``client=198.51.100.55``. Now the upstream keys on the real peer."""
    spoof = _request("203.0.113.9", {"X-Forwarded-For": "10.1.1.1, 198.51.100.55", "X-Real-IP": "198.51.100.55"})
    assert _client_ip_for_rate_limit(_upstream_view(_forward(spoof))) == "203.0.113.9"


def test_rotating_headers_collapse_to_one_upstream_identity():
    keys = {
        _client_ip_for_rate_limit(
            _upstream_view(_forward(_request("203.0.113.9", {"X-Real-IP": f"192.0.2.{i}", "X-Forwarded-For": f"192.0.2.{i}"})))
        )
        for i in range(1, 250)
    }
    assert keys == {"203.0.113.9"}


def test_nginx_chain_overwrites_with_the_observed_peer_only():
    """#1177 (operator ruling): XFF is overwritten, never appended — the
    client-supplied chain must not reach upstream even as non-rightmost
    entries. uvicorn --proxy-headers already resolved the peer to the real
    client, so the stamped value is that address alone."""
    edge = _request("198.51.100.4", {"X-Real-IP": "198.51.100.4", "X-Forwarded-For": "6.6.6.6, 198.51.100.4"})
    out = _forward(edge)
    assert out["x-forwarded-for"] == "198.51.100.4"
    assert out["x-real-ip"] == "198.51.100.4"
    assert _client_ip_for_rate_limit(_upstream_view(out)) == "198.51.100.4"


def test_spoofed_chain_entries_never_reach_upstream():
    """Every element of a forged XFF chain is dropped, not just the tail —
    downstream readers that scan the whole header see only the peer."""
    spoof = _request("203.0.113.9", {"X-Forwarded-For": "10.0.0.1, 192.168.1.1, 198.51.100.55"})
    out = _forward(spoof)
    assert out["x-forwarded-for"] == "203.0.113.9"
    assert "198.51.100.55" not in out["x-forwarded-for"]


def test_ws_upgrade_request_gets_the_same_stamp():
    """WS cap pin (#1177): a websocket-upgrade-shaped request takes the same
    proxy path, so the per-IP connection cap upstream keys on the stamped
    peer — rotating spoofed headers cannot mint extra WS identities."""
    ws = _request(
        "203.0.113.9",
        {
            "X-Forwarded-For": "192.0.2.1",
            "X-Real-IP": "192.0.2.1",
            "Connection": "Upgrade",
            "Upgrade": "websocket",
        },
    )
    out = _forward(ws)
    keys = {
        _client_ip_for_rate_limit(_upstream_view(_forward(_request("203.0.113.9", {"X-Real-IP": f"192.0.2.{i}"}))))
        for i in range(1, 50)
    }
    assert keys == {"203.0.113.9"}
    assert out["x-real-ip"] == "203.0.113.9" and out["x-forwarded-for"] == "203.0.113.9"


def test_no_incoming_xff_gets_a_single_observed_entry():
    out = _forward(_request("203.0.113.9", {}))
    assert out["x-forwarded-for"] == "203.0.113.9"


def test_header_case_variants_are_all_overwritten():
    req = _request("203.0.113.9", {"x-REAL-ip": "1.1.1.1"})
    out = gw._strip_hop_by_hop(req.headers)
    out["X-Real-IP"] = "2.2.2.2"  # a differently-cased key that survived the strip
    gw._stamp_forwarding_headers(out, req)
    assert [v for k, v in out.items() if k.lower() == "x-real-ip"] == ["203.0.113.9"]


def test_unknown_peer_forwards_no_identity_at_all():
    out = _forward(_request(None, {"X-Real-IP": "198.51.100.1", "X-Forwarded-For": "198.51.100.1"}))
    assert "x-real-ip" not in out
    assert "x-forwarded-for" not in out


# --- through the real proxy route: the stamp must actually be on the path ---

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class _HeaderCapture:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    async def get(self, url, **kwargs):
        self.headers = dict(kwargs.get("headers") or {})
        return httpx.Response(200, json={"ok": True})

    async def aclose(self) -> None:
        pass


@pytest.fixture
def served(monkeypatch):
    monkeypatch.setattr(gw, "REQUIRE_AUTH", False)
    capture = _HeaderCapture()
    # The module-level ``app`` can be stale after another test module reloads
    # api_gateway.main; serve the current one like test_gateway.py does.
    with TestClient(gw.app, client=("203.0.113.9", 50000)) as c:
        monkeypatch.setattr(c.app.state, "http_client", capture)
        yield c, capture


def test_proxy_route_never_forwards_client_supplied_identity_headers(served):
    client, capture = served
    response = client.get(
        "/v1/coordinator/jobs",
        headers={"X-Real-IP": "198.51.100.55", "X-Forwarded-For": "10.1.1.1, 198.51.100.55"},
    )
    assert response.status_code == 200
    assert capture.headers["x-real-ip"] == "203.0.113.9"
    assert capture.headers["x-forwarded-for"].split(",")[-1].strip() == "203.0.113.9"
    # what the upstream's rate limiter derives from exactly these headers
    assert _client_ip_for_rate_limit(_upstream_view(capture.headers)) == "203.0.113.9"


def test_proxy_route_stamps_identity_when_the_client_sent_none(served):
    client, capture = served
    client.get("/v1/coordinator/jobs")
    assert capture.headers["x-real-ip"] == "203.0.113.9"
    assert capture.headers["x-forwarded-for"] == "203.0.113.9"
