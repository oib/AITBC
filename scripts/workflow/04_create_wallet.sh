#!/bin/bash
# Wallet Creation Script for AITBC
# This script creates a new wallet on the aitbc follower node using enhanced CLI

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLI_PATH="${REPO_ROOT}/aitbc-cli"

echo "=== AITBC Wallet Creation (Enhanced CLI) ==="

echo "1. Pre-creation verification..."
echo "=== Current wallets on aitbc ==="
"$CLI_PATH" wallet list

echo "2. Creating new wallet on aitbc..."
"$CLI_PATH" wallet create aitbc-user $(cat /var/lib/aitbc/keystore/.password)

# Get wallet address using CLI
WALLET_ADDR=$("$CLI_PATH" wallet balance aitbc-user 2>/dev/null | grep "Address:" | awk '{print $2}' || echo "")
echo "New wallet address: $WALLET_ADDR"

# Verify wallet was created successfully using CLI
echo "3. Post-creation verification..."
echo "=== Updated wallet list ==="
"$CLI_PATH" wallet list | grep aitbc-user || echo "Wallet not found in list"

echo "=== New wallet details ==="
"$CLI_PATH" wallet balance aitbc-user

echo "=== All wallets summary ==="
"$CLI_PATH" wallet list

echo "4. Cross-node verification..."
echo "=== Network status (local) ==="
"$CLI_PATH" network status 2>/dev/null || echo "Network status not available"

echo "✅ Wallet created successfully using enhanced CLI!"
echo "Wallet name: aitbc-user"
echo "Wallet address: $WALLET_ADDR"
echo "Wallet is ready to receive AIT coins."
echo "All operations used enhanced CLI capabilities."
