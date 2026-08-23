# Async HTTP Client Non-Blocking

**Level**: Intermediate
**Prerequisites**: [Scenario 30 Secret Manager Thread Safety](./30_secret_manager_thread_safety.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Async HTTP Client Non-Blocking

---

## See Also

- **Previous Scenario**: [Scenario 30 Secret Manager Thread Safety](./30_secret_manager_thread_safety.md)
- **Next Scenario**: [Scenario 32 Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

Async services use `httpx.AsyncClient` (B5), not `requests` wrapped in `run_in_executor`. Operators exercise the async RPC path with `aitbc bridge` and `aitbc explorer`.

### Use Case

Bridge health and explorer queries must not block the event loop on the node; the CLI is the client of that stack.

### What You'll Learn

- How to issue overlapping CLI reads against async RPC
- How to confirm the unit tests for the HTTP pool (validation)

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- Blockchain RPC and explorer reachable

---

## Step-by-Step Workflow

### Step 1: Async bridge client

```bash
aitbc bridge health
aitbc bridge pending
aitbc bridge security-status
```

**Expected output:** three RPC reads complete without hanging the shell.

### Step 2: Explorer (overlapping reads)

```bash
aitbc explorer chain-head
aitbc explorer network-stats
aitbc explorer latest-blocks
```

### Step 3: Fire several reads back-to-back

```bash
aitbc bridge health &
aitbc explorer chain-head &
wait
```

**Expected output:** both complete. This is not a load test; it just shows the CLI does not serialize on a stuck thread-pool `requests` call.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Use `aitbc bridge` and `aitbc explorer` as the async HTTP clients they wrap
- Confirm B5 tests still pass (validation)

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit/test_http_pool.py -q
```

---

## Related Resources

- [Next Scenario: Hardcoded Secrets Fail-Fast](./32_hardcoded_secrets_failfast.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
