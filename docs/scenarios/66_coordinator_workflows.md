# Coordinator Workflows

**Level**: Intermediate
**Prerequisites**: Scenario 10 Agent SDK Identity, Scenario 34 Hub↔Customer Node End-to-End
**Estimated Time**: 15 minutes
**Last Updated**: 2026-11-18
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Coordinator Workflows

---

## See Also

- **Previous Scenario**: [Simulated Workloads](./65_simulate_workloads.md)
- **Next Scenario**: [DAO Grants](./67_dao_grants.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/workflow.py`

---

## Scenario Overview

> **Live vs. simulated:** `aitbc workflow` calls the coordinator's
> `/v1/agents/workflows/*` endpoints using the configured coordinator URL
> and stored auth headers. `workflow run --dry-run` is the only local-only
> path. When the coordinator is unreachable, the commands error out — no
> simulated fallback.

This scenario covers the `aitbc workflow` group: listing registered
workflows, dry-running and executing one, polling status, and stopping a
run.

### Use Case

An operator runs a named coordinator workflow (e.g. `gpu-market`,
`ai-job-processing`) with a small YAML input file, then monitors and, if
needed, stops the execution.

### What You'll Learn

- `workflow list` — workflows registered on the coordinator
- `workflow run` — `--dry-run` first, then real execution with `--config`
- `workflow status` / `workflow stop` — execution lifecycle

---

## Prerequisites

- Coordinator reachable and an **admin-role** credential. Every
  `/v1/agents/workflows/*` and `/v1/agents/executions/*` endpoint is
  `AdminDep`-gated server-side, so a plain `aitbc auth login` client JWT
  gets `HTTP 403 {"detail":"Role required"}` on `list`, `status`, `run`,
  and `stop` alike. Store an admin login with
  `aitbc auth login --credential-name admin` (the CLI prefers the `admin`
  slot and falls back to `client`), pass `--api-key`, or set
  `COORDINATOR_API_KEY` to an admin JWT. The CLI names this gate
  explicitly on a 403 instead of surfacing the bare server detail.
- A workflow name known to the coordinator (see `workflow list`)

---

## Steps

### 1. List workflows

```bash
aitbc workflow list
aitbc workflow list --format json
```

**Expected output:** the coordinator's registered workflow names and
states.

### 2. Dry-run

```bash
aitbc workflow run --workflow-name gpu-market --dry-run
```

Local check only — prints what would execute; no coordinator call, no
spend.

### 3. Execute (write — coordinator-side execution)

```bash
cat > /tmp/workflow.yaml <<'EOF'
region: eu
max_price: 100
EOF
aitbc workflow run --workflow-name gpu-market --config /tmp/workflow.yaml
```

Posts `{workflow_id, inputs}` to `/v1/agents/workflows/<name>/execute` and
returns an `execution_id`. What the workflow then does (jobs, offers,
messages) depends on its definition — treat every real `run` as a write;
on a live island it needs the operator's line.

### 4. Status and stop

```bash
aitbc workflow status --workflow-name gpu-market
```

`aitbc workflow stop --workflow-name gpu-market` halts the execution —
a write; not played on a workflow the operator did not start.

---

## Cost Table

| Step | Spend |
|---|---|
| `list`, `status`, `run --dry-run` | 0 AIT |
| `run` (real), `stop` | workflow-defined — not played |

---

## Verification

- `workflow status` returns a terminal state (`completed`/`stopped`) after
  a real run finishes or `stop` lands.
- `--dry-run` output names the workflow without contacting the
  coordinator.

## Troubleshooting

- `Failed to start workflow: …` — auth headers missing (`aitbc auth
  login`) or the workflow name is not registered on this coordinator.
- `… requires an admin-role credential … (HTTP 403 — {"detail":"Role
  required"})` — the stored credential is a client JWT; store an admin
  login (`aitbc auth login --credential-name admin`) or pass `--api-key`.
