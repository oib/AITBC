# Fire-and-Forget Logging (B10/B11)

**Level**: Intermediate
**Prerequisites**: [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Fire-and-Forget Logging

---

## See Also

- **Previous Scenario**: [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
- **Related Scenario**: [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md)
- **Release Notes**: [v0.10.3 Change Log](../releases/v0.10.3/change.log)
- **Feature Documentation**: [Async Tasks Module](../../aitbc/async_tasks.py)

---

## Scenario Overview

This scenario verifies that fire-and-forget background tasks in the **agent-coordinator** (B10) and **coordinator-api** (B11) services log their exceptions instead of silently swallowing them. Scenario 24 covered B8 (blockchain-node) and B9 (edge); this scenario fills the gap for the remaining two services.

> **Difference from Scenario 24**: Scenario 24 tests `create_task_with_logging` in the blockchain-node gossip/P2P layer and edge health reporting. This scenario tests `TaskRegistry` in the agent-coordinator lifespan and `create_task_with_logging` in the coordinator-api analytics/trading services.

### Use Case

A hub operator restarts the agent-coordinator and coordinator-api services after the v0.10.3 upgrade. Background tasks (task distribution, message processing, learning sessions, market data collection) start automatically. If any of these tasks fail, the operator needs to see the error in `journalctl` — not discover it hours later from missing data or stale state.

### What You'll Learn

- How to verify the agent-coordinator's `TaskRegistry` starts background tasks with error logging (B10)
- How to verify the coordinator-api's analytics and trading services use `create_task_with_logging` (B11)
- How to trigger a background task failure and confirm it appears in logs
- How to distinguish `TaskRegistry` (long-running restartable tasks) from `create_task_with_logging` (one-shot fire-and-forget)

---

## Prerequisites

### Knowledge Required

- Familiarity with `asyncio.create_task` and fire-and-forget patterns
- Understanding of done-callbacks and exception propagation in asyncio
- Basic familiarity with `journalctl` log inspection

### Tools Required

- `journalctl` (log inspection)
- `systemctl` (service management)
- `curl` (HTTP requests to trigger task activity)

### Setup Required

- A running hub node with `aitbc-agent-coordinator` and `aitbc-coordinator-api` services active
- Access to `/opt/aitbc/aitbc/async_tasks.py` source

---

## Step-by-Step Workflow

### Step 1: Verify B10 — Agent-Coordinator Uses TaskRegistry

On the **hub node**:

```bash
# Confirm the agent-coordinator lifespan uses TaskRegistry
grep -n "TaskRegistry\|_task_registry\|create_task" /opt/aitbc/apps/agent-coordinator/src/app/lifespan.py
```

**Expected output:**

```
10:from aitbc.async_tasks import TaskRegistry
18:_task_registry = TaskRegistry()
72:_task_registry.create_task(state.task_distributor.start_distribution, name="task_distribution")
73:_task_registry.create_task(state.message_processor.start_processing, name="message_processing")
88:_task_registry.create_task(expire_old_requests, name="expire_old_requests")
```

**Interpretation:** Three background tasks are registered via `TaskRegistry`: `task_distribution`, `message_processing`, and `expire_old_requests`. The `TaskRegistry` wraps each task in a try/except that logs failures with `logger.error(..., exc_info=True)`.

### Step 2: Verify B10 — Tasks Started Successfully After Restart

```bash
# Check agent-coordinator logs for task startup messages
journalctl -u aitbc-agent-coordinator --since "1 hour ago" --no-pager | grep "Started background task"
```

**Expected output:**

```
Jul 05 15:47:18 hub.aitbc.bubuit.net aitbc-agent-coordinator[246938]: [INFO] [aitbc.async_tasks] Started background task: task_distribution
Jul 05 15:47:18 hub.aitbc.bubuit.net aitbc-agent-coordinator[246938]: [INFO] [aitbc.async_tasks] Started background task: message_processing
Jul 05 15:47:18 hub.aitbc.bubuit.net aitbc-agent-coordinator[246938]: [INFO] [aitbc.async_tasks] Started background task: expire_old_requests
```

**Interpretation:** All three B10 tasks started successfully after the restart. The `[aitbc.async_tasks]` logger prefix confirms they're tracked by `TaskRegistry`.

### Step 3: Verify B10 — TaskRegistry Error Logging Logic

```bash
# Inspect the TaskRegistry's error handling code
sed -n '44,60p' /opt/aitbc/aitbc/async_tasks.py
```

**Expected output:**

```python
        async def _wrapped() -> Any:
            while True:
                try:
                    return await coro()
                except asyncio.CancelledError:
                    logger.info("Task %s cancelled", name)
                    raise
                except Exception as exc:
                    logger.error("Task %s failed: %s", name, exc, exc_info=True)
                    if not restart:
                        raise
                    logger.info("Restarting task %s in %.1f seconds", name, restart_delay)
                    await asyncio.sleep(restart_delay)
```

**Interpretation:**

- `asyncio.CancelledError` → logged at INFO, re-raised (clean shutdown)
- Any other `Exception` → logged at ERROR with full traceback (`exc_info=True`)
- If `restart=True`, the task auto-restarts after a delay; otherwise it re-raises

> **Before B10**: `asyncio.create_task()` was called directly with no wrapping. Exceptions were silently lost (Python only logs "Task exception was never retrieved" at GC time, if at all).

### Step 4: Verify B11 — Coordinator-API Uses create_task_with_logging

```bash
# Confirm the coordinator-api analytics service uses create_task_with_logging
grep -n "create_task_with_logging" /opt/aitbc/apps/coordinator-api/src/app/contexts/analytics/services/ai_analytics/advanced_learning.py

# Confirm the coordinator-api trading services use it too
grep -rn "create_task_with_logging" /opt/aitbc/apps/coordinator-api/src/app/contexts/trading/services/
```

**Expected output:**

```
apps/coordinator-api/src/app/contexts/analytics/services/ai_analytics/advanced_learning.py:16:from aitbc.async_tasks import create_task_with_logging
apps/coordinator-api/src/app/contexts/analytics/services/ai_analytics/advanced_learning.py:189:        create_task_with_logging(self._monitor_learning_sessions(), name="monitor_learning_sessions")
apps/coordinator-api/src/app/contexts/analytics/services/ai_analytics/advanced_learning.py:190:        create_task_with_logging(self._process_federated_learning(), name="process_federated_learning")
apps/coordinator-api/src/app/contexts/analytics/services/ai_analytics/advanced_learning.py:191:        create_task_with_logging(self._optimize_model_performance(), name="optimize_model_performance")
apps/coordinator-api/src/app/contexts/analytics/services/ai_analytics/advanced_learning.py:192:        create_task_with_logging(self._cleanup_inactive_sessions(), name="cleanup_inactive_sessions")
---
apps/coordinator-api/src/app/contexts/trading/services/market_data_collector.py:19:from aitbc.async_tasks import create_task_with_logging
apps/coordinator-api/src/app/contexts/trading/services/market_data_collector.py:92:        create_task_with_logging(self._collect_data_source(source), name=f"collect_data_{source.value}")
apps/coordinator-api/src/app/contexts/trading/services/market_data_collector.py:93:        create_task_with_logging(self._aggregate_market_data(), name="aggregate_market_data")
apps/coordinator-api/src/app/contexts/trading/services/market_data_collector.py:94:        create_task_with_logging(self._cleanup_old_data(), name="cleanup_old_data")
---
apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py:15:from aitbc.async_tasks import create_task_with_logging
apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py:222:        create_task_with_logging(self._update_market_conditions(), name="update_market_conditions")
apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py:223:        create_task_with_logging(self._monitor_price_volatility(), name="monitor_price_volatility")
apps/coordinator-api/src/app/contexts/trading/services/trading_marketplace/dynamic_pricing.py:224:        create_task_with_logging(self._optimize_strategies(), name="optimize_strategies")
```

**Interpretation:** B11 is deployed across two service domains:

- **Analytics**: 4 background tasks (learning session monitoring, federated learning, model optimization, session cleanup)
- **Trading**: 6 background tasks (market data collection, aggregation, cleanup, market conditions, price volatility, strategy optimization)

### Step 5: Verify B11 — create_task_with_logging Error Handling

```bash
# Inspect the create_task_with_logging done-callback
sed -n '113,140p' /opt/aitbc/aitbc/async_tasks.py
```

**Expected output:**

```python
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

**Interpretation:** Unlike `TaskRegistry` (which wraps the coroutine in a restart loop), `create_task_with_logging` attaches a **done-callback** that logs any exception after the task completes. This is the fire-and-forget pattern — the task runs once, and if it fails, the error is logged.

### Step 6: Trigger Task Activity and Verify No Silent Failures

```bash
# Trigger agent-coordinator task activity by listing agents (causes task_distribution to process)
curl -s http://localhost:8107/api/agents 2>/dev/null | head -c 200
echo

# Trigger coordinator-api analytics by checking the analytics endpoint
curl -s http://localhost:8203/v1/analytics/summary 2>/dev/null | head -c 200
echo

# Check for any background task errors in the last 10 minutes
echo "=== Agent-coordinator task errors ==="
journalctl -u aitbc-agent-coordinator --since "10 min ago" --no-pager | grep -iE "Task.*failed|Background task.*failed" | head -5

echo "=== Coordinator-api task errors ==="
journalctl -u aitbc-coordinator-api --since "10 min ago" --no-pager | grep -iE "Task.*failed|Background task.*failed" | head -5
```

**Expected output (no errors):**

```
=== Agent-coordinator task errors ===
(no output)
=== Coordinator-api task errors ===
(no output)
```

**Interpretation:** No background task failures in the last 10 minutes. This is the happy path — tasks are running without errors.

### Step 7: Verify the Logging Infrastructure Works (Synthetic Test)

To confirm the error logging path actually works (not just that no errors occurred), run a synthetic test:

```bash
cd /opt/aitbc && ./venv/bin/python -c "
import asyncio
from aitbc.async_tasks import create_task_with_logging, TaskRegistry
import logging

# Enable logging to see the output
logging.basicConfig(level=logging.ERROR, format='[%(levelname)s] %(message)s')

async def failing_task():
    await asyncio.sleep(0.1)
    raise ValueError('Synthetic B11 test failure')

async def main():
    # Test create_task_with_logging (B11 pattern)
    task = create_task_with_logging(failing_task(), name='synthetic_b11_test')
    await asyncio.sleep(0.3)  # wait for task to complete and callback to fire

    # Test TaskRegistry (B10 pattern)
    registry = TaskRegistry()

    async def failing_coro():
        await asyncio.sleep(0.1)
        raise RuntimeError('Synthetic B10 test failure')

    # TaskRegistry.create_task takes a callable, not a coroutine
    registry.create_task(failing_coro, name='synthetic_b10_test', restart=False)
    await asyncio.sleep(0.3)

asyncio.run(main())
print('Synthetic test complete — check for ERROR lines above')
"
```

**Expected output:**

```
[ERROR] Background task synthetic_b11_test failed: Synthetic B11 test failure
Traceback (most recent call last):
  File "...", line ..., in failing_task
    raise ValueError('Synthetic B11 test failure')
ValueError: Synthetic B11 test failure
[ERROR] Task synthetic_b10_test failed: Synthetic B10 test failure
Traceback (most recent call last):
  File "...", line ..., in failing_coro
    raise RuntimeError('Synthetic B10 test failure')
RuntimeError: Synthetic B10 test failure
Synthetic test complete — check for ERROR lines above
```

**Interpretation:**

- `create_task_with_logging` (B11 pattern) logged the exception via the done-callback
- `TaskRegistry.create_task` (B10 pattern) logged the exception via the try/except wrapper
- Both include full tracebacks (`exc_info=True`)

> **Before B10/B11**: These exceptions would have been silently lost. Python only warns "Task exception was never retrieved" at garbage collection time, which may never happen if the task object is referenced.

---

## Code Examples

### B10: TaskRegistry in Agent-Coordinator Lifespan

```python
# apps/agent-coordinator/src/app/lifespan.py
from aitbc.async_tasks import TaskRegistry

_task_registry = TaskRegistry()

@asynccontextmanager
async def lifespan(app):
    # ... initialization ...
    _task_registry.create_task(state.task_distributor.start_distribution, name="task_distribution")
    _task_registry.create_task(state.message_processor.start_processing, name="message_processing")
    _task_registry.create_task(expire_old_requests, name="expire_old_requests")
    yield
    # ... shutdown: _task_registry cancels all tasks ...
```

### B11: create_task_with_logging in Coordinator-API Services

```python
# apps/coordinator-api/src/app/contexts/trading/services/market_data_collector.py
from aitbc.async_tasks import create_task_with_logging

class MarketDataCollector:
    async def start(self):
        for source in self.sources:
            create_task_with_logging(self._collect_data_source(source), name=f"collect_data_{source.value}")
        create_task_with_logging(self._aggregate_market_data(), name="aggregate_market_data")
        create_task_with_logging(self._cleanup_old_data(), name="cleanup_old_data")
```

### Two Patterns, Same Goal

| Pattern | Used by | Restarts? | How errors are caught |
|---------|---------|-----------|----------------------|
| `TaskRegistry.create_task` | B10 (agent-coordinator) | Optional (`restart=True`) | try/except wrapper around `await coro()` |
| `create_task_with_logging` | B11 (coordinator-api), B8 (blockchain-node), B9 (edge) | No (one-shot) | done-callback checks `task.exception()` |

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Verify the agent-coordinator's `TaskRegistry` starts background tasks with error logging (B10)
- Verify the coordinator-api's analytics and trading services use `create_task_with_logging` (B11)
- Confirm that background task exceptions appear in `journalctl` with full tracebacks
- Distinguish the two logging patterns (`TaskRegistry` vs `create_task_with_logging`) and when each is used
- Run a synthetic test to confirm the error logging path works end-to-end

---

## Validation

```bash
# 1. B10: agent-coordinator tasks registered via TaskRegistry
grep -c "TaskRegistry" /opt/aitbc/apps/agent-coordinator/src/app/lifespan.py
# Expected: 2 (import + instantiation)

# 2. B10: tasks started after restart
journalctl -u aitbc-agent-coordinator --since "1 hour ago" --no-pager | grep -c "Started background task"
# Expected: 3 (task_distribution, message_processing, expire_old_requests)

# 3. B11: coordinator-api uses create_task_with_logging
grep -rl "create_task_with_logging" /opt/aitbc/apps/coordinator-api/src/app/contexts/ | wc -l
# Expected: 3+ (advanced_learning.py, market_data_collector.py, dynamic_pricing.py)

# 4. Synthetic test: error logging works
cd /opt/aitbc && ./venv/bin/python -c "
import asyncio
from aitbc.async_tasks import create_task_with_logging
async def fail():
    raise ValueError('test')
async def main():
    create_task_with_logging(fail(), name='validation_test')
    await asyncio.sleep(0.2)
asyncio.run(main())
" 2>&1 | grep -c "Background task validation_test failed"
# Expected: 1 (the error was logged)
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `hub.aitbc` ↔ shop `aitbc3`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- The megaplan test suite is green: **0 failures**, **0 skipped**, and **4 expected xfails** for removed BlockSearch/TransactionSearch model tests.


## Related Resources

- [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md) (B8/B9 — blockchain-node and edge)
- [v0.10.3 Change Log](../releases/v0.10.3/change.log)
- [Async Tasks Source](../../aitbc/async_tasks.py)

---

*Last updated: 2026-08-20*
*Version: 1.2*
