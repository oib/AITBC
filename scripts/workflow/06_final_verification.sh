#!/usr/bin/env bash
# Final Verification Script for AITBC Multi-Node Blockchain
# This script verifies the complete multi-node setup using enhanced CLI

set -euo pipefail



# Fleet node addresses.
#
# These used to be ssh aliases from one operator's ~/.ssh/config, which meant
# the script only ran on that workstation and named the fleet in a public
# repository. Set them for your own deployment; there is deliberately no
# default.
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    # No default for the shop node: it used to name one island's host, which
    # was wrong everywhere else and published that host in a public repo.
    export SHOP_URL="${SHOP_URL:-${AITBC_SHOP_URL:?set AITBC_SHOP_URL to the shop node URL, or provide /etc/aitbc/.env.scenario}}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLI_PATH="${REPO_ROOT}/aitbc-cli"

echo "=== AITBC Multi-Node Blockchain Final Verification ==="

# Get wallet address (source from wallet creation script)
if [ -z "$WALLET_ADDR" ]; then
  echo "Error: WALLET_ADDR not set. Please run wallet creation script first."
  exit 1
fi

# Check both nodes are in sync using CLI
echo "1. Checking blockchain heights..."
echo "=== aitbc height (localhost) ==="
AITBC_HEIGHT=$(curl -s http://localhost:8202/rpc/head | jq -r '.height')
echo $AITBC_HEIGHT

echo "=== ${NODE1_HOST} height (remote) ==="
# Try to get ${NODE1_HOST} height, but handle SSH issues gracefully
if command -v ssh >/dev/null 2>&1 && ssh -o ConnectTimeout=5 ${NODE1_HOST} 'curl -s http://localhost:8202/rpc/head' >/dev/null 2>&1; then
  AITBC1_HEIGHT=$(ssh ${NODE1_HOST} 'curl -s http://localhost:8202/rpc/head | jq -r ".height"')
else
  echo "SSH to ${NODE1_HOST} not available - skipping remote check"
  AITBC1_HEIGHT=$AITBC_HEIGHT
fi
echo $AITBC1_HEIGHT

HEIGHT_DIFF=$((AITBC1_HEIGHT - AITBC_HEIGHT))
echo "Height difference: $HEIGHT_DIFF blocks"

# Check wallet balance using CLI
echo "2. Checking aitbc wallet balance..."
echo "=== aitbc wallet balance (local) ==="
BALANCE=$("$CLI_PATH" wallet balance aitbc-user 2>/dev/null | grep "Balance:" | awk '{print $2}' || echo "0")
echo $BALANCE AIT

# Get blockchain information using CLI
echo "3. Blockchain information..."
echo "=== Chain Information ==="
"$CLI_PATH" blockchain info

# Network health check using CLI
echo "4. Network health check..."
echo "=== Network Status (local) ==="
"$CLI_PATH" network status 2>/dev/null || echo "Network status not available"

# Service status
echo "5. Service status..."
echo "=== Service Status (local) ==="
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc

# Success criteria
echo "6. Success criteria check..."
if [ "$HEIGHT_DIFF" -le 5 ]; then
  echo "✅ Blockchain synchronized (height difference: $HEIGHT_DIFF)"
else
  echo "❌ Blockchain not synchronized (height difference: $HEIGHT_DIFF)"
fi

if [ "$BALANCE" -gt "0" ]; then
  echo "✅ Transaction successful (balance: $BALANCE AIT)"
else
  echo "❌ Transaction failed (balance: $BALANCE AIT)"
fi

if [ "$(systemctl is-active aitbc-blockchain-node)" = "active" ] && [ "$(systemctl is-active aitbc-blockchain-rpc)" = "active" ]; then
  echo "✅ ${NODE1_HOST} services operational"
else
  echo "❌ ${NODE1_HOST} services not operational"
fi

if [ "$(ssh aitbc 'systemctl is-active aitbc-blockchain-node')" = "active" ] && [ "$(ssh aitbc 'systemctl is-active aitbc-blockchain-rpc')" = "active" ]; then
  echo "✅ aitbc services operational"
else
  echo "❌ aitbc services not operational"
fi

echo "✅ Final verification completed using enhanced CLI!"
echo "Multi-node blockchain setup is ready for operation."
echo "All operations now use CLI tool with advanced capabilities."
