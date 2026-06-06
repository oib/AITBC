#!/bin/bash
# Setup contract monitoring for deployed contracts

set -e

NETWORK="${1:-testnet}"
REPO_DIR="/opt/aitbc"
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
    "AgentMarketplace": {
      "address": "\${AGENT_MARKETPLACE_ADDRESS}",
      "monitor_events": ["AgentRegistered", "AgentDeregistered", "JobPosted", "JobCompleted"],
      "alert_thresholds": {
        "failed_registrations": 3,
        "marketplace downtime": 300
      }
    },
    "StakingContract": {
      "address": "\${STAKING_CONTRACT_ADDRESS}",
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
