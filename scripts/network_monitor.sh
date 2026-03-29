#!/bin/bash
# Network monitoring script
echo "=== Network Monitor ==="
echo "Time: $(date)"
echo "aitbc1 height: $(curl -s http://localhost:8006/rpc/head | jq .height)"
echo "aitbc height: $(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0"')"
echo "Redis status: $(redis-cli ping)"
echo "Network latency: $(ping -c 1 10.1.223.93 | grep "time=" | cut -d= -f2)"
echo "Memory usage: $(free -h | grep Mem)"
echo "CPU usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d% -f1)%"
echo "================================"
