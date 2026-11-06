"""Security pins — gateway rate-limit identity comes from the trusted peer (#1189, R9-4).

The limiter keys on ``request.client.host`` via slowapi's
``get_remote_address``. That address is only honest because uvicorn runs
with ``proxy_headers=True`` + ``forwarded_allow_ips="127.0.0.1"`` — nginx is
the sole peer allowed to assert forwarded identity. If either literal
regresses, every client collapses into the loopback bucket again (the
original R9-4 defect: one global 100/min bucket for the whole fleet).

Source-level pins: the values live in the ``__main__`` block and the systemd
unit, not in an importable object — asserting on the module source is the
fastest honest check available at this tier.
"""

from __future__ import annotations

import inspect

import api_gateway.main as gw


def test_limiter_keys_on_remote_address_not_a_spoofable_header():
    src = inspect.getsource(gw)
    assert "Limiter(key_func=get_remote_address)" in src
    # No header-derived key function may replace the peer address.
    assert "key_func=lambda" not in src


def test_uvicorn_proxy_headers_restricted_to_loopback():
    src = inspect.getsource(gw)
    assert "proxy_headers=True" in src
    assert 'forwarded_allow_ips="127.0.0.1"' in src


def test_no_wildcard_forwarded_allow_ips():
    src = inspect.getsource(gw)
    assert 'forwarded_allow_ips="*"' not in src
    assert "forwarded_allow_ips=None" not in src
