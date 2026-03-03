#!/bin/bash

echo "🚀 COMPREHENSIVE BASELINE TEST (Pre-Deployment)"
echo "==============================================="

sites=(
    "localhost|http://127.0.0.1:8000|http://127.0.0.1:8082"
    "aitbc (Primary)|http://10.1.223.93:8000|http://10.1.223.93:8082"
    "aitbc1 (Secondary)|http://10.1.223.40:8000|http://10.1.223.40:8082"
)

for site in "${sites[@]}"; do
    IFS='|' read -r name api_url rpc_url <<< "$site"
    echo ""
    echo "🔍 Testing Site: $name"
    echo "-----------------------------------------------"
    
    # 1. API Live Health
    api_live=$(curl -s --connect-timeout 2 "$api_url/health/live" || echo "FAILED")
    if [[ "$api_live" == *"FAILED"* ]] || [[ -z "$api_live" ]]; then
        echo "❌ API Live: DOWN"
    else
        echo "✅ API Live: UP ($api_live)"
    fi

    # 2. Blockchain RPC (Testnet Head)
    rpc_head=$(curl -s --connect-timeout 2 "$rpc_url/rpc/head?chain_id=ait-testnet" || echo "FAILED")
    if [[ "$rpc_head" == *"FAILED"* ]] || [[ -z "$rpc_head" ]]; then
        echo "❌ Blockchain RPC: DOWN"
    else
        height=$(echo $rpc_head | jq -r '.height // "error"')
        echo "✅ Blockchain RPC: UP (Height: $height)"
    fi

    # 3. ZK ML Circuits (Phase 5 check)
    zk_circuits=$(curl -s --connect-timeout 2 "$api_url/ml-zk/circuits" || echo "FAILED")
    if [[ "$zk_circuits" == *"FAILED"* ]] || [[ -z "$zk_circuits" ]] || [[ "$zk_circuits" == *"Not Found"* ]]; then
        echo "⚠️  ZK Circuits: Unavailable or Not Found"
    else
        circuit_count=$(echo "$zk_circuits" | jq '.circuits | length' 2>/dev/null || echo "0")
        echo "✅ ZK Circuits: Available ($circuit_count circuits)"
    fi

    # 4. Marketplace GPU List
    gpu_list=$(curl -s --connect-timeout 2 "$api_url/marketplace/offers" || echo "FAILED")
    if [[ "$gpu_list" == *"FAILED"* ]] || [[ -z "$gpu_list" ]]; then
        echo "⚠️  Marketplace Offers: Unavailable"
    else
        offer_count=$(echo "$gpu_list" | jq 'length' 2>/dev/null || echo "0")
        echo "✅ Marketplace Offers: Available ($offer_count offers)"
    fi
done

echo ""
echo "==============================================="
echo "🏁 BASELINE TEST COMPLETE"
