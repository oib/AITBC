# Secret Manager Thread Safety

**Level**: Intermediate
**Prerequisites**: [Scenario 29 Database Connection Leak](./29_database_connection_leak.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-07-05
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Secret Manager Thread Safety

---

## See Also

- **Previous Scenario**: [Scenario 29 Database Connection Leak](./29_database_connection_leak.md)
- **Next Scenario**: [Scenario 31 Async HTTP Client Non-Blocking](./31_async_http_client.md)
- **Feature Documentation**: Crypto & Secrets Reference

---

## Scenario Overview

This scenario verifies that the `SecretManager` class is thread-safe under concurrent access. This covers the A11 fix: a `threading.Lock` was added to protect all secret operations (set, get, rotate, cleanup).

### Use Case

Multiple threads (e.g., web request handlers, background workers) concurrently set, get, rotate, and clean up secrets. Without proper locking, race conditions can cause lost updates, corrupted state, or crashes.

### What You'll Learn

- How to run a multi-threaded stress test on `SecretManager`
- How to verify that concurrent operations complete without errors
- How to confirm that the threading lock protects all mutating operations

---

## Prerequisites

### Knowledge Required

- Understanding of Python threading and race conditions
- Familiarity with the `threading.Lock` pattern

### Tools Required

- Python 3.13 with access to the `aitbc` package

### Setup Required

- No running services required

---

## Step-by-Step Workflow

### Step 1: Run Multi-Threaded Stress Test (A11)

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import sys, threading
sys.path.insert(0, '/opt/aitbc')
from aitbc.crypto.secrets import SecretManager

mgr = SecretManager()
errors = []

def worker():
    try:
        for i in range(100):
            key = f'key_{threading.get_ident()}_{i}'
            mgr.set_secret(key, f'val_{i}')
            mgr.get_secret(key)
            if i % 10 == 0:
                mgr.rotate_secret(key, f'new_{i}')
            if i % 25 == 0:
                mgr.cleanup_expired_secrets()
    except Exception as e:
        errors.append(e)

threads = [threading.Thread(target=worker) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print(f'Errors: {len(errors)}')
if errors:
    print(f'First 3 errors: {errors[:3]}')
else:
    print('PASS: No race conditions — all 10 threads x 100 ops completed without errors (A11)')
"
```

**Expected output:**

```
Errors: 0
PASS: No race conditions — all 10 threads x 100 ops completed without errors (A11)
```

---

## Code Examples

### A11 Fix: Threading Lock

The `SecretManager` uses a `threading.Lock` to protect all operations:

```python
# aitbc/crypto/secrets.py
import threading

class SecretManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._secrets: dict[str, ...] = {}

    def set_secret(self, key: str, value: str) -> None:
        with self._lock:
            self._secrets[key] = ...

    def get_secret(self, key: str) -> str | None:
        with self._lock:
            return self._secrets.get(key)

    def rotate_secret(self, key: str, new_value: str) -> None:
        with self._lock:
            if key in self._secrets:
                self._secrets[key] = ...

    def cleanup_expired_secrets(self) -> int:
        with self._lock:
            expired = [k for k, v in self._secrets.items() if ...]
            for k in expired:
                del self._secrets[k]
            return len(expired)
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm that `SecretManager` is thread-safe under concurrent access
- Verify that 10 threads × 100 operations (set, get, rotate, cleanup) complete with 0 errors
- Understand how `threading.Lock` protects mutating operations

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import sys, threading
sys.path.insert(0, '.')
from aitbc.crypto.secrets import SecretManager

mgr = SecretManager()
errors = []

def worker():
    try:
        for i in range(100):
            key = f'key_{threading.get_ident()}_{i}'
            mgr.set_secret(key, f'val_{i}')
            mgr.get_secret(key)
            if i % 10 == 0:
                mgr.rotate_secret(key, f'new_{i}')
            if i % 25 == 0:
                mgr.cleanup_expired_secrets()
    except Exception as e:
        errors.append(e)

threads = [threading.Thread(target=worker) for _ in range(10)]
for t in threads: t.start()
for t in threads: t.join()

assert len(errors) == 0, f'FAIL: {len(errors)} race condition errors'
print('PASS: A11 thread safety verified')
"
```

---

## Related Resources

- Crypto & Secrets Reference
- [Next Scenario: Async HTTP Client Non-Blocking](./31_async_http_client.md)

---

*Last updated: 2026-07-05*
*Version: 1.0*
