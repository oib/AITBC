# Web Security

This guide covers XSS prevention, CSRF protection, and SQL injection prevention.

## XSS Prevention

### Content Security Policy

```http
# HTTP header
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'
```

### Output Encoding

```python
import markupsafe

def safe_render_template(template: str, context: dict) -> str:
    """Safely render template"""
    return markupsafe.escape(template.format(**context))
```

### Input Sanitization

```python
import bleach

def sanitize_html(html: str) -> str:
    """Sanitize HTML input"""
    return bleach.clean(html, tags=['p', 'br', 'strong', 'em'], strip=True)
```

## CSRF Protection

### CSRF Tokens

```python
import secrets
from fastapi import Request

def generate_csrf_token() -> str:
    """Generate CSRF token"""
    return secrets.token_urlsafe(32)

def validate_csrf_token(request: Request, token: str) -> bool:
    """Validate CSRF token"""
    session_token = request.session.get('csrf_token')
    return secrets.compare_digest(session_token, token)
```

### SameSite Cookies

```python
from fastapi import Response

response = Response()
response.set_cookie(
    key="session",
    value="session-value",
    httponly=True,
    secure=True,
    samesite="strict"
)
```

## SQL Injection Prevention

### Parameterized Queries

```python
from sqlmodel import Session, select

# Safe: parameterized query
def get_job_safe(session: Session, job_id: str):
    statement = select(Job).where(Job.id == job_id)
    return session.exec(statement).first()

# Unsafe: string concatenation (NEVER DO THIS)
def get_job_unsafe(session: Session, job_id: str):
    query = f"SELECT * FROM job WHERE id = '{job_id}'"  # VULNERABLE
    return session.exec(query).first()
```

### ORM Usage

```python
# Use ORM instead of raw SQL
def create_job_safe(session: Session, job_data: dict):
    job = Job(**job_data)
    session.add(job)
    session.commit()
    return job
```

## See Also

- [Input Validation](input-validation.md) - Input sanitization
- [Output Encoding](output-encoding.md) - Safe output handling
- [Database Security](database-security.md) - Database protection
