# Hardcoded Secrets Fail-Fast

**Level**: Intermediate
**Prerequisites**: [Scenario 31 Async HTTP Client Non-Blocking](./31_async_http_client.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Hardcoded Secrets Fail-Fast

---

## See Also

- **Previous Scenario**: [Scenario 31 Async HTTP Client Non-Blocking](./31_async_http_client.md)
- **Next Scenario**: [Scenario 33 Exchange Financial Correctness](./33_exchange_financial_correctness.md)
- **Feature Documentation**: [Security Configuration](../security/README.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

Production configs reject missing or default secrets at startup (A4 agent-coordinator `SECRET_KEY`, A5 coordinator-api `JWT_SECRET`). Operators confirm a live node is not running on `change-me-in-production` via `aitbc security` and `aitbc config`. Instantiating Settings in Python is validation only — do not put that in the play, and do not print secrets.

### Use Case

A production unit must refuse to boot with `change-me-in-production`. A live node that already started should show a clean security audit.

### What You'll Learn

- How to audit a running node without dumping env files
- How to run the fail-fast unit tests as validation

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

---

## Step-by-Step Workflow

### Step 1: Security audit of the running node

```bash
aitbc security audit
aitbc security scan
```

**Expected output:** a passing audit (live aitbc3: score A+, 0 vulnerabilities). The audit is the operator-visible signal that production secrets are not defaults.

### Step 2: Config check (redacted)

```bash
aitbc config show
aitbc config check
aitbc config check-keys
```

**Expected output:** URLs and timeouts; API keys redacted as `***REDACTED***` or reported missing — never a raw JWT secret.

### Step 3: Do not cat env files as the play

`/etc/aitbc/aitbc-coordinator-api.env` holds `JWT_SECRET`. Reading it is an operator recovery step, not a scenario. If `aitbc security audit` fails, fix the unit env and restart with `aitbc system restart --service coordinator-api`.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Prove the live node passes `aitbc security audit`
- Inspect config without leaking secrets
- Know that A4/A5 fail-fast is enforced in Settings validators (validation tests)

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/security/test_secrets_are_not_published.py -q
```

---

## Related Resources

- [Security Configuration](../security/README.md)
- [Next Scenario: Exchange Financial Correctness](./33_exchange_financial_correctness.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
