#!/bin/bash
# AITBC Node Setup Template
# Usage: ./node_setup_template.sh <node-name> <role> <genesis-authority>

NODE_NAME=$1
ROLE=$2
GENESIS_AUTHORITY=$3

echo "Setting up AITBC node: $NODE_NAME"
echo "Role: $ROLE"
echo "Genesis Authority: $GENESIS_AUTHORITY"

# Install dependencies
apt update && apt install -y python3 python3-venv redis-server

# Setup directories
mkdir -p /var/lib/aitbc/{data,keystore,logs}
mkdir -p /etc/aitbc

# Copy configuration from genesis authority
scp $GENESIS_AUTHORITY:/etc/aitbc/blockchain.env /etc/aitbc/

# Pull code
cd /opt/aitbc
git clone http://gitea.bubuit.net:oib/aitbc.git
cd aitbc

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure node role
if [ "$ROLE" = "follower" ]; then
  sed -i 's/enable_block_production=true/enable_block_production=false/g' /etc/aitbc/blockchain.env
  sed -i "s/proposer_id=.*/proposer_id=follower-node-$NODE_NAME/g" /etc/aitbc/blockchain.env
fi

# Setup systemd services
cp systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable aitbc-blockchain-node aitbc-blockchain-rpc

echo "Node $NODE_NAME setup complete!"
