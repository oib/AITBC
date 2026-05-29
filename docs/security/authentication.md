# Authentication

This guide covers MFA, session management, and JWT security.

## Multi-Factor Authentication (MFA)

```python
import pyotp

def generate_totp_secret() -> str:
    """Generate TOTP secret"""
    return pyotp.random_base32()

def verify_totp(secret: str, token: str) -> bool:
    """Verify TOTP token"""
    totp = pyotp.TOTP(secret)
    return totp.verify(token)
```

## Session Management

```python
import secrets
from datetime import datetime, timedelta

def create_session(user_id: str) -> dict:
    """Create session"""
    return {
        "session_id": secrets.token_urlsafe(32),
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=24)
    }

def validate_session(session: dict) -> bool:
    """Validate session"""
    return datetime.utcnow() < session["expires_at"]
```

## JWT Security

```python
import jwt
from datetime import datetime, timedelta

def generate_jwt(user_id: str, secret: str) -> str:
    """Generate JWT token"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def verify_jwt(token: str, secret: str) -> dict:
    """Verify JWT token"""
    return jwt.decode(token, secret, algorithms=["HS256"])
```

## See Also

- [API Key Management](api-key-management.md) - Key-based authentication
- [Access Control](access-control.md) - RBAC and permissions
- [Rate Limiting](rate-limiting.md) - Brute force protection
