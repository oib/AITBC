# Operations Admin (Deprecated Command Surface)

**Level**: Intermediate
**Prerequisites**: Scenario 07 AI Job Submission, Scenario 17 Governance Voting
**Estimated Time**: 15 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Operations Admin

---

## See Also

- **Previous Scenario**: [CLI Configuration](./63_cli_configuration.md)
- **Next Scenario**: [Simulate Workloads](./65_simulate_workloads.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/operations.py`

---

## Scenario Overview

> **Deprecated surface:** `aitbc operations` is a legacy/umbrella group kept
> for backward compatibility. `operations governance` is registered as
> deprecated/hidden — the live governance path is `aitbc governance`
> (scenario 17), the live AI path is `aitbc ai` (scenario 07), and agent
> management is `aitbc agent` (scenario 10). This play documents the legacy
> leaves so coverage is complete; prefer the modern groups for real work.

This scenario inventories the `aitbc operations` group: agent registry
admin, AI job submission/cancellation, and the governance voting/staking
leaves that predate the dedicated `aitbc governance` group.

### Use Case

An old runbook or third-party script still calls `aitbc operations …`; the
operator needs to know what each leaf does and which modern command
replaces it.

### What You'll Learn

- `operations agent` — a flat agent registry (`register`, `list`,
  `deregister`, `message`)
- `operations ai` — job submit/status/cancel with a wallet
- `operations governance` — proposal, vote, stake, execute, get-proposal

---

## Prerequisites

- A reachable blockchain RPC (`--rpc-url`, default `8202`) for the
  governance and agent-message leaves
- A funded wallet for any write step (integer units)

---

## Steps

### 1. Agent registry

```bash
aitbc operations agent list
aitbc operations agent list --status active --format json
```

**Writes — need the operator's line:**

```bash
aitbc operations agent register   --agent-id agent-1 --status active
aitbc operations agent deregister --agent-id agent-1
aitbc operations agent message    --agent 0x<agent-address> --message 'hello' --wallet default
```

`agent message` signs and submits an on-chain message — a real transaction.
Modern replacement: `aitbc agent` / `aitbc agent-msg`.

### 2. AI jobs

```bash
aitbc operations ai status                  # all jobs
aitbc operations ai status --job-id job-123
```

**Writes — need the operator's line:**

```bash
aitbc operations ai submit-job --wallet-name default --job-type inference \
    --prompt 'hello' --payment 1.0 --model ollama
aitbc operations ai cancel --job-id job-123
```

`--payment` is a decimal AIT amount; modern replacement: `aitbc ai submit` /
`aitbc ai cancel`.

### 3. Governance (deprecated surface)

```bash
aitbc operations governance get-proposal --proposal-id prop-1
aitbc operations governance voting-power --address 0x<addr>    # played in 17 via live group
```

**Writes — need the operator's line:**

```bash
aitbc operations governance proposal --proposal-id prop-2 --title 'Param change' \
    --description '…' --category general --wallet default --voting-days 7
aitbc operations governance vote   --proposal-id prop-1 --vote for --wallet default --voting-power 1
aitbc operations governance stake  --address 0x<addr> --amount 36000000 --lock-days 30   # integer token units on the deprecated ops path
aitbc operations governance execute --proposal-id prop-1
aitbc operations governance delegate --delegator 0x<a> --delegate 0x<b> --amount 36000000   # integer token units
```

`stake` locks real tokens, `execute` applies a passed proposal — both
irreversible. Modern replacement: `aitbc governance` (scenario 17).

---

## Live leaf status (verified 21 Nov, fleet `dc162a63f`)

The deprecated surface parses everywhere, but most leaves are dead or
broken — tracked as #2378. Per-leaf reality on hub + node2:

| Leaf | Live result |
|---|---|
| `operations agent list` | **401** — hits `/v1/agents/discover` with no credentials; the endpoint now requires signed `X-Agent-*` auth (same family as #2363). Dead unless the deprecated surface gains auth. |
| `operations agent register` | **422** — posts `{agent_id, status}` but the registry requires the full schema (name, chain_id, endpoint, capabilities, wallet identity). Dead leaf. |
| `operations agent deregister` / `message` | unplayed — `message` is an on-chain write (operator line); `deregister` untested this sweep. |
| `operations ai status` / `cancel` / `submit-job` | **404** — targets `{agent_coordinator_url}/v1/jobs…`, but the agent-coordinator does not serve job routes (AI jobs live on coordinator-api). Wrong-service dead leaves. |
| `operations governance get-proposal` / `proposal` / `vote` / `stake` / `execute` / `delegate` | **404** on hub + node2 — the `/rpc/governance/*` paths are absent on the current node RPC. Dead leaves. |
| `operations governance voting-power` | **live** — the only confirmed-working read on the surface. |

Bottom line: treat `operations` as parse-only compatibility surface; the
only functional leaf found is `governance voting-power`. Use the modern
groups for everything else.

---

## Cost Table

| Step | Spend |
|---|---|
| `agent list`, `ai status`, `get-proposal`, `voting-power` | 0 AIT |
| `ai submit-job` | `--payment` AIT — not played |
| `governance stake` | `--amount` locked — not played |
| `agent message`, `proposal`, `vote`, `execute`, `delegate` | chain fee — not played |

---

## Verification

- Each legacy leaf's output matches the corresponding modern group
  (`operations ai status` ≈ `aitbc ai jobs`).
- Deprecated commands still parse — the group must not break until removal.

## Troubleshooting

- Prefer `aitbc governance`/`aitbc ai`/`aitbc agent`; the operations
  surface is kept only so existing scripts keep working.
