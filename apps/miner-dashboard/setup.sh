#!/bin/bash

echo "=== AITBC Miner Dashboard Setup ==="
echo ""

# Create directory
sudo mkdir -p /opt/aitbc-miner-dashboard
sudo cp -r /home/oib/windsurf/aitbc/apps/miner-dashboard/* /opt/aitbc-miner-dashboard/

# Create virtual environment
cd /opt/aitbc-miner-dashboard
sudo python3 -m venv .venv
sudo .venv/bin/pip install psutil

# Install systemd service
sudo cp aitbc-miner-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aitbc-miner-dashboard
sudo systemctl start aitbc-miner-dashboard

# Wait for service to start
sleep 3

# Check status
sudo systemctl status aitbc-miner-dashboard --no-pager -l | head -10

echo ""
echo "✅ Miner Dashboard is running at: http://localhost:8080"
echo ""
echo "To access from other machines, use: http://$(hostname -I | awk '{print $1}'):8080"
