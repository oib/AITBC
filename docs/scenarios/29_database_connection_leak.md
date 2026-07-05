# Database Connection Leak Prevention

**Level**: Intermediate
**Prerequisites**: [Scenario 28 HTTP Client Resource Cleanup](./28_http_client_cleanup.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-07-05
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Database Connection Leak Prevention

---

## See Also

- **Previous Scenario**: [Scenario 28 HTTP Client Resource Cleanup](./28_http_client_cleanup.md)
- **Next Scenario**: [Scenario 30 Secret Manager Thread Safety](./30_secret_manager_thread_safety.md)
- **Feature Documentation**: [Database Service Reference](../reference/database-service.md)

---

## Scenario Overview

This scenario verifies that the `SQLiteDatabaseService` properly closes database connections on garbage collection and emits a `__del__` warning when not properly closed. This covers the B7 fix: `__del__`, `close()`, `__enter__`, and `__exit__` methods were added to prevent connection leaks.

### Use Case

When a `SQLiteDatabaseService` instance is created but not properly closed (e.g., not used as a context manager), SQLite connections leak. The B7 fix adds a `__del__` safety net that warns and closes connections on garbage collection.

### What You'll Learn

- How to verify that `__del__` warnings are emitted for unclosed database services
- How to confirm that context managers properly close connections (no warning)
- How the `close()` method is idempotent and clears the connection list

---

## Prerequisites

### Knowledge Required

- Understanding of SQLite connection management
- Familiarity with Python context managers and `__del__`

### Tools Required

- Python 3.13 with access to the `aitbc` package

### Setup Required

- No running services required (uses temp files)

---

## Step-by-Step Workflow

### Step 1: Test SQLiteDatabaseService Without Close (B7)

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import sys, warnings, gc, tempfile
from pathlib import Path
sys.path.insert(0, '/opt/aitbc')
from aitbc.database.service import SQLiteDatabaseService

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / 'test.db'
    print('Test 1: SQLiteDatabaseService with open connection, no close...')
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        svc = SQLiteDatabaseService(db_path)
        conn = svc._get_connection()
        conn.execute('CREATE TABLE IF NOT EXISTS test (id INTEGER)')
        conn.commit()
        print(f'  Connections opened: {len(svc._connections)}')
        del svc
        gc.collect()
        if any('not properly closed' in str(x.message) for x in w):
            print('PASS: __del__ warning emitted and connections closed')
        else:
            print('FAIL: no __del__ warning')
"
```

**Expected output:**
```
Test 1: SQLiteDatabaseService with open connection, no close...
  Connections opened: 1
PASS: __del__ warning emitted and connections closed
```

### Step 2: Test SQLiteDatabaseService With Context Manager (B7)

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import sys, warnings, gc, tempfile
from pathlib import Path
sys.path.insert(0, '/opt/aitbc')
from aitbc.database.service import SQLiteDatabaseService

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / 'test.db'
    print('Test 2: SQLiteDatabaseService with context manager...')
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        with SQLiteDatabaseService(db_path) as svc:
            conn = svc._get_connection()
            conn.execute('SELECT 1')
        gc.collect()
        if not any('not properly closed' in str(x.message) for x in w):
            print('PASS: no warning when using context manager')
        else:
            print(f'FAIL: unexpected warning')
"
```

**Expected output:**
```
Test 2: SQLiteDatabaseService with context manager...
PASS: no warning when using context manager
```

---

## Code Examples

### B7 Fix: __del__, close(), Context Manager Support

```python
# aitbc/database/service.py
class SQLiteDatabaseService:
    def close(self) -> None:
        """Close all database connections (idempotent)."""
        if self._closed:
            return
        for conn in self._connections:
            try:
                conn.close()
            except Exception as e:
                logger.warning("Error closing connection: %s", e)
        self._connections.clear()
        self._closed = True
        logger.info("Closed all database connections")

    def __del__(self) -> None:
        """Ensure connections are closed on garbage collection."""
        if not self._closed and self._connections:
            import warnings
            warnings.warn(
                f"{self.__class__.__name__} was not properly closed — closing connections in __del__",
                stacklevel=2,
            )
            self.close()

    def __enter__(self) -> "SQLiteDatabaseService":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm that `__del__` warns and closes connections when the service isn't properly closed
- Verify that the context manager (`with` statement) properly closes connections without warnings
- Understand that `close()` is idempotent (safe to call multiple times)

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import sys, warnings, gc, tempfile
from pathlib import Path
sys.path.insert(0, '.')
from aitbc.database.service import SQLiteDatabaseService

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / 'test.db'
    # Test 1: no close -> warning
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        svc = SQLiteDatabaseService(db_path)
        svc._get_connection()
        del svc; gc.collect()
        assert any('not properly closed' in str(x.message) for x in w), 'FAIL: no warning'
    # Test 2: context manager -> no warning
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        with SQLiteDatabaseService(db_path) as svc:
            svc._get_connection()
        gc.collect()
        assert not any('not properly closed' in str(x.message) for x in w), 'FAIL: unexpected warning'
    print('PASS: B7 database connection leak prevention verified')
"
```

---

## Related Resources

- [Database Service Reference](../reference/database-service.md)
- [Next Scenario: Secret Manager Thread Safety](./30_secret_manager_thread_safety.md)

---

*Last updated: 2026-07-05*
*Version: 1.0*
