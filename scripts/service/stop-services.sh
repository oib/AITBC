#!/bin/bash

# Stop all AITBC services

echo "🛑 Stopping AITBC Services"
echo "========================"

# Stop by PID if file exists
if [ -f .service_pids ]; then
    PIDS=$(cat .service_pids)
    echo "Found PIDs: $PIDS"
    for PID in $PIDS; do
        if kill -0 $PID 2>/dev/null; then
            echo "Stopping PID $PID..."
            kill $PID
        fi
    done
    rm -f .service_pids
fi

# Force kill any remaining services
echo "Cleaning up any remaining processes..."
sudo fuser -k 8000/tcp 2>/dev/null || true
sudo fuser -k 9080/tcp 2>/dev/null || true
sudo fuser -k 3001/tcp 2>/dev/null || true
sudo fuser -k 3002/tcp 2>/dev/null || true
pkill -f "uvicorn.*aitbc" 2>/dev/null || true
pkill -f "server.py" 2>/dev/null || true

echo "✅ All services stopped!"
