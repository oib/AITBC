# Service Startup & Connectivity

**Level**: Intermediate
**Prerequisites**: [Scenario 20 Cross-Chain Transfer](./20_cross_chain_transfer.md)
**Estimated Time**: 10 minutes
**Last Updated**: 2026-08-21
**Version**: 1.3

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Service Startup & Connectivity

---

## See Also

- **Previous Scenario**: [Scenario 20 Cross-Chain Transfer](./20_cross_chain_transfer.md)
- **Next Scenario**: [Scenario 22 Bridge RPC Input Validation](./22_bridge_rpc_validation.md)
- **Feature Documentation**: [Service Ports Reference](../reference/SERVICE_PORTS.md)
- **Closed cycle**: [DESIGN_CYCLE.md](../DESIGN_CYCLE.md)

---

## Scenario Overview

> **Operator play:** This scenario is an operator-driven validation of a production hardening item, not a bug-ticket reproduction. The A/B task ids in the text are change-log cross-references.

A shop-node operator confirms that the role's systemd units are up, the miner is heartbeating, the edge GPU inventory is reachable, and the bridge RPC is healthy after a restart or upgrade.

### Use Case

After an upgrade, restart the shop role and prove the inner loop services answer the CLI.

### What You'll Learn

- How to start and inspect role services with `aitbc start` / `aitbc system`
- How to confirm mining, GPU, and bridge from the CLI
- How to read miner/edge logs only as validation

---

## Prerequisites

### Knowledge Required

- Hub vs shop vs follower roles (`docs/getting-started/setup-service-selection.md`)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- A shop node (`<node2>`) with miner, edge, blockchain RPC, and coordinator deployed

---

## Step-by-Step Workflow

### Step 1: Start (or dry-run) shop services

```bash
aitbc start --role shop --dry-run
aitbc start --role shop
aitbc system check
aitbc system status
```

**Expected output:** `aitbc start --dry-run` lists the systemd units for the shop role. After start, `system check` reports service files present. `system status` may fail on a shop node if it still probes the hub-only agent-coordinator URL — that is expected; do not treat it as a shop outage.

### Step 2: Mining heartbeat path

```bash
aitbc mining status
aitbc mining list
```

**Expected output:** status hits `/rpc/mining/status` on the configured blockchain RPC (8202). A 401 means the endpoint exists and wants wallet auth — that is success for connectivity. `list` shows configured miners if any.

### Step 3: Edge / GPU inventory

```bash
aitbc gpu list-gpus
aitbc edge status
```

**Expected output:** `gpu list-gpus` talks to the GPU service (8101) and does **not** require island credentials. `edge status` talks to the agent-coordinator URL; on a shop node that URL should resolve to the **hub**, not localhost:8107.

### Step 4: Bridge health

```bash
aitbc bridge health
```

**Expected output:** `success: true`, `bridge_initialized: true` (or an honest RPC error if 8202 is down). Do not curl `/rpc/bridge/health` as the play.

---


---

<!-- PLAY3 coverage extension: uncovered CLI leaves folded into this scenario (issue #438) -->

### Step 5: System architect overview

Prints the service architecture map.

```bash
aitbc system architect
```

### Step 6: Audit service configuration

Runs the configuration audit across services.

```bash
aitbc system audit
```

### Step 7: Show service config

Prints resolved configuration for services (no secrets without --show-secrets).

```bash
aitbc system config
```

### Step 8: List cron entries

Shows scheduled jobs the CLI manages.

```bash
aitbc system cron
```

### Step 9: List env var names

Lists the environment variable names a service consumes.

```bash
aitbc system env-names --service aitbc-coordinator-api
```

### Step 10: Read a managed file

Prints a managed config file.

```bash
aitbc system file --path /etc/aitbc/aitbc-coordinator-api.env
```

### Step 11: Managed file metadata

Shows size/mtime metadata for a managed file.

```bash
aitbc system file-info --path /etc/aitbc/aitbc-coordinator-api.env
```

### Step 12: Read service logs

Tails a service's journal.

```bash
aitbc system logs --service aitbc-coordinator-api -n 20
```

### Step 13: Show a service unit

Prints systemd properties for a service.

```bash
aitbc system show --service aitbc-coordinator-api
```

### Step 14: Dump a service env file

`aitbc system cat --service aitbc-coordinator-api` is prints the raw env file including secrets — env/key material; not played, needs the operator's line.

<!-- COVERAGE-LEFT-1: remaining top-level control/health leaves (issue #445) -->

### Step 14a: Remote health probe

`aitbc health` probes the standard AITBC `/health` endpoints on a host with plain GETs — read-only:

```bash
aitbc health --host localhost
```

**Expected output:** a per-service table (`api-gateway`, `blockchain-rpc`, `coordinator-api`, …) with status/latency; down services show `connect_error`/`timeout`, which is an honest result, not a CLI failure.

### Step 14b: Update check only

`aitbc update --check` reports HEAD vs upstream without pulling or deploying — read-only:

```bash
aitbc update --check
```

**Expected output:** current commit, upstream commit, ahead/behind counts. `aitbc update` without `--check` runs `scripts/deployment/update.sh` (git pull + deploy) — env mutation; not played, needs the operator's line.

### Step 14c: Stop / restart dry-run

`aitbc stop` and `aitbc restart` accept `--dry-run`, which only lists the systemd units that would be acted on — read-only:

```bash
aitbc stop --role shop --dry-run
aitbc restart --role shop --dry-run
```

**Expected output:** the unit list for the role, no systemctl action. `aitbc stop` / `aitbc restart` without `--dry-run` stop or restart live services — service control; not played, needs the operator's line.

### Step 14d: Service harden dry-run

`aitbc service harden --dry-run` prints the systemd hardening directives it would apply without writing unit files or restarting:

```bash
aitbc service harden --service aitbc-coordinator-api --dry-run
```

**Expected output:** a preview of the hardening changes. `aitbc service harden` without `--dry-run` rewrites systemd units and restarts services — env mutation + service control; not played, needs the operator's line.

### Step 15: Set service env vars

`aitbc system env-set aitbc-coordinator-api KEY=VALUE` is rewrites a service env file — env mutation; not played, needs the operator's line.

### Step 16: Run a script on a service

`aitbc system run-script --path /tmp/script.sh` is executes an arbitrary script — service control; not played, needs the operator's line.

### Step 17: Start a service

`aitbc system start --service aitbc-coordinator-api` is starts a systemd unit — service control; not played, needs the operator's line.

### Step 18: Stop a service

`aitbc system stop --service aitbc-coordinator-api` is stops a systemd unit — service control; not played, needs the operator's line.

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Start shop-role units with `aitbc start --role shop`
- Confirm mining, GPU, and bridge from `aitbc` without raw HTTP
- Know that hub-only URLs on a shop node come from `HUB_DISCOVERY_URL` / `HUB_P2P_HOST`, not localhost

---

## Validation

```bash
# systemd (validation only)
systemctl is-active aitbc-miner aitbc-edge aitbc-blockchain-rpc aitbc-coordinator-api aitbc-blockchain-node

# miner heartbeats (validation only)
journalctl -u aitbc-miner -n 10 --no-pager | grep -i heartbeat || true

# edge registration logged, not swallowed (B9)
journalctl -u aitbc-edge -n 30 --no-pager | grep -iE "register|blockchain" || true
```

---

## Related Resources

- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- [Next Scenario: Bridge RPC Input Validation](./22_bridge_rpc_validation.md)

---

*Last updated: 2026-08-21*
*Version: 1.3*
