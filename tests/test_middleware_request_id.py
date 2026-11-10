"""
Middleware Request ID Tests
Tests for AITBC middleware request ID
"""

import pytest

from aitbc.middleware.request_id import RequestIDMiddleware, _sanitize_inbound_request_id


class TestRequestIDMiddleware:
    """Test RequestIDMiddleware class"""

    def test_request_id_middleware_class_exists(self):
        """Test RequestIDMiddleware class exists"""
        assert RequestIDMiddleware is not None

    def test_request_id_middleware_can_be_instantiated(self):
        """Test RequestIDMiddleware can be instantiated"""
        middleware = RequestIDMiddleware(app=None)
        assert middleware is not None


def _scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": headers or [],
        "client": ("203.0.113.9", 50000),
        "query_string": b"",
        "state": {},
    }


async def _app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


async def _run(middleware: RequestIDMiddleware, scope: dict) -> dict:
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)
    return scope["state"]["request_id"], sent


class TestInboundRequestIdTrust:
    """APIGW-HEADER-TRUST-2 (#1681): the edge must not honor client ids."""

    async def test_trusted_path_honors_safe_inbound_id(self):
        middleware = RequestIDMiddleware(_app, trust_inbound=True)
        rid, _ = await _run(middleware, _scope([(b"x-request-id", b"abc-123_DEF.456")]))
        assert rid == "abc-123_DEF.456"

    async def test_untrusted_path_ignores_client_id(self):
        """The api-gateway edge generates its own id — a client cannot pick
        the correlation id that lands in logs, the response header and the
        upstream x-request-id stamp."""
        middleware = RequestIDMiddleware(_app, trust_inbound=False)
        rid, sent = await _run(middleware, _scope([(b"x-request-id", b"forged-id")]))
        assert rid != "forged-id"
        # the response reflects the generated id, never the client's
        start = next(m for m in sent if m["type"] == "http.response.start")
        echoed = dict(start["headers"])[b"x-request-id"].decode()
        assert echoed == rid

    async def test_hostile_inbound_id_rejected_even_when_trusted(self):
        """Log/response injection bytes never reach the correlation id."""
        middleware = RequestIDMiddleware(_app, trust_inbound=True)
        for hostile in (b"a\nb", b"x\x00y", b"a b", b"a;b", b"' OR 1=1--"):
            rid, _ = await _run(middleware, _scope([(b"x-request-id", hostile)]))
            assert rid != hostile.decode("latin1")
            assert "\n" not in rid and "\x00" not in rid

    async def test_overlong_inbound_id_rejected(self):
        middleware = RequestIDMiddleware(_app, trust_inbound=True)
        rid, _ = await _run(middleware, _scope([(b"x-request-id", b"x" * 129)]))
        assert rid != "x" * 129


class TestSanitizeInboundRequestId:
    def test_accepts_uuid_and_hex(self):
        assert _sanitize_inbound_request_id("9f8e7d6c-5b4a-3210-fedc-ba9876543210") is not None
        assert _sanitize_inbound_request_id("deadbeef" * 8) is not None

    def test_rejects_empty_and_control_chars(self):
        assert _sanitize_inbound_request_id(None) is None
        assert _sanitize_inbound_request_id("") is None
        assert _sanitize_inbound_request_id("   ") is None
        assert _sanitize_inbound_request_id("a\rb") is None
        assert _sanitize_inbound_request_id("a\x1bb") is None

    def test_rejects_over_128_chars(self):
        assert _sanitize_inbound_request_id("a" * 128) == "a" * 128
        assert _sanitize_inbound_request_id("a" * 129) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
