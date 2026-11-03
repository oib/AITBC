#!/bin/bash
# Verify monitoring setup is working correctly

set -euo pipefail

NETWORK="${1:-mainnet}"
# Resolved from this script rather than hardcoded (AITBC-138).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_DIR="$REPO_ROOT"
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
if systemctl is-active --quiet aitbc-monitoring.service; then
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

# Test alert configuration — a present-but-broken file is a failure,
# not a pass (#922).
echo "🔍 Testing alert configuration..."
AM_YML="${MONITORING_DIR}/config/alertmanager.yml"
if [[ ! -f "$AM_YML" ]]; then
  echo "❌ Alertmanager configuration not found"
  exit 1
fi
if command -v amtool &> /dev/null; then
  if amtool check-config "$AM_YML" &> /dev/null; then
    echo "✅ Alertmanager configuration is valid"
  else
    echo "❌ Alertmanager configuration is invalid"
    exit 1
  fi
else
  # No amtool — require the file to at least parse as YAML with a route
  # and a receivers list (system python3, PyYAML where available).
  if python3 - "$AM_YML" << 'YAMLCHK' 2>/dev/null
import sys
try:
    import yaml
    doc = yaml.safe_load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(doc, dict) and doc.get("route") and doc.get("receivers") else 1)
YAMLCHK
  then
    echo "✅ Alertmanager configuration is valid"
  else
    echo "❌ Alertmanager configuration is invalid (does not parse or lacks route/receivers)"
    exit 1
  fi
fi

echo "=== Monitoring verification complete for ${NETWORK} ==="
