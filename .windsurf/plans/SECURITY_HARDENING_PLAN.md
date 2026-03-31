# Security Hardening Implementation Plan

## 🎯 **Objective**
Implement comprehensive security measures to protect AITBC platform and user data.

## 🔴 **Critical Priority - 4 Week Implementation**

---

## 📋 **Phase 1: Authentication & Authorization (Week 1-2)**

### **1.1 JWT-Based Authentication**
```python
# File: apps/coordinator-api/src/app/auth/jwt_handler.py
from datetime import datetime, timedelta
from typing import Optional
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

class JWTHandler:
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
    
    def create_access_token(self, user_id: str, expires_delta: timedelta = None) -> str:
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=24)
        
        payload = {
            "user_id": user_id,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

# Usage in endpoints
@router.get("/protected")
async def protected_endpoint(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt_handler: JWTHandler = Depends()
):
    payload = jwt_handler.verify_token(credentials.credentials)
    user_id = payload["user_id"]
    return {"message": f"Hello user {user_id}"}
```

### **1.2 Role-Based Access Control (RBAC)**
```python
# File: apps/coordinator-api/src/app/auth/permissions.py
from enum import Enum
from typing import List, Set
from functools import wraps

class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    READONLY = "readonly"

class Permission(str, Enum):
    READ_DATA = "read_data"
    WRITE_DATA = "write_data"
    DELETE_DATA = "delete_data"
    MANAGE_USERS = "manage_users"
    SYSTEM_CONFIG = "system_config"
    BLOCKCHAIN_ADMIN = "blockchain_admin"

# Role permissions mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        Permission.READ_DATA, Permission.WRITE_DATA, Permission.DELETE_DATA,
        Permission.MANAGE_USERS, Permission.SYSTEM_CONFIG, Permission.BLOCKCHAIN_ADMIN
    },
    UserRole.OPERATOR: {
        Permission.READ_DATA, Permission.WRITE_DATA, Permission.BLOCKCHAIN_ADMIN
    },
    UserRole.USER: {
        Permission.READ_DATA, Permission.WRITE_DATA
    },
    UserRole.READONLY: {
        Permission.READ_DATA
    }
}

def require_permission(permission: Permission):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get user from JWT token
            user_role = get_current_user_role()  # Implement this function
            user_permissions = ROLE_PERMISSIONS.get(user_role, set())
            
            if permission not in user_permissions:
                raise HTTPException(
                    status_code=403, 
                    detail=f"Insufficient permissions for {permission}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage
@router.post("/admin/users")
@require_permission(Permission.MANAGE_USERS)
async def create_user(user_data: dict):
    return {"message": "User created successfully"}
```

### **1.3 API Key Management**
```python
# File: apps/coordinator-api/src/app/auth/api_keys.py
import secrets
from datetime import datetime, timedelta
from sqlalchemy import Column, String, DateTime, Boolean
from sqlmodel import SQLModel, Field

class APIKey(SQLModel, table=True):
    __tablename__ = "api_keys"
    
    id: str = Field(default_factory=lambda: secrets.token_hex(16), primary_key=True)
    key_hash: str = Field(index=True)
    user_id: str = Field(index=True)
    name: str
    permissions: List[str] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    is_active: bool = Field(default=True)
    last_used: Optional[datetime] = None

class APIKeyManager:
    def __init__(self):
        self.keys = {}
    
    def generate_api_key(self) -> str:
        return f"aitbc_{secrets.token_urlsafe(32)}"
    
    def create_api_key(self, user_id: str, name: str, permissions: List[str], 
                      expires_in_days: Optional[int] = None) -> tuple[str, str]:
        api_key = self.generate_api_key()
        key_hash = self.hash_key(api_key)
        
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        # Store in database
        api_key_record = APIKey(
            key_hash=key_hash,
            user_id=user_id,
            name=name,
            permissions=permissions,
            expires_at=expires_at
        )
        
        return api_key, api_key_record.id
    
    def validate_api_key(self, api_key: str) -> Optional[APIKey]:
        key_hash = self.hash_key(api_key)
        # Query database for key_hash
        # Check if key is active and not expired
        # Update last_used timestamp
        return None  # Implement actual validation
```

---

## 📋 **Phase 2: Input Validation & Rate Limiting (Week 2-3)**

### **2.1 Input Validation Middleware**
```python
# File: apps/coordinator-api/src/app/middleware/validation.py
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
import re

class SecurityValidator:
    @staticmethod
    def validate_sql_input(value: str) -> str:
        """Prevent SQL injection"""
        dangerous_patterns = [
            r"('|(\\')|(;)|(\\;))",
            r"((\%27)|(\'))\s*((\%6F)|o|(\%4F))((\%72)|r|(\%52))",
            r"((\%27)|(\'))union",
            r"exec(\s|\+)+(s|x)p\w+",
            r"UNION.*SELECT",
            r"INSERT.*INTO",
            r"DELETE.*FROM",
            r"DROP.*TABLE"
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                raise HTTPException(status_code=400, detail="Invalid input detected")
        
        return value
    
    @staticmethod
    def validate_xss_input(value: str) -> str:
        """Prevent XSS attacks"""
        xss_patterns = [
            r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>",
            r"javascript:",
            r"on\w+\s*=",
            r"<iframe",
            r"<object",
            r"<embed"
        ]
        
        for pattern in xss_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                raise HTTPException(status_code=400, detail="Invalid input detected")
        
        return value

# Pydantic models with validation
class SecureUserInput(BaseModel):
    name: str
    description: Optional[str] = None
    
    @validator('name')
    def validate_name(cls, v):
        return SecurityValidator.validate_sql_input(
            SecurityValidator.validate_xss_input(v)
        )
    
    @validator('description')
    def validate_description(cls, v):
        if v:
            return SecurityValidator.validate_sql_input(
                SecurityValidator.validate_xss_input(v)
            )
        return v
```

### **2.2 User-Specific Rate Limiting**
```python
# File: apps/coordinator-api/src/app/middleware/rate_limiting.py
from fastapi import Request, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis
from typing import Dict
from datetime import datetime, timedelta

# Redis client for rate limiting
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

class UserRateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.default_limits = {
            'readonly': {'requests': 1000, 'window': 3600},  # 1000 requests/hour
            'user': {'requests': 500, 'window': 3600},        # 500 requests/hour
            'operator': {'requests': 2000, 'window': 3600},    # 2000 requests/hour
            'admin': {'requests': 5000, 'window': 3600}        # 5000 requests/hour
        }
    
    def get_user_role(self, user_id: str) -> str:
        # Get user role from database
        return 'user'  # Implement actual role lookup
    
    def check_rate_limit(self, user_id: str, endpoint: str) -> bool:
        user_role = self.get_user_role(user_id)
        limits = self.default_limits.get(user_role, self.default_limits['user'])
        
        key = f"rate_limit:{user_id}:{endpoint}"
        current_requests = self.redis.get(key)
        
        if current_requests is None:
            # First request in window
            self.redis.setex(key, limits['window'], 1)
            return True
        
        if int(current_requests) >= limits['requests']:
            return False
        
        # Increment request count
        self.redis.incr(key)
        return True
    
    def get_remaining_requests(self, user_id: str, endpoint: str) -> int:
        user_role = self.get_user_role(user_id)
        limits = self.default_limits.get(user_role, self.default_limits['user'])
        
        key = f"rate_limit:{user_id}:{endpoint}"
        current_requests = self.redis.get(key)
        
        if current_requests is None:
            return limits['requests']
        
        return max(0, limits['requests'] - int(current_requests))

# Admin bypass functionality
class AdminRateLimitBypass:
    @staticmethod
    def can_bypass_rate_limit(user_id: str) -> bool:
        # Check if user has admin privileges
        user_role = get_user_role(user_id)  # Implement this function
        return user_role == 'admin'
    
    @staticmethod
    def log_bypass_usage(user_id: str, endpoint: str):
        # Log admin bypass usage for audit
        pass

# Usage in endpoints
@router.post("/api/data")
@limiter.limit("100/hour")  # Default limit
async def create_data(request: Request, data: dict):
    user_id = get_current_user_id(request)  # Implement this
    
    # Check user-specific rate limits
    rate_limiter = UserRateLimiter(redis_client)
    
    # Allow admin bypass
    if not AdminRateLimitBypass.can_bypass_rate_limit(user_id):
        if not rate_limiter.check_rate_limit(user_id, "/api/data"):
            raise HTTPException(
                status_code=429, 
                detail="Rate limit exceeded",
                headers={"X-RateLimit-Remaining": str(rate_limiter.get_remaining_requests(user_id, "/api/data"))}
            )
    else:
        AdminRateLimitBypass.log_bypass_usage(user_id, "/api/data")
    
    return {"message": "Data created successfully"}
```

---

## 📋 **Phase 3: Security Headers & Monitoring (Week 3-4)**

### **3.1 Security Headers Middleware**
```python
# File: apps/coordinator-api/src/app/middleware/security_headers.py
from fastapi import Request, Response
from fastapi.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.openai.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        
        # Security headers
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # HSTS (only in production)
        if app.config.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        return response

# Add to FastAPI app
app.add_middleware(SecurityHeadersMiddleware)
```

### **3.2 Security Event Logging**
```python
# File: apps/coordinator-api/src/app/security/audit_logging.py
import json
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from sqlalchemy import Column, String, DateTime, Text, Integer
from sqlmodel import SQLModel, Field

class SecurityEventType(str, Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    API_KEY_CREATED = "api_key_created"
    API_KEY_DELETED = "api_key_deleted"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    ADMIN_ACTION = "admin_action"

class SecurityEvent(SQLModel, table=True):
    __tablename__ = "security_events"
    
    id: str = Field(default_factory=lambda: secrets.token_hex(16), primary_key=True)
    event_type: SecurityEventType
    user_id: Optional[str] = Field(index=True)
    ip_address: str = Field(index=True)
    user_agent: Optional[str] = None
    endpoint: Optional[str] = None
    details: Dict[str, Any] = Field(sa_column=Column(Text))
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    severity: str = Field(default="medium")  # low, medium, high, critical

class SecurityAuditLogger:
    def __init__(self):
        self.events = []
    
    def log_event(self, event_type: SecurityEventType, user_id: Optional[str] = None,
                  ip_address: str = "", user_agent: Optional[str] = None,
                  endpoint: Optional[str] = None, details: Dict[str, Any] = None,
                  severity: str = "medium"):
        
        event = SecurityEvent(
            event_type=event_type,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            details=details or {},
            severity=severity
        )
        
        # Store in database
        # self.db.add(event)
        # self.db.commit()
        
        # Also send to external monitoring system
        self.send_to_monitoring(event)
    
    def send_to_monitoring(self, event: SecurityEvent):
        # Send to security monitoring system
        # Could be Sentry, Datadog, or custom solution
        pass

# Usage in authentication
@router.post("/auth/login")
async def login(credentials: dict, request: Request):
    username = credentials.get("username")
    password = credentials.get("password")
    ip_address = request.client.host
    user_agent = request.headers.get("user-agent")
    
    # Validate credentials
    if validate_credentials(username, password):
        audit_logger.log_event(
            SecurityEventType.LOGIN_SUCCESS,
            user_id=username,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"login_method": "password"}
        )
        return {"token": generate_jwt_token(username)}
    else:
        audit_logger.log_event(
            SecurityEventType.LOGIN_FAILURE,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"username": username, "reason": "invalid_credentials"},
            severity="high"
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
```

---

## 🎯 **Success Metrics & Testing**

### **Security Testing Checklist**
```bash
# 1. Automated security scanning
./venv/bin/bandit -r apps/coordinator-api/src/app/

# 2. Dependency vulnerability scanning
./venv/bin/safety check

# 3. Penetration testing
# - Use OWASP ZAP or Burp Suite
# - Test for common vulnerabilities
# - Verify rate limiting effectiveness

# 4. Authentication testing
# - Test JWT token validation
# - Verify role-based permissions
# - Test API key management

# 5. Input validation testing
# - Test SQL injection prevention
# - Test XSS prevention
# - Test CSRF protection
```

### **Performance Metrics**
- Authentication latency < 100ms
- Authorization checks < 50ms
- Rate limiting overhead < 10ms
- Security header overhead < 5ms

### **Security Metrics**
- Zero critical vulnerabilities
- 100% input validation coverage
- 100% endpoint protection
- Complete audit trail

---

## 📅 **Implementation Timeline**

### **Week 1**
- [ ] JWT authentication system
- [ ] Basic RBAC implementation
- [ ] API key management foundation

### **Week 2**
- [ ] Complete RBAC with permissions
- [ ] Input validation middleware
- [ ] Basic rate limiting

### **Week 3**
- [ ] User-specific rate limiting
- [ ] Security headers middleware
- [ ] Security audit logging

### **Week 4**
- [ ] Advanced security features
- [ ] Security testing and validation
- [ ] Documentation and deployment

---

**Last Updated**: March 31, 2026  
**Owner**: Security Team  
**Review Date**: April 7, 2026
