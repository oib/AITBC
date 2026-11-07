"""Security pins — rate-limit identity trust boundary (#1244, R12-A2-6).

``aitbc.rate_limiting._client_ip_for_rate_limit`` keys every ``@rate_limit``
bucket. It used to read ``X-Real-IP`` / the right-most ``X-Forwarded-For``
entry from anyone, so a caller rotating either header minted a fresh bucket
per request (450 requests: 448 x 200 with rotation, 347 x 429 with a fixed
identity). Forwarding headers now count only when the TCP peer is a trusted
proxy (``AITBC_TRUSTED_PROXIES``, default loopback).
"""

from __future__ import annotations

import pytest
from aitbc.rate_limiting import _client_ip_for_rate_limit, rate_limit, reset_rate_limit
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest

NGINX = "127.0.0.1"
ATTACKER = "203.0.113.50"
VICTIM = "198.51.100.77"


@pytest.fixture(autouse=True)
def _default_trust(monkeypatch):
    monkeypatch.delenv("AITBC_TRUSTED_PROXIES", raising=False)
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "true")


def _req(peer: str | None, **headers: str) -> StarletteRequest:
    return StarletteRequest(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(k.replace("_", "-").lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 50000) if peer else None,
            "query_string": b"",
        }
    )


def test_untrusted_peer_cannot_choose_its_identity_with_x_real_ip():
    assert _client_ip_for_rate_limit(_req(ATTACKER, x_real_ip=VICTIM)) == ATTACKER


def test_untrusted_peer_cannot_choose_its_identity_with_xff():
    assert _client_ip_for_rate_limit(_req(ATTACKER, x_forwarded_for=f"1.1.1.1, {VICTIM}")) == ATTACKER


def test_rotating_headers_from_one_peer_collapse_to_one_identity():
    keys = {
        _client_ip_for_rate_limit(
            _req(ATTACKER, x_real_ip=f"10.9.{i // 250}.{i % 250 + 1}", x_forwarded_for=f"10.8.0.{i % 250 + 1}")
        )
        for i in range(450)
    }
    assert keys == {ATTACKER}


def test_trusted_proxy_x_real_ip_is_honoured():
    """nginx overwrites X-Real-IP with $remote_addr: the legitimate chain."""
    assert _client_ip_for_rate_limit(_req(NGINX, x_real_ip=VICTIM)) == VICTIM


def test_trusted_proxy_xff_takes_rightmost_untrusted_hop_not_the_forged_left():
    req = _req(NGINX, x_forwarded_for=f"6.6.6.6, {VICTIM}, 127.0.0.1")
    assert _client_ip_for_rate_limit(req) == VICTIM


def test_trusted_proxy_with_garbage_headers_falls_back_to_the_peer():
    req = _req(NGINX, x_real_ip="not-an-ip", x_forwarded_for="also, junk")
    assert _client_ip_for_rate_limit(req) == NGINX


def test_ipv4_mapped_loopback_peer_counts_as_loopback():
    assert _client_ip_for_rate_limit(_req("::ffff:127.0.0.1", x_real_ip=VICTIM)) == VICTIM
    assert _client_ip_for_rate_limit(_req("::ffff:203.0.113.50", x_real_ip=VICTIM)) == "::ffff:203.0.113.50"


def test_missing_peer_reports_unknown():
    assert _client_ip_for_rate_limit(_req(None, x_real_ip=VICTIM)) == "unknown"


def test_non_ip_peer_is_never_trusted():
    # TestClient's default peer; also any unparseable ASGI client host.
    assert _client_ip_for_rate_limit(_req("testclient", x_real_ip=VICTIM)) == "testclient"


def test_trusted_proxy_list_is_configurable_with_cidr(monkeypatch):
    monkeypatch.setenv("AITBC_TRUSTED_PROXIES", "10.1.223.0/24, ::1")
    assert _client_ip_for_rate_limit(_req("10.1.223.9", x_real_ip=VICTIM)) == VICTIM
    # loopback is no longer implicitly trusted once the operator narrows the list
    assert _client_ip_for_rate_limit(_req("127.0.0.1", x_real_ip=VICTIM)) == "127.0.0.1"


def _limited_app(rate: int) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    @rate_limit(rate=rate, per=60)
    def ping(request: Request) -> dict[str, bool]:
        return {"ok": True}

    return app


def _burst(client: TestClient, n: int, header_for) -> list[int]:
    return [client.get("/ping", headers=header_for(i)).status_code for i in range(n)]


def test_rotating_headers_from_an_untrusted_peer_still_hit_the_limit():
    """End to end through the decorator: direct hit on the service port."""
    reset_rate_limit(ATTACKER)
    client = TestClient(_limited_app(5), client=(ATTACKER, 50000))
    codes = _burst(client, 20, lambda i: {"x-real-ip": f"192.0.2.{i + 1}", "x-forwarded-for": f"192.0.2.{i + 1}"})
    assert codes.count(200) == 5
    assert codes.count(429) == 15


def test_distinct_callers_behind_a_trusted_proxy_keep_separate_buckets():
    """The legitimate nginx chain must not collapse into the proxy's own bucket."""
    for ip in ("192.0.2.1", "192.0.2.2", NGINX):
        reset_rate_limit(ip)
    client = TestClient(_limited_app(3), client=(NGINX, 50000))
    first = _burst(client, 5, lambda i: {"x-real-ip": "192.0.2.1"})
    second = _burst(client, 3, lambda i: {"x-real-ip": "192.0.2.2"})
    assert first.count(429) == 2
    assert second == [200, 200, 200]
