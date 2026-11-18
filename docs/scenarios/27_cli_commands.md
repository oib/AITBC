# CLI Commands Verification

**Level**: Intermediate
**Prerequisites**: [Scenario 26 GPU Market N+1 Query Fix](./26_gpu_nplus1_query.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-11-18
**Version**: 1.5

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > CLI Commands Verification

---

## See Also

- **Previous Scenario**: [Scenario 26 GPU Market N+1 Query Fix](./26_gpu_nplus1_query.md)
- **Next Scenario**: [Scenario 28 HTTP Client Resource Cleanup](./28_http_client_cleanup.md)
- **Feature Documentation**: [CLI README](../../cli/README.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

> **Live vs. simulated:** This scenario exercises several CLI groups. `aitbc simulate` commands produce deterministic output; `aitbc messaging send` is a dry run by default (nothing signed or sent). Other groups (`aitbc agent`, `aitbc pool-hub`, `aitbc mining`, `aitbc gpu`) are live when their services are running.

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

**Expected output:** live JSON from the hub (`status: ok`, `db`/`redis` flags) when discovery is configured. Simulated output is only acceptable if the hub URL cannot be resolved — on `<node2>` it should be live (scenario 36).

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

### Step 6: Deterministic messaging dry run

```bash
aitbc messaging send --wallet <existing-wallet> --message "hello" --topic broadcast
```

**Expected output:** `aitbc messaging send` is a **dry run by default** — it prints `DRY RUN — nothing signed, nothing sent. Re-run with --confirm to sign and submit once:` on stderr, then a `Message dry run` payload with `wallet`, `sender`, `topic`, `kind`, `parent`, `body_bytes` and `fee_ait`. Nothing is signed or submitted, so there is **no `message_id`**: the on-chain message id is the transaction hash, which only exists after `--confirm` (a live, permanent post — needs the operator's line, not played here). `--wallet` must name an existing wallet file (the sender address is read from its metadata; no password is needed for the dry run). The dry-run payload is deterministic — two runs with the same wallet and arguments produce identical JSON:

```bash
aitbc --output json messaging send --wallet <existing-wallet> --message "hello" --topic broadcast 2>/dev/null > /tmp/msg1.json
aitbc --output json messaging send --wallet <existing-wallet> --message "hello" --topic broadcast 2>/dev/null > /tmp/msg2.json
diff /tmp/msg1.json /tmp/msg2.json && echo DETERMINISTIC
```

(`--output` is a global `aitbc` option and goes before the group.) `aitbc agent-msg send "hello" --to-agent alice` is the live agent-coordinator path — it posts a real message through the coordinator and is not part of this deterministic check.

---


---

<!-- PLAY3 coverage extension: uncovered CLI leaves folded into this scenario (issue #438) -->

### Step 8: Log out of an auth session

Clears the stored CLI auth credential.

```bash
aitbc auth logout
```

### Step 9: Allocate agent resources

Reserves a resource allocation for an agent.

Cost: 0 units — reservation record only.

```bash
aitbc resource allocate --agent-id agent-001 --cpu-cores 4 --memory-gb 8
```

### Step 10: Optimize agent resources

Runs the resource optimizer against a target metric.

Cost: 0 units — recommendation/adjustment only.

```bash
aitbc resource optimize --agent-id agent-001 --target-metric latency
```

<!-- COVERAGE-LEFT-1: generic HTTP pivot leaf (issue #445) -->

### Step 11: HTTP pivot (read-only GET)

`aitbc http call` reaches a named local service without remembering its port. A GET is read-only:

```bash
aitbc http call blockchain-rpc /health
```

**Expected output:** the service's `/health` JSON. The leading `/` resolves the path against the service origin, so this reaches the root `/health` endpoint even though the `blockchain-rpc` alias is mounted at `/rpc` (a bare `health` path would resolve to `/rpc/health` and 404). Non-GET `--method` values and paths that mutate state are not played, needs the operator's line.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run `agent list`, `pool-hub status`, `mining status`, and `gpu list-gpus` without the old crash/404/wrong-port failures
- Prove simulate output and the messaging dry run are deterministic

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
aitbc governance --help
aitbc operations governance --help
```

**Expected output:**

- `aitbc market` is the GPU/software offer group used by shop providers and customers.
- `aitbc market` no longer exists — the old global chain-listings group has been removed from the CLI (`aitbc market --help` returns an error).
- `aitbc governance` queries the governance service on port 8105.
- `aitbc operations governance` uses the blockchain RPC vote/proposal path; the `operations` group is deprecated and hidden from `aitbc --help`.

Scenarios choose the live group: `market` for GPU offers and `governance` for proposals/voting; `operations governance` remains only for the few RPC-path operations (stake, delegate, voting-power) that have no canonical equivalent.

---

## Related Resources

- [CLI README](../../cli/README.md)
- [Next Scenario: HTTP Client Resource Cleanup](./28_http_client_cleanup.md)

---

*Last updated: 2026-11-18*
*Version: 1.5*
