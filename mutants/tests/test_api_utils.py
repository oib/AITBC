"""
Tests for API utilities
"""

from datetime import datetime
from unittest.mock import Mock

import pytest
from aitbc.api import (
    APIResponse,
    PaginatedResponse,
    PaginationParams,
    RateLimitHeaders,
    build_cors_headers,
    build_paginated_response,
    build_request_metadata,
    build_sort_params,
    build_standard_headers,
    conflict_response,
    error_response,
    exclude_fields,
    filter_fields,
    forbidden_response,
    get_client_ip,
    get_user_agent,
    internal_error_response,
    merge_responses,
    not_found_response,
    paginate_items,
    sanitize_response,
    success_response,
    unauthorized_response,
    validate_sort_field,
    validate_sort_order,
    validation_error_response,
)


class TestAPIResponse:
    """Tests for APIResponse"""

    def test_api_response_creation(self):
        """Test APIResponse creation"""
        response = APIResponse(success=True, message="Test message", data={"key": "value"})
        assert response.success is True
        assert response.message == "Test message"
        assert response.data == {"key": "value"}
        assert response.timestamp is not None

    def test_api_response_default_timestamp(self):
        """Test APIResponse auto-generates timestamp"""
        response = APIResponse(success=True, message="Test")
        assert response.timestamp is not None
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(response.timestamp)


class TestPaginatedResponse:
    """Tests for PaginatedResponse"""

    def test_paginated_response_creation(self):
        """Test PaginatedResponse creation"""
        response = PaginatedResponse(success=True, message="Success", data=[1, 2, 3], pagination={"page": 1, "total": 10})
        assert response.success is True
        assert response.data == [1, 2, 3]
        assert response.pagination == {"page": 1, "total": 10}
        assert response.timestamp is not None


class TestResponseBuilders:
    """Tests for response builder functions"""

    def test_success_response(self):
        """Test success_response function"""
        response = success_response("Operation successful", {"id": 1})
        assert response.success is True
        assert response.message == "Operation successful"
        assert response.data == {"id": 1}

    def test_success_response_no_data(self):
        """Test success_response without data"""
        response = success_response("Success")
        assert response.success is True
        assert response.message == "Success"
        assert response.data is None

    def test_error_response(self):
        """Test error_response function"""
        response = error_response("Error occurred", "ERROR_CODE", 400)
        assert response.status_code == 400
        assert response.detail["success"] is False
        assert response.detail["message"] == "Error occurred"
        assert response.detail["error"] == "ERROR_CODE"

    def test_not_found_response(self):
        """Test not_found_response function"""
        response = not_found_response("User")
        assert response.status_code == 404
        assert "User not found" in response.detail["message"]
        assert response.detail["error"] == "NOT_FOUND"

    def test_unauthorized_response(self):
        """Test unauthorized_response function"""
        response = unauthorized_response("Access denied")
        assert response.status_code == 401
        assert response.detail["message"] == "Access denied"
        assert response.detail["error"] == "UNAUTHORIZED"

    def test_forbidden_response(self):
        """Test forbidden_response function"""
        response = forbidden_response("Forbidden")
        assert response.status_code == 403
        assert response.detail["message"] == "Forbidden"
        assert response.detail["error"] == "FORBIDDEN"

    def test_validation_error_response(self):
        """Test validation_error_response function"""
        response = validation_error_response(["Field required", "Invalid format"])
        assert response.status_code == 422
        assert response.detail["error"] == "VALIDATION_ERROR"

    def test_conflict_response(self):
        """Test conflict_response function"""
        response = conflict_response("Resource already exists")
        assert response.status_code == 409
        assert response.detail["message"] == "Resource already exists"
        assert response.detail["error"] == "CONFLICT"

    def test_internal_error_response(self):
        """Test internal_error_response function"""
        response = internal_error_response("Server error")
        assert response.status_code == 500
        assert response.detail["error"] == "INTERNAL_ERROR"


class TestPaginationParams:
    """Tests for PaginationParams"""

    def test_pagination_params_defaults(self):
        """Test PaginationParams with defaults"""
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 10
        assert params.offset == 0

    def test_pagination_params_custom(self):
        """Test PaginationParams with custom values"""
        params = PaginationParams(page=2, page_size=20)
        assert params.page == 2
        assert params.page_size == 20
        assert params.offset == 20

    def test_pagination_params_page_minimum(self):
        """Test PaginationParams enforces minimum page"""
        params = PaginationParams(page=0)
        assert params.page == 1

    def test_pagination_params_page_size_minimum(self):
        """Test PaginationParams enforces minimum page_size"""
        params = PaginationParams(page_size=0)
        assert params.page_size == 1

    def test_pagination_params_page_size_maximum(self):
        """Test PaginationParams enforces maximum page_size"""
        params = PaginationParams(page_size=200, max_page_size=100)
        assert params.page_size == 100

    def test_get_limit(self):
        """Test get_limit method"""
        params = PaginationParams(page_size=25)
        assert params.get_limit() == 25

    def test_get_offset(self):
        """Test get_offset method"""
        params = PaginationParams(page=3, page_size=10)
        assert params.get_offset() == 20


class TestPaginateItems:
    """Tests for paginate_items function"""

    def test_paginate_items_basic(self):
        """Test basic pagination"""
        items = list(range(25))
        result = paginate_items(items, page=1, page_size=10)

        assert len(result["items"]) == 10
        assert result["items"] == list(range(10))
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["total"] == 25
        assert result["pagination"]["total_pages"] == 3
        assert result["pagination"]["has_next"] is True
        assert result["pagination"]["has_prev"] is False

    def test_paginate_items_second_page(self):
        """Test pagination second page"""
        items = list(range(25))
        result = paginate_items(items, page=2, page_size=10)

        assert result["items"] == list(range(10, 20))
        assert result["pagination"]["has_next"] is True
        assert result["pagination"]["has_prev"] is True

    def test_paginate_items_last_page(self):
        """Test pagination last page"""
        items = list(range(25))
        result = paginate_items(items, page=3, page_size=10)

        assert result["items"] == list(range(20, 25))
        assert result["pagination"]["has_next"] is False
        assert result["pagination"]["has_prev"] is True

    def test_paginate_items_empty_list(self):
        """Test pagination with empty list"""
        result = paginate_items([], page=1, page_size=10)

        assert result["items"] == []
        assert result["pagination"]["total"] == 0
        assert result["pagination"]["total_pages"] == 0

    def test_build_paginated_response(self):
        """Test build_paginated_response function"""
        items = list(range(15))
        response = build_paginated_response(items, page=1, page_size=10)

        assert isinstance(response, PaginatedResponse)
        assert response.success is True
        assert len(response.data) == 10
        assert response.pagination["total"] == 15


class TestRateLimitHeaders:
    """Tests for RateLimitHeaders"""

    def test_get_headers(self):
        """Test get_headers method"""
        headers = RateLimitHeaders.get_headers(limit=100, remaining=50, reset=3600, window=60)

        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "50"
        assert headers["X-RateLimit-Reset"] == "3600"
        assert headers["X-RateLimit-Window"] == "60"

    def test_get_retry_after(self):
        """Test get_retry_after method"""
        headers = RateLimitHeaders.get_retry_after(30)

        assert headers["Retry-After"] == "30"


class TestHeaderBuilders:
    """Tests for header builder functions"""

    def test_build_cors_headers_defaults(self):
        """Test build_cors_headers with defaults"""
        headers = build_cors_headers()

        assert "Access-Control-Allow-Origin" in headers
        assert "Access-Control-Allow-Methods" in headers
        assert "Access-Control-Allow-Headers" in headers
        assert "Access-Control-Max-Age" in headers

    def test_build_cors_headers_custom(self):
        """Test build_cors_headers with custom values"""
        headers = build_cors_headers(allowed_origins=["http://localhost:3000"], allowed_methods=["GET", "POST"], max_age=7200)

        assert "http://localhost:3000" in headers["Access-Control-Allow-Origin"]
        assert "GET, POST" in headers["Access-Control-Allow-Methods"]
        assert headers["Access-Control-Max-Age"] == "7200"

    def test_build_standard_headers_defaults(self):
        """Test build_standard_headers with defaults"""
        headers = build_standard_headers()

        assert headers["Content-Type"] == "application/json"
        assert "Cache-Control" not in headers
        assert "X-Request-ID" not in headers

    def test_build_standard_headers_with_options(self):
        """Test build_standard_headers with options"""
        headers = build_standard_headers(content_type="application/xml", cache_control="no-cache", x_request_id="req-123")

        assert headers["Content-Type"] == "application/xml"
        assert headers["Cache-Control"] == "no-cache"
        assert headers["X-Request-ID"] == "req-123"


class TestSortValidation:
    """Tests for sort validation functions"""

    def test_validate_sort_field_valid(self):
        """Test validate_sort_field with valid field"""
        field = validate_sort_field("name", ["name", "email", "age"])
        assert field == "name"

    def test_validate_sort_field_invalid(self):
        """Test validate_sort_field with invalid field"""
        with pytest.raises(ValueError) as exc_info:
            validate_sort_field("invalid", ["name", "email"])
        assert "Invalid sort field" in str(exc_info.value)

    def test_validate_sort_order_asc(self):
        """Test validate_sort_order with ASC"""
        order = validate_sort_order("asc")
        assert order == "ASC"

    def test_validate_sort_order_desc(self):
        """Test validate_sort_order with DESC"""
        order = validate_sort_order("desc")
        assert order == "DESC"

    def test_validate_sort_order_invalid(self):
        """Test validate_sort_order with invalid order"""
        with pytest.raises(ValueError) as exc_info:
            validate_sort_order("invalid")
        assert "Invalid sort order" in str(exc_info.value)

    def test_build_sort_params_valid(self):
        """Test build_sort_params with valid parameters"""
        params = build_sort_params(sort_by="name", sort_order="ASC", allowed_fields=["name", "email"])
        assert params == {"sort_by": "name", "sort_order": "ASC"}

    def test_build_sort_params_no_sort(self):
        """Test build_sort_params without sort_by"""
        params = build_sort_params(sort_by=None, allowed_fields=["name"])
        assert params == {}

    def test_build_sort_params_no_allowed_fields(self):
        """Test build_sort_params without allowed_fields"""
        params = build_sort_params(sort_by="name", allowed_fields=None)
        assert params == {}


class TestFieldFiltering:
    """Tests for field filtering functions"""

    def test_filter_fields(self):
        """Test filter_fields function"""
        data = {"name": "John", "email": "john@example.com", "age": 30}
        result = filter_fields(data, ["name", "email"])

        assert result == {"name": "John", "email": "john@example.com"}

    def test_exclude_fields(self):
        """Test exclude_fields function"""
        data = {"name": "John", "email": "john@example.com", "age": 30}
        result = exclude_fields(data, ["age"])

        assert result == {"name": "John", "email": "john@example.com"}


class TestSanitizeResponse:
    """Tests for sanitize_response function"""

    def test_sanitize_response_dict(self):
        """Test sanitize_response with dictionary"""
        data = {"username": "john", "password": "secret123", "email": "john@example.com"}
        result = sanitize_response(data)

        assert result["username"] == "john"
        assert result["password"] == "***"
        assert result["email"] == "john@example.com"

    def test_sanitize_response_list(self):
        """Test sanitize_response with list"""
        data = [{"username": "john", "token": "abc123"}, {"username": "jane", "token": "xyz789"}]
        result = sanitize_response(data)

        assert result[0]["username"] == "john"
        assert result[0]["token"] == "***"
        assert result[1]["username"] == "jane"
        assert result[1]["token"] == "***"

    def test_sanitize_response_custom_fields(self):
        """Test sanitize_response with custom sensitive fields"""
        data = {"username": "john", "api_key": "secret", "email": "john@example.com"}
        result = sanitize_response(data, sensitive_fields=["api_key"])

        assert result["username"] == "john"
        assert result["api_key"] == "***"
        assert result["email"] == "john@example.com"

    def test_sanitize_response_nested(self):
        """Test sanitize_response with nested structure"""
        data = {"user": {"username": "john", "password": "secret"}}
        result = sanitize_response(data)

        assert result["user"]["username"] == "john"
        assert result["user"]["password"] == "***"


class TestMergeResponses:
    """Tests for merge_responses function"""

    def test_merge_responses_api_response(self):
        """Test merge_responses with APIResponse objects"""
        response1 = success_response("Success1", {"key1": "value1"})
        response2 = success_response("Success2", {"key2": "value2"})

        result = merge_responses(response1, response2)

        assert result["data"]["key1"] == "value1"
        assert result["data"]["key2"] == "value2"

    def test_merge_responses_dict(self):
        """Test merge_responses with dict objects"""
        response1 = {"data": {"key1": "value1"}}
        response2 = {"data": {"key2": "value2"}}

        result = merge_responses(response1, response2)

        assert result["data"]["key1"] == "value1"
        assert result["data"]["key2"] == "value2"

    def test_merge_responses_mixed(self):
        """Test merge_responses with mixed types"""
        response1 = success_response("Success1", {"key1": "value1"})
        response2 = {"data": {"key2": "value2"}}

        result = merge_responses(response1, response2)

        assert result["data"]["key1"] == "value1"
        assert result["data"]["key2"] == "value2"

    def test_merge_responses_empty(self):
        """Test merge_responses with no responses"""
        result = merge_responses()
        assert result == {"data": {}}


class TestRequestHelpers:
    """Tests for request helper functions"""

    def test_get_client_ip_forwarded(self):
        """Test get_client_ip with X-Forwarded-For header"""
        request = Mock()
        request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        request.client = Mock()

        ip = get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_real_ip(self):
        """Test get_client_ip with X-Real-IP header"""
        request = Mock()
        request.headers = {"X-Real-IP": "192.168.1.2"}
        request.client = Mock()

        ip = get_client_ip(request)
        assert ip == "192.168.1.2"

    def test_get_client_ip_from_client(self):
        """Test get_client_ip from request.client"""
        request = Mock()
        request.headers = {}
        request.client = Mock()
        request.client.host = "192.168.1.3"

        ip = get_client_ip(request)
        assert ip == "192.168.1.3"

    def test_get_client_ip_unknown(self):
        """Test get_client_ip when no IP available"""
        request = Mock()
        request.headers = {}
        request.client = None

        ip = get_client_ip(request)
        assert ip == "unknown"

    def test_get_user_agent(self):
        """Test get_user_agent function"""
        request = Mock()
        request.headers = {"User-Agent": "Mozilla/5.0"}

        ua = get_user_agent(request)
        assert ua == "Mozilla/5.0"

    def test_get_user_agent_unknown(self):
        """Test get_user_agent when header missing"""
        request = Mock()
        request.headers = {}

        ua = get_user_agent(request)
        assert ua == "unknown"

    def test_build_request_metadata(self):
        """Test build_request_metadata function"""
        request = Mock()
        request.headers = {"X-Forwarded-For": "192.168.1.1", "User-Agent": "Mozilla/5.0", "X-Request-ID": "req-123"}
        request.client = Mock()
        request.client.host = "192.168.1.1"

        metadata = build_request_metadata(request)

        assert metadata["client_ip"] == "192.168.1.1"
        assert metadata["user_agent"] == "Mozilla/5.0"
        assert metadata["request_id"] == "req-123"
        assert metadata["timestamp"] is not None
