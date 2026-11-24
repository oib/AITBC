"""AUDIT-EDGE pins: #2914 — capacity publisher URL/response hardening.

provider_id is interpolated into the request path (encoded now), the
urllib default redirect handling could re-POST X-Api-Key to a 30x target
(refused now), and resp.read() was unbounded (capped now).
"""

from __future__ import annotations

import io
import urllib.error
from typing import Any

import pytest

from gpu_app import capacity_publisher
from gpu_app.capacity_publisher import _NoRedirectHandler, publish_capacity


def _fake_open(seen: dict[str, Any]):
    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self, n: int = -1):
            return self._body if n is None or n < 0 else self._body[:n]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _open(req, timeout=0):
        seen["url"] = req.full_url
        return _Resp(b'{"ok": true}')

    return _open


@pytest.mark.unit
def test_provider_id_is_path_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(capacity_publisher, "_open", _fake_open(seen))
    result = publish_capacity("prov/../x?y", 1, coordinator_url="http://coord:8203")
    assert result == {"ok": True}
    assert seen["url"] == "http://coord:8203/v1/market/providers/prov%2F..%2Fx%3Fy/capacity"


@pytest.mark.unit
def test_redirects_are_refused() -> None:
    """The opener must not follow 30x — a redirect would re-POST the
    api-key-bearing request to an arbitrary host."""
    assert any(isinstance(h, _NoRedirectHandler) for h in capacity_publisher._OPENER.handlers)
    handler = _NoRedirectHandler()
    assert handler.redirect_request(None, None, 302, "Found", {}, "http://evil") is None


@pytest.mark.unit
def test_response_read_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    big = b"x" * (capacity_publisher._MAX_RESPONSE_BYTES + 1)

    class _Resp:
        def read(self, n: int = -1):
            return big[:n] if n and n > 0 else big

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(capacity_publisher, "_open", lambda req, timeout=0: _Resp())
    result = publish_capacity("prov-1", 1, coordinator_url="http://coord:8203")
    assert result["status"] == 502
    assert "too large" in result["error"]


@pytest.mark.unit
def test_http_error_body_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 500, "err", {}, io.BytesIO(b"e" * 10))

    monkeypatch.setattr(capacity_publisher, "_open", _boom)
    result = publish_capacity("prov-1", 1, coordinator_url="http://coord:8203")
    assert result["status"] == 500
