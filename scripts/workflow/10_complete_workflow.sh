#!/usr/bin/env bash
set -euo pipefail
# AITBC Complete Multi-Node Workflow Script
# Runs the entire multi-node blockchain setup with error handling

echo "=== AITBC Complete Multi-Node Workflow ==="
echo "This script sets up a complete two-node blockchain network"

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
echo "aitbc1: Genesis Authority | aitbc: Follower Node"
echo

# This must run on the genesis authority node. That used to be decided by
# comparing `hostname` against one island's node name, which answered the
# question only on that island. The keystore is what actually makes a host the
# genesis authority, so test for that instead.
GENESIS_KEYSTORE="${AITBC_GENESIS_KEYSTORE:-/var/lib/aitbc/keystore/genesis.json}"
if [ ! -f "$GENESIS_KEYSTORE" ]; then
  echo "❌ Error: no genesis keystore at $GENESIS_KEYSTORE -- this is not the genesis" >&2
  echo "   authority node. Set AITBC_GENESIS_KEYSTORE if it lives elsewhere." >&2
  exit 1
fi

# Define workflow steps
STEPS=(
  "01_preflight_setup.sh:Pre-Flight Setup"
  "02_genesis_authority_setup.sh:Genesis Authority Setup"
  "03_follower_node_setup.sh:Follower Node Setup"
  "08_blockchain_sync_fix.sh:Blockchain Sync Fix"
  "04_create_wallet.sh:Wallet Creation"
  "09_transaction_manager.sh:Transaction Manager"
  "06_final_verification.sh:Final Verification"
)

# Execute workflow steps
for step in "${STEPS[@]}"; do
  SCRIPT=$(echo "$step" | cut -d: -f1)
  DESCRIPTION=$(echo "$step" | cut -d: -f2)

  echo
  echo "=========================================="
  echo "STEP: $DESCRIPTION"
  echo "SCRIPT: $SCRIPT"
  echo "=========================================="

  if [ -f "/opt/aitbc/scripts/workflow/$SCRIPT" ]; then
    echo "Executing $SCRIPT..."
    bash "/opt/aitbc/scripts/workflow/$SCRIPT"

    if [ $? -eq 0 ]; then
      echo "✅ $DESCRIPTION completed successfully"
    else
      echo "❌ $DESCRIPTION failed"
      echo "Continue with next step? (y/N)"
      read -r response
      if [[ ! $response =~ ^[Yy]$ ]]; then
        echo "Workflow stopped by user"
        exit 1
      fi
    fi
  else
    echo "❌ Script not found: $SCRIPT"
    echo "Continue with next step? (y/N)"
    read -r response
    if [[ ! $response =~ ^[Yy]$ ]]; then
      echo "Workflow stopped by user"
      exit 1
    fi
  fi

  echo "Press Enter to continue to next step..."
  read -r
done

echo
echo "=========================================="
echo "🎉 MULTI-NODE BLOCKCHAIN WORKFLOW COMPLETE!"
echo "=========================================="
echo

# Final status check
echo "Final Status Check:"
echo "=================="

AITBC1_HEIGHT=$(curl -s $BLOCKCHAIN_RPC/rpc/head | jq .height 2>/dev/null || echo "0")
AITBC_HEIGHT=$(ssh aitbc 'curl -s $BLOCKCHAIN_RPC/rpc/head | jq .height 2>/dev/null || echo "0"')

echo "aitbc1 (Genesis):"
echo "  Height: $AITBC1_HEIGHT"
echo "  Services: $(systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc | tr '\n' ' ')"

echo
echo "aitbc (Follower):"
echo "  Height: $AITBC_HEIGHT"
echo "  Services: $(ssh aitbc 'systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc 2>/dev/null | tr "\n" " "')"

echo
echo "Wallet Status:"
if [ -f "/var/lib/aitbc/keystore/aitbc-wallet.json" ]; then
  WALLET_ADDR=$(cat /var/lib/aitbc/keystore/aitbc-wallet.json | jq -r '.address')
  WALLET_BALANCE=$(curl -s "$BLOCKCHAIN_RPC/rpc/getBalance/$WALLET_ADDR" | jq .balance 2>/dev/null || echo "0")
  echo "  Wallet: $WALLET_ADDR"
  echo "  Balance: $WALLET_BALANCE AIT"
else
  echo "  Wallet: Not created"
fi

echo
echo "Network Status:"
HEIGHT_DIFF=$((AITBC1_HEIGHT - AITBC_HEIGHT))
if [ $HEIGHT_DIFF -le 2 ]; then
  echo "  ✅ Nodes synchronized (diff: $HEIGHT_DIFF blocks)"
else
  echo "  ⚠️ Nodes not synchronized (diff: $HEIGHT_DIFF blocks)"
fi

echo
echo "🚀 Multi-node blockchain setup is ready!"
echo "Next Steps:"
echo "1. Run enterprise automation: /opt/aitbc/scripts/workflow/07_enterprise_automation.sh"
echo "2. Monitor with health checks: /opt/aitbc/scripts/health_check.sh"
echo "3. Test with integration tests: /opt/aitbc/tests/integration_test.sh"

echo "=== Complete Workflow Finished ==="
