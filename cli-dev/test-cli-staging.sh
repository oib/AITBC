#!/bin/bash

# CLI Staging Test Script
echo "=== CLI Staging Test ==="
echo "Date: $(date)"
echo ""

# Start mock server in background
echo "Starting CLI Mock Server..."
python3 /home/oib/windsurf/aitbc/cli-dev/mock-cli-server.py &
MOCK_PID=$!
sleep 3

# Test CLI with staging configuration
echo "1. Testing CLI with Mock Server:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-staging-config.yaml test api
echo ""

echo "2. Testing CLI Marketplace with Mock:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-staging-config.yaml marketplace gpu list
echo ""

echo "3. Testing CLI Agents with Mock:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-staging-config.yaml agent list
echo ""

echo "4. Testing CLI Blockchain with Mock:"
aitbc --config-file /home/oib/windsurf/aitbc/cli-dev/cli-staging-config.yaml blockchain status
echo ""

# Clean up
echo "Stopping Mock Server..."
kill $MOCK_PID 2>/dev/null
wait $MOCK_PID 2>/dev/null

echo "=== CLI Staging Test Complete ==="
