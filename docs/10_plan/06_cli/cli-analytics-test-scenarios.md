# CLI Analytics Commands Test Scenarios

This document outlines the test scenarios for the `aitbc analytics` command group. These scenarios are designed to verify the functionality, output formatting, and error handling of each analytics command.

## 1. `analytics alerts`

**Command Description:** View performance alerts across chains.

### Scenario 1.1: Default Alerts View
- **Command:** `aitbc analytics alerts`
- **Description:** Run the alerts command without any arguments to see all recent alerts in table format.
- **Expected Output:** A formatted table displaying alerts (or a message indicating no alerts if the system is healthy), showing severity, chain ID, message, and timestamp.

### Scenario 1.2: Filter by Severity
- **Command:** `aitbc analytics alerts --severity critical`
- **Description:** Filter alerts to show only those marked as 'critical'.
- **Expected Output:** Table showing only critical alerts. If none exist, an empty table or "No alerts found" message.

### Scenario 1.3: Time Range Filtering
- **Command:** `aitbc analytics alerts --hours 48`
- **Description:** Fetch alerts from the last 48 hours instead of the default 24 hours.
- **Expected Output:** Table showing alerts from the extended time period.

### Scenario 1.4: JSON Output Format
- **Command:** `aitbc analytics alerts --format json`
- **Description:** Request the alerts data in JSON format for programmatic parsing.
- **Expected Output:** Valid JSON array containing alert objects with detailed metadata.

---

## 2. `analytics dashboard`

**Command Description:** Get complete dashboard data for all chains.

### Scenario 2.1: JSON Dashboard Output
- **Command:** `aitbc analytics dashboard --format json`
- **Description:** Retrieve the comprehensive system dashboard data.
- **Expected Output:** A large JSON object containing:
  - `chain_metrics`: Detailed stats for each chain (TPS, block time, memory, nodes).
  - `alerts`: Current active alerts across the network.
  - `predictions`: Any future performance predictions.
  - `recommendations`: Optimization suggestions.

### Scenario 2.2: Default Dashboard View
- **Command:** `aitbc analytics dashboard`
- **Description:** Run the dashboard command without specifying format (defaults to JSON).
- **Expected Output:** Same comprehensive JSON output as 2.1.

---

## 3. `analytics monitor`

**Command Description:** Monitor chain performance in real-time.

### Scenario 3.1: Real-time Monitoring (Default Interval)
- **Command:** `aitbc analytics monitor --realtime`
- **Description:** Start a real-time monitoring session. (Note: May need manual termination `Ctrl+C`).
- **Expected Output:** A continuously updating display (like a top/htop view or appending log lines) showing current TPS, block times, and node health.

### Scenario 3.2: Custom Update Interval
- **Command:** `aitbc analytics monitor --realtime --interval 5`
- **Description:** Real-time monitoring updating every 5 seconds.
- **Expected Output:** The monitoring display updates at the specified 5-second interval.

### Scenario 3.3: Specific Chain Monitoring
- **Command:** `aitbc analytics monitor --realtime --chain-id ait-devnet`
- **Description:** Focus real-time monitoring on a single specific chain.
- **Expected Output:** Metrics displayed are exclusively for the `ait-devnet` chain.

---

## 4. `analytics optimize`

**Command Description:** Get optimization recommendations based on current chain metrics.

### Scenario 4.1: General Recommendations
- **Command:** `aitbc analytics optimize`
- **Description:** Fetch recommendations for all configured chains.
- **Expected Output:** A table listing the Chain ID, the specific Recommendation (e.g., "Increase validator count"), the target metric, and potential impact.

### Scenario 4.2: Chain-Specific Recommendations
- **Command:** `aitbc analytics optimize --chain-id ait-healthchain`
- **Description:** Get optimization advice only for the healthchain.
- **Expected Output:** Table showing recommendations solely for `ait-healthchain`.

### Scenario 4.3: JSON Output
- **Command:** `aitbc analytics optimize --format json`
- **Description:** Get optimization data as JSON.
- **Expected Output:** Valid JSON dictionary mapping chain IDs to arrays of recommendation objects.

---

## 5. `analytics predict`

**Command Description:** Predict chain performance trends based on historical data.

### Scenario 5.1: Default Prediction
- **Command:** `aitbc analytics predict`
- **Description:** Generate predictions for all chains over the default time horizon.
- **Expected Output:** Table displaying predicted trends for metrics like TPS, Block Time, and Resource Usage (e.g., "Trend: Stable", "Trend: Degrading").

### Scenario 5.2: Extended Time Horizon
- **Command:** `aitbc analytics predict --hours 72`
- **Description:** Generate predictions looking 72 hours ahead.
- **Expected Output:** Prediction table updated to reflect the longer timeframe analysis.

### Scenario 5.3: Specific Chain Prediction (JSON)
- **Command:** `aitbc analytics predict --chain-id ait-testnet --format json`
- **Description:** Get JSON formatted predictions for a single chain.
- **Expected Output:** JSON object containing predictive models/trends for `ait-testnet`.

---

## 6. `analytics summary`

**Command Description:** Get performance summary for chains over a specified period.

### Scenario 6.1: Global Summary (Table)
- **Command:** `aitbc analytics summary`
- **Description:** View a high-level summary of all chains over the default 24-hour period.
- **Expected Output:** A formatted table showing aggregated stats (Avg TPS, Min/Max block times, Health Score) per chain.

### Scenario 6.2: Custom Time Range
- **Command:** `aitbc analytics summary --hours 12`
- **Description:** Limit the summary to the last 12 hours.
- **Expected Output:** Table showing stats calculated only from data generated in the last 12 hours.

### Scenario 6.3: Chain-Specific Summary (JSON)
- **Command:** `aitbc analytics summary --chain-id ait-devnet --format json`
- **Description:** Detailed summary for a single chain in JSON format.
- **Expected Output:** Valid JSON object containing the `chain_id`, `time_range_hours`, `latest_metrics`, `statistics`, and `health_score` for `ait-devnet`.
