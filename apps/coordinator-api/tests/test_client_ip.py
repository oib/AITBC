"""PI-API-001 / #1177: get_client_ip must not trust client-supplied XFF hops.

The hub nginx vhost sets ``X-Real-IP`` to the realip-resolved client and
appends that address as the LAST ``X-Forwarded-For`` entry. Entries earlier
in the chain are whatever the client claimed — spoofable. These pins lock
the precedence: X-Real-IP > rightmost XFF > direct peer.
"""

from starlette.requests import Request

from coordinator_api.utils.security import get_client_ip


def _request(headers: list[tuple[bytes, bytes]], client: tuple[str, int] | None = ("10.0.0.1", 50000)) -> Request:
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


def test_x_real_ip_wins_over_spoofed_xff():
    req = _request(
        [
            (b"x-real-ip", b"203.0.113.10"),
            (b"x-forwarded-for", b"1.2.3.4, 5.6.7.8, 203.0.113.10"),
        ]
    )
    assert get_client_ip(req) == "203.0.113.10"


def test_rightmost_xff_is_the_proxy_appended_peer():
    req = _request([(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8, 203.0.113.10")])
    assert get_client_ip(req) == "203.0.113.10"


def test_single_xff_entry_is_used():
    req = _request([(b"x-forwarded-for", b"203.0.113.10")])
    assert get_client_ip(req) == "203.0.113.10"


def test_direct_peer_when_no_forwarded_headers():
    req = _request([], client=("192.0.2.1", 50000))
    assert get_client_ip(req) == "192.0.2.1"


def test_unknown_when_no_client_and_no_headers():
    req = _request([], client=None)
    assert get_client_ip(req) == "unknown"
