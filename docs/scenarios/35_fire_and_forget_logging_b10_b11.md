# Fire-and-Forget Logging (B10/B11)

**Level**: Intermediate
**Prerequisites**: [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Fire-and-Forget Logging

---

## See Also

- **Previous Scenario**: [Scenario 34 Hub↔Customer Node End-to-End](./34_hub_customer_node_e2e.md)
- **Related Scenario**: [Scenario 24 Fire-and-Forget Task Error Logging](./24_task_error_logging.md)

---

## Scenario Overview

Hub background tasks must log failures: agent-coordinator `TaskRegistry` (B10) and coordinator-api `create_task_with_logging` (B11). Operators poke those services with `aitbc system` and `aitbc agent-comm`, then read journals as validation.

### Use Case

After a hub restart, task_distribution / message_processing are running; if they die, `journalctl` shows the error.

### What You'll Learn

- How to restart hub units through `aitbc system`
- How to exercise agent-comm (which starts coordinator work)
- How to confirm background-task log lines

---

## Prerequisites

### Tools Required

- `aitbc` on the hub

### Setup Required

- `aitbc-agent-coordinator` and `aitbc-coordinator-api` active on the hub

---

## Step-by-Step Workflow

### Step 1: Restart and probe the hub units

```bash
aitbc system check --service agent-coordinator
aitbc system check --service coordinator-api
aitbc system restart --service coordinator-api
```

Restarting coordinator-api is enough to re-enter the lifespan that starts B11 tasks. Only restart agent-coordinator if you can tolerate a brief messaging blip.

### Step 2: Exercise agent-comm (B10 path)

```bash
aitbc agent-comm list
aitbc agent-comm discover
aitbc agent-comm status
```

**Expected output:** agent list/discover via the `/v1` coordinator mount (Hermes is gone). Cross-node register/discover was fixed in `6200888ca`.

### Step 3: Exercise coordinator work (B11 path)

```bash
aitbc auth login --wallet customer-wallet
aitbc analytics summary
aitbc ai jobs --limit 3
```

**Expected output:** analytics summary and a job list. Those requests run on the same process that owns the fire-and-forget analytics/trading tasks.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Drive hub coordinator surfaces from `aitbc`
- Confirm B10/B11 tasks appear in journals after restart (validation)

---

## Validation

```bash
journalctl -u aitbc-agent-coordinator --since "1 hour ago" --no-pager | grep "Started background task" | tail -5
journalctl -u aitbc-coordinator-api --since "1 hour ago" --no-pager | grep -iE "background task|create_task_with_logging" | tail -5 || true
```

Source inspection (not the play) lives in `aitbc/async_tasks.py`.

---

## Related Resources

- [Scenario 24](./24_task_error_logging.md)
- [Next Scenario: Pool Hub SLA End-to-End](./36_pool_hub_sla_e2e.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
