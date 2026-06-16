"""
Tests for request validation middleware
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, Request
from starlette.responses import Response

from aitbc.middleware.validation import RequestValidationMiddleware


class TestRequestValidationMiddleware:
    """Tests for RequestValidationMiddleware"""

    @patch("aitbc.middleware.validation.logger")
    def test_initialization(self, mock_logger):
        """Test middleware initialization"""
        app = Mock()
        middleware = RequestValidationMiddleware(app)

        assert middleware.max_request_size == 10 * 1024 * 1024
        assert middleware.max_response_size == 10 * 1024 * 1024

    @patch("aitbc.middleware.validation.logger")
    def test_initialization_custom_sizes(self, mock_logger):
        """Test middleware with custom sizes"""
        app = Mock()
        middleware = RequestValidationMiddleware(app, max_request_size=5 * 1024 * 1024, max_response_size=5 * 1024 * 1024)

        assert middleware.max_request_size == 5 * 1024 * 1024
        assert middleware.max_response_size == 5 * 1024 * 1024

    @pytest.mark.asyncio
    @patch("aitbc.middleware.validation.logger")
    async def test_dispatch_valid_request(self, mock_logger):
        """Test dispatch with valid request size"""
        app = Mock()
        middleware = RequestValidationMiddleware(app, max_request_size=1024)

        request = Mock(spec=Request)
        request.headers = {"content-length": "512"}
        request.client = Mock(host="127.0.0.1")
        request.url = Mock(path="/test")

        call_next = AsyncMock()
        response = Mock(spec=Response)
        response.body = b"test response"
        call_next.return_value = response

        result = await middleware.dispatch(request, call_next)

        assert result == response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("aitbc.middleware.validation.logger")
    async def test_dispatch_request_too_large(self, mock_logger):
        """Test dispatch with request too large"""
        app = Mock()
        middleware = RequestValidationMiddleware(app, max_request_size=1024)

        request = Mock(spec=Request)
        request.headers = {"content-length": "2048"}
        request.client = Mock(host="127.0.0.1")

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 413
        assert "Request too large" in exc_info.value.detail
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    @patch("aitbc.middleware.validation.logger")
    async def test_dispatch_invalid_content_length(self, mock_logger):
        """Test dispatch with invalid content-length header"""
        app = Mock()
        middleware = RequestValidationMiddleware(app, max_request_size=1024)

        request = Mock(spec=Request)
        request.headers = {"content-length": "invalid"}

        call_next = AsyncMock()
        response = Mock(spec=Response)
        response.body = b"test"
        call_next.return_value = response

        result = await middleware.dispatch(request, call_next)

        assert result == response
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    @patch("aitbc.middleware.validation.logger")
    async def test_dispatch_no_content_length(self, mock_logger):
        """Test dispatch without content-length header"""
        app = Mock()
        middleware = RequestValidationMiddleware(app, max_request_size=1024)

        request = Mock(spec=Request)
        request.headers = {}

        call_next = AsyncMock()
        response = Mock(spec=Response)
        response.body = b"test"
        call_next.return_value = response

        result = await middleware.dispatch(request, call_next)

        assert result == response

    @pytest.mark.asyncio
    @patch("aitbc.middleware.validation.logger")
    async def test_dispatch_response_too_large(self, mock_logger):
        """Test dispatch with response too large"""
        app = Mock()
        middleware = RequestValidationMiddleware(app, max_response_size=100)

        request = Mock(spec=Request)
        request.headers = {}
        request.url = Mock(path="/test")

        call_next = AsyncMock()
        response = Mock(spec=Response)
        response.body = b"x" * 200  # 200 bytes, exceeds max_response_size
        call_next.return_value = response

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 500
        assert "Response too large" in exc_info.value.detail
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    @patch("aitbc.middleware.validation.logger")
    async def test_dispatch_response_no_body(self, mock_logger):
        """Test dispatch with response without body attribute"""
        app = Mock()
        middleware = RequestValidationMiddleware(app, max_response_size=100)

        request = Mock(spec=Request)
        request.headers = {}

        call_next = AsyncMock()
        response = Mock(spec=Response)
        # Response doesn't have body attribute (streaming response)
        delattr(response, "body")
        call_next.return_value = response

        result = await middleware.dispatch(request, call_next)

        assert result == response

    @pytest.mark.asyncio
    @patch("aitbc.middleware.validation.logger")
    async def test_dispatch_response_within_limit(self, mock_logger):
        """Test dispatch with response within size limit"""
        app = Mock()
        middleware = RequestValidationMiddleware(app, max_response_size=1024)

        request = Mock(spec=Request)
        request.headers = {}
        request.url = Mock(path="/test")

        call_next = AsyncMock()
        response = Mock(spec=Request)
        response.body = b"x" * 512  # 512 bytes, within limit
        call_next.return_value = response

        result = await middleware.dispatch(request, call_next)

        assert result == response
