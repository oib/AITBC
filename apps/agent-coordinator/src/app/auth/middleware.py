"""
Authentication Middleware for AITBC Agent Coordinator
Implements JWT and API key authentication middleware
"""

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, List, Optional
import logging
from functools import wraps

from .jwt_handler import jwt_handler, api_key_manager

logger = logging.getLogger(__name__)

# Security schemes
security = HTTPBearer(auto_error=False)

class AuthenticationError(Exception):
    """Custom authentication error"""
    pass

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests = {}  # {user_id: [timestamp, ...]}
        self.limits = {
            "default": {"requests": 100, "window": 3600},  # 100 requests per hour
            "admin": {"requests": 1000, "window": 3600},   # 1000 requests per hour
            "api_key": {"requests": 10000, "window": 3600}  # 10000 requests per hour
        }
    
    def is_allowed(self, user_id: str, user_role: str = "default") -> Dict[str, Any]:
        """Check if user is allowed to make request"""
        import time
        from collections import deque
        
        current_time = time.time()
        
        # Get rate limit for user role
        limit_config = self.limits.get(user_role, self.limits["default"])
        max_requests = limit_config["requests"]
        window_seconds = limit_config["window"]
        
        # Initialize user request queue if not exists
        if user_id not in self.requests:
            self.requests[user_id] = deque()
        
        # Remove old requests outside the window
        user_requests = self.requests[user_id]
        while user_requests and user_requests[0] < current_time - window_seconds:
            user_requests.popleft()
        
        # Check if under limit
        if len(user_requests) < max_requests:
            user_requests.append(current_time)
            return {
                "allowed": True,
                "remaining": max_requests - len(user_requests),
                "reset_time": current_time + window_seconds
            }
        else:
            # Find when the oldest request will expire
            oldest_request = user_requests[0]
            reset_time = oldest_request + window_seconds
            
            return {
                "allowed": False,
                "remaining": 0,
                "reset_time": reset_time
            }

# Global rate limiter instance
rate_limiter = RateLimiter()

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, Any]:
    """Get current user from JWT token or API key"""
    try:
        # Try JWT authentication first
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            validation = jwt_handler.validate_token(token)
            
            if validation["valid"]:
                payload = validation["payload"]
                user_id = payload.get("user_id")
                
                # Check rate limiting
                rate_check = rate_limiter.is_allowed(
                    user_id, 
                    payload.get("role", "default")
                )
                
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": "Rate limit exceeded",
                            "reset_time": rate_check["reset_time"]
                        },
                        headers={"Retry-After": str(int(rate_check["reset_time"] - rate_limiter.requests[user_id][0]))}
                    )
                
                return {
                    "user_id": user_id,
                    "username": payload.get("username"),
                    "role": payload.get("role", "default"),
                    "permissions": payload.get("permissions", []),
                    "auth_type": "jwt"
                }
        
        # Try API key authentication
        api_key = None
        if credentials and credentials.scheme == "ApiKey":
            api_key = credentials.credentials
        else:
            # Check for API key in headers (fallback)
            # In a real implementation, you'd get this from request headers
            pass
        
        if api_key:
            validation = api_key_manager.validate_api_key(api_key)
            
            if validation["valid"]:
                user_id = validation["user_id"]
                
                # Check rate limiting for API keys
                rate_check = rate_limiter.is_allowed(user_id, "api_key")
                
                if not rate_check["allowed"]:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": "API key rate limit exceeded",
                            "reset_time": rate_check["reset_time"]
                        }
                    )
                
                return {
                    "user_id": user_id,
                    "username": f"api_user_{user_id}",
                    "role": "api",
                    "permissions": validation["permissions"],
                    "auth_type": "api_key"
                }
        
        # No valid authentication found
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

def require_permissions(required_permissions: List[str]):
    """Decorator to require specific permissions"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current user from dependency injection
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user_permissions = current_user.get("permissions", [])
            
            # Check if user has all required permissions
            missing_permissions = [
                perm for perm in required_permissions 
                if perm not in user_permissions
            ]
            
            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "Insufficient permissions",
                        "missing_permissions": missing_permissions
                    }
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_role(required_roles: List[str]):
    """Decorator to require specific role"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user_role = current_user.get("role", "default")
            
            if user_role not in required_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "Insufficient role",
                        "required_roles": required_roles,
                        "current_role": user_role
                    }
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

class SecurityHeaders:
    """Security headers middleware"""
    
    @staticmethod
    def get_security_headers() -> Dict[str, str]:
        """Get security headers for responses"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
        }

class InputValidator:
    """Input validation and sanitization"""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_password(password: str) -> Dict[str, Any]:
        """Validate password strength"""
        import re
        
        errors = []
        
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        
        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    @staticmethod
    def sanitize_input(input_string: str) -> str:
        """Sanitize user input"""
        import html
        # Basic HTML escaping
        sanitized = html.escape(input_string)
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', '\x00', '\n', '\r', '\t']
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        
        return sanitized.strip()
    
    @staticmethod
    def validate_json_structure(data: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
        """Validate JSON structure and required fields"""
        errors = []
        
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # Check for nested required fields
        for field, value in data.items():
            if isinstance(value, dict):
                nested_validation = InputValidator.validate_json_structure(
                    value, 
                    [f"{field}.{subfield}" for subfield in required_fields if subfield.startswith(f"{field}.")]
                )
                errors.extend(nested_validation["errors"])
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

# Global instances
security_headers = SecurityHeaders()
input_validator = InputValidator()
