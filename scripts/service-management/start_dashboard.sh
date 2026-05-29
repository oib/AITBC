#!/bin/bash

echo "=== Starting AITBC Miner Dashboard ==="
echo ""

# Find available port
PORT=8080
while [ $PORT -le 8090 ]; do
    if ! netstat -tuln 2>/dev/null | grep -q ":$PORT "; then
        echo "✓ Found available port: $PORT"
        break
    fi
    echo "Port $port is in use, trying next..."
    PORT=$((PORT + 1))
done

if [ $PORT -gt 8090 ]; then
    echo "❌ No available ports found between 8080-8090"
    exit 1
fi

# Start the dashboard
echo "Starting dashboard on port $PORT..."
nohup python3 -m http.server $PORT --bind 0.0.0.0 > dashboard.log 2>&1 &
PID=$!

echo ""
echo "✅ Dashboard is running!"
echo ""
echo "Access URLs:"
echo "  Local:    http://localhost:$PORT"
echo "  Network:  http://$(hostname -I | awk '{print $1}'):$PORT"
echo ""
echo "Dashboard file: miner-dashboard.html"
echo "Process ID: $PID"
echo "Log file: dashboard.log"
echo ""
echo "To stop: kill $PID"
echo "To view logs: tail -f dashboard.log"
