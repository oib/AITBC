# Password Policies

This guide covers password requirements, hashing, and storage best practices.

## Password Requirements

- Minimum length: 16 characters
- Include uppercase, lowercase, numbers, special characters
- No common words or patterns
- Change every 90 days
- No reuse of previous 10 passwords

## Password Hashing

```python
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt)

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)
```

## Password Storage

- Never store passwords in plain text
- Use bcrypt or Argon2 for hashing
- Use unique salt for each password
- Never log passwords

## See Also

- [API Key Management](api-key-management.md) - Key generation and storage
- [Authentication](authentication.md) - Session and JWT management
- [Access Control](access-control.md) - User permissions
