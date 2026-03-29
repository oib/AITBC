#!/bin/bash
# Comprehensive health check for AITBC multi-node setup

echo "=== AITBC Multi-Node Health Check ==="

# Check services
echo "1. Service Status:"
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc
ssh aitbc 'systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc'

# Check blockchain sync
echo "2. Blockchain Sync:"
HEIGHT1=$(curl -s http://localhost:8006/rpc/head | jq .height)
HEIGHT2=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')
echo "aitbc1: $HEIGHT1, aitbc: $HEIGHT2, diff: $((HEIGHT1-HEIGHT2))"

# Check network connectivity
echo "3. Network Connectivity:"
ping -c 1 10.1.223.40 >/dev/null && echo "aitbc reachable" || echo "aitbc unreachable"
redis-cli -h localhost ping >/dev/null && echo "Redis OK" || echo "Redis failed"

# Check disk space
echo "4. Disk Usage:"
df -h /var/lib/aitbc/ | tail -1

# Check memory usage
echo "5. Memory Usage:"
free -h | grep Mem

echo "=== Health Check Complete ==="
