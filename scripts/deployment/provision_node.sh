#!/bin/bash
# Provision new AITBC node


# Fleet node addresses.
#
# These used to be ssh aliases from one operator's ~/.ssh/config, which meant
# the script only ran on that workstation and named the fleet in a public
# repository. Set them for your own deployment; there is deliberately no
# default.
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

NODE_NAME=$1
if [ -z "$NODE_NAME" ]; then
    echo "Usage: $0 <node-name>"
    exit 1
fi

echo "Provisioning node: $NODE_NAME"

# Install dependencies
apt update && apt install -y python3 python3-venv redis-server postgresql postgresql-contrib

# Setup directories
mkdir -p /var/lib/aitbc/{data,keystore}
mkdir -p /etc/aitbc
mkdir -p /var/log/aitbc

# Copy configuration
scp ${NODE1_HOST}:/etc/aitbc/blockchain.env /etc/aitbc/
scp ${NODE1_HOST}:/opt/aitbc/aitbc-cli-final /opt/aitbc/

# Pull code
cd /opt/aitbc
git pull origin main

# Install psycopg for PostgreSQL
/opt/aitbc/venv/bin/pip install psycopg

# Setup PostgreSQL databases
/opt/aitbc/infra/scripts/setup_postgresql_databases.sh

# Setup as follower
sed -i 's|enable_block_production=true|enable_block_production=false|g' /etc/aitbc/blockchain.env
sed -i 's|proposer_id=.*|proposer_id=follower-node-'$NODE_NAME'|g' /etc/aitbc/blockchain.env

echo "Node $NODE_NAME provisioned successfully"
