#!/bin/bash
# Weekly maintenance tasks

echo "=== Weekly Maintenance ==="

# Clean old logs
find /var/log/aitbc -name "*.log" -mtime +7 -delete

# Update software
cd /opt/aitbc && git pull origin main
/opt/aitbc/venv/bin/pip install -r requirements.txt

# Restart services if needed
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc

# Run health check
/opt/aitbc/scripts/health_check.sh

echo "=== Weekly Maintenance Complete ==="
