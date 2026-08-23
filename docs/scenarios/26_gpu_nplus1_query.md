# GPU Marketplace N+1 Query Fix

**Level**: Intermediate
**Prerequisites**: [Scenario 25 Job Submission with Payment Failure](./25_job_payment_failure.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > GPU Marketplace N+1 Query Fix

---

## See Also

- **Previous Scenario**: [Scenario 25 Job Submission with Payment Failure](./25_job_payment_failure.md)
- **Next Scenario**: [Scenario 27 CLI Commands](./27_cli_commands.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

Listing marketplace orders used to `session.get()` each GPU (N+1). B14 batch-fetches with `WHERE id IN (...)`. Operators hit that code by listing GPU hardware and marketplace offers through `aitbc gpu` and `aitbc market`.

### Use Case

A shop with many GPU bookings must list offers/orders without one SQL round-trip per row.

### What You'll Learn

- How to list local GPUs with `aitbc gpu list-gpus`
- How to list live software offers with `aitbc market list`
- How to confirm the batch-fetch is still in source (validation)

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- Shop GPU service (8101) and hub marketplace reachable via CLI config

---

## Step-by-Step Workflow

### Step 1: Local GPU inventory

```bash
aitbc gpu discover
aitbc gpu list-gpus
```

**Expected output:** nvidia-smi-backed discovery and the registered GPU list. No island credentials required.

### Step 2: Marketplace offers (the list path customers actually use)

```bash
aitbc market list
aitbc market list --service-type ollama
```

**Expected output:** offer rows (or an empty table). This is the live shop→hub offer path, not `curl /v1/marketplace/orders`.

### Step 3: Optional — publish an offer if the list is empty

```bash
aitbc market offer ollama llama3.2:3b 0.001 --unit per_1k_tokens --gpu-device 0
aitbc market list --service-type ollama
```

**Expected output:** a `GPU_MARKETPLACE` submission, then the offer visible in `list`. File-ownership issues with island credentials are documented in scenario 34.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Inventory GPUs and marketplace offers entirely through `aitbc`
- Distinguish `aitbc gpu` (local hardware) from `aitbc market` (software+GPU bundles)

---

## Validation

Confirm B14 is still in the coordinator source (additional validation):

```bash
cd /opt/aitbc && PYTHONPATH=apps/coordinator-api/src ./venv/bin/python -c "
import inspect
from coordinator_api.contexts.marketplace.routers.marketplace_gpu import list_orders
source = inspect.getsource(list_orders)
assert 'gpu_map' in source
assert '.in_(' in source or 'in_(' in source
print('PASS: B14 N+1 fix verified')
"
```

---

## Related Resources

- [Next Scenario: CLI Commands](./27_cli_commands.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
