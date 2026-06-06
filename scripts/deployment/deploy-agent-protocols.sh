#!/bin/bash
# Deploy AITBC Agent Protocols

set -e

echo "🚀 Deploying AITBC Agent Protocols..."

# Install dependencies
pip3 install fastapi uvicorn pydantic cryptography aiohttp sqlite3

# Copy service files
sudo cp /opt/aitbc/deployment/agent-protocols/aitbc-agent-registry.service /etc/systemd/system/
sudo cp /opt/aitbc/deployment/agent-protocols/aitbc-agent-coordinator.service /etc/systemd/system/

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable aitbc-agent-registry
sudo systemctl enable aitbc-agent-coordinator
sudo systemctl start aitbc-agent-registry
sudo systemctl start aitbc-agent-coordinator

# Wait for services to start
sleep 5

# Check service status
echo "Checking service status..."
sudo systemctl status aitbc-agent-registry --no-pager
sudo systemctl status aitbc-agent-coordinator --no-pager

# Test services
echo "Testing services..."
curl -s http://localhost:8003/api/health || echo "Agent Registry not responding"
curl -s http://localhost:8004/api/health || echo "Agent Coordinator not responding"

echo "✅ Agent Protocols deployment complete!"
