# Analytics Collection

**Level**: Beginner
**Prerequisites**: [Scenario 17 Governance Voting](./17_governance_voting.md)
**Estimated Time**: 20 minutes
**Last Updated**: 2026-06-25
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Analytics Collection

---

## See Also

- **Previous Scenario**: [Scenario 17 Governance Voting](./17_governance_voting.md)
- **Next Scenario**: [Scenario 19 Security Setup](./19_security_setup.md)
- **Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **Feature Documentation**: [Analytics Reference](../analytics/README.md)

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
aitbc analytics summary --chain-id ait-hub --hours 48
```

**Expected output (cross-chain):**
```
Cross-Chain Analysis Overview

Metric                Value
Total Chains          3
Active Chains         3
Total Alerts          2
Critical Alerts       0
Total Memory Usage    512.3MB
Total Disk Usage      2048.5MB
Total Clients         15
Total Agents          8

Chain Performance Comparison

Chain ID     TPS       Block Time   Health Score
ait-hub      125.50    2.10s        85.0/100
ait-devnet   98.30     3.20s        72.0/100
ait-testnet  45.00     5.00s        60.0/100
```

**Expected output (single chain):**
```
Chain Summary: ait-hub

Metric              Value
Chain ID            ait-hub
Time Range          48 hours
Data Points         1440
Health Score        85.0/100
Active Alerts       1
Avg TPS             125.50
Avg Block Time      2.10s
Avg Gas Price       12,500 wei
```

### Step 2: Monitor Chain Performance

Take a single snapshot of chain metrics, or start a real-time monitoring dashboard that refreshes at a configurable interval.

```bash
# Single snapshot of all chains
aitbc analytics monitor

# Single snapshot of a specific chain
aitbc analytics monitor --chain-id ait-hub

# Real-time monitoring with 15-second refresh
aitbc analytics monitor --realtime --interval 15
```

**Expected output (single snapshot, all chains):**
```
System Monitor

Metric                Value
Total Chains          3
Active Chains         3
Total Memory Usage    512.3MB
Total Disk Usage      2048.5MB
Total Clients         15
Total Agents          8
Total Alerts          2
Critical Alerts       0
```

**Expected output (single snapshot, specific chain):**
```
Chain Monitor: ait-hub

Metric              Value
Chain ID            ait-hub
Current TPS         128.40
Current Block Time  2.05s
Health Score        86.0/100
Active Alerts       1
Memory Usage        256.1MB
Disk Usage          1024.2MB
Active Nodes        5
Client Count        12
Agent Count         6
```

### Step 3: Predict Future Chain Performance

Generate performance predictions for the next time horizon. The command collects current metrics and then runs prediction models.

```bash
# Predict performance for all chains over the next 24 hours
aitbc analytics predict --hours 24

# Predict for a specific chain over the next 12 hours
aitbc analytics predict --chain-id ait-hub --hours 12
```

**Expected output (single chain):**
```
Performance Predictions: ait-hub

Metric          Predicted Value   Confidence   Time Horizon
tps             130.50            87.5%        12h
block_time      2.08s             92.0%        12h
gas_price       12,000 wei        78.3%        12h
memory_usage    260.00MB          85.0%        12h
```

### Step 4: View Performance Alerts

Check for active alerts filtered by severity and time range.

```bash
# View all alerts from the last 24 hours
aitbc analytics alerts

# View only critical alerts from the last 6 hours
aitbc analytics alerts --severity critical --hours 6
```

**Expected output:**
```
Performance Alerts (Last 24h)

Chain ID     Type            Severity   Message                    Current Value   Threshold    Time
ait-devnet   high_block_time  warning    Block time above 3s        3.20            3.00         2026-06-25 09:30:00
ait-testnet  low_tps          warning    TPS below 50               45.00           50.00        2026-06-25 08:15:00
```

### Step 5: Get Optimization Recommendations

Receive actionable recommendations for improving chain performance.

```bash
# Recommendations for a specific chain
aitbc analytics optimize --chain-id ait-devnet

# Recommendations for all chains
aitbc analytics optimize
```

**Expected output (single chain):**
```
Optimization Recommendations: ait-devnet

Type        Priority   Issue               Current Value   Recommended Action              Expected Improvement
scaling     high       High block time     3.20s           Increase validator count        25%
resource    medium     High memory usage   180MB           Enable state pruning            15%
```

### Step 6: Export Complete Dashboard Data

Get a full JSON dashboard export suitable for ingestion by external monitoring tools.

```bash
aitbc analytics dashboard
```

**Expected output:**
```json
{
  "overview": {
    "total_chains": 3,
    "active_chains": 3,
    "health_scores": {"ait-hub": 85.0, "ait-devnet": 72.0, "ait-testnet": 60.0}
  },
  "alerts": [...],
  "performance_comparison": {...},
  "resource_usage": {...}
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
# monitoring_loop("ait-hub", interval=60)
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
aitbc analytics predict --chain-id ait-hub --hours 6 --format json

# Check for active alerts
aitbc analytics alerts --severity all --hours 24

# Validate dashboard export is valid JSON
aitbc analytics dashboard | python -m json.tool
```

---

## Related Resources

- [Analytics Documentation](../analytics/README.md)
- [Agent SDK Quick Start](../agent-sdk/QUICK_START_GUIDE.md)
- [Next Scenario: Security Setup](./19_security_setup.md)

---

*Last updated: 2026-06-25*
*Version: 1.0*
