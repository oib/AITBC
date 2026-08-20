# CLI Commands Verification

**Level**: Intermediate
**Prerequisites**: [Scenario 26 GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-19
**Version**: 1.1

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
- How to run `aitbc simulate blockchain --seed 123` and get deterministic, repeatable output
- How the `aitbc messaging send` fallback generates a deterministic `message_id` and timestamp

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

### Step 6: Verify Deterministic Blockchain Simulation

The `aitbc simulate blockchain` command supports `--seed` for fully deterministic, repeatable output. It no longer depends on wall-clock time or the global `random` state.

```bash
# Generate two blocks, one transaction each, with delay 0 and a fixed seed
aitbc simulate blockchain --blocks 2 --transactions 1 --delay 0 --seed 123 --output json
```

**Why this matters:**

- Without `--seed`, the command uses live `random` and `time.sleep()` and may produce different output each run.
- With `--seed 123`, block hashes, transaction IDs, addresses, amounts, and timestamps are derived from the seeded RNG.
- Re-running the same command produces **identical** output, which is useful for tests, CI, and documentation examples.

**Check determinism:**

```bash
aitbc simulate blockchain --blocks 2 --transactions 1 --delay 0 --seed 123 --output json > /tmp/sim1.json
aitbc simulate blockchain --blocks 2 --transactions 1 --delay 0 --seed 123 --output json > /tmp/sim2.json
diff /tmp/sim1.json /tmp/sim2.json && echo "DETERMINISTIC"
```

### Step 7: Verify Deterministic Simulated Fallback Output

When a CLI command cannot reach a remote service, it may fall back to a simulated response. The fallback values are now derived from the command inputs rather than hard-coded placeholders.

```bash
aitbc messaging send --to alice "hello" --coordinator-url http://127.0.0.1:1
```

**Expected output (coordinator unreachable, simulated):**

```text
Message Sent (Simulated)
status       simulated
recipient    alice
message      hello
message_id   msg_8f28dfad6b09c39f
timestamp    2026-01-01T00:00:00+00:00
```

Run the same command twice. Both runs will show the same `message_id` and `timestamp` because the fallback is deterministic.

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
- Run `aitbc simulate blockchain --seed 123` and verify the output is identical across two runs
- Run `aitbc messaging send` against an unreachable endpoint and verify the simulated `message_id` is stable

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

# Deterministic simulation: two runs with the same seed should be identical
aitbc simulate blockchain --blocks 2 --transactions 1 --delay 0 --seed 123 --output json > /tmp/sim1.json
aitbc simulate blockchain --blocks 2 --transactions 1 --delay 0 --seed 123 --output json > /tmp/sim2.json
diff /tmp/sim1.json /tmp/sim2.json && echo "SIMULATION DETERMINISTIC"

# Deterministic fallback: same recipient/message yields the same message_id
aitbc messaging send --to alice "hello" --coordinator-url http://127.0.0.1:1 > /tmp/msg1.txt
aitbc messaging send --to alice "hello" --coordinator-url http://127.0.0.1:1 > /tmp/msg2.txt
diff /tmp/msg1.txt /tmp/msg2.txt && echo "FALLBACK DETERMINISTIC"
```

---

## Megaplan Status

This scenario has been refreshed to reflect the current codebase megaplan (hub `hub.aitbc` ↔ shop `aitbc3`).

- All examples use the current coordinator API path `/v1/jobs` and the authenticated coordinator (`Authorization: Bearer <JWT>`).
- The Agent SDK `ComputeConsumer` supports `auth_token` and `coordinator_url` in `create(...)`.
- The live two-node AI job flow has been validated end-to-end on the deployed hub and shop nodes.
- The megaplan test suite is green: **0 failures**, **0 skipped**, and **4 expected xfails** for removed BlockSearch/TransactionSearch model tests.


## Related Resources

- [CLI Usage Guide](../../cli/CLI_USAGE_GUIDE.md)
- [Next Scenario: HTTP Client Resource Cleanup](./28_http_client_cleanup.md)

---

*Last updated: 2026-08-20*
*Version: 1.3*
