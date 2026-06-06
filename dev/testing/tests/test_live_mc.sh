#!/bin/bash

# Define the proxy ports and internal container ports
# Coordinator proxies: localhost:8000 -> aitbc:8000, localhost:8015 -> aitbc1:8015
# However, the node RPC is on port 8082 in the container and proxied differently.
# For direct access, we'll ssh into the containers to test the RPC directly on 8082.

echo "=== Testing Multi-Chain Support on Live System ==="
echo ""

CHAINS=("ait-devnet" "ait-testnet" "ait-healthchain")

for CHAIN in "${CHAINS[@]}"; do
    echo "=== Testing Chain: $CHAIN ==="
    
    echo "1. Fetching head block from aitbc (Primary Node):"
    ssh aitbc-cascade "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=$CHAIN\" | jq ."
    
    echo "2. Fetching head block from aitbc1 (Secondary Node):"
    ssh aitbc1-cascade "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=$CHAIN\" | jq ."
    
    echo "3. Submitting a test transaction to $CHAIN on aitbc..."
    ssh aitbc-cascade "curl -s -X POST \"http://127.0.0.1:8082/rpc/sendTx?chain_id=$CHAIN\" -H \"Content-Type: application/json\" -d '{\"sender\":\"test_user\",\"recipient\":\"test_recipient\",\"payload\":{\"data\":\"multi-chain test\"},\"nonce\":1,\"fee\":0,\"type\":\"TRANSFER\"}'" | jq .
    
    echo "Waiting for blocks to process..."
    sleep 3
    
    echo "4. Checking updated head block on aitbc1 (Cross-Site Sync Test)..."
    ssh aitbc1-cascade "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=$CHAIN\" | jq ."
    echo "--------------------------------------------------------"
    echo ""
done

echo "✅ Multi-chain live testing complete."
