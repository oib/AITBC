# CLI Commands Verification

**Level**: Intermediate
**Prerequisites**: [Scenario 26 GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.4

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > CLI Commands Verification

---

## See Also

- **Previous Scenario**: [Scenario 26 GPU Marketplace N+1 Query Fix](./26_gpu_nplus1_query.md)
- **Next Scenario**: [Scenario 28 HTTP Client Resource Cleanup](./28_http_client_cleanup.md)
- **Feature Documentation**: [CLI README](../../cli/README.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

> **Live vs. simulated:** This scenario exercises several CLI groups. `aitbc messaging` and any `aitbc simulate` commands can produce `(Simulated)` output. Other groups (`aitbc agent`, `aitbc pool-hub`, `aitbc mining`, `aitbc gpu`) are live when their services are running.

Smoke-test the CLI groups that used to crash or hit the wrong port (A2 agent list, A7 pool-hub, A8 mining status, A3 edge/GPU port). Also re-check deterministic `simulate` and `messaging` fallbacks.

### Use Case

A node operator runs a short `aitbc` checklist after an upgrade.

### What You'll Learn

- The live command for each historically-broken group
- How to tell live data from deterministic simulated fallbacks

---

## Prerequisites

### Tools Required

- AITBC CLI (`aitbc`) on `$PATH` — not `/opt/aitbc/scripts/aitbc-cli`

### Setup Required

- Shop node with blockchain RPC 8202, coordinator 8203, GPU 8101, edge 8111

---

## Step-by-Step Workflow

### Step 1: Agent list (A2)

```bash
aitbc agent list
```

**Expected output:** a table or `No local agents found`. Must not raise `AttributeError`.

### Step 2: Pool-hub (A7)

```bash
aitbc pool-hub status
aitbc pool-hub sla
```

**Expected output:** live JSON from the hub (`status: ok`, `db`/`redis` flags) when discovery is configured. Simulated output is only acceptable if the hub URL cannot be resolved — on `aitbc3` it should be live (scenario 36).

### Step 3: Mining (A8)

```bash
aitbc mining status
```

**Expected output:** a status payload, or HTTP 401 on `/rpc/mining/status` (endpoint exists). Must not 404.

### Step 4: GPU list (A3 / not edge-on-8103)

```bash
aitbc gpu list-gpus
```

**Expected output:** local GPUs from the GPU service (8101). Prefer this over `aitbc edge gpu list-gpus`, which historically 422'd on `/v1/gpu/` because of missing query params.

### Step 5: Deterministic simulation

```bash
aitbc simulate blockchain --blocks 2 --transactions 1 --delay 0 --seed 123 --output json > /tmp/sim1.json
aitbc simulate blockchain --blocks 2 --transactions 1 --delay 0 --seed 123 --output json > /tmp/sim2.json
diff /tmp/sim1.json /tmp/sim2.json && echo DETERMINISTIC
```

### Step 6: Deterministic messaging fallback

```bash
aitbc messaging send --to alice "hello" --coordinator-url http://127.0.0.1:1
```

**Expected output:** `Message Sent (Simulated)` with a stable `message_id` across two runs.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run `agent list`, `pool-hub status`, `mining status`, and `gpu list-gpus` without the old crash/404/wrong-port failures
- Prove simulate and messaging fallbacks are deterministic

---

## Validation

```bash
aitbc agent list 2>&1 | grep -v "UserWarning" | head -5
aitbc pool-hub status 2>&1 | grep -v "UserWarning" | head -8
aitbc mining status 2>&1 | grep -v "UserWarning" | head -8
aitbc gpu list-gpus 2>&1 | grep -v "UserWarning" | head -8
diff /tmp/sim1.json /tmp/sim2.json && echo SIMULATION_DETERMINISTIC
```

---

### Step 7: Command-family clarity

```bash
aitbc market --help
aitbc marketplace --help
aitbc governance --help
aitbc operations governance --help
```

**Expected output:**

- `aitbc market` is the GPU/software offer group used by shop providers and customers.
- `aitbc marketplace` is the older global chain-listings group.
- `aitbc governance` queries the governance service on port 8105.
- `aitbc operations governance` uses the blockchain RPC vote/proposal path.

Scenarios choose the live group: `market` for GPU offers, `governance` for status, and `operations governance` only when the RPC vote path is required.

---

## Related Resources

- [CLI README](../../cli/README.md)
- [Next Scenario: HTTP Client Resource Cleanup](./28_http_client_cleanup.md)

---

*Last updated: 2026-08-21*
*Version: 1.4*
