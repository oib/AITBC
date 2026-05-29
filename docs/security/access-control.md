# Access Control

This guide covers RBAC, principle of least privilege, and service accounts.

## Role-Based Access Control (RBAC)

```python
from enum import Enum

class Role(Enum):
    ADMIN = "admin"
    USER = "user"
    MINER = "miner"
    GUEST = "guest"

def check_permission(user_role: Role, required_role: Role) -> bool:
    """Check if user has required permission"""
    role_hierarchy = {
        Role.ADMIN: 4,
        Role.MINER: 3,
        Role.USER: 2,
        Role.GUEST: 1
    }
    return role_hierarchy[user_role] >= role_hierarchy[required_role]
```

## Principle of Least Privilege

```python
# Grant minimum required permissions
def get_job(job_id: str, user_role: Role):
    """Get job with permission check"""
    if not check_permission(user_role, Role.USER):
        raise PermissionError("Insufficient permissions")
    return job_service.get_job(job_id)
```

## Service Accounts

```python
# Use service accounts for inter-service communication
SERVICE_ACCOUNT_KEY = "service-account-key"

def authenticate_service_account(key: str) -> bool:
    """Authenticate service account"""
    return key == SERVICE_ACCOUNT_KEY
```

## See Also

- [Authentication](authentication.md) - JWT and session management
- [API Key Management](api-key-management.md) - Key-based access
- [Network Security](network-security.md) - Network-level access
