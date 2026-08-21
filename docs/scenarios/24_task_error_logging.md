# Fire-and-Forget Task Error Logging

**Level**: Intermediate
**Prerequisites**: [Scenario 23 Mempool Eviction Order](./23_mempool_eviction_order.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Fire-and-Forget Task Error Logging

---

## See Also

- **Previous Scenario**: [Scenario 23 Mempool Eviction Order](./23_mempool_eviction_order.md)
- **Next Scenario**: [Scenario 25 Job Submission with Payment Failure](./25_job_payment_failure.md)
- **Related**: [Scenario 35](./35_fire_and_forget_logging_b10_b11.md) (hub coordinator tasks)

---

## Scenario Overview

Background asyncio tasks on the shop node (gossip/P2P, edge health) must log failures instead of swallowing them (`create_task_with_logging`, B8/B9). Operators poke those paths with `aitbc system`, `aitbc network`, and `aitbc edge` / `aitbc gpu`.

### Use Case

If Redis or the blockchain RPC blips, the operator sees the error in logs after a CLI-triggered action — not hours later as silent stale state.

### What You'll Learn

- How to exercise edge/GPU and network from the CLI
- How to confirm failed background work is logged (validation)

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- Shop node with `aitbc-blockchain-node` and `aitbc-edge` running

---

## Step-by-Step Workflow

### Step 1: System and network probe

```bash
aitbc system check --service blockchain-node
aitbc network status
aitbc network peers
```

**Expected output:** service file present; peer/status payload or an honest network error. These calls run through the same HTTP clients the background tasks use.

### Step 2: Edge / GPU path (B9)

```bash
aitbc gpu list-gpus
aitbc edge status
```

**Expected output:** GPU list from port 8101. Edge status hits the configured agent-coordinator URL. A failure here is logged by the edge process (B9), not swallowed.

### Step 3: Restart edge via CLI and re-probe

```bash
aitbc system restart --service edge
aitbc gpu list-gpus
```

**Expected output:** restart succeeds if sudo-n is allowed; GPU list still works. Registration on blockchain is logged (success or WARNING).

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Probe shop networking and GPU/edge through `aitbc`
- Restart edge with `aitbc system restart --service edge`
- Find registration / gossip failures in logs (validation)

---

## Validation

```bash
# Direct helper (not the operator play)
cd /opt/aitbc && ./venv/bin/python -c "
import asyncio
from aitbc.async_tasks import create_task_with_logging
async def failing():
    raise ValueError('test')
async def main():
    t = create_task_with_logging(failing(), name='test')
    try:
        await t
    except ValueError:
        pass
    await asyncio.sleep(0.1)
asyncio.run(main())
print('PASS')
"

journalctl -u aitbc-blockchain-node -n 50 --no-pager | grep -iE "gossip|task.*fail" | tail -5 || true
journalctl -u aitbc-edge -n 50 --no-pager | grep -i register | tail -5 || true
```

Do **not** stop Redis as the play — that is a destructive lab step. If you do it in a dedicated lab, restart Redis immediately after.

---

## Related Resources

- [Next Scenario: Job Submission with Payment Failure](./25_job_payment_failure.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
