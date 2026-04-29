#!/bin/bash
# Setup automated monitoring alerts for deployed contracts

set -e

NETWORK="${1:-mainnet}"
REPO_DIR="/opt/aitbc"
MONITORING_DIR="${REPO_DIR}/scripts/monitoring"

echo "=== Setting up automated alerts for ${NETWORK} ==="

# Create alerting rules
cat > "${MONITORING_DIR}/config/${NETWORK}/alert-rules.yml" << EOF
groups:
  - name: aitbc-contracts-alerts
    interval: 30s
    rules:
      # Payment Processor Alerts
      - alert: HighFailedTransactionRate
        expr: rate(contract_failed_transactions_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          network: ${NETWORK}
          contract: PaymentProcessor
        annotations:
          summary: "High failed transaction rate on PaymentProcessor"
          description: "Failed transaction rate is {{ $value }} per second"

      - alert: PaymentProcessorDown
        expr: up{job="aitbc-contracts-${NETWORK}", contract="PaymentProcessor"} == 0
        for: 2m
        labels:
          severity: critical
          network: ${NETWORK}
          contract: PaymentProcessor
        annotations:
          summary: "PaymentProcessor contract is down"
          description: "PaymentProcessor has been down for more than 2 minutes"

      # Agent Marketplace Alerts
      - alert: FailedAgentRegistrations
        expr: rate(contract_failed_registrations_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
          network: ${NETWORK}
          contract: AgentMarketplace
        annotations:
          summary: "High failed agent registration rate"
          description: "Failed registration rate is {{ $value }} per second"

      - alert: MarketplaceLowActivity
        expr: rate(contract_jobs_posted_total[1h]) < 0.001
        for: 1h
        labels:
          severity: info
          network: ${NETWORK}
          contract: AgentMarketplace
        annotations:
          summary: "Low marketplace activity"
          description: "Job posting rate is unusually low"

      # Staking Contract Alerts
      - alert: UnusualWithdrawalActivity
        expr: rate(contract_stake_withdrawals_total[10m]) > 0.1
        for: 5m
        labels:
          severity: warning
          network: ${NETWORK}
          contract: StakingContract
        annotations:
          summary: "Unusual withdrawal activity detected"
          description: "Withdrawal rate is {{ $value }} per second"

      - alert: RewardDistributionDelay
        expr: time() - contract_last_reward_distribution_timestamp > 3600
        for: 10m
        labels:
          severity: warning
          network: ${NETWORK}
          contract: StakingContract
        annotations:
          summary: "Reward distribution delayed"
          description: "Rewards have not been distributed for over 1 hour"

      # General Contract Health
      - alert: ContractGasPriceSpike
        expr: contract_gas_price > 100000000000
        for: 5m
        labels:
          severity: warning
          network: ${NETWORK}
        annotations:
          summary: "Gas price spike detected"
          description: "Gas price is {{ $value }} wei"

      - alert: ContractBalanceLow
        expr: contract_balance < 0.1
        for: 10m
        labels:
          severity: critical
          network: ${NETWORK}
        annotations:
          summary: "Contract balance critically low"
          description: "Contract balance is {{ $value }} ETH"
EOF

echo "✅ Alert rules created for ${NETWORK}"

# Setup notification templates
mkdir -p "${MONITORING_DIR}/templates"

cat > "${MONITORING_DIR}/templates/alert-notification.tmpl" << EOF
{{ define "slack.default.title" }}
{{ .Status | toUpper }}: {{ .CommonLabels.alertname }} on {{ .CommonLabels.network }}
{{ end }}

{{ define "slack.default.text" }}
{{ range .Alerts }}
*Alert:* {{ .Labels.alertname }}
*Severity:* {{ .Labels.severity }}
*Contract:* {{ .Labels.contract }}
*Network:* {{ .Labels.network }}
*Description:* {{ .Annotations.description }}
*Timestamp:* {{ .StartsAt.Format "2006-01-02 15:04:05" }}
{{ end }}
{{ end }}
EOF

echo "✅ Notification templates created"

# Setup alertmanager configuration
cat > "${MONITORING_DIR}/config/alertmanager.yml" << EOF
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'network', 'contract']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'

  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
    - match:
        severity: warning
      receiver: 'slack-warnings'
    - match:
        severity: info
      receiver: 'slack-info'

receivers:
  - name: 'default'
    slack_configs:
      - api_url: '\${SLACK_WEBHOOK_URL}'
        channel: '#aitbc-alerts'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '\${PAGERDUTY_API_KEY}'
        severity: 'critical'

  - name: 'slack-warnings'
    slack_configs:
      - api_url: '\${SLACK_WEBHOOK_URL}'
        channel: '#aitbc-warnings'

  - name: 'slack-info'
    slack_configs:
      - api_url: '\${SLACK_WEBHOOK_URL}'
        channel: '#aitbc-info'
EOF

echo "✅ Alertmanager configuration created"

# Enable monitoring service
if [[ -f "/etc/systemd/system/aitbc-monitor.service" ]]; then
  systemctl enable aitbc-monitor.service
  systemctl start aitbc-monitor.service
  echo "✅ Monitoring service started"
else
  echo "⚠️  Monitoring service not found, skipping service start"
fi

echo "=== Automated alerts setup complete for ${NETWORK} ==="
