# Script Runner

**Level**: Beginner
**Prerequisites**: Scenario 21 Service Startup & Connectivity
**Estimated Time**: 10 minutes
**Last Updated**: 2026-10-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Script Runner

---

## See Also

- **Previous Scenario**: [Cluster Ops](./69_cluster_ops.md)
- **Next Scenario**: [Reinvest Policy](./71_reinvest_policy.md)
- **Feature Documentation**: `cli/aitbc_cli/commands/script.py`

---

## Scenario Overview

> **Arbitrary execution:** `aitbc script run` executes any script file with
> `subprocess` and captures stdout/stderr — it is a convenience wrapper,
> not a sandbox. Only run scripts you have read.

This scenario covers `aitbc script`: listing the scripts directory and
running a script with optional arguments.

### Use Case

An operator enumerates the ops scripts shipped in the repo and runs a
read-only one (e.g. a status/report script) through the CLI so the output
lands in the same table/json format as the rest of the tooling.

### What You'll Learn

- `script list` — discover `*.sh` files under the scripts directory
- `script run` — execute with `--args`, capture return code and output

---

## Prerequisites

- `aitbc` on `$PATH`; the scripts directory present (default
  `/opt/aitbc/scripts`)

---

## Steps

### 1. List available scripts

```bash
aitbc script list
aitbc script list --script-dir /opt/aitbc/scripts
```

**Expected output:** name + path for every `*.sh` found recursively.
Errors out if the directory does not exist.

### 2. Run a read-only script

```bash
aitbc script run --script-path /opt/aitbc/scripts/monitoring/fleet-config-check.sh
aitbc script run --script-path /path/to/script.sh --args '--verbose'
```

**Expected output:** `{stdout, stderr, returncode}` for the script.

> **Caution:** pick a script known to be read-only (status/reporting).
> `script run` will happily execute destructive scripts — anything that
> restarts services, spends, or mutates chain state needs the operator's
> line, exactly as if it were run by hand.

---

## Cost Table

| Step | Spend |
|---|---|
| `script list` | 0 AIT |
| `script run` | whatever the chosen script does — 0 AIT for read-only scripts |

---

## Verification

- `returncode: 0` and the script's own output in `stdout`.
- `script list` on a missing directory reports the error rather than
  silently listing nothing.

## Troubleshooting

- `Scripts directory not found` — pass `--script-dir` with the checkout's
  actual scripts path.
