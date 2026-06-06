#!/bin/bash
# Performance optimization

echo "=== Performance Tuning ==="

# Optimize Redis
redis-cli CONFIG SET maxmemory 2gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Optimize Python processes
echo 'ulimit -n 65536' >> /etc/security/limits.conf

# Optimize system parameters
echo 'vm.swappiness=10' >> /etc/sysctl.conf
echo 'net.core.somaxconn=65535' >> /etc/sysctl.conf
sysctl -p

echo "=== Performance Tuning Complete ==="
