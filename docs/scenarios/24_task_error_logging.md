# Fire-and-Forget Task Error Logging

**Level**: Intermediate
**Prerequisites**: [Scenario 23 Mempool Eviction Order](./23_mempool_eviction_order.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Fire-and-Forget Task Error Logging

---

## See Also

- **Previous Scenario**: [Scenario 23 Mempool Eviction Order](./23_mempool_eviction_order.md)
- **Next Scenario**: [Scenario 25 Job Submission with Payment Failure](./25_job_payment_failure.md)
- **Feature Documentation**: Async Task Management

---

## Scenario Overview

This scenario verifies that background (fire-and-forget) asyncio tasks log their exceptions instead of silently swallowing them. This covers the B8 fix (blockchain-node gossip/P2P tasks use `create_task_with_logging`) and the B9 fix (edge health report task uses `create_task_with_logging`).

### Use Case

When a background task (e.g., gossip subscription, edge health report, P2P dial) fails, the error must be visible in logs so operators can diagnose issues. Before the fix, these tasks used bare `asyncio.create_task()` which silently swallowed exceptions.

### What You'll Learn

- How `create_task_with_logging` wraps `asyncio.create_task` with a done-callback
- How to verify that task failures appear in logs
- How to trigger real failures by disrupting dependencies (e.g., stopping Redis)

---

## Prerequisites

### Knowledge Required

- Understanding of asyncio background tasks
- Familiarity with `journalctl` for log inspection

### Tools Required

- `systemctl`, `journalctl` (service management)
- Python 3.13 with access to the `aitbc` package

### Setup Required

- A running shop node with `aitbc-blockchain-node` and `aitbc-edge` services
- Redis running (for gossip broker)

---

## Step-by-Step Workflow

### Step 1: Verify create_task_with_logging Works (Direct Test)

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import asyncio
from aitbc.async_tasks import create_task_with_logging

async def failing_task():
    raise RuntimeError('Test failure for B8/B9 verification')

async def main():
    task = create_task_with_logging(failing_task(), name='test_b8_failure')
    try:
        await task
    except RuntimeError:
        pass
    await asyncio.sleep(0.1)

asyncio.run(main())
print('PASS: create_task_with_logging executed and logged the failure')
"
```

**Expected output:**

```
Background task test_b8_failure failed: Test failure for B8/B9 verification
Traceback (most recent call last):
  File "<string>", line 6, in failing_task
    raise RuntimeError('Test failure for B8/B9 verification')
RuntimeError: Test failure for B8/B9 verification
PASS: create_task_with_logging executed and logged the failure
```

### Step 2: Trigger Real Gossip Failures (B8)

Stop Redis temporarily to trigger gossip subscription errors:

```bash
# Stop Redis
systemctl stop redis

# Wait for gossip failures
sleep 10

# Check blockchain-node logs for gossip errors
journalctl -u aitbc-blockchain-node --since "15 sec ago" --no-pager | grep -iE "gossip|task.*failed|redis|connection" | tail -10

# Restart Redis
systemctl start redis
```

**Expected output:**

```
Jul 05 14:33:24 aitbc3 aitbc-blockchain[988]: [ERROR] [aitbc_chain.gossip.broker] [BROKER SUB ERROR] Redis subscription error for topic blocks.ait-hub.aitbc.bubuit.net: Error Multiple exceptions: [Errno 111] Connect call failed ('127.0.0.1', 6379) connecting to localhost:6379.
Jul 05 14:33:24 aitbc3 aitbc-blockchain[988]: [INFO] [aitbc_chain.gossip.broker] [BROKER SUB] Redis subscription ended for topic: blocks.ait-hub.aitbc.bubuit.net
```

### Step 3: Verify Edge Registration Failure Is Logged (B9)

If the blockchain RPC is unavailable when edge starts, the registration failure must be logged:

```bash
# Check edge logs for registration failures
journalctl -u aitbc-edge -n 50 --no-pager | grep -iE "register|blockchain"
```

**Expected output (on failure):**

```
Jul 05 11:37:28 aitbc3 python[2207]: [WARNING] [aitbc_edge.main] Failed to register edge node on blockchain: All connection attempts failed
```

**Expected output (on success):**

```
Jul 05 14:28:13 aitbc3 python[50134]: [INFO] [aitbc_edge.main] Edge node registered on blockchain: edge-aitbc3
```

---

## Code Examples

### create_task_with_logging (B8/B9)

The function adds a done-callback that logs any unhandled exception:

```python
# aitbc/async_tasks.py
def create_task_with_logging(coro: Any, *, name: str) -> asyncio.Task[Any]:
    """Create a fire-and-forget background task with exception logging."""
    task = asyncio.create_task(coro, name=name)

    def _log_exception(t: asyncio.Task[Any]) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("Background task %s failed: %s", name, exc, exc_info=exc)

    task.add_done_callback(_log_exception)
    return task
```

### Edge Health Report Task (B9)

```python
# apps/edge/src/aitbc_edge/main.py
from aitbc.async_tasks import create_task_with_logging

health_task = create_task_with_logging(_report_health_to_coordinator(), name="edge_health_report")
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Confirm that `create_task_with_logging` logs exceptions with full tracebacks
- Verify that gossip subscription errors appear in blockchain-node logs when Redis is unavailable
- Confirm that edge registration failures are logged (not silently swallowed)

---

## Validation

```bash
# Direct test
cd /opt/aitbc && ./venv/bin/python -c "
import asyncio
from aitbc.async_tasks import create_task_with_logging

async def failing():
    raise ValueError('test')

async def main():
    t = create_task_with_logging(failing(), name='test')
    try: await t
    except ValueError: pass
    await asyncio.sleep(0.1)

asyncio.run(main())
print('PASS')
"

# Check gossip errors are logged
journalctl -u aitbc-blockchain-node -n 50 --no-pager | grep -i "gossip.*error" | tail -3

# Check edge registration is logged
journalctl -u aitbc-edge -n 50 --no-pager | grep -i "register" | tail -3
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `hub.aitbc` ↔ shop `aitbc3`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- The megaplan test suite is green: **0 failures**, **0 skipped**, and **4 expected xfails** for removed BlockSearch/TransactionSearch model tests.


## Related Resources

- Async Task Management
- [Next Scenario: Job Submission with Payment Failure](./25_job_payment_failure.md)

---

*Last updated: 2026-08-20*
*Version: 1.2*
