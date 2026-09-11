#!/bin/bash

# Fleet node addresses.
#
# These used to be ssh aliases from one operator's ~/.ssh/config, which meant
# the script only ran on that workstation and named the fleet in a public
# repository. Set them for your own deployment; there is deliberately no
# default.
# ssh target for the blockchain container on node1. This used to be a private
# ~/.ssh/config alias, so the script only worked on one operator's workstation.
NODE1_CONTAINER_SSH="${AITBC_NODE1_CONTAINER_SSH:?set AITBC_NODE1_CONTAINER_SSH to the ssh target for the container on node1}"

NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

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
echo "5. Checking head of ait-testnet on ${NODE1_HOST} (Secondary):"
ssh ${NODE1_CONTAINER_SSH} "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=ait-testnet\" | jq ."

echo ""
echo "6. Checking head of ait-devnet on aitbc (Should be 0 if no txs since genesis fixed):"
ssh aitbc-cascade "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=ait-devnet\" | jq ."
