#!/bin/bash
# Wallet Creation Script for AITBC
# This script creates a new wallet on the aitbc follower node

set -e  # Exit on any error

echo "=== AITBC Wallet Creation ==="

# On aitbc, create a new wallet using AITBC simple wallet CLI
echo "1. Creating new wallet on aitbc..."
ssh aitbc 'python /opt/aitbc/cli/simple_wallet.py create --name aitbc-user --password-file /var/lib/aitbc/keystore/.password'

# Note the new wallet address
WALLET_ADDR=$(ssh aitbc 'cat /var/lib/aitbc/keystore/aitbc-user.json | jq -r .address')
echo "New wallet: $WALLET_ADDR"

# Verify wallet was created successfully
echo "2. Verifying wallet creation..."
ssh aitbc "python /opt/aitbc/cli/simple_wallet.py list --format json | jq '.[] | select(.name == \"aitbc-user\")'"

echo "✅ Wallet created successfully!"
echo "Wallet name: aitbc-user"
echo "Wallet address: $WALLET_ADDR"
echo "Wallet is ready to receive AIT coins."
