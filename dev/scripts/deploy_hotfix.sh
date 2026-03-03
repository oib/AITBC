#!/bin/bash
set -e

# Extract the update
cd /home/oib/aitbc
tar -xzf update.tar.gz

# Deploy to blockchain-node
echo "Deploying to blockchain-node..."
sudo cp -r apps/blockchain-node/src/* /opt/blockchain-node/src/
sudo cp -r apps/blockchain-node/migrations/* /opt/blockchain-node/migrations/

# Deploy to coordinator-api
echo "Deploying to coordinator-api..."
sudo cp -r apps/coordinator-api/src/* /opt/coordinator-api/src/

# Stop services
sudo systemctl stop aitbc-blockchain-node-1 aitbc-blockchain-rpc-1 aitbc-coordinator-api || true
sudo systemctl stop aitbc-blockchain-node aitbc-blockchain-rpc || true

# Run DB Migrations
echo "Running DB migrations..."
cd /opt/blockchain-node
# Drop the old database to be safe since it might have schema issues we fixed
sudo rm -f data/chain.db* data/blockchain.db* || true
sudo -u root PYTHONPATH=src:scripts .venv/bin/python -m alembic upgrade head

# Run Genesis
echo "Creating Genesis..."
cd /opt/blockchain-node
sudo -u root PYTHONPATH=src:scripts .venv/bin/python /home/oib/aitbc/dev/scripts/create_genesis_all.py

# Start services
echo "Restarting services..."
sudo systemctl restart aitbc-blockchain-node-1 aitbc-blockchain-rpc-1 aitbc-coordinator-api || true
sudo systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc || true

echo "Done!"
