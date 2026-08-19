# HTTP Client Resource Cleanup

**Level**: Intermediate
**Prerequisites**: [Scenario 27 CLI Commands](./27_cli_commands.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > HTTP Client Resource Cleanup

---

## See Also

- **Previous Scenario**: [Scenario 27 CLI Commands](./27_cli_commands.md)
- **Next Scenario**: [Scenario 29 Database Connection Leak](./29_database_connection_leak.md)
- **Feature Documentation**: HTTP Client Reference

---

## Scenario Overview

This scenario verifies that HTTP clients in the AITBC codebase properly close their underlying `httpx.AsyncClient` connections and emit `__del__` warnings when not properly closed. This covers the A12 (edge clients), A13 (CLI HTTP client), and A14 (bridge/trading clients) fixes.

### Use Case

When HTTP clients are created but not properly closed (e.g., not used as a context manager), file descriptors and TCP connections leak. The fixes add `__del__` methods that warn about unclosed clients and `close()` methods that set the client to `None` after closing.

### What You'll Learn

- How to verify that `__del__` warnings are emitted for unclosed HTTP clients
- How to confirm that context managers properly close clients (no warning)
- How to check file descriptor stability under load on the live edge service

---

## Prerequisites

### Knowledge Required

- Understanding of Python context managers and `__del__` methods
- Familiarity with `httpx.AsyncClient` lifecycle

### Tools Required

- Python 3.13 with access to `aitbc` and `aitbc_edge` packages
- `curl` (for load testing)

### Setup Required

- A running edge service on port 8111

---

## Step-by-Step Workflow

### Step 1: Test BridgeClient **del** Warning (A14)

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import sys, warnings, asyncio, gc
sys.path.insert(0, '/opt/aitbc')
from aitbc.bridge.client import BridgeClient

# Test 1: Create client, force client creation, don't close
print('Test 1: BridgeClient without close...')
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    async def test_noclose():
        client = BridgeClient()
        client._ensure_client()  # Force httpx.AsyncClient creation
        return client
    client = asyncio.run(test_noclose())
    del client
    gc.collect()
    if any('not properly closed' in str(x.message) for x in w):
        print('PASS: __del__ warning emitted for unclosed BridgeClient')
    else:
        print('FAIL: no __del__ warning')

# Test 2: Use with context manager — should NOT warn
print()
print('Test 2: BridgeClient with context manager...')
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    async def test():
        async with BridgeClient() as client:
            client._ensure_client()
    asyncio.run(test())
    gc.collect()
    if not any('not properly closed' in str(x.message) for x in w):
        print('PASS: no warning when using context manager')
    else:
        print(f'FAIL: unexpected warning')
"
```

**Expected output:**

```
Test 1: BridgeClient without close...
PASS: __del__ warning emitted for unclosed BridgeClient

Test 2: BridgeClient with context manager...
PASS: no warning when using context manager
```

### Step 2: Test Edge BlockchainRPCClient (A12)

```bash
cd /opt/aitbc && PYTHONPATH=apps/edge/src:/opt/aitbc ./venv/bin/python -c "
import sys, warnings, asyncio, gc

# Test 1: Create without closing
print('Test 1: BlockchainRPCClient without close...')
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    from aitbc_edge.clients.blockchain_rpc import BlockchainRPCClient
    client = BlockchainRPCClient()
    del client
    gc.collect()
    if any('not properly closed' in str(x.message) for x in w):
        print('PASS: __del__ warning emitted')
    else:
        print('FAIL: no __del__ warning')

# Test 2: Use with context manager
print()
print('Test 2: BlockchainRPCClient with context manager...')
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    async def test():
        async with BlockchainRPCClient() as client:
            pass
    asyncio.run(test())
    gc.collect()
    if not any('not properly closed' in str(x.message) for x in w):
        print('PASS: no warning when using context manager')
    else:
        print(f'FAIL: unexpected warning')
"
```

**Expected output:**

```
Test 1: BlockchainRPCClient without close...
PASS: __del__ warning emitted

Test 2: BlockchainRPCClient with context manager...
PASS: no warning when using context manager
```

### Step 3: Verify CLI HTTP Client **del** Warning (A13)

Run any CLI command and check for the `AITBCHTTPClient was not properly closed` warning:

```bash
aitbc agent list 2>&1 | grep "not properly closed"
```

**Expected output:**

```
/opt/aitbc/cli/aitbc_cli/utils/chain_id.py:90: UserWarning: AITBCHTTPClient was not properly closed
```

(This warning comes from the `__del__` safety net in the CLI's HTTP client utility.)

### Step 4: Verify FD Stability Under Load (Live Service)

```bash
EDGE_PID=$(pgrep -f "aitbc_edge" | head -1)
echo "FDs before: $(ls /proc/$EDGE_PID/fd 2>/dev/null | wc -l)"

# Send 200 requests
for i in $(seq 1 200); do curl -sf http://localhost:8111/health > /dev/null 2>&1; done

echo "FDs after 200 requests: $(ls /proc/$EDGE_PID/fd 2>/dev/null | wc -l)"
```

**Expected output:**

```
FDs before: 16
FDs after 200 requests: 16
```

(FD count should remain stable — no leak.)

---

## Code Examples

### **del** Safety Net (A12/A13/A14)

All HTTP clients now have a `__del__` method that warns if the client wasn't properly closed:

```python
# aitbc/bridge/client.py (A14)
def __del__(self) -> None:
    if hasattr(self, "_client") and self._client is not None:
        import warnings
        warnings.warn(f"{self.__class__.__name__} was not properly closed", stacklevel=2)

# apps/edge/src/aitbc_edge/clients/blockchain_rpc.py (A12)
def __del__(self):
    if hasattr(self, "client") and self.client is not None:
        import warnings
        warnings.warn(f"{self.__class__.__name__} was not properly closed", stacklevel=2)
```

### close() Must Set Client to None

The `close()` method must set `self.client = None` after closing, otherwise `__del__` will warn even after proper cleanup:

```python
# CORRECT — close() sets client to None
async def close(self) -> None:
    if self.client:
        await self.client.aclose()
        self.client = None  # prevents false __del__ warning

# INCORRECT — close() doesn't clear the reference
async def close(self) -> None:
    if self.client:
        await self.client.aclose()
        # missing: self.client = None — __del__ will still warn!
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm that `__del__` warnings are emitted for unclosed HTTP clients
- Verify that context managers properly close clients (no warning)
- Check that the live edge service maintains stable FD counts under load
- Identify the `close()` must set `client = None` pattern to prevent false warnings

---

## Validation

```bash
# BridgeClient __del__ warning
cd /opt/aitbc && ./venv/bin/python -c "
import sys, warnings, asyncio, gc
sys.path.insert(0, '.')
from aitbc.bridge.client import BridgeClient
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    async def t():
        c = BridgeClient()
        c._ensure_client()
        return c
    c = asyncio.run(t())
    del c; gc.collect()
    assert any('not properly closed' in str(x.message) for x in w)
    print('PASS: A14 __del__ warning')
"

# FD stability
EDGE_PID=$(pgrep -f "aitbc_edge" | head -1)
BEFORE=$(ls /proc/$EDGE_PID/fd | wc -l)
for i in $(seq 1 100); do curl -sf http://localhost:8111/health > /dev/null 2>&1; done
AFTER=$(ls /proc/$EDGE_PID/fd | wc -l)
echo "FDs: $BEFORE -> $AFTER (should be equal)"
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `hub.aitbc` ↔ shop `aitbc3`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- Test-suite hardening is still in progress; the targeted scenarios here are green, but the full project suite still has a small number of unrelated failures.


## Related Resources

- HTTP Client Reference
- [Next Scenario: Database Connection Leak](./29_database_connection_leak.md)

---

*Last updated: 2026-08-19*
*Version: 1.1*
