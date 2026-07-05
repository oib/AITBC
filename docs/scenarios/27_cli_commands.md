# CLI Commands Verification

**Level**: Intermediate
**Prerequisites**: [Scenario 26 GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-07-05
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > CLI Commands Verification

---

## See Also

- **Previous Scenario**: [Scenario 26 GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)
- **Next Scenario**: [Scenario 28 HTTP Client Resource Cleanup](./28_http_client_cleanup.md)
- **Feature Documentation**: [CLI Usage Guide](../../cli/CLI_USAGE_GUIDE.md)

---

## Scenario Overview

This scenario verifies that the AITBC CLI commands work correctly after the A2 (agent command AttributeError fix), A7 (pool-hub endpoint path fix), A8 (mining endpoint path fix), and A3 (edge port correction) fixes. Each command should connect to the correct service port and not crash with AttributeErrors or 404 errors.

### Use Case

A node operator uses the CLI to check agent status, pool-hub status, mining status, and edge status. Before the fixes, these commands either crashed (AttributeError) or connected to wrong ports (404 errors).

### What You'll Learn

- How to run `aitbc agent list` without AttributeError (A2)
- How to run `aitbc pool-hub status` without 404 from blockchain node (A7)
- How to run `aitbc mining status` hitting the correct endpoint (A8)
- How to run `aitbc edge gpu list-gpus` connecting to port 8111 (A3)

---

## Prerequisites

### Knowledge Required

- Basic familiarity with the AITBC CLI command groups

### Tools Required

- AITBC CLI (`/opt/aitbc/scripts/aitbc-cli` or `aitbc` on `$PATH`)

### Setup Required

- A running shop node with blockchain-node (8202), coordinator-api (8203), and edge (8111) services

---

## Step-by-Step Workflow

### Step 1: Verify Agent Commands (A2)

The `agent list` command should not crash with AttributeError:

```bash
aitbc agent list
```

**Expected output:**
```
No local agents found
```

(Before A2 fix, this threw `AttributeError: 'module' object has no attribute ...`)

### Step 2: Verify Pool-Hub Commands (A7)

The `pool-hub status` command should connect to the pool-hub service (port 8210), not the blockchain node:

```bash
aitbc pool-hub status
```

**Expected output:**
```
Pool Hub Status (Simulated)
===========================
{
  "status": "simulated",
  "pools": 0,
  "active_pools": 0,
  "message": "RPC endpoint not available - showing simulated status"
}
```

(Before A7 fix, this returned a 404 from the blockchain node because the endpoint path was wrong.)

### Step 3: Verify Mining Commands (A8)

The `mining status` command should hit the correct mining status endpoint:

```bash
aitbc mining status
```

**Expected output:**
```
Error getting mining status: HTTP error: Client error '401 Unauthorized' for url 'http://localhost:8202/rpc/mining/status'
```

(401 means the endpoint exists but requires auth — this is correct. Before A8 fix, this returned 404 because the endpoint path was wrong.)

### Step 4: Verify Edge Commands (A3)

The `edge gpu list-gpus` command should connect to port 8111 (the edge API), not the old port 8103:

```bash
aitbc edge gpu list-gpus
```

**Expected output:**
```
Error listing GPUs: Client error '422 Unprocessable Content' for url 'http://localhost:8111/v1/gpu/'
```

(The 422 means the request reached the edge API on port 8111 — correct. Before A3 fix, this connected to port 8103 and got a connection refused.)

### Step 5: Verify Edge Status Command

```bash
aitbc edge status
```

This connects to the coordinator-api (`agent_coordinator_url`) to fetch edge status. On a shop node without the agent-coordinator running locally, it will get a connection error — this is expected behavior.

---

## Code Examples

### A2 Fix: Agent Command Imports

The agent command module was fixed to import from the correct path:

```python
# cli/aitbc_cli/commands/agent_sdk.py
# A2 fix: corrected import paths that caused AttributeError
from aitbc.agent_bridge.src.integration_layer import ...
```

### A3 Fix: Edge API Port

The CLI config default for edge API port was corrected:

```python
# cli/aitbc_cli/config.py
class CLIConfig(BaseSettings):
    edge_api_host: str = Field(default="localhost")
    edge_api_port: int = Field(default=8111)  # was 8103 before A3
```

### A7/A8 Fix: Endpoint Paths

The pool-hub and mining commands were updated to use correct endpoint paths:

```python
# cli/aitbc_cli/commands/pool_hub.py — A7: routes to 8210, not blockchain node
# cli/aitbc_cli/commands/mining.py — A8: uses /rpc/mining/status, not old path
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run `aitbc agent list` without AttributeError crashes
- Run `aitbc pool-hub status` and get a response (not 404)
- Run `aitbc mining status` and hit the correct endpoint (401, not 404)
- Run `aitbc edge gpu list-gpus` and connect to port 8111 (not 8103)

---

## Validation

```bash
# A2: agent list should not crash
aitbc agent list 2>&1 | grep -v "UserWarning" | head -3

# A7: pool-hub status should return a response (not 404)
aitbc pool-hub status 2>&1 | grep -v "UserWarning" | head -5

# A8: mining status should hit /rpc/mining/status (401, not 404)
aitbc mining status 2>&1 | grep "8202/rpc/mining/status"

# A3: edge gpu should connect to 8111
aitbc edge gpu list-gpus 2>&1 | grep "8111"
```

---

## Related Resources

- [CLI Usage Guide](../../cli/CLI_USAGE_GUIDE.md)
- [Next Scenario: HTTP Client Resource Cleanup](./28_http_client_cleanup.md)

---

*Last updated: 2026-07-05*
*Version: 1.0*
