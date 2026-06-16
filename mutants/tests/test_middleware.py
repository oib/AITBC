"""
Tests for AITBC middleware modules
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from aitbc.middleware.error_handler import ErrorHandlerMiddleware
from aitbc.middleware.performance import PerformanceLoggingMiddleware
from aitbc.middleware.request_id import RequestIDMiddleware
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp


class TestPerformanceLoggingMiddleware:
    """Tests for PerformanceLoggingMiddleware"""

    @pytest.mark.asyncio
    async def test_dispatch_adds_performance_header(self):
        """Test that middleware adds X-Process-Time header"""
        app = Mock(spec=ASGIApp)
        middleware = PerformanceLoggingMiddleware(app)

        request = Mock(spec=Request)
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"

        response = Mock(spec=Response)
        response.status_code = 200
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "X-Process-Time" in result.headers
        assert float(result.headers["X-Process-Time"]) >= 0

    @pytest.mark.asyncio
    async def test_dispatch_logs_performance_metrics(self):
        """Test that middleware logs performance metrics"""
        app = Mock(spec=ASGIApp)
        middleware = PerformanceLoggingMiddleware(app)

        request = Mock(spec=Request)
        request.method = "POST"
        request.url = Mock()
        request.url.path = "/api/test"

        response = Mock(spec=Response)
        response.status_code = 201
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        with patch("aitbc.middleware.performance.logger") as mock_logger:
            await middleware.dispatch(request, call_next)
            mock_logger.info.assert_called_once()
            assert "Request performance" in mock_logger.info.call_args[0][0]

    @pytest.mark.asyncio
    async def test_dispatch_measures_time_correctly(self):
        """Test that middleware measures request duration accurately"""
        app = Mock(spec=ASGIApp)
        middleware = PerformanceLoggingMiddleware(app)

        request = Mock(spec=Request)
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"

        response = Mock(spec=Response)
        response.status_code = 200
        response.headers = {}

        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        process_time = float(result.headers["X-Process-Time"])
        assert 0 <= process_time < 1.0  # Should complete in under 1 second


class TestRequestIDMiddleware:
    """Tests for RequestIDMiddleware"""

    @pytest.mark.asyncio
    async def test_dispatch_generates_request_id_when_missing(self):
        """Test that middleware generates request ID when not in headers"""
        app = Mock(spec=ASGIApp)
        middleware = RequestIDMiddleware(app)

        request = Mock(spec=Request)
        request.headers = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"
        request.client = Mock()
        request.client.host = "127.0.0.1"
        request.state = Mock()

        response = Mock(spec=Response)
        response.headers = {}
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert "X-Request-ID" in result.headers
        assert len(result.headers["X-Request-ID"]) > 0
        assert request.state.request_id == result.headers["X-Request-ID"]

    @pytest.mark.asyncio
    async def test_dispatch_uses_existing_request_id_from_header(self):
        """Test that middleware uses existing request ID from header"""
        app = Mock(spec=ASGIApp)
        middleware = RequestIDMiddleware(app)

        existing_id = "test-request-id-123"
        request = Mock(spec=Request)
        request.headers = {"X-Request-ID": existing_id}
        request.method = "POST"
        request.url = Mock()
        request.url.path = "/api/test"
        request.client = Mock()
        request.client.host = "192.168.1.1"
        request.state = Mock()

        response = Mock(spec=Response)
        response.headers = {}
        response.status_code = 201

        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result.headers["X-Request-ID"] == existing_id
        assert request.state.request_id == existing_id

    @pytest.mark.asyncio
    async def test_dispatch_logs_request_info(self):
        """Test that middleware logs request information"""
        app = Mock(spec=ASGIApp)
        middleware = RequestIDMiddleware(app)

        request = Mock(spec=Request)
        request.headers = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/test"
        request.client = Mock()
        request.client.host = "127.0.0.1"
        request.state = Mock()

        response = Mock(spec=Response)
        response.headers = {}
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        with patch("aitbc.middleware.request_id.logger") as mock_logger:
            await middleware.dispatch(request, call_next)
            assert mock_logger.info.call_count >= 2  # Logs start and completion


class TestErrorHandlerMiddleware:
    """Tests for ErrorHandlerMiddleware"""

    @pytest.mark.asyncio
    async def test_dispatch_passes_through_normal_response(self):
        """Test that middleware passes through normal responses"""
        app = Mock(spec=ASGIApp)
        middleware = ErrorHandlerMiddleware(app)

        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/test"
        request.method = "GET"

        response = Mock(spec=Response)
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result == response

    @pytest.mark.asyncio
    async def test_dispatch_handles_http_exception(self):
        """Test that middleware handles HTTPException"""
        app = Mock(spec=ASGIApp)
        middleware = ErrorHandlerMiddleware(app)

        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/error"
        request.method = "GET"

        exception = HTTPException(status_code=404, detail="Not found")
        call_next = AsyncMock(side_effect=exception)

        result = await middleware.dispatch(request, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 404
        result.body.decode() if hasattr(result, "body") else {}
        assert "error" in result.body.decode() if hasattr(result, "body") else True

    @pytest.mark.asyncio
    async def test_dispatch_handles_generic_exception(self):
        """Test that middleware handles generic exceptions"""
        app = Mock(spec=ASGIApp)
        middleware = ErrorHandlerMiddleware(app)

        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/crash"
        request.method = "POST"

        exception = ValueError("Something went wrong")
        call_next = AsyncMock(side_effect=exception)

        result = await middleware.dispatch(request, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 500

    @pytest.mark.asyncio
    async def test_dispatch_logs_http_exception(self):
        """Test that middleware logs HTTPException"""
        app = Mock(spec=ASGIApp)
        middleware = ErrorHandlerMiddleware(app)

        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/test"
        request.method = "GET"

        exception = HTTPException(status_code=400, detail="Bad request")
        call_next = AsyncMock(side_effect=exception)

        with patch("aitbc.middleware.error_handler.logger") as mock_logger:
            await middleware.dispatch(request, call_next)
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_logs_generic_exception(self):
        """Test that middleware logs generic exceptions"""
        app = Mock(spec=ASGIApp)
        middleware = ErrorHandlerMiddleware(app)

        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/test"
        request.method = "GET"

        exception = RuntimeError("Runtime error")
        call_next = AsyncMock(side_effect=exception)

        with patch("aitbc.middleware.error_handler.logger") as mock_logger:
            await middleware.dispatch(request, call_next)
            mock_logger.error.assert_called_once()
