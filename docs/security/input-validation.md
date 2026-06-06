# Input Validation

This guide covers input validation, sanitization, and type checking.

## Validate All Inputs

```python
from pydantic import BaseModel, validator

class JobCreate(BaseModel):
    payload: dict
    ttl_seconds: int
    
    @validator('ttl_seconds')
    def validate_ttl(cls, v):
        if v < 1 or v > 86400:
            raise ValueError('TTL must be between 1 and 86400 seconds')
        return v
    
    @validator('payload')
    def validate_payload(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Payload must be a dictionary')
        if 'model' not in v:
            raise ValueError('Payload must include model field')
        return v
```

## Sanitize User Input

```python
import re

def sanitize_input(input_string: str) -> str:
    """Sanitize user input"""
    # Remove dangerous characters
    sanitized = re.sub(r'[<>"\']', '', input_string)
    # Limit length
    return sanitized[:1000]
```

## Type Checking

```python
from typing import Any

def validate_type(value: Any, expected_type: type) -> bool:
    """Validate value type"""
    return isinstance(value, expected_type)
```

## See Also

- [Web Security](web-security.md) - XSS, CSRF, SQL injection prevention
- [Output Encoding](output-encoding.md) - Safe output handling
- [Authentication](authentication.md) - Input-based authentication
