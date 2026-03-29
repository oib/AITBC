#!/bin/bash
# AITBC Network Optimization Script
# Optimizes network configuration and performance

echo "=== AITBC Network Optimization ==="

# Check current network status
echo "1. Current network status:"
echo "   aitbc1 height: $(curl -s http://localhost:8006/rpc/head | jq .height)"
echo "   aitbc height: $(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height 2>/dev/null || echo "0"')"
echo "   Network latency: $(ping -c 1 10.1.223.93 | grep "time=" | cut -d= -f2)"

# Optimize Redis configuration
echo "2. Optimizing Redis configuration..."
redis-cli CONFIG SET maxmemory 2gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
redis-cli CONFIG SET tcp-keepalive 300
redis-cli CONFIG SET timeout 0

# Optimize blockchain node configuration
echo "3. Optimizing blockchain node configuration..."
# Update environment file for better performance
sed -i 's|block_time_seconds=10|block_time_seconds=2|g' /etc/aitbc/blockchain.env
sed -i 's|p2p_bind_port=7070|p2p_bind_port=7070|g' /etc/aitbc/blockchain.env

# Copy optimized config to aitbc
scp /etc/aitbc/blockchain.env aitbc:/etc/aitbc/blockchain.env

# Restart services with new configuration
echo "4. Restarting services with optimized configuration..."
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
ssh aitbc 'systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc'

# Wait for services to start
sleep 5

# Verify optimization
echo "5. Verifying optimization results..."
echo "   aitbc1 RPC response time: $(curl -w "%{time_total}" -s -o /dev/null http://localhost:8006/rpc/head) seconds"
echo "   aitbc RPC response time: $(ssh aitbc 'curl -w "%{time_total}" -s -o /dev/null http://localhost:8006/rpc/head') seconds"

# Check system resources
echo "6. System resource optimization..."
# Optimize file descriptors
echo 'root soft nofile 65536' >> /etc/security/limits.conf
echo 'root hard nofile 65536' >> /etc/security/limits.conf

# Optimize network parameters
echo 'net.core.somaxconn = 65535' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_max_syn_backlog = 65535' >> /etc/sysctl.conf
echo 'vm.swappiness = 10' >> /etc/sysctl.conf

# Apply sysctl changes
sysctl -p

# Setup monitoring
echo "7. Setting up network monitoring..."
cat > /opt/aitbc/scripts/network_monitor.sh << 'EOF'
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
EOF

chmod +x /opt/aitbc/scripts/network_monitor.sh

# Add to cron for continuous monitoring
(crontab -l 2>/dev/null; echo "*/2 * * * * /opt/aitbc/scripts/network_monitor.sh >> /var/log/aitbc/network_monitor.log") | crontab -

echo "✅ Network optimization completed!"
echo "Monitoring script: /opt/aitbc/scripts/network_monitor.sh"
echo "Log file: /var/log/aitbc/network_monitor.log"

echo "=== Network Optimization Complete ==="
