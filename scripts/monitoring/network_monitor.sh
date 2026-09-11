#!/bin/bash
# Network monitoring script

# Fleet node addresses.
#
# These were hardcoded to one island's private subnet, which made the script
# useless anywhere else and put internal addressing in a public repository.
# Set them for your own deployment; there is deliberately no default.
NODE0_HOST="${AITBC_NODE0_HOST:?set AITBC_NODE0_HOST to the address of node0}"

echo "=== Network Monitor ==="
echo "Time: $(date)"
echo "aitbc1 height: $(curl -s http://localhost:8006/rpc/head | jq .height)"
echo "aitbc height: $(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0"')"
echo "Redis status: $(redis-cli ping)"
echo "Network latency: $(ping -c 1 ${NODE0_HOST} | grep "time=" | cut -d= -f2)"
echo "Memory usage: $(free -h | grep Mem)"
echo "CPU usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d% -f1)%"
echo "================================"
