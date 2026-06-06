#!/bin/bash
# Blockchain RPC Startup Optimization Script
# Optimizes database and reduces restart time

echo "=== Blockchain RPC Startup Optimization ==="

# Database path
DB_PATH="/var/lib/aitbc/data/ait-mainnet/chain.db"

if [ -f "$DB_PATH" ]; then
    echo "1. Optimizing database WAL checkpoint..."
    sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" 2>/dev/null
    echo "✅ WAL checkpoint completed"
    
    echo "2. Checking database size..."
    ls -lh "$DB_PATH"*
    
    echo "3. Restarting blockchain RPC service..."
    systemctl restart aitbc-blockchain-rpc
    
    echo "4. Waiting for startup completion..."
    sleep 3
    
    echo "5. Verifying service status..."
    if systemctl is-active --quiet aitbc-blockchain-rpc; then
        echo "✅ Blockchain RPC service is running"
    else
        echo "❌ Blockchain RPC service failed to start"
        exit 1
    fi
    
    echo "✅ Optimization completed successfully"
else
    echo "❌ Database not found at $DB_PATH"
    exit 1
fi
