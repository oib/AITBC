#!/bin/bash
# Sync blockchain from aitbc1 to localhost

echo "=== BLOCKCHAIN SYNC FROM AITBC1 ==="

# AITBC1 connection details
AITBC1_HOST="aitbc1"
AITBC1_RPC_PORT="8006"
LOCAL_RPC_PORT="8006"

echo "1. Checking aitbc1 availability..."
if ! ssh $AITBC1_HOST "curl -s http://localhost:$AITBC1_RPC_PORT/rpc/head" > /dev/null; then
    echo "❌ aitbc1 RPC not available"
    exit 1
fi

echo "✅ aitbc1 RPC available"

echo "2. Starting local blockchain RPC..."
systemctl start aitbc-blockchain-rpc
sleep 5

echo "3. Checking local RPC availability..."
if ! curl -s http://localhost:$LOCAL_RPC_PORT/rpc/head > /dev/null; then
    echo "❌ Local RPC not available"
    exit 1
fi

echo "✅ Local RPC available"

echo "4. Syncing blockchain from aitbc1..."
# Use the sync utility to sync from aitbc1
cd /opt/aitbc
python3 -m aitbc_chain.sync_cli \
    --source http://$AITBC1_HOST:$AITBC1_RPC_PORT \
    --import-url http://localhost:$LOCAL_RPC_PORT \
    --batch-size 100

echo "✅ Blockchain sync completed"

echo "5. Verifying sync..."
sleep 3
LOCAL_HEIGHT=$(curl -s http://localhost:$LOCAL_RPC_PORT/rpc/head | jq -r '.height // 0')
AITBC1_HEIGHT=$(ssh $AITBC1_HOST "sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db 'SELECT MAX(height) FROM block;'")

echo "Local height: $LOCAL_HEIGHT"
echo "aitbc1 height: $AITBC1_HEIGHT"

if [ "$LOCAL_HEIGHT" -eq "$AITBC1_HEIGHT" ]; then
    echo "✅ Sync successful - nodes are on same height"
else
    echo "⚠️  Heights differ, but sync may still be in progress"
fi

echo "=== SYNC COMPLETE ==="
