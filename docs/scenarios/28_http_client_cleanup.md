# HTTP Client Resource Cleanup

**Level**: Intermediate
**Prerequisites**: [Scenario 27 CLI Commands](./27_cli_commands.md)
**Estimated Time**: 15 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > HTTP Client Resource Cleanup

---

## See Also

- **Previous Scenario**: [Scenario 27 CLI Commands](./27_cli_commands.md)
- **Next Scenario**: [Scenario 29 Database Connection Leak](./29_database_connection_leak.md)

---

## Scenario Overview

HTTP clients (`AITBCHTTPClient`, `BridgeClient`, edge RPC clients) must close their `httpx` sessions. Unclosed clients emit a `__del__` warning (A12/A13/A14). Operators exercise those clients by running ordinary CLI commands that open and close them.

### Use Case

After a burst of CLI calls, the edge process FD count stays flat and CLI commands complete without leaking sockets.

### What You'll Learn

- Which CLI commands open the HTTP clients under test
- How to notice an `AITBCHTTPClient was not properly closed` warning
- How to confirm FD stability (validation)

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- Edge / GPU / bridge RPC reachable for the live probes

---

## Step-by-Step Workflow

### Step 1: CLI HTTP client (A13)

```bash
aitbc agent list
aitbc explorer chain-head
```

**Expected output:** a normal table/JSON payload. A `UserWarning: AITBCHTTPClient was not properly closed` may still appear from helpers that do not use a context manager — that warning **is** the A13 safety net, not a failure of the play.

### Step 2: Bridge client (A14)

```bash
aitbc bridge health
aitbc bridge pending
```

**Expected output:** health/pending payloads. These go through `BridgeClient` as an async context manager (no warning on the happy path).

### Step 3: Edge / GPU clients (A12)

```bash
aitbc gpu list-gpus
aitbc edge status
```

**Expected output:** GPU list from 8101; edge status from the configured coordinator URL.

### Step 4: Repeat under load (CLI, not curl)

```bash
for i in $(seq 1 20); do aitbc gpu list-gpus >/dev/null; done
```

**Expected output:** 20 successful invocations. FD check is validation below.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Exercise CLI, bridge, and GPU HTTP clients from `aitbc`
- Recognize `__del__` warnings as a safety net
- Confirm the edge process does not leak FDs after a CLI burst

---

## Validation

```bash
cd /opt/aitbc && ./venv/bin/python -m pytest tests/unit/test_http_pool.py -q

EDGE_PID=$(pgrep -f "aitbc_edge" | head -1)
if [ -n "$EDGE_PID" ]; then
  echo "FDs: $(ls /proc/$EDGE_PID/fd 2>/dev/null | wc -l)"
fi
```

---

## Related Resources

- [Next Scenario: Database Connection Leak](./29_database_connection_leak.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
