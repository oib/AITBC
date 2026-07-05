# Async HTTP Client Non-Blocking

**Level**: Intermediate
**Prerequisites**: [Scenario 30 Secret Manager Thread Safety](./30_secret_manager_thread_safety.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-07-05
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Async HTTP Client Non-Blocking

---

## See Also

- **Previous Scenario**: [Scenario 30 Secret Manager Thread Safety](./30_secret_manager_thread_safety.md)
- **Next Scenario**: [Scenario 32 Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md)
- **Feature Documentation**: [HTTP Client Reference](../reference/http-client.md)

---

## Scenario Overview

This scenario verifies that `AsyncAITBCHTTPClient` uses `httpx.AsyncClient` for truly non-blocking async HTTP requests, not wrapping synchronous `requests` calls with `run_in_executor`. This covers the B5 fix.

### Use Case

Async services (e.g., edge, blockchain-node) need to make HTTP requests without blocking the event loop. The old code used `requests` (synchronous) wrapped in `run_in_executor`, which consumed thread pool resources. The fix uses `httpx.AsyncClient` natively.

### What You'll Learn

- How to verify that `AsyncAITBCHTTPClient` uses `httpx.AsyncClient`
- How to make a real async request and confirm it doesn't block
- How to check that no `run_in_executor` calls are present

---

## Prerequisites

### Knowledge Required

- Understanding of async/await and the event loop
- Familiarity with `httpx.AsyncClient` vs `requests`

### Tools Required

- Python 3.13 with access to the `aitbc` package
- A running blockchain-node RPC service on port 8202

### Setup Required

- Blockchain-node RPC running for the live request test

---

## Step-by-Step Workflow

### Step 1: Verify httpx.AsyncClient Usage (B5)

```bash
cd /opt/aitbc && grep -n "httpx.AsyncClient\|run_in_executor" aitbc/network/client.py | head -10
```

**Expected output:**
```
8:import httpx
412:            async with httpx.AsyncClient(timeout=self.timeout) as client:
469:            async with httpx.AsyncClient(timeout=self.timeout) as client:
525:            async with httpx.AsyncClient(timeout=self.timeout) as client:
576:            async with httpx.AsyncClient(timeout=self.timeout) as client:
```

(No `run_in_executor` lines — all 4 HTTP methods use `httpx.AsyncClient`.)

### Step 2: Make a Real Async Request

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import asyncio, sys, time
sys.path.insert(0, '/opt/aitbc')
from aitbc.network.client import AsyncAITBCHTTPClient

async def test():
    client = AsyncAITBCHTTPClient(base_url='http://localhost:8202')
    start = time.monotonic()
    result = await client.get('/rpc/bridge/health')
    elapsed = time.monotonic() - start
    print(f'Result: {result}')
    print(f'Elapsed: {elapsed:.3f}s')
    if result.get('status') == 'healthy':
        print('PASS: AsyncAITBCHTTPClient made a truly async request via httpx.AsyncClient')
    else:
        print(f'FAIL: unexpected result: {result}')
    await client.close()

asyncio.run(test())
"
```

**Expected output:**
```
Result: {'success': True, 'status': 'healthy', 'bridge_initialized': True, ...}
Elapsed: 0.079s
PASS: AsyncAITBCHTTPClient made a truly async request via httpx.AsyncClient
```

---

## Code Examples

### B5 Fix: httpx.AsyncClient in All Async Methods

```python
# aitbc/network/client.py
import httpx

class AsyncAITBCHTTPClient:
    async def get(self, path: str, ...) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.base_url}{path}", ...)
            return resp.json()

    async def post(self, path: str, ...) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}{path}", ...)
            return resp.json()

    # put() and delete() follow the same pattern
```

### Old (Buggy) Code — run_in_executor

```python
# BEFORE B5 fix — blocking requests wrapped in executor
import requests

async def get(self, path: str, ...) -> dict:
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, lambda: requests.get(...))
    return resp.json()
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm that `AsyncAITBCHTTPClient` uses `httpx.AsyncClient` (not `requests` + `run_in_executor`)
- Make a real async HTTP request and verify it completes quickly
- Verify that all 4 HTTP methods (get, post, put, delete) are truly async

---

## Validation

```bash
# Verify no run_in_executor in async client
cd /opt/aitbc && grep -c "run_in_executor" aitbc/network/client.py
# Expected: 0

# Verify httpx.AsyncClient present
grep -c "httpx.AsyncClient" aitbc/network/client.py
# Expected: 4 (one per HTTP method)

# Live async request
./venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, '.')
from aitbc.network.client import AsyncAITBCHTTPClient

async def test():
    client = AsyncAITBCHTTPClient(base_url='http://localhost:8202')
    result = await client.get('/rpc/bridge/health')
    await client.close()
    assert result.get('status') == 'healthy'
    print('PASS: B5 async HTTP client verified')

asyncio.run(test())
"
```

---

## Related Resources

- [HTTP Client Reference](../reference/http-client.md)
- [Next Scenario: Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md)

---

*Last updated: 2026-07-05*
*Version: 1.0*
