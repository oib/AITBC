#!/bin/bash

# Define the proxy ports and internal container ports
# Coordinator proxies: localhost:8000 -> aitbc:8000, localhost:8015 -> ${NODE1_HOST}:8015
# However, the node RPC is on port 8082 in the container and proxied differently.
# For direct access, we'll ssh into the containers to test the RPC directly on 8082.


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

echo "=== Testing Multi-Chain Support on Live System ==="
echo ""

CHAINS=("ait-devnet" "ait-testnet" "ait-healthchain")

for CHAIN in "${CHAINS[@]}"; do
    echo "=== Testing Chain: $CHAIN ==="

    echo "1. Fetching head block from aitbc (Primary Node):"
    ssh "${CONTAINER_SSH:?set CONTAINER_SSH to the ssh target for the aitbc container}" "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=$CHAIN\" | jq ."

    echo "2. Fetching head block from ${NODE1_HOST} (Secondary Node):"
    ssh ${NODE1_CONTAINER_SSH} "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=$CHAIN\" | jq ."

    echo "3. Submitting a test transaction to $CHAIN on aitbc..."
    ssh "${CONTAINER_SSH:?set CONTAINER_SSH to the ssh target for the aitbc container}" "curl -s -X POST \"http://127.0.0.1:8082/rpc/sendTx?chain_id=$CHAIN\" -H \"Content-Type: application/json\" -d '{\"sender\":\"test_user\",\"recipient\":\"test_recipient\",\"payload\":{\"data\":\"multi-chain test\"},\"nonce\":1,\"fee\":0,\"type\":\"TRANSFER\"}'" | jq .

    echo "Waiting for blocks to process..."
    sleep 3

    echo "4. Checking updated head block on ${NODE1_HOST} (Cross-Site Sync Test)..."
    ssh ${NODE1_CONTAINER_SSH} "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=$CHAIN\" | jq ."
    echo "--------------------------------------------------------"
    echo ""
done

echo "✅ Multi-chain live testing complete."
