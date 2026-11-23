# Analytics Collection

**Level**: Beginner
**Prerequisites**: [Scenario 17 Governance Voting](./17_governance_voting.md)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-11-21
**Version**: 1.3

**Legs**: 6

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Analytics Collection

---

## See Also

- **Previous Scenario**: [Scenario 17 Governance Voting](./17_governance_voting.md)
- **Next Scenario**: [Scenario 19 Security Setup](./19_security_setup.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: Analytics Reference

---

## Scenario Overview

This scenario demonstrates how to collect chain analytics, monitor performance in real-time, generate predictions, view alerts, and get optimization recommendations using the `aitbc analytics` command group.

### Use Case

A network operator wants to monitor the health and performance of multiple blockchain chains, detect anomalies through alerts, and predict future performance to proactively allocate resources.

### What You'll Learn

- How to generate cross-chain and single-chain performance summaries
- How to monitor chains in real-time or take a single snapshot
- How to predict future chain performance
- How to view performance alerts and get optimization recommendations

> **Reality check (live chain-rpc nodes):** On nodes that expose only the public
> chain RPC (no `/api/*` admin surface), metrics are composed from real probes —
> mean block interval and TPS from the recent `/rpc/blocks-range` window,
> validator count from `/rpc/network-info`, and the configured block interval
> (`block_time_seconds`) from `/rpc/info`. Host telemetry the RPC does not
> publish (memory, disk, client/agent counts) renders as `unknown` — that is
> "not measured", not a real zero, and it never feeds alerts or the "Add more
> nodes" recommendation. `block_time_high` alerts and the "High block time"
> recommendation fire only when blocks run >50% slower than the chain's
> configured interval, so a PBFT chain idling at its ~60s design interval does
> not alert. Metrics samples persist across invocations under
> `~/.aitbc/analytics_metrics.json` (`AITBC_ANALYTICS_HISTORY` overrides the
> path), so `predict` accumulates history between CLI runs — it still needs
> ≥10 collected samples and reports honestly when there are not enough.

---

## Prerequisites

### Knowledge Required

- Basic familiarity with the `aitbc` CLI (see [Scenario 01 Wallet Basics](./01_wallet_basics.md))
- Understanding of blockchain metrics (TPS, block time, gas price)

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`

### Setup Required

- A running blockchain node reachable at `http://localhost:8202` (RPC)
- At least one chain configured in the multichain config

---

## Step-by-Step Workflow

### Step 1: Get a Cross-Chain Performance Summary

Generate a performance summary across all configured chains. Without `--chain-id`, the command produces a cross-chain analysis with an overview and per-chain comparison.

```bash
# Cross-chain summary for the last 24 hours (default)
aitbc analytics summary

# Summary for a specific chain over the last 48 hours
aitbc analytics summary --chain-id bc-2 --hours 48
```

**Expected output (cross-chain) — illustrative; a single-chain node looks like:**

```
Cross-Chain Analysis Overview

Metric                Value
Total Chains          1
Active Chains         1
Total Alerts          0
Critical Alerts       0
Total Memory Usage    unknown
Total Disk Usage      unknown
Total Clients         unknown
Total Agents          unknown

Chain Performance Comparison

Chain ID     TPS       Block Time   Health Score
bc-2      0.00       61.20s       55.0/100
```

On a live PBFT chain empty blocks legitimately measure ~0 TPS and a ~60s
block interval — that is the chain's design, not a fault. Memory/disk/client
counts read `unknown` because the public chain RPC does not publish host
telemetry.

**Expected output (single chain):**

```
Chain Summary: bc-2

Metric              Value
Chain ID            bc-2
Time Range          48 hours
Data Points         3
Health Score        55.0/100
Active Alerts       0
Avg TPS             0.00
Avg Block Time      61.20s
Avg Gas Price       unknown
Data Source         live
```

### Step 2: Monitor Chain Performance

Take a single snapshot of chain metrics, or start a real-time monitoring dashboard that refreshes at a configurable interval.

```bash
# Single snapshot of all chains
aitbc analytics monitor

# Single snapshot of a specific chain
aitbc analytics monitor --chain-id bc-2

# Real-time monitoring with 15-second refresh
aitbc analytics monitor --realtime --interval 15
```

**Expected output (single snapshot, all chains) — illustrative; on a
chain-rpc node the unmeasured totals read `unknown`:**

```
System Monitor

Metric                Value
Total Chains          1
Active Chains         1
Total Memory Usage    unknown
Total Disk Usage      unknown
Total Clients         unknown
Total Agents          unknown
Total Alerts          0
Critical Alerts       0
```

**Expected output (single snapshot, specific chain):**

```
Chain Monitor: bc-2

Metric              Value
Chain ID            bc-2
Current TPS         0.00
Current Block Time  61.20s
Health Score        55.0/100
Active Alerts       0
Memory Usage        unknown
Disk Usage          unknown
Active Nodes        4
Client Count        unknown
Agent Count         unknown
```

### Step 3: Predict Future Chain Performance

Generate performance predictions for the next time horizon. The command collects current metrics and then runs prediction models.

```bash
# Predict performance for all chains over the next 24 hours
aitbc analytics predict --hours 24

# Predict for a specific chain over the next 12 hours
aitbc analytics predict --chain-id bc-2 --hours 12
```

**Expected output (single chain) — only `tps` and `memory_usage_mb` are
predicted today, and only once ≥10 samples have accumulated across runs:**

```
Performance Predictions: bc-2

Metric          Predicted Value   Confidence   Time Horizon
tps             0.00               90.0%        12h
memory_usage_mb 0.00               90.0%        12h
```

### Step 4: View Performance Alerts

Check for active alerts filtered by severity and time range.

```bash
# View all alerts from the last 24 hours
aitbc analytics alerts

# View only critical alerts from the last 6 hours
aitbc analytics alerts --severity critical --hours 6
```

**Expected output — illustrative; a healthy PBFT chain at its configured
interval typically shows no alerts at all:**

```
Performance Alerts (Last 24h)

Chain ID     Type               Severity   Message                          Current Value   Threshold    Time
bc-2   block_time_high   warning    High block time: 95.00s            95.00           90.00        2026-06-25 09:30:00
```

### Step 5: Get Optimization Recommendations

Receive actionable recommendations for improving chain performance.

```bash
# Recommendations for a specific chain
aitbc analytics optimize --chain-id bc-2

# Recommendations for all chains
aitbc analytics optimize
```

**Expected output (single chain) — illustrative:**

```
Optimization Recommendations: bc-2

Type        Priority   Issue                  Current Value   Recommended Action                     Expected Improvement
resource    medium     High memory usage      512.0           Implement data pruning or increase node memory   40-70% memory usage reduction
```

### Step 6: Export Complete Dashboard Data

Get a full JSON dashboard export suitable for ingestion by external monitoring tools.

```bash
aitbc analytics dashboard
```

**Expected output — the real dashboard shape is `overview` /
`chain_summaries` / `alerts` / `predictions` / `recommendations`; values
below are illustrative:**

```json
{
  "overview": {
    "total_chains": 1,
    "active_chains": 1,
    "chains_by_type": {"unknown": 1},
    "performance_comparison": {
      "bc-2": {"tps": 0.0, "block_time": 61.2, "health_score": 55.0}
    },
    "resource_usage": {
      "total_memory_mb": null,
      "total_disk_mb": null,
      "total_clients": null,
      "total_agents": null
    },
    "alerts_summary": {"total_alerts": 0, "critical_alerts": 0, "warning_alerts": 0}
  },
  "chain_summaries": {"bc-2": {"data_points": 3, "data_source": "live"}},
  "alerts": [],
  "predictions": {},
  "recommendations": {"bc-2": []}
}
```

---

## Code Examples Using Agent SDK

### Example 1: Agent Collects Analytics via CLI Subprocess

The `aitbc_agent` SDK does not expose a direct analytics API, but agents can collect analytics data by invoking the real `aitbc` CLI through subprocess calls and parsing the JSON output.

```python
import asyncio
import subprocess
import json
from aitbc_agent import Agent, AgentCapabilities

async def main():
    agent = Agent.create(
        name="Analytics Agent",
        agent_type="processing",
        capabilities={"compute_type": "processing", "max_concurrent_jobs": 2},
    )
    await agent.register()

    # Collect cross-chain summary in JSON format
    result = subprocess.run(
        ["aitbc", "analytics", "summary", "--format", "json"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        summary = json.loads(result.stdout)
        print(f"Total chains: {summary.get('total_chains', 'N/A')}")
        print(f"Active alerts: {summary.get('alerts_summary', {}).get('total_alerts', 0)}")

asyncio.run(main())
```

### Example 2: Predictive Monitoring Loop

An agent can periodically poll predictions and alerts to make autonomous scaling decisions.

```python
import subprocess
import json
import time

def get_predictions(chain_id: str, hours: int = 12) -> list:
    """Fetch performance predictions via the real aitbc CLI."""
    result = subprocess.run(
        ["aitbc", "analytics", "predict", "--chain-id", chain_id,
         "--hours", str(hours), "--format", "json"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return json.loads(result.stdout)
    return []

def get_critical_alerts() -> list:
    """Fetch critical alerts via the real aitbc CLI."""
    result = subprocess.run(
        ["aitbc", "analytics", "alerts", "--severity", "critical",
         "--hours", "1", "--format", "json"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return json.loads(result.stdout)
    return []

def monitoring_loop(chain_id: str, interval: int = 60):
    """Continuously monitor predictions and alerts."""
    while True:
        predictions = get_predictions(chain_id)
        for pred in predictions:
            metric = pred.get("metric", "unknown")
            value = pred.get("predicted_value", 0)
            confidence = pred.get("confidence", 0)
            print(f"[{chain_id}] Predicted {metric}: {value:.2f} (confidence: {confidence:.1%})")

        alerts = get_critical_alerts()
        if alerts:
            print(f"WARNING: {len(alerts)} critical alert(s) detected!")
            for alert in alerts:
                print(f"  - {alert.get('chain_id')}: {alert.get('message')}")

        time.sleep(interval)

# Run the monitoring loop (Ctrl+C to stop)
# monitoring_loop("bc-2", interval=60)
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Generate cross-chain and single-chain performance summaries with `aitbc analytics summary`
- Monitor chains in real-time or via snapshots with `aitbc analytics monitor`
- Predict future performance with `aitbc analytics predict`
- View and filter alerts with `aitbc analytics alerts`
- Get optimization recommendations with `aitbc analytics optimize`
- Export full dashboard data in JSON with `aitbc analytics dashboard`

---

## Validation

Verify that analytics commands return data correctly:

```bash
# Confirm summary returns chain data
aitbc analytics summary --format json

# Verify predictions are generated
aitbc analytics predict --chain-id bc-2 --hours 6 --format json

# Check for active alerts
aitbc analytics alerts --severity all --hours 24

# Validate dashboard export is valid JSON
aitbc analytics dashboard | python3 -m json.tool
```

---

## Related Resources

- Analytics Documentation
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- [Next Scenario: Security Setup](./19_security_setup.md)

---

*Last updated: 2026-08-20*
*Version: 1.3*
