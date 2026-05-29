# API Key Management

This guide covers API key generation, storage, and rotation best practices.

## Key Generation

```python
import secrets
import string

def generate_api_key():
    """Generate a secure API key"""
    alphabet = string.ascii_letters + string.digits
    return 'aitbc_' + ''.join(secrets.choice(alphabet) for _ in range(40))
```

## Key Storage

- Never store API keys in code
- Use environment variables or secret management systems
- Rotate keys regularly (every 90 days)
- Use different keys for different environments

```bash
# Environment variable
export AITBC_API_KEY="your-api-key"
```

## Key Rotation

```python
# Rotate API keys
old_key = "old-key"
new_key = generate_api_key()

# Update database
update_api_key(old_key, new_key)

# Invalidate old key
invalidate_api_key(old_key)
```

## See Also

- [Secret Management](secret-management.md) - Advanced secret storage solutions
- [Authentication](authentication.md) - JWT and session management
- [Access Control](access-control.md) - RBAC and permissions
