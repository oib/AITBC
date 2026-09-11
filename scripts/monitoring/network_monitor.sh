#!/bin/bash
# Network monitoring script

# Fleet node addresses.
#
# These were hardcoded to one island's private subnet, which made the script
# useless anywhere else and put internal addressing in a public repository.
# Set them for your own deployment; there is deliberately no default.
NODE0_HOST="${AITBC_NODE0_HOST:?set AITBC_NODE0_HOST to the address of node0}"
LOCAL_CONTAINER="${AITBC_CONTAINER_NAME:-aitbc}"
REMOTE_CONTAINER="${AITBC_NODE1_CONTAINER_NAME:-aitbc1}"

echo "=== Network Monitor ==="
echo "Time: $(date)"
echo "${REMOTE_CONTAINER} height: $(curl -s http://localhost:8202/rpc/head | jq .height)"
echo "${LOCAL_CONTAINER} height: $(ssh ${LOCAL_CONTAINER} 'curl -s http://localhost:8202/rpc/head | jq .height 2>/dev/null || echo "0"')"
echo "Redis status: $(redis-cli ping)"
echo "Network latency: $(ping -c 1 ${NODE0_HOST} | grep "time=" | cut -d= -f2)"
echo "Memory usage: $(free -h | grep Mem)"
echo "CPU usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d% -f1)%"
echo "================================"
