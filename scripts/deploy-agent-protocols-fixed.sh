#!/bin/bash
# Deploy AITBC Agent Protocols - Using existing virtual environment

set -e

echo "🚀 Deploying AITBC Agent Protocols..."

# Use existing virtual environment
VENV_PATH="/opt/aitbc/cli/venv"

# Install dependencies in virtual environment
echo "Installing dependencies..."
$VENV_PATH/bin/pip install fastapi uvicorn pydantic cryptography aiohttp

# Copy service files
echo "Setting up systemd services..."
sudo cp /opt/aitbc/deployment/agent-protocols/aitbc-agent-registry.service /etc/systemd/system/
sudo cp /opt/aitbc/deployment/agent-protocols/aitbc-agent-coordinator.service /etc/systemd/system/

# Enable and start services
echo "Starting agent services..."
sudo systemctl daemon-reload
sudo systemctl enable aitbc-agent-registry
sudo systemctl enable aitbc-agent-coordinator
sudo systemctl start aitbc-agent-registry
sudo systemctl start aitbc-agent-coordinator

# Wait for services to start
sleep 5

# Check service status
echo "Checking service status..."
sudo systemctl status aitbc-agent-registry --no-pager | head -5
sudo systemctl status aitbc-agent-coordinator --no-pager | head -5

# Test services
echo "Testing services..."
curl -s http://localhost:8003/api/health || echo "Agent Registry not responding"
curl -s http://localhost:8004/api/health || echo "Agent Coordinator not responding"

echo "✅ Agent Protocols deployment complete!"
