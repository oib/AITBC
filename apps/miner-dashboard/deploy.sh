#!/bin/bash

echo "=== AITBC Miner Dashboard & Service Deployment ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

# Create directories
echo "Creating directories..."
mkdir -p /opt/aitbc-miner-dashboard
mkdir -p /var/log/aitbc-miner

# Copy files
echo "Copying files..."
cp -r /home/oib/windsurf/aitbc/apps/miner-dashboard/* /opt/aitbc-miner-dashboard/

# Set permissions
chown -R root:root /opt/aitbc-miner-dashboard
chmod +x /opt/aitbc-miner-dashboard/*.py
chmod +x /opt/aitbc-miner-dashboard/*.sh

# Create virtual environment
echo "Setting up Python environment..."
cd /opt/aitbc-miner-dashboard
python3 -m venv .venv
.venv/bin/pip install psutil

# Install systemd services
echo "Installing systemd services..."
cp aitbc-miner-dashboard.service /etc/systemd/system/
cp aitbc-miner.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable and start services
echo "Starting services..."
systemctl enable aitbc-miner
systemctl enable aitbc-miner-dashboard
systemctl start aitbc-miner
systemctl start aitbc-miner-dashboard

# Wait for services to start
sleep 5

# Check status
echo ""
echo "=== Service Status ==="
systemctl status aitbc-miner --no-pager -l | head -5
systemctl status aitbc-miner-dashboard --no-pager -l | head -5

# Get IP address
IP=$(hostname -I | awk '{print $1}')

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Services:"
echo "  - Miner Service: Running (background)"
echo "  - Dashboard: http://localhost:8080"
echo ""
echo "Access from other machines:"
echo "  http://$IP:8080"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u aitbc-miner -f"
echo "  sudo journalctl -u aitbc-miner-dashboard -f"
