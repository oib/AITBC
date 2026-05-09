"""
API versioning utilities for AITBC
Provides API versioning for backward compatibility
"""

from typing import Optional, Dict, Any, Callable
from functools import wraps
from enum import Enum
from datetime import datetime

from .aitbc_logging import get_logger

logger = get_logger(__name__)


class APIVersion(Enum):
    """API version enumeration"""
    V1 = "v1"
    V2 = "v2"
    LATEST = "latest"


class DeprecatedAPIError(Exception):
    """Exception raised when deprecated API is called"""
    pass


def api_version(
    version: APIVersion = APIVersion.V1,
    deprecated: bool = False,
    deprecation_date: Optional[datetime] = None,
    sunset_date: Optional[datetime] = None
):
    """
    Decorator to mark API endpoint with version information
    
    Args:
        version: API version
        deprecated: Whether the endpoint is deprecated
        deprecation_date: Date when endpoint was deprecated
        sunset_date: Date when endpoint will be removed
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if deprecated:
                warning_msg = f"API endpoint {func.__name__} is deprecated"
                if sunset_date:
                    warning_msg += f" and will be removed on {sunset_date.isoformat()}"
                logger.warning(warning_msg)
            
            # Add version info to response if applicable
            result = func(*args, **kwargs)
            
            if isinstance(result, dict):
                result["_meta"] = result.get("_meta", {})
                result["_meta"]["api_version"] = version.value
                if deprecated:
                    result["_meta"]["deprecated"] = True
                    if deprecation_date:
                        result["_meta"]["deprecated_since"] = deprecation_date.isoformat()
                    if sunset_date:
                        result["_meta"]["sunset_date"] = sunset_date.isoformat()
            
            return result
        
        wrapper._api_version = version.value
        wrapper._deprecated = deprecated
        wrapper._deprecation_date = deprecation_date
        wrapper._sunset_date = sunset_date
        
        return wrapper
    
    return decorator


class APIVersionRouter:
    """
    API version router for handling multiple API versions.
    Routes requests to appropriate version handlers.
    """
    
    def __init__(self):
        """Initialize API version router"""
        self._version_handlers: Dict[str, Callable] = {}
        self._default_version = APIVersion.V1.value
    
    def register_handler(self, version: str, handler: Callable) -> None:
        """
        Register a handler for a specific API version
        
        Args:
            version: API version string
            handler: Handler function
        """
        self._version_handlers[version] = handler
        logger.info(f"Registered handler for API version {version}")
    
    def set_default_version(self, version: str) -> None:
        """
        Set default API version
        
        Args:
            version: Default version string
        """
        self._default_version = version
        logger.info(f"Set default API version to {version}")
    
    def route(self, version: Optional[str] = None) -> Callable:
        """
        Route request to appropriate version handler
        
        Args:
            version: Requested version (uses default if None)
            
        Returns:
            Handler function
            
        Raises:
            ValueError: If version is not supported
        """
        target_version = version or self._default_version
        
        if target_version not in self._version_handlers:
            raise ValueError(f"Unsupported API version: {target_version}")
        
        return self._version_handlers[target_version]
    
    def get_supported_versions(self) -> list:
        """
        Get list of supported API versions
        
        Returns:
            List of supported version strings
        """
        return list(self._version_handlers.keys())
