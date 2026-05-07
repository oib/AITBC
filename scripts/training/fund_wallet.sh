#!/bin/bash
# AITBC Wallet Funding Script
# Funds a wallet from the genesis wallet using the genesis password

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AITBC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLI_PATH="$AITBC_DIR/aitbc-cli"
GENESIS_PASSWORD_FILE="/var/lib/aitbc/keystore/.genesis_password"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

usage() {
    echo "Usage: $0 <wallet_name> [amount]"
    echo ""
    echo "Arguments:"
    echo "  wallet_name  Name of the wallet to fund"
    echo "  amount      Amount of AIT to send (default: 1000)"
    echo ""
    echo "Example:"
    echo "  $0 hermes-trainee 1000"
    echo ""
    echo "Note: The genesis password is read from $GENESIS_PASSWORD_FILE"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

WALLET_NAME="$1"
AMOUNT="${2:-1000}"

print_status "Funding wallet: $WALLET_NAME"
print_status "Amount: $AMOUNT AIT"

# Check if genesis password file exists
if [ ! -f "$GENESIS_PASSWORD_FILE" ]; then
    print_error "Genesis password file not found: $GENESIS_PASSWORD_FILE"
    print_error "Please ensure the genesis wallet is properly configured"
    exit 1
fi

# Read genesis password
GENESIS_PASSWORD=$(cat "$GENESIS_PASSWORD_FILE")
if [ -z "$GENESIS_PASSWORD" ]; then
    print_error "Genesis password file is empty"
    exit 1
fi

print_status "Genesis password loaded"

# Check if CLI exists
if [ ! -f "$CLI_PATH" ]; then
    print_error "AITBC CLI not found: $CLI_PATH"
    exit 1
fi

# Check genesis wallet balance
print_status "Checking genesis wallet balance..."
GENESIS_BALANCE=$("$CLI_PATH" wallet balance genesis 2>&1 || echo "0")
print_status "Genesis wallet balance: $GENESIS_BALANCE"

# Fund the wallet
print_status "Sending $AMOUNT AIT from genesis to $WALLET_NAME..."
cd "$AITBC_DIR"
RESULT=$("$CLI_PATH" wallet send genesis "$WALLET_NAME" "$AMOUNT" "$GENESIS_PASSWORD" 2>&1)

if [ $? -eq 0 ]; then
    print_success "Transaction sent successfully"
    echo "Transaction hash: $RESULT"
    
    # Verify balance
    print_status "Verifying wallet balance..."
    WALLET_BALANCE=$("$CLI_PATH" wallet balance "$WALLET_NAME" 2>&1 || echo "0")
    print_success "Wallet $WALLET_NAME balance: $WALLET_BALANCE"
else
    print_error "Funding failed: $RESULT"
    exit 1
fi

print_success "Wallet funding completed"
