"""Security pins — api-gateway hop-by-hop header stripping (#1192, PI-API-006).

Forwarding connection-specific headers upstream produced the proven TE+CL
conflict (upstream 400 on every chunked request through ``/api/``) and is a
request-smuggling primitive on any future parser change. These pins lock:
the RFC 7230 §6.1 set is always dropped, ``Connection``-nominated tokens are
dropped per-request (including across duplicate Connection headers), and the
response direction strips framing headers.
"""

from __future__ import annotations

import api_gateway.main as gw
from starlette.datastructures import Headers


def _headers(pairs: list[tuple[str, str]]) -> Headers:
    return Headers(raw=[(k.lower().encode(), v.encode()) for k, v in pairs])


def test_rfc7230_hop_by_hop_set_is_dropped():
    headers = _headers(
        [
            ("connection", "keep-alive"),
            ("keep-alive", "timeout=5"),
            ("te", "trailers"),
            ("trailer", "x-foo"),
            ("transfer-encoding", "chunked"),
            ("upgrade", "websocket"),
            ("proxy-authorization", "Basic abc"),
            ("x-custom", "keep"),
        ]
    )
    out = gw._strip_hop_by_hop(headers)
    assert out == {"x-custom": "keep"}


def test_connection_nominated_headers_are_dropped():
    """``Connection: X-Foo`` makes X-Foo hop-by-hop for this request only."""
    headers = _headers(
        [
            ("connection", "x-secret-hop"),
            ("x-secret-hop", "value"),
            ("x-end-to-end", "value"),
        ]
    )
    out = gw._strip_hop_by_hop(headers)
    assert out == {"x-end-to-end": "value"}


def test_duplicate_connection_headers_each_nominate():
    """Two Connection headers must both be honored — collapsing to the first
    would leave the second header's nominated tokens forwarded."""
    headers = Headers(
        raw=[
            (b"connection", b"x-hop-a"),
            (b"connection", b"x-hop-b"),
            (b"x-hop-a", b"1"),
            (b"x-hop-b", b"2"),
            (b"x-keep", b"3"),
        ]
    )
    out = gw._strip_hop_by_hop(headers)
    assert out == {"x-keep": "3"}


def test_te_and_content_length_conflict_cannot_survive():
    """The exact PI-API-006 shape: TE + CL both present must not both forward."""
    headers = _headers(
        [
            ("connection", "keep-alive"),
            ("te", "chunked"),
            ("transfer-encoding", "chunked"),
            ("content-length", "4"),
            ("content-type", "application/json"),
        ]
    )
    out = gw._strip_hop_by_hop(headers)
    # content-length is end-to-end framing and survives the request strip;
    # what must be gone is every hop-by-hop token.
    assert "te" not in out
    assert "transfer-encoding" not in out
    assert "connection" not in out


def test_upstream_response_headers_strip_framing():
    class _Resp:
        headers = {
            "content-length": "10",
            "content-encoding": "gzip",
            "server": "nginx",
            "date": "today",
            "x-request-id": "abc",
        }

    out = gw._upstream_headers(_Resp())  # type: ignore[arg-type]
    assert out == {"x-request-id": "abc"}
