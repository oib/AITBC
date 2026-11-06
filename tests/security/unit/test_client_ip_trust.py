"""Security pins — client-IP trust boundary (#1177, PI-API-001).

``get_client_ip`` decides whose bucket a rate limit lands in and whose
identity lands in audit logs. The hub nginx chain is: client → ns2 edge
(``$realip_remote_addr``) → hub nginx (``X-Real-IP`` + rightmost XFF append)
→ uvicorn. Anything a client can write into XFF *before* the trusted append
is attacker-controlled; these pins lock the precedence that makes forged
left-hand entries harmless.

Canonical pin file for the property; the app's own
``apps/coordinator-api/tests/test_client_ip.py`` carries the broader matrix.
"""

from __future__ import annotations

from starlette.requests import Request

from coordinator_api.utils.security import get_client_ip


def _request(
    headers: list[tuple[bytes, bytes]],
    client: tuple[str, int] | None = ("10.0.0.1", 50000),
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": client,
            "query_string": b"",
        }
    )


def test_forged_leftmost_xff_cannot_mint_identity():
    """A client-supplied first XFF hop must never win over the trusted tail."""
    req = _request(
        [
            (b"x-forwarded-for", b"6.6.6.6, 203.0.113.10"),
        ]
    )
    assert get_client_ip(req) == "203.0.113.10"


def test_x_real_ip_beats_every_xff_entry():
    req = _request(
        [
            (b"x-real-ip", b"198.51.100.7"),
            (b"x-forwarded-for", b"1.1.1.1, 2.2.2.2, 198.51.100.7"),
        ]
    )
    assert get_client_ip(req) == "198.51.100.7"


def test_whitespace_and_empty_hops_do_not_confuse_the_tail():
    req = _request([(b"x-forwarded-for", b"1.1.1.1 ,  203.0.113.10  ")])
    assert get_client_ip(req) == "203.0.113.10"


def test_no_forwarded_headers_falls_back_to_peer():
    req = _request([], client=("192.0.2.9", 443))
    assert get_client_ip(req) == "192.0.2.9"


def test_missing_client_socket_reports_unknown_not_empty():
    req = _request([(b"x-forwarded-for", b"")], client=None)
    assert get_client_ip(req) == "unknown"
