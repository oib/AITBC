#!/bin/bash
echo "=== Multi-Chain Capability Test ==="
echo ""
echo "1. Verify Health (Supported Chains):"
curl -s "http://127.0.0.1:8000/v1/health" | jq '{status: .status, supported_chains: .supported_chains}'

echo ""
echo "2. Submitting test transaction to ait-testnet:"
curl -s -X POST "http://127.0.0.1:8082/rpc/sendTx?chain_id=ait-testnet" -H "Content-Type: application/json" -d '{"sender":"test_mc","recipient":"test_mc2","payload":{"test":true},"nonce":1,"fee":0,"type":"TRANSFER"}' | jq .

echo ""
echo "3. Waiting 3 seconds for block production..."
sleep 3

echo ""
echo "4. Checking head of ait-testnet on aitbc (Primary):"
ssh aitbc-cascade "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=ait-testnet\" | jq ."

echo ""
echo "5. Checking head of ait-testnet on aitbc1 (Secondary):"
ssh aitbc1-cascade "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=ait-testnet\" | jq ."

echo ""
echo "6. Checking head of ait-devnet on aitbc (Should be 0 if no txs since genesis fixed):"
ssh aitbc-cascade "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=ait-devnet\" | jq ."

