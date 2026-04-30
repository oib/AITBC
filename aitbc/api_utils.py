"""
API utilities for AITBC
Provides standard response formatters, pagination helpers, error response builders, and rate limit headers helpers
"""

from typing import Any, Optional, List, Dict, Union
from datetime import datetime, UTC
from fastapi import HTTPException, status
from pydantic import BaseModel


class APIResponse(BaseModel):
    """Standard API response model"""
    success: bool
    message: str
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: str = None
    
    def __init__(self, **data):
        if 'timestamp' not in data:
            data['timestamp'] = datetime.now(datetime.UTC).isoformat()
        super().__init__(**data)


class PaginatedResponse(BaseModel):
    """Paginated API response model"""
    success: bool
    message: str
    data: List[Any]
    pagination: Dict[str, Any]
    timestamp: str = None
    
    def __init__(self, **data):
        if 'timestamp' not in data:
            data['timestamp'] = datetime.now(datetime.UTC).isoformat()
        super().__init__(**data)


def success_response(message: str = "Success", data: Optional[Any] = None) -> APIResponse:
    """Create a success response"""
    return APIResponse(success=True, message=message, data=data)


def error_response(message: str, error: Optional[str] = None, status_code: int = 400) -> HTTPException:
    """Create an error response"""
    return HTTPException(
        status_code=status_code,
        detail={"success": False, "message": message, "error": error}
    )


def not_found_response(resource: str = "Resource") -> HTTPException:
    """Create a not found response"""
    return error_response(
        message=f"{resource} not found",
        error="NOT_FOUND",
        status_code=404
    )


def unauthorized_response(message: str = "Unauthorized") -> HTTPException:
    """Create an unauthorized response"""
    return error_response(
        message=message,
        error="UNAUTHORIZED",
        status_code=401
    )


def forbidden_response(message: str = "Forbidden") -> HTTPException:
    """Create a forbidden response"""
    return error_response(
        message=message,
        error="FORBIDDEN",
        status_code=403
    )


def validation_error_response(errors: List[str]) -> HTTPException:
    """Create a validation error response"""
    return error_response(
        message="Validation failed",
        error="VALIDATION_ERROR",
        status_code=422
    )


def conflict_response(message: str = "Resource conflict") -> HTTPException:
    """Create a conflict response"""
    return error_response(
        message=message,
        error="CONFLICT",
        status_code=409
    )


def internal_error_response(message: str = "Internal server error") -> HTTPException:
    """Create an internal server error response"""
    return error_response(
        message=message,
        error="INTERNAL_ERROR",
        status_code=500
    )


class PaginationParams:
    """Pagination parameters"""
    
    def __init__(self, page: int = 1, page_size: int = 10, max_page_size: int = 100):
        """Initialize pagination parameters"""
        self.page = max(1, page)
        self.page_size = min(max_page_size, max(1, page_size))
        self.offset = (self.page - 1) * self.page_size
    
    def get_limit(self) -> int:
        """Get SQL limit"""
        return self.page_size
    
    def get_offset(self) -> int:
        """Get SQL offset"""
        return self.offset


def paginate_items(items: List[Any], page: int = 1, page_size: int = 10) -> Dict[str, Any]:
    """Paginate a list of items"""
    total = len(items)
    params = PaginationParams(page, page_size)
    
    paginated_items = items[params.offset:params.offset + params.page_size]
    total_pages = (total + params.page_size - 1) // params.page_size
    
    return {
        "items": paginated_items,
        "pagination": {
            "page": params.page,
            "page_size": params.page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": params.page < total_pages,
            "has_prev": params.page > 1
        }
    }


def build_paginated_response(
    items: List[Any],
    page: int = 1,
    page_size: int = 10,
    message: str = "Success"
) -> PaginatedResponse:
    """Build a paginated API response"""
    pagination_data = paginate_items(items, page, page_size)
    
    return PaginatedResponse(
        success=True,
        message=message,
        data=pagination_data["items"],
        pagination=pagination_data["pagination"]
    )


class RateLimitHeaders:
    """Rate limit headers helper"""
    
    @staticmethod
    def get_headers(
        limit: int,
        remaining: int,
        reset: int,
        window: int
    ) -> Dict[str, str]:
        """Get rate limit headers"""
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset),
            "X-RateLimit-Window": str(window)
        }
    
    @staticmethod
    def get_retry_after(retry_after: int) -> Dict[str, str]:
        """Get retry after header"""
        return {"Retry-After": str(retry_after)}


def build_cors_headers(
    allowed_origins: List[str] = ["*"],
    allowed_methods: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowed_headers: List[str] = ["*"],
    max_age: int = 3600
) -> Dict[str, str]:
    """Build CORS headers"""
    return {
        "Access-Control-Allow-Origin": ", ".join(allowed_origins),
        "Access-Control-Allow-Methods": ", ".join(allowed_methods),
        "Access-Control-Allow-Headers": ", ".join(allowed_headers),
        "Access-Control-Max-Age": str(max_age)
    }


def build_standard_headers(
    content_type: str = "application/json",
    cache_control: Optional[str] = None,
    x_request_id: Optional[str] = None
) -> Dict[str, str]:
    """Build standard response headers"""
    headers = {
        "Content-Type": content_type,
    }
    
    if cache_control:
        headers["Cache-Control"] = cache_control
    
    if x_request_id:
        headers["X-Request-ID"] = x_request_id
    
    return headers


def validate_sort_field(field: str, allowed_fields: List[str]) -> str:
    """Validate and return sort field"""
    if field not in allowed_fields:
        raise ValueError(f"Invalid sort field: {field}. Allowed fields: {', '.join(allowed_fields)}")
    return field


def validate_sort_order(order: str) -> str:
    """Validate and return sort order"""
    order = order.upper()
    if order not in ["ASC", "DESC"]:
        raise ValueError(f"Invalid sort order: {order}. Must be 'ASC' or 'DESC'")
    return order


def build_sort_params(
    sort_by: Optional[str] = None,
    sort_order: str = "ASC",
    allowed_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Build sort parameters"""
    if sort_by and allowed_fields:
        sort_by = validate_sort_field(sort_by, allowed_fields)
        sort_order = validate_sort_order(sort_order)
        return {"sort_by": sort_by, "sort_order": sort_order}
    return {}


def filter_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """Filter dictionary to only include specified fields"""
    return {k: v for k, v in data.items() if k in fields}


def exclude_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """Exclude specified fields from dictionary"""
    return {k: v for k, v in data.items() if k not in fields}


def sanitize_response(data: Any, sensitive_fields: List[str] = None) -> Any:
    """Sanitize response by masking sensitive fields"""
    if sensitive_fields is None:
        sensitive_fields = ["password", "token", "api_key", "secret", "private_key"]
    
    if isinstance(data, dict):
        return {
            k: "***" if any(sensitive in k.lower() for sensitive in sensitive_fields) else sanitize_response(v, sensitive_fields)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [sanitize_response(item, sensitive_fields) for item in data]
    else:
        return data


def merge_responses(*responses: Union[APIResponse, Dict[str, Any]]) -> Dict[str, Any]:
    """Merge multiple responses into one"""
    merged = {"data": {}}
    
    for response in responses:
        if isinstance(response, APIResponse):
            if response.data:
                if isinstance(response.data, dict):
                    merged["data"].update(response.data)
                else:
                    merged["data"] = response.data
        elif isinstance(response, dict):
            if "data" in response:
                if isinstance(response["data"], dict):
                    merged["data"].update(response["data"])
                else:
                    merged["data"] = response["data"]
    
    return merged


def get_client_ip(request) -> str:
    """Get client IP address from request"""
    # Check for forwarded headers first
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    return request.client.host if request.client else "unknown"


def get_user_agent(request) -> str:
    """Get user agent from request"""
    return request.headers.get("User-Agent", "unknown")


def build_request_metadata(request) -> Dict[str, str]:
    """Build request metadata"""
    return {
        "client_ip": get_client_ip(request),
        "user_agent": get_user_agent(request),
        "request_id": request.headers.get("X-Request-ID", "unknown"),
        "timestamp": datetime.now(datetime.UTC).isoformat()
    }
