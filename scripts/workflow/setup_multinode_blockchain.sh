#!/bin/bash
# Master AITBC Multi-Node Blockchain Setup Script
# This script orchestrates the complete multi-node blockchain setup

set -e  # Exit on any error

echo "=== AITBC Multi-Node Blockchain Setup ==="
echo "This script will set up a complete multi-node blockchain network"
echo "with aitbc1 as genesis authority and aitbc as follower node"
echo

# Check if running on aitbc1
if [ "$(hostname)" != "aitbc1" ]; then
  echo "Error: This script must be run on aitbc1 (genesis authority node)"
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

echo "Step 2: Genesis Authority Setup (aitbc1)"
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
echo "✅ aitbc1: Genesis authority node running"
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
echo "🌐 Web Interface: http://localhost:8006 (aitbc1) and http://10.1.223.40:8006 (aitbc)"
