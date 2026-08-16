"""Tests for request validation middleware.

Rewritten in V23-71 tranche 3. Every test here previously exercised an interface that
v0.22's CORE-13 removed: a `max_response_size` constructor argument, a response-body size
cap, and a request cap that trusted the `Content-Length` header. CORE-13 replaced all of
that with a read of the actual body stream, precisely because a chunked request or a
spoofed `Content-Length` walked through the header check untouched.

So the file asserted the bypass it was meant to guard against, for ten days, in a middleware
that fronts every service. Nothing said so because `tests/test_middleware_validation.py`
sits at `tests/` root, which no `testpaths` entry collects.

The tests below cover the contract that exists: the body is read and capped as it arrives,
the header is not consulted at all, and the limit holds whatever the header claims.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, Request
from starlette.responses import Response

from aitbc.middleware.validation import RequestValidationMiddleware


def _request(chunks: list[bytes], headers: dict[str, str] | None = None) -> Mock:
    """A Request whose `stream()` yields `chunks`, as an ASGI server would."""

    async def _stream() -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk

    request = Mock(spec=Request)
    request.headers = headers if headers is not None else {}
    request.client = Mock(host="127.0.0.1")
    request.url = Mock(path="/test")
    request.stream = _stream
    return request


class TestRequestValidationMiddleware:
    """Tests for RequestValidationMiddleware"""

    def test_initialization(self):
        """Default request cap is 10MB."""
        middleware = RequestValidationMiddleware(Mock())

        assert middleware.max_request_size == 10 * 1024 * 1024

    def test_initialization_custom_size(self):
        """The cap is settable."""
        middleware = RequestValidationMiddleware(Mock(), max_request_size=5 * 1024 * 1024)

        assert middleware.max_request_size == 5 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_dispatch_body_within_limit(self):
        """A body under the cap reaches the app, and the read body is handed on with it."""
        middleware = RequestValidationMiddleware(Mock(), max_request_size=1024)
        request = _request([b"x" * 512])

        response = Mock(spec=Response)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result is response
        call_next.assert_called_once_with(request)
        # The stream is consumed here, so the body has to be attached for the route to read.
        assert request._body == b"x" * 512

    @pytest.mark.asyncio
    async def test_dispatch_empty_body(self):
        """No body at all is fine."""
        middleware = RequestValidationMiddleware(Mock(), max_request_size=1024)
        request = _request([])

        response = Mock(spec=Response)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result is response
        assert request._body == b""

    @pytest.mark.asyncio
    @patch("aitbc.middleware.validation.logger")
    async def test_dispatch_body_over_limit(self, mock_logger):
        """A body over the cap is refused with 413 and never reaches the app."""
        middleware = RequestValidationMiddleware(Mock(), max_request_size=1024)
        request = _request([b"x" * 2048])

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 413
        assert "Request too large" in exc_info.value.detail
        assert "1024" in exc_info.value.detail
        call_next.assert_not_called()
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_body_exactly_at_limit(self):
        """The cap is inclusive: exactly max_request_size bytes is allowed."""
        middleware = RequestValidationMiddleware(Mock(), max_request_size=1024)
        request = _request([b"x" * 1024])

        response = Mock(spec=Response)
        call_next = AsyncMock(return_value=response)

        assert await middleware.dispatch(request, call_next) is response

    @pytest.mark.asyncio
    async def test_dispatch_ignores_lying_content_length(self):
        """A `Content-Length` that understates the body does not get the body through.

        This is CORE-13. The previous middleware read the header, believed it, and let
        anything with a small enough number in it past.
        """
        middleware = RequestValidationMiddleware(Mock(), max_request_size=1024)
        request = _request([b"x" * 4096], headers={"content-length": "10"})

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 413
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_caps_chunked_body_with_no_content_length(self):
        """A chunked upload with no `Content-Length` is capped as it arrives.

        The limit trips partway through rather than after the whole body is buffered, so an
        unbounded stream cannot exhaust memory first.
        """
        middleware = RequestValidationMiddleware(Mock(), max_request_size=1024)
        request = _request([b"x" * 256] * 100)

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 413
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_does_not_read_content_length_header(self):
        """An unparseable `Content-Length` is simply not consulted."""
        middleware = RequestValidationMiddleware(Mock(), max_request_size=1024)
        request = _request([b"small"], headers={"content-length": "invalid"})

        response = Mock(spec=Response)
        call_next = AsyncMock(return_value=response)

        assert await middleware.dispatch(request, call_next) is response
