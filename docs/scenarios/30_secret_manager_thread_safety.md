# Secret Manager Thread Safety

**Level**: Intermediate
**Prerequisites**: [Scenario 29 Database Connection Leak](./29_database_connection_leak.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Secret Manager Thread Safety

---

## See Also

- **Previous Scenario**: [Scenario 29 Database Connection Leak](./29_database_connection_leak.md)
- **Next Scenario**: [Scenario 31 Async HTTP Client Non-Blocking](./31_async_http_client.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

`SecretManager` is locked for concurrent set/get/rotate (A11). Operators do not stress the lock from a Python one-liner; they use `aitbc security` and `aitbc config` which read secrets and keys through the same process.

### Use Case

Several CLI commands touching secrets at once must not corrupt the secret store.

### What You'll Learn

- How to audit and inspect config/secrets from the CLI
- How to run the security unit tests as validation

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

---

## Step-by-Step Workflow

### Step 1: Security audit

```bash
aitbc security audit
aitbc security scan
```

**Expected output:** a score/report (live validation recorded A+ / 0 vulnerabilities on aitbc3). Must not crash under concurrent-looking sequential calls.

### Step 2: Config / secret inspection

```bash
aitbc config show
aitbc config check
aitbc config path
```

**Expected output:** redacted config; missing-key report without dumping secret values.

### Step 3: Sequential burst (stand-in for threads)

```bash
aitbc security audit
aitbc config check
aitbc security audit
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run `aitbc security` and `aitbc config` without secret leakage in output
- Confirm the A11 tests still pass (validation)

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/security/test_secrets_are_not_published.py -q
```

---

## Related Resources

- [Next Scenario: Async HTTP Client Non-Blocking](./31_async_http_client.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
