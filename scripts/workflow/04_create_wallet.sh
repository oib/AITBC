#!/bin/bash
# Wallet Creation Script for AITBC
# This script creates a new wallet on the aitbc follower node using enhanced CLI

set -e  # Exit on any error

echo "=== AITBC Wallet Creation (Enhanced CLI) ==="

echo "1. Pre-creation verification..."
echo "=== Current wallets on aitbc ==="
ssh aitbc '/opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py list'

echo "2. Creating new wallet on aitbc..."
ssh aitbc '/opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py create --name aitbc-user --password-file /var/lib/aitbc/keystore/.password'

# Get wallet address using CLI
WALLET_ADDR=$(ssh aitbc '/opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py balance --name aitbc-user --format json | jq -r ".address"')
echo "New wallet address: $WALLET_ADDR"

# Verify wallet was created successfully using CLI
echo "3. Post-creation verification..."
echo "=== Updated wallet list ==="
ssh aitbc "/opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py list --format json | jq '.[] | select(.name == \"aitbc-user\")'"

echo "=== New wallet details ==="
ssh aitbc '/opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py balance --name aitbc-user'

echo "=== All wallets summary ==="
ssh aitbc '/opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py list'

echo "4. Cross-node verification..."
echo "=== Network status (aitbc1) ==="
/opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py network

echo "=== Network status (aitbc) ==="
ssh aitbc '/opt/aitbc/venv/bin/python /opt/aitbc/cli/simple_wallet.py network'

echo "✅ Wallet created successfully using enhanced CLI!"
echo "Wallet name: aitbc-user"
echo "Wallet address: $WALLET_ADDR"
echo "Wallet is ready to receive AIT coins."
echo "All operations used enhanced CLI capabilities."
