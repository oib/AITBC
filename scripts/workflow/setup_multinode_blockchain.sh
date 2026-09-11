#!/usr/bin/env bash
# Master AITBC Multi-Node Blockchain Setup Script
# This script orchestrates the complete multi-node blockchain setup

set -euo pipefail


# Source scenario configuration

# Fleet node addresses.
#
# These were hardcoded to one island's private subnet, which made the script
# useless anywhere else and put internal addressing in a public repository.
# Set them for your own deployment; there is deliberately no default.
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

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
echo "=== AITBC Multi-Node Blockchain Setup ==="
echo "This script will set up a complete multi-node blockchain network"
echo "with <node1> as genesis authority and aitbc as follower node"
echo

# This must run on the genesis authority node. That used to be decided by
# comparing `hostname` against one island's node name, which answered the
# question only on that island. The keystore is what actually makes a host the
# genesis authority, so test for that instead.
GENESIS_KEYSTORE="${AITBC_GENESIS_KEYSTORE:-/var/lib/aitbc/keystore/genesis.json}"
if [ ! -f "$GENESIS_KEYSTORE" ]; then
  echo "Error: no genesis keystore at $GENESIS_KEYSTORE -- this is not the genesis" >&2
  echo "   authority node. Set AITBC_GENESIS_KEYSTORE if it lives elsewhere." >&2
  exit 1
fi

read -p "Do you want to execute the complete workflow? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Workflow execution cancelled."
  echo "You can run individual scripts as needed:"
  echo "  ./01_preflight_setup.sh"
  echo "  ./02_genesis_authority_setup.sh"
  echo "  ./03_follower_node_setup.sh"
  echo "  ./04_create_wallet.sh"
  echo "  ./05_send_transaction.sh"
  echo "  ./06_final_verification.sh"
  exit 0
fi

echo "🚀 Starting complete multi-node blockchain setup..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Execute all steps in sequence
echo "Step 1: Pre-Flight Setup"
./01_preflight_setup.sh
echo

echo "Step 2: Genesis Authority Setup (<node1>)"
./02_genesis_authority_setup.sh
echo

echo "Step 3: Follower Node Setup (aitbc)"
./03_follower_node_setup.sh
echo

echo "Step 4: Wallet Creation"
./04_create_wallet.sh
echo

echo "Step 5: Transaction Sending"
./05_send_transaction.sh
echo

echo "Step 6: Final Verification"
./06_final_verification.sh
echo

echo
echo "🎉 COMPLETE MULTI-NODE BLOCKCHAIN SETUP FINISHED!"
echo
echo "📋 Summary:"
echo "✅ <node1>: Genesis authority node running"
echo "✅ aitbc: Follower node synchronized"
echo "✅ Network: Multi-node blockchain operational"
echo "✅ Transactions: Cross-node transfers working"
echo "✅ Configuration: Both nodes properly configured"
echo "✅ CLI Tool: All operations use CLI interface"
echo
echo "🔗 Quick Commands:"
echo "  Check status: ./06_final_verification.sh"
echo "  Create wallet: ./04_create_wallet.sh"
echo "  Send transaction: ./05_send_transaction.sh"
echo
echo "📚 Documentation: See workflow documentation for detailed information"
echo "🌐 Web Interface: $BLOCKCHAIN_RPC (<node1>) and http://${NODE1_HOST}:${BLOCKCHAIN_RPC_PORT:-8202} (aitbc)"
