# Blockchain Monitoring

**Level**: Beginner
**Prerequisites**: Scenario 14 Staking Basics
**Estimated Time**: 25 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Blockchain Monitoring

---

## See Also

- **Previous Scenario**: [Staking Basics](./14_staking_basics.md)
- **Next Scenario**: [Agent Registration](./16_agent_registration.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Monitor CLI source](../../cli/aitbc_cli/commands/monitor.py), [Explorer CLI source](../../cli/aitbc_cli/commands/explorer.py)

---

## Scenario Overview

This scenario shows how an AI agent observes the AITBC network using the `aitbc monitor` and `aitbc explorer` CLI groups. `monitor` provides a live dashboard, collected metrics, alert configuration, and historical analysis. `explorer` reads chain data (chain head, latest blocks, non-empty blocks, block/transaction lookups, address searches, activity timeline) from the Explorer API. Together they let an agent answer "is the network healthy?" and "what just happened on-chain?".

### Use Case

A monitoring agent needs to (1) watch a live dashboard while a job runs, (2) export a 24h metrics snapshot, (3) register an alert that fires when miners go offline, (4) read the current chain head, and (5) inspect the latest non-empty blocks to confirm a transaction landed.

### What You'll Learn

- Run the live dashboard with `aitbc monitor dashboard`
- Collect and export metrics with `aitbc monitor metrics`
- Add, list, test, and remove alerts with `aitbc monitor alerts`
- Read historical analysis with `aitbc monitor history`
- Query the chain head, latest blocks, and non-empty blocks with `aitbc explorer`

---

## Prerequisites

### Knowledge Required

- Scenario 14 (Staking Basics) — comfortable with the `aitbc` CLI and wallet context
- The coordinator API (default `http://localhost:8203`) and Explorer API must be reachable for the respective commands

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- `rich` (for the dashboard rendering, already a CLI dependency)

### Setup Required

- Coordinator API running at `http://localhost:8203`
- Explorer API running (URL from config `explorer_api_url`)
- A blockchain node producing blocks (RPC `http://localhost:8202`)

---

## Step-by-Step Workflow

Monitor commands are grounded in `cli/aitbc_cli/commands/monitor.py`; explorer commands in `cli/aitbc_cli/commands/explorer.py`.

### Step 1: Run the live dashboard

`aitbc monitor dashboard` renders a `rich` dashboard that clears and redraws. Options: `--refresh` (seconds, default `5`), `--duration` (seconds, `0` = indefinite). It fetches `/api/v1/dashboard` from the coordinator and prints overall status, per-service status, and health percentage. Press Ctrl+C to exit.

```bash
aitbc monitor dashboard --refresh 5 --duration 60
```

**Expected output (one frame):**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ AITBC Dashboard ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Refreshing every 5s | Elapsed: 3s

Dashboard Status: Online
  Overall Status: healthy
  Services: 4
    coordinator: online
    blockchain-node: online
    exchange: online
    wallet: online
  Health: 100.0%

Press Ctrl+C to exit
```

### Step 2: Collect and export metrics

`aitbc monitor metrics` collects coordinator, job, and miner metrics for a period. Options: `--period` (default `24h`; accepts `1h`, `24h`, `7d`, `30d`), `--export <path>` (writes JSON to a file).

```bash
aitbc monitor metrics --period 24h --export /tmp/aitbc-metrics.json
```

**Expected output:**
```
Metrics exported to /tmp/aitbc-metrics.json
period: 24h
since: 2026-06-24T12:00:00
collected_at: 2026-06-25T12:00:00
coordinator:
  status: online
jobs:
  total: 142
  completed: 128
  pending: 8
  failed: 6
miners:
  total: 5
  online: 4
  offline: 1
```

### Step 3: Configure alerts

`aitbc monitor alerts <action>` manages alerts stored in `~/.aitbc/alerts/alerts.json`. `action` is one of `add | list | remove | test`. Options: `--name`, `--type` (choice of `coordinator_down | miner_offline | job_failed | low_balance`), `--threshold` (float), `--webhook` (URL).

Add an alert that fires when a miner goes offline:

```bash
aitbc monitor alerts add --name miner-watch --type miner_offline --threshold 1 --webhook https://hooks.example/aitbc
```

**Expected output:**
```
Alert 'miner-watch' added
name: miner-watch
type: miner_offline
threshold: 1.0
webhook: https://hooks.example/aitbc
created_at: 2026-06-25T12:05:00
enabled: true
```

List configured alerts:

```bash
aitbc monitor alerts list
```

**Expected output:**
```
- name: miner-watch
  type: miner_offline
  threshold: 1.0
  webhook: https://hooks.example/aitbc
  enabled: true
```

Test an alert's webhook (posts a test payload to the configured webhook):

```bash
aitbc monitor alerts test --name miner-watch
```

**Expected output:**
```
status: sent
response_code: 200
```

Remove an alert:

```bash
aitbc monitor alerts remove --name miner-watch
```
```
Alert 'miner-watch' removed
```

### Step 4: Historical analysis

`aitbc monitor history` summarizes jobs over a period. Options: `--period` (default `7d`; `1d`, `7d`, `30d`).

```bash
aitbc monitor history --period 7d
```

**Expected output:**
```
period: 7d
since: 2026-06-18T12:00:00
analyzed_at: 2026-06-25T12:00:00
summary:
  total_jobs: 980
  completed: 902
  failed: 78
  success_rate: 92.0%
```

### Step 5: Read the chain head

`aitbc explorer chain-head` calls `GET /api/chain/head`. Option: `--chain-id`.

```bash
aitbc explorer chain-head
```

**Expected output:**
```json
{
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "height": 128452,
  "hash": "0xabc123...",
  "timestamp": "2026-06-25T12:00:00Z"
}
```

### Step 6: Inspect latest and non-empty blocks

`aitbc explorer latest-blocks` calls `GET /api/blocks/latest`; `aitbc explorer non-empty-blocks` calls `GET /api/blocks/non-empty`. Both take `--limit` (default `10`), `--offset` (default `0`), `--chain-id`.

```bash
aitbc explorer latest-blocks --limit 3
```

**Expected output:**
```json
[
  {"height": 128452, "hash": "0xabc123...", "tx_count": 2, "timestamp": "2026-06-25T12:00:00Z"},
  {"height": 128451, "hash": "0xdef456...", "tx_count": 0, "timestamp": "2026-06-25T11:59:30Z"},
  {"height": 128450, "hash": "0x789abc...", "tx_count": 1, "timestamp": "2026-06-25T11:59:00Z"}
]
```

```bash
aitbc explorer non-empty-blocks --limit 3
```

**Expected output:**
```json
[
  {"height": 128452, "hash": "0xabc123...", "tx_count": 2, "timestamp": "2026-06-25T12:00:00Z"},
  {"height": 128450, "hash": "0x789abc...", "tx_count": 1, "timestamp": "2026-06-25T11:59:00Z"},
  {"height": 128448, "hash": "0x111abc...", "tx_count": 3, "timestamp": "2026-06-25T11:58:00Z"}
]
```

### Step 7: Drill into a block or transaction

`aitbc explorer block <height>` and `aitbc explorer transaction <tx_hash>` (alias of `transaction-by-hash`) give full details. `--chain-id` optional.

```bash
aitbc explorer block 128452
aitbc explorer transaction 0xdeadbeef...
```

---

## Code Examples Using Agent SDK

Monitoring is observability tooling driven through the CLI/Explorer API; the agent SDK does not expose a dedicated monitor helper. Agents poll the same endpoints the CLI uses, or shell out to `aitbc monitor` / `aitbc explorer`.

### Example 1: Poll the Explorer API from an agent

```python
import requests

explorer = "http://localhost:8204"  # config.explorer_api_url

head = requests.get(f"{explorer}/api/chain/head", timeout=10).json()
print(head["height"], head["hash"])

blocks = requests.get(f"{explorer}/api/blocks/non-empty",
                      params={"limit": 5}, timeout=10).json()["blocks"]
for b in blocks:
    print(b["height"], b["tx_count"])
```

### Example 2: Drive the monitor CLI from an agent

```python
import subprocess, json

def metrics(period: str = "24h") -> dict:
    out = subprocess.run(["aitbc", "monitor", "metrics", "--period", period],
                         capture_output=True, text=True, check=True).stdout
    # metrics prints a YAML-ish table; export to JSON for structured parsing
    subprocess.run(["aitbc", "monitor", "metrics", "--period", period,
                    "--export", "/tmp/m.json"], check=True)
    return json.load(open("/tmp/m.json"))

def add_alert(name: str, atype: str, webhook: str) -> str:
    return subprocess.run(
        ["aitbc", "monitor", "alerts", "add", "--name", name,
         "--type", atype, "--webhook", webhook],
        capture_output=True, text=True, check=True).stdout

print(metrics("1h"))
print(add_alert("miner-watch", "miner_offline", "https://hooks.example/aitbc"))
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Run a live system dashboard and export metrics snapshots
- Configure, test, list, and remove monitoring alerts with webhooks
- Pull historical job analysis for a chosen period
- Read the chain head, latest blocks, and non-empty blocks from the Explorer API
- Drill into a specific block or transaction by hash

---

## Validation

```bash
# Dashboard runs and exits after a short duration
aitbc monitor dashboard --duration 5

# Metrics export file exists and is valid JSON
aitbc monitor metrics --period 1h --export /tmp/m.json && python -m json.tool /tmp/m.json

# Alert was added and can be listed
aitbc monitor alerts add --name probe --type coordinator_down && aitbc monitor alerts list
aitbc monitor alerts remove --name probe

# Explorer returns a chain head
aitbc explorer chain-head
aitbc explorer non-empty-blocks --limit 2
```

---

## Related Resources

- [Monitor CLI source](../../cli/aitbc_cli/commands/monitor.py)
- [Explorer CLI source](../../cli/aitbc_cli/commands/explorer.py)
- [Service Ports Reference](../reference/SERVICE_PORTS.md)
- Next: [Agent Registration](./16_agent_registration.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
