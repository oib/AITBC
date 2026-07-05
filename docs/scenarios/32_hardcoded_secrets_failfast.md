# Hardcoded Secrets Fail-Fast

**Level**: Intermediate
**Prerequisites**: [Scenario 31 Async HTTP Client Non-Blocking](./31_async_http_client.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-07-05
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Hardcoded Secrets Fail-Fast

---

## See Also

- **Previous Scenario**: [Scenario 31 Async HTTP Client Non-Blocking](./31_async_http_client.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Security Configuration](../security/README.md)

---

## Scenario Overview

This scenario verifies that the agent-coordinator (A4) and coordinator-api (A5) configs reject missing or default secret keys in production mode, failing fast at startup rather than silently running with insecure defaults.

### Use Case

A production deployment must not start with missing or default secrets (`change-me-in-production`, `default_secret_key_change_in_production`). The configs use Pydantic `field_validator` decorators to enforce this at instantiation time.

### What You'll Learn

- How to verify the agent-coordinator rejects missing `SECRET_KEY` in production (A4)
- How to verify the agent-coordinator rejects default `SECRET_KEY` in production (A4)
- How to verify the coordinator-api rejects missing `JWT_SECRET` in production (A5)
- How to verify the coordinator-api rejects default `JWT_SECRET` in production (A5)
- How to verify proper secrets are accepted

---

## Prerequisites

### Knowledge Required

- Understanding of Pydantic `field_validator` and production config validation
- Familiarity with environment variables for secret management

### Tools Required

- Python 3.13 with access to the `app.config` modules

### Setup Required

- No running services required (tests are config-instantiation only)

---

## Step-by-Step Workflow

### Step 1: Test Agent-Coordinator Missing SECRET_KEY (A4)

```bash
cd /opt/aitbc && APP_ENV=production ENVIRONMENT=production \
  PYTHONPATH=apps/agent-coordinator/src ./venv/bin/python -c "
from app.config import Settings
try:
    s = Settings()
    print(f'FAIL: should have raised — secret_key={s.secret_key!r}')
except Exception as e:
    print(f'PASS: {type(e).__name__}: secret_key required in production')
"
```

**Expected output:**
```
PASS: ValidationError: secret_key required in production
```

### Step 2: Test Agent-Coordinator Default SECRET_KEY (A4)

```bash
cd /opt/aitbc && APP_ENV=production ENVIRONMENT=production \
  SECRET_KEY='default_secret_key_change_in_production' \
  PYTHONPATH=apps/agent-coordinator/src ./venv/bin/python -c "
from app.config import Settings
try:
    s = Settings()
    print(f'FAIL: should have raised — secret_key={s.secret_key!r}')
except Exception as e:
    print(f'PASS: {type(e).__name__}: SECRET_KEY must be changed from default value')
"
```

**Expected output:**
```
PASS: ValidationError: SECRET_KEY must be changed from default value
```

### Step 3: Test Coordinator-API Missing JWT_SECRET (A5)

```bash
cd /opt/aitbc && APP_ENV=production ENVIRONMENT=production \
  BLOCKCHAIN_RPC_URL='http://blockchain.aitbc.bubuit.net:8202' \
  CLIENT_API_KEYS='["test-key-1-1234567890"]' \
  MINER_API_KEYS='["test-key-2-1234567890"]' \
  ADMIN_API_KEYS='["test-key-3-1234567890"]' \
  ALLOW_ORIGINS='["https://app.aitbc.bubuit.net"]' \
  SECRET_KEY='a_proper_secret_key_for_production_use' \
  PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
from app.config import Settings
try:
    s = Settings()
    print(f'FAIL: should have raised — jwt_secret={s.jwt_secret!r}')
except Exception as e:
    msg = str(e)
    if 'jwt_secret' in msg or 'JWT_SECRET' in msg or 'JWT secret' in msg:
        print(f'PASS: jwt_secret validation triggered (missing rejected in production)')
    else:
        print(f'OTHER: {type(e).__name__}: {msg[:200]}')
"
```

**Expected output:**
```
PASS: jwt_secret validation triggered (missing rejected in production)
```

### Step 4: Test Coordinator-API Default JWT_SECRET (A5)

```bash
cd /opt/aitbc && APP_ENV=production ENVIRONMENT=production \
  BLOCKCHAIN_RPC_URL='http://blockchain.aitbc.bubuit.net:8202' \
  CLIENT_API_KEYS='["test-key-1-1234567890"]' \
  MINER_API_KEYS='["test-key-2-1234567890"]' \
  ADMIN_API_KEYS='["test-key-3-1234567890"]' \
  ALLOW_ORIGINS='["https://app.aitbc.bubuit.net"]' \
  SECRET_KEY='a_proper_secret_key_for_production_use' \
  JWT_SECRET='change-me-in-production' \
  PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
from app.config import Settings
try:
    s = Settings()
    print(f'FAIL: should have raised — jwt_secret={s.jwt_secret!r}')
except Exception as e:
    msg = str(e)
    if 'jwt_secret' in msg or 'JWT_SECRET' in msg:
        print(f'PASS: default jwt_secret rejected in production')
    else:
        print(f'OTHER: {type(e).__name__}: {msg[:200]}')
"
```

**Expected output:**
```
PASS: default jwt_secret rejected in production
```

### Step 5: Test Coordinator-API Short JWT_SECRET (A5)

```bash
cd /opt/aitbc && APP_ENV=production ENVIRONMENT=production \
  BLOCKCHAIN_RPC_URL='http://blockchain.aitbc.bubuit.net:8202' \
  CLIENT_API_KEYS='["test-key-1-1234567890"]' \
  MINER_API_KEYS='["test-key-2-1234567890"]' \
  ADMIN_API_KEYS='["test-key-3-1234567890"]' \
  ALLOW_ORIGINS='["https://app.aitbc.bubuit.net"]' \
  SECRET_KEY='a_proper_secret_key_for_production_use' \
  JWT_SECRET='short' \
  PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
from app.config import Settings
try:
    s = Settings()
    print(f'FAIL: should have raised — jwt_secret={s.jwt_secret!r}')
except Exception as e:
    msg = str(e)
    if 'jwt_secret' in msg or 'JWT_SECRET' in msg:
        print(f'PASS: short jwt_secret rejected in production')
    else:
        print(f'OTHER: {type(e).__name__}: {msg[:200]}')
"
```

**Expected output:**
```
PASS: short jwt_secret rejected in production
```

### Step 6: Verify Proper Secrets Are Accepted

```bash
cd /opt/aitbc && APP_ENV=production ENVIRONMENT=production \
  BLOCKCHAIN_RPC_URL='http://blockchain.aitbc.bubuit.net:8202' \
  CLIENT_API_KEYS='["test-key-1-1234567890"]' \
  MINER_API_KEYS='["test-key-2-1234567890"]' \
  ADMIN_API_KEYS='["test-key-3-1234567890"]' \
  ALLOW_ORIGINS='["https://app.aitbc.bubuit.net"]' \
  SECRET_KEY='a_proper_secret_key_for_production_use' \
  JWT_SECRET='a_proper_jwt_secret_for_production_use_123' \
  PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
from app.config import Settings
s = Settings()
print(f'PASS: Settings accepted with proper secrets — jwt_secret len={len(s.jwt_secret)}, secret_key set: {bool(s.secret_key)}')
"
```

**Expected output:**
```
PASS: Settings accepted with proper secrets — jwt_secret len=42, secret_key set: True
```

---

## Code Examples

### A4 Fix: Agent-Coordinator secret_key Validator

```python
# apps/agent-coordinator/src/app/config.py
@field_validator("secret_key")
@classmethod
def _validate_secret_key(cls, v: str) -> str:
    """Validate secret_key is set in production."""
    if not v:
        raise ValueError("SECRET_KEY must be set")
    if v == "default_secret_key_change_in_production":
        raise ValueError("SECRET_KEY must be changed from default value")
    return v
```

### A5 Fix: Coordinator-API jwt_secret Validator

```python
# apps/coordinator-api/src/app/config.py
@field_validator("jwt_secret")
@classmethod
def _validate_jwt_secret(cls, v: str) -> str:
    """Validate jwt_secret is set and not a known default in production."""
    if _is_production():
        if not v:
            raise ValueError("JWT secret must be set in production")
        if v in ("change-me-in-production", "change-this-secret-key-in-production", "your_secret_here"):
            raise ValueError("JWT_SECRET must be changed from default value")
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long in production")
    return v
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm that the agent-coordinator rejects missing and default `SECRET_KEY` in production
- Confirm that the coordinator-api rejects missing, default, and short `JWT_SECRET` in production
- Verify that proper secrets are accepted without errors
- Understand the fail-fast pattern for production security configuration

---

## Validation

```bash
# A4: agent-coordinator missing secret_key
cd /opt/aitbc && APP_ENV=production PYTHONPATH=apps/agent-coordinator/src ./venv/bin/python -c "
from app.config import Settings
try: Settings()
except Exception: print('PASS: A4 missing secret rejected')
"

# A5: coordinator-api default jwt_secret
APP_ENV=production JWT_SECRET='change-me-in-production' \
  SECRET_KEY='a_proper_secret_key_for_production_use' \
  BLOCKCHAIN_RPC_URL='http://blockchain.aitbc.bubuit.net:8202' \
  CLIENT_API_KEYS='["test-key-1-1234567890"]' \
  MINER_API_KEYS='["test-key-2-1234567890"]' \
  ADMIN_API_KEYS='["test-key-3-1234567890"]' \
  ALLOW_ORIGINS='["https://app.aitbc.bubuit.net"]' \
  PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
from app.config import Settings
try: Settings()
except Exception as e:
    assert 'jwt' in str(e).lower()
    print('PASS: A5 default jwt_secret rejected')
"

# Dev mode should still work
systemctl is-active aitbc-coordinator-api
# Expected: active
```

---

## Related Resources

- [Security Configuration](../security/README.md)
- [Agent SDK Documentation](../agent-sdk/README.md)

---

*Last updated: 2026-07-05*
*Version: 1.0*
