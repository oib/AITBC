#!/bin/bash
# Setup contract monitoring for deployed contracts

set -euo pipefail

NETWORK="${1:-mainnet}"
# Resolved from this script rather than hardcoded (AITBC-138).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_DIR="$REPO_ROOT"
MONITORING_DIR="${REPO_DIR}/scripts/monitoring"

echo "=== Setting up contract monitoring for ${NETWORK} ==="

# Ensure monitoring directory exists
mkdir -p "${MONITORING_DIR}/config/${NETWORK}"

# Create monitoring configuration
cat > "${MONITORING_DIR}/config/${NETWORK}/contracts.json" << EOF
{
  "network": "${NETWORK}",
  "contracts": {
    "PaymentProcessor": {
      "address": "\${PAYMENT_PROCESSOR_ADDRESS}",
      "monitor_events": ["PaymentReceived", "PaymentRefunded", "PaymentCompleted"],
      "alert_thresholds": {
        "failed_transactions": 5,
        "gas_price_spike": 100
      }
    },
    "AgentMarketplaceV2": {
      "address": "\${AGENT_MARKETPLACE_V2_ADDRESS}",
      "monitor_events": ["AgentRegistered", "AgentDeregistered", "JobPosted", "JobCompleted"],
      "alert_thresholds": {
        "failed_registrations": 3,
        "market downtime": 300
      }
    },
    "AgentStaking": {
      "address": "\${AGENT_STAKING_ADDRESS}",
      "monitor_events": ["StakeDeposited", "StakeWithdrawn", "RewardsDistributed"],
      "alert_thresholds": {
        "unusual_withdrawals": 10,
        "reward_delay": 3600
      }
    }
  },
  "alert_channels": {
    "slack": "\${SLACK_WEBHOOK_URL}",
    "email": "\${ALERT_EMAIL}",
    "pagerduty": "\${PAGERDUTY_API_KEY}"
  }
}
EOF

echo "✅ Contract monitoring configuration created for ${NETWORK}"

# Setup Prometheus metrics for contract monitoring
cat > "${MONITORING_DIR}/config/${NETWORK}/prometheus.yml" << EOF
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'aitbc-contracts-${NETWORK}'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: '/metrics/contracts'
EOF

# Alert rules the verifier requires — ship them with the same setup run.
cat > "${MONITORING_DIR}/config/${NETWORK}/alert-rules.yml" << 'RULES'
groups:
  - name: aitbc-contracts
    rules:
      - alert: ContractFailedTransactions
        expr: increase(contract_failed_transactions_total[5m]) > 5
        for: 5m
        labels: {severity: warning}
        annotations: {summary: "Failed contract transactions above threshold"}
RULES

# Alertmanager config at the path verify-monitoring.sh checks.
cat > "${MONITORING_DIR}/config/alertmanager.yml" << 'AM'
global:
  smtp_smarthost: 'localhost:587'
  smtp_from: 'alerts@aitbc'
route:
  receiver: 'default'
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://localhost:5001/alerts'
AM
