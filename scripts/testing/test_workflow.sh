#!/bin/bash
# Test Updated Workflow Scripts
echo "=== Testing Updated Workflow Scripts ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKFLOW_DIR="${REPO_ROOT}/scripts/workflow"
CLI_PATH="${REPO_ROOT}/aitbc-cli"

echo "1. Testing wallet creation script..."
"${WORKFLOW_DIR}/04_create_wallet.sh"

echo ""
echo "2. Testing final verification script..."
export WALLET_ADDR=$("$CLI_PATH" wallet balance aitbc-user 2>/dev/null | grep "Address:" | awk '{print $2}' || echo "")
"${WORKFLOW_DIR}/06_final_verification.sh"

echo ""
echo "3. Testing transaction manager script..."
"${WORKFLOW_DIR}/09_transaction_manager.sh"

echo ""
echo "✅ All script tests completed!"
