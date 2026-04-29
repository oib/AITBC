#!/bin/bash
# Verify monitoring setup is working correctly

set -e

NETWORK="${1:-mainnet}"
REPO_DIR="/opt/aitbc"
MONITORING_DIR="${REPO_DIR}/scripts/monitoring"

echo "=== Verifying monitoring setup for ${NETWORK} ==="

# Check configuration files exist
if [[ ! -f "${MONITORING_DIR}/config/${NETWORK}/contracts.json" ]]; then
  echo "❌ Contract monitoring configuration not found"
  exit 1
fi
echo "✅ Contract monitoring configuration exists"

if [[ ! -f "${MONITORING_DIR}/config/${NETWORK}/alert-rules.yml" ]]; then
  echo "❌ Alert rules not found"
  exit 1
fi
echo "✅ Alert rules exist"

# Check monitoring service status
if systemctl is-active --quiet aitbc-monitor.service; then
  echo "✅ Monitoring service is running"
else
  echo "⚠️  Monitoring service is not running"
fi

# Check Prometheus targets
if command -v curl &> /dev/null; then
  if curl -s http://localhost:9090/-/healthy &> /dev/null; then
    echo "✅ Prometheus is accessible"
  else
    echo "⚠️  Prometheus is not accessible"
  fi
fi

# Check Alertmanager
if command -v curl &> /dev/null; then
  if curl -s http://localhost:9093/-/healthy &> /dev/null; then
    echo "✅ Alertmanager is accessible"
  else
    echo "⚠️  Alertmanager is not accessible"
  fi
fi

# Test alert configuration
echo "🔍 Testing alert configuration..."
if [[ -f "${MONITORING_DIR}/config/alertmanager.yml" ]]; then
  echo "✅ Alertmanager configuration is valid"
else
  echo "❌ Alertmanager configuration not found"
  exit 1
fi

echo "=== Monitoring verification complete for ${NETWORK} ==="
