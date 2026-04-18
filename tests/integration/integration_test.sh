#!/bin/bash
# Integration test suite for AITBC multi-node setup

echo "=== AITBC Integration Tests ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLI_CMD="${REPO_ROOT}/aitbc-cli"

# Test 1: Basic connectivity
echo "1. Testing connectivity..."
curl -s http://localhost:8006/rpc/head >/dev/null && echo "✅ RPC accessible" || echo "❌ RPC failed"
ssh -i ~/.ssh/id_ed25519_aitbc -o StrictHostKeyChecking=no root@aitbc1 'curl -s http://localhost:8007/rpc/head' >/dev/null && echo "✅ Remote RPC accessible" || echo "❌ Remote RPC failed"

# Test 2: Wallet operations
echo "2. Testing wallet operations..."
"$CLI_CMD" wallet list >/dev/null && echo "✅ Wallet list works" || echo "❌ Wallet list failed"

# Test 3: Transaction operations
echo "3. Testing transactions..."
# Create test wallet
"$CLI_CMD" wallet create test-integration --password-file /var/lib/aitbc/keystore/.password >/dev/null && echo "✅ Wallet creation works" || echo "❌ Wallet creation failed"

# Test 4: Blockchain operations
echo "4. Testing blockchain operations..."
"$CLI_CMD" blockchain info >/dev/null && echo "✅ Chain info works" || echo "❌ Chain info failed"

# Test 5: Enterprise CLI operations
echo "5. Testing enterprise CLI operations..."
"$CLI_CMD" market list >/dev/null && echo "✅ Marketplace CLI works" || echo "❌ Marketplace CLI failed"

# Test 6: Mining operations
echo "6. Testing mining operations..."
"$CLI_CMD" mining status >/dev/null && echo "✅ Mining operations work" || echo "❌ Mining operations failed"

# Test 7: AI services
echo "7. Testing AI services..."
curl -s http://localhost:8006/rpc/ai/stats >/dev/null && echo "✅ AI services work" || echo "❌ AI services failed"

# Test 8: Marketplace
echo "8. Testing marketplace..."
curl -s http://localhost:8006/rpc/marketplace/listings >/dev/null && echo "✅ Marketplace works" || echo "❌ Marketplace failed"

echo "=== Integration Tests Complete ==="
