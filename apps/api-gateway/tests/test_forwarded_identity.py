"""R9-4 pins: the rate limiter keys on post-realip client identity.

Pre-fix every request reached uvicorn from the local nginx peer, so
``get_remote_address`` saw 127.0.0.1 for everyone — one global bucket.
The fix is launch-side: ``--proxy-headers --forwarded-allow-ips 127.0.0.1``
makes ``request.client.host`` carry the forwarded (post-realip) address,
which is what slowapi keys on. These pins cover the repo-side contract:
the unit flags, the key function's inputs, and that a raw X-Forwarded-For
header cannot influence the key by itself.
"""

from pathlib import Path

from slowapi.util import get_remote_address
from starlette.requests import Request

UNIT = Path(__file__).resolve().parents[1] / "aitbc-api-gateway.service"


def _request(client_host: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (client_host, 50000),
            "query_string": b"",
        }
    )


def test_unit_enables_proxy_headers_with_localhost_only_trust():
    unit = UNIT.read_text()
    assert "--proxy-headers" in unit
    assert "--forwarded-allow-ips 127.0.0.1" in unit


def test_key_is_the_client_host_not_the_listener_peer():
    """Two distinct post-realip clients must produce distinct limiter keys."""
    assert get_remote_address(_request("203.0.113.10")) == "203.0.113.10"
    assert get_remote_address(_request("198.51.100.20")) == "198.51.100.20"


def test_raw_xff_header_does_not_change_the_key():
    """X-Forwarded-For is honoured only by uvicorn's trusted-peer middleware;
    the limiter key function itself must not read it — otherwise a client
    could mint a fresh bucket per request."""
    base = _request("203.0.113.10")
    forged = _request("203.0.113.10", xff="198.51.100.99")
    other = _request("198.51.100.99")

    assert get_remote_address(forged) == get_remote_address(base)
    assert get_remote_address(forged) != get_remote_address(other)


def test_main_py_dev_default_matches_unit_flags():
    """`python main.py` must not silently diverge from the unit's trust model."""
    src = (Path(__file__).resolve().parents[1] / "src" / "api_gateway" / "main.py").read_text()
    assert "proxy_headers=True" in src
    assert 'forwarded_allow_ips="127.0.0.1"' in src
