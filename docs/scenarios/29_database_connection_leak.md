# Database Connection Leak Prevention

**Level**: Intermediate
**Prerequisites**: [Scenario 28 HTTP Client Resource Cleanup](./28_http_client_cleanup.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Database Connection Leak Prevention

---

## See Also

- **Previous Scenario**: [Scenario 28 HTTP Client Resource Cleanup](./28_http_client_cleanup.md)
- **Next Scenario**: [Scenario 30 Secret Manager Thread Safety](./30_secret_manager_thread_safety.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

`SQLiteDatabaseService` must close connections (`close()`, context manager, `__del__` safety net — B7). Operators hit DB-backed services through `aitbc explorer` and `aitbc system` rather than instantiating the service in a Python snippet.

### Use Case

Explorer and chain queries keep working under repeated CLI use without leaking SQLite connections.

### What You'll Learn

- How to query chain state through `aitbc explorer`
- How to treat the unit test as validation, not the play

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- Explorer API / blockchain RPC reachable

---

## Step-by-Step Workflow

### Step 1: Read-only chain queries

```bash
aitbc explorer chain-head
aitbc explorer network-stats
aitbc explorer latest-blocks
```

**Expected output:** live head hash/height, network stats, recent blocks.

### Step 2: Repeat

```bash
for i in $(seq 1 10); do aitbc explorer chain-head >/dev/null; done
aitbc explorer chain-head
```

**Expected output:** stable responses; no growth in error rate.

### Step 3: Service check

```bash
aitbc system check --service blockchain-node
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Drive DB-backed explorer queries from the CLI
- Confirm the B7 unit test still passes (validation)

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/test_database_subpackage.py -q
```

The suite may warn that `SQLiteDatabaseService` was not closed before `__del__` — that warning is the B7 safety net.

---

## Related Resources

- [Next Scenario: Secret Manager Thread Safety](./30_secret_manager_thread_safety.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
