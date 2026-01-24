#!/bin/bash
# Start SSH tunnel to remote AITBC coordinator

echo "Starting SSH tunnel to remote AITBC coordinator..."

# Check if tunnel is already running
if pgrep -f "ssh.*-L.*8001:localhost:8000.*aitbc" > /dev/null; then
    echo "✅ Tunnel is already running"
    exit 0
fi

# Start the tunnel
ssh -f -N -L 8001:localhost:8000 aitbc

if [ $? -eq 0 ]; then
    echo "✅ SSH tunnel established on port 8001"
    echo "   Remote coordinator available at: http://localhost:8001"
    echo "   Health check: curl http://localhost:8001/v1/health"
else
    echo "❌ Failed to establish SSH tunnel"
    exit 1
fi
