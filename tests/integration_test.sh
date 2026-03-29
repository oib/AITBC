#!/bin/bash
# Integration test suite for AITBC multi-node setup

echo "=== AITBC Integration Tests ==="

# Test 1: Basic connectivity
echo "1. Testing connectivity..."
curl -s http://localhost:8006/rpc/head >/dev/null && echo "✅ RPC accessible" || echo "❌ RPC failed"
ssh aitbc 'curl -s http://localhost:8006/rpc/head' >/dev/null && echo "✅ Remote RPC accessible" || echo "❌ Remote RPC failed"

# Test 2: Wallet operations
echo "2. Testing wallet operations..."
python /opt/aitbc/cli/simple_wallet.py list >/dev/null && echo "✅ Wallet list works" || echo "❌ Wallet list failed"

# Test 3: Transaction operations
echo "3. Testing transactions..."
# Create test wallet
python /opt/aitbc/cli/simple_wallet.py create --name test-integration --password-file /var/lib/aitbc/keystore/.password >/dev/null && echo "✅ Wallet creation works" || echo "❌ Wallet creation failed"

# Test 4: Blockchain operations
echo "4. Testing blockchain operations..."
python /opt/aitbc/cli/simple_wallet.py chain >/dev/null && echo "✅ Chain info works" || echo "❌ Chain info failed"

echo "=== Integration Tests Complete ==="
