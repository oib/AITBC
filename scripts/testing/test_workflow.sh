#!/bin/bash
# Test Updated Workflow Scripts
echo "=== Testing Updated Workflow Scripts ==="

echo "1. Testing wallet creation script..."
/opt/aitbc/scripts/workflow/04_create_wallet.sh

echo ""
echo "2. Testing final verification script..."
export WALLET_ADDR=$(/opt/aitbc/aitbc-cli balance --name aitbc-user 2>/dev/null | grep "Address:" | awk '{print $2}' || echo "")
/opt/aitbc/scripts/workflow/06_final_verification.sh

echo ""
echo "3. Testing transaction manager script..."
/opt/aitbc/scripts/workflow/09_transaction_manager.sh

echo ""
echo "✅ All script tests completed!"
