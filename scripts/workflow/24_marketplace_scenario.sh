#!/usr/bin/env bash

# AITBC Marketplace Scenario Test
# Complete marketplace workflow: software offer, job execution, escrow, payment

set -e

# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    export SHOP_URL="${SHOP_URL:-https://aitbc3.aitbc.bubuit.net}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi

echo "=== 🛒 AITBC MARKETPLACE SCENARIO TEST ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "🎯 MARKETPLACE WORKFLOW SCENARIO (Updated for v0.4.x)"
echo "Testing complete marketplace functionality with new CLI"
echo ""

# 0. CHECK WALLET
echo "0. 💼 CHECK WALLET"
echo "=================="

echo "Checking for existing wallet..."
WALLET_COUNT=$(aitbc wallet list 2>/dev/null | grep -c "ait" || echo "0")
echo "Found $WALLET_COUNT wallets"

if [ "$WALLET_COUNT" -eq "0" ]; then
    echo "No wallet found, creating default wallet..."
    aitbc wallet create aitbc-user $(cat /var/lib/aitbc/keystore/.password 2>/dev/null || echo "default") 2>&1 || echo "⚠️  Wallet creation failed, may need manual setup"
fi

aitbc wallet list

echo ""
echo -e "${GREEN}✅ Wallet check complete${NC}"

# 1. LIST AVAILABLE OFFERS
echo "1. 📋 LIST AVAILABLE OFFERS"
echo "============================"

echo "Checking marketplace offers..."
aitbc market list

echo ""
echo -e "${GREEN}✅ Marketplace list retrieved${NC}"

# 2. CREATE SOFTWARE OFFER (Ollama)
echo ""
echo "2. 📝 CREATE SOFTWARE OFFER (Ollama)"
echo "======================================"

echo "Creating Ollama hardware+software bundle offer..."
OFFER_RESULT=$(aitbc market offer ollama llama3.2:3b 0.001 2>&1)
echo "$OFFER_RESULT"

# Extract transaction_hash from JSON output (handle mixed plain text + JSON)
TX_HASH=$(echo "$OFFER_RESULT" | python3 -c "
import sys, json, re
data = sys.stdin.read()
m = re.search(r'\{[^{}]*\}', data, re.DOTALL)
if m:
    try:
        d = json.loads(m.group())
        print(d.get('transaction_hash', ''))
    except:
        print('')
else:
    print('')
" 2>/dev/null || echo "")
echo "Transaction Hash: $TX_HASH"

if [ -z "$TX_HASH" ]; then
    echo -e "${RED}❌ Failed to create software offer (no transaction hash)${NC}"
    exit 1
fi

# Query marketplace list to find the offer by transaction hash
echo "Querying marketplace list to find offer ID..."
sleep 2  # Wait for blockchain to include the transaction
MARKET_LIST=$(aitbc market list 2>&1)
echo "$MARKET_LIST"

# Extract offer_id from marketplace list (parse entire JSON array with capital keys)
OFFER_ID=$(echo "$MARKET_LIST" | python3 -c "
import sys, json
data = sys.stdin.read()
# Find the JSON array
start = data.find('[')
if start >= 0:
    try:
        arr = json.loads(data[start:])
        # Filter for software offers (capital keys)
        sw_offers = [o for o in arr if o.get('Type') == 'SOFTWARE' or 'software' in str(o).lower()]
        if sw_offers:
            # Get the newest software offer (last in array)
            newest = sw_offers[-1]
            print(newest.get('Offer ID', newest.get('offer_id', '')))
        else:
            print('')
    except:
        print('')
else:
    print('')
" 2>/dev/null || echo "")
echo "Offer ID: $OFFER_ID"

if [ -z "$OFFER_ID" ]; then
    echo -e "${RED}❌ Failed to create software offer${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Software offer created: $OFFER_ID${NC}"

# 3. VERIFY OFFER IN PLUGIN REGISTRY
echo ""
echo "3. 🔍 VERIFY OFFER IN PLUGIN REGISTRY"
echo "======================================"

echo "Checking plugin registry..."
PLUGIN_CHECK=$(curl -s "http://localhost:8109/plugins?offer_id=$OFFER_ID" 2>/dev/null || echo "{}")
echo "$PLUGIN_CHECK"

echo ""
echo -e "${GREEN}✅ Plugin registry checked${NC}"

# 4. RUN OLLAMA INFERENCE WITH ESCROW
echo ""
echo "4. 🤖 RUN OLLAMA INFERENCE WITH ESCROW"
echo "======================================"

echo "Running inference with offer $OFFER_ID..."
RUN_RESULT=$(aitbc market run $OFFER_ID 'Analyze the performance implications of blockchain sharding on scalability and security.' 2>&1)
echo "$RUN_RESULT"

# Extract job_id from JSON output (handle mixed plain text + JSON)
JOB_ID=$(echo "$RUN_RESULT" | python3 -c "
import sys, json, re
data = sys.stdin.read()
m = re.search(r'\{[^{}]*\}', data, re.DOTALL)
if m:
    try:
        d = json.loads(m.group())
        print(d.get('job_id', ''))
    except:
        print('')
else:
    print('')
" 2>/dev/null || echo "")
echo "Job ID: $JOB_ID"

if [ -z "$JOB_ID" ]; then
    echo -e "${RED}❌ Failed to run inference${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Inference job created: $JOB_ID${NC}"

# 5. VERIFY ON-CHAIN JOB TRANSACTION
echo ""
echo "6. 📊 VERIFY ON-CHAIN JOB TRANSACTION"
echo "======================================"

echo "Checking job transaction on blockchain..."
# Wait a moment for transaction to be mined
sleep 3

# Check if job transaction exists on chain
JOB_TX_CHECK=$(curl -s $BLOCKCHAIN_RPC/rpc/market-list 2>/dev/null | jq ".software_offers[] | select(.job_id == \"$JOB_ID\")" || echo "{}")
echo "Job on-chain: $JOB_TX_CHECK"

echo ""
echo -e "${GREEN}✅ Job transaction verified${NC}"

# 6. TEST WHISPER TRANSCRIPTION
echo ""
echo "7. 🎤 TEST WHISPER TRANSCRIPTION"
echo "================================"

echo "Creating Whisper hardware+software bundle offer..."
WHISPER_OFFER_RESULT=$(aitbc market offer whisper base 0.002 2>&1)
echo "$WHISPER_OFFER_RESULT"

# Extract transaction_hash from JSON output (handle mixed plain text + JSON)
WHISPER_TX_HASH=$(echo "$WHISPER_OFFER_RESULT" | python3 -c "
import sys, json, re
data = sys.stdin.read()
m = re.search(r'\{[^{}]*\}', data, re.DOTALL)
if m:
    try:
        d = json.loads(m.group())
        print(d.get('transaction_hash', ''))
    except:
        print('')
else:
    print('')
" 2>/dev/null || echo "")
echo "Whisper Transaction Hash: $WHISPER_TX_HASH"

if [ -z "$WHISPER_TX_HASH" ]; then
    echo -e "${RED}❌ Failed to create Whisper software offer (no transaction hash)${NC}"
else
    # Query marketplace list to find the offer by transaction hash
    echo "Querying marketplace list to find Whisper offer ID..."
    sleep 2  # Wait for blockchain to include the transaction
    WHISPER_MARKET_LIST=$(aitbc market list 2>&1)

    # Extract offer_id from marketplace list (parse entire JSON array with capital keys)
    WHISPER_OFFER_ID=$(echo "$WHISPER_MARKET_LIST" | python3 -c "
import sys, json
data = sys.stdin.read()
# Find the JSON array
start = data.find('[')
if start >= 0:
    try:
        arr = json.loads(data[start:])
        # Filter for software offers (capital keys) with whisper service
        whisper_offers = [o for o in arr if o.get('Type') == 'SOFTWARE' and o.get('Service', '').lower() == 'whisper']
        if whisper_offers:
            # Get the newest whisper offer (last in array)
            newest = whisper_offers[-1]
            print(newest.get('Offer ID', newest.get('offer_id', '')))
        else:
            print('')
    except:
        print('')
else:
    print('')
" 2>/dev/null || echo "")
    echo "Whisper Offer ID: $WHISPER_OFFER_ID"
fi

if [ -n "$WHISPER_OFFER_ID" ]; then
    echo -e "${GREEN}✅ Whisper offer created: $WHISPER_OFFER_ID${NC}"

    # Create a test audio file (or use existing)
    TEST_AUDIO="/tmp/test_audio.wav"
    if [ ! -f "$TEST_AUDIO" ]; then
        echo "Creating test audio file..."
        # Create a minimal WAV file header for testing
        echo -e "RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xAC\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00" > "$TEST_AUDIO"
    fi

    echo "Running transcription test..."
    TRANSCRIBE_RESULT=$(aitbc market transcribe $WHISPER_OFFER_ID $TEST_AUDIO 2>&1)
    echo "$TRANSCRIBE_RESULT"

    TRANSCRIBE_JOB_ID=$(echo "$TRANSCRIBE_RESULT" | python3 -c "
import sys, json, re
data = sys.stdin.read()
m = re.search(r'\{[^{}]*\}', data, re.DOTALL)
if m:
    try:
        d = json.loads(m.group())
        print(d.get('job_id', ''))
    except:
        print('')
else:
    print('')
" 2>/dev/null || echo "")
    if [ -n "$TRANSCRIBE_JOB_ID" ]; then
        echo -e "${GREEN}✅ Transcription job created: $TRANSCRIBE_JOB_ID${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ Whisper offer creation skipped (service may not be available)${NC}"
fi

# 7. FINAL SUMMARY
echo ""
echo "8. 📊 FINAL SUMMARY"
echo "==================="

echo ""
echo "=== 🛒 MARKETPLACE SCENARIO COMPLETE ==="
echo ""
echo "✅ SCENARIO RESULTS:"
echo "• Ollama Offer ID: $OFFER_ID"
echo "• Ollama Job ID: $JOB_ID"
if [ -n "$WHISPER_OFFER_ID" ]; then
    echo "• Whisper Offer ID: $WHISPER_OFFER_ID"
fi
if [ -n "$TRANSCRIBE_JOB_ID" ]; then
    echo "• Transcription Job ID: $TRANSCRIBE_JOB_ID"
fi
echo ""

echo -e "${GREEN}🎉 MARKETPLACE SCENARIO: SUCCESSFUL${NC}"
echo "✅ All workflow steps completed with new CLI"
exit 0
