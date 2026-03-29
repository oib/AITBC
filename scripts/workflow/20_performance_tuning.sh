#!/bin/bash

# AITBC Performance Tuning Script - DISABLED
# This script has been disabled to prevent system modifications
# To re-enable, remove this notice and make the script executable

echo "❌ PERFORMANCE TUNING SCRIPT DISABLED"
echo "This script has been disabled to prevent system modifications."
echo "To re-enable:"
echo "  1. Remove this disable notice"
echo "  2. Make the script executable: chmod +x $0"
echo ""
echo "Current status: DISABLED"
exit 1

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "1. 🔧 SYSTEM PERFORMANCE OPTIMIZATION"
echo "===================================="

# Optimize CPU affinity
echo "Setting CPU affinity for blockchain services..."
if [ ! -f "/opt/aitbc/systemd/cpuset.conf" ]; then
    mkdir -p /opt/aitbc/systemd
    echo "CPUAffinity=0-3" > /opt/aitbc/systemd/cpuset.conf
    echo -e "   ${GREEN}✅${NC} CPU affinity configured"
else
    echo -e "   ${YELLOW}⚠️${NC} CPU affinity already configured"
fi

# Optimize memory management
echo "Optimizing memory management..."
# Add swap if needed
if [ $(swapon --show | wc -l) -eq 0 ]; then
    echo "Creating 2GB swap file..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo -e "   ${GREEN}✅${NC} Swap file created"
else
    echo -e "   ${YELLOW}⚠️${NC} Swap already exists"
fi

# Optimize kernel parameters
echo "Optimizing kernel parameters..."
cat >> /etc/sysctl.conf << 'EOF'

# AITBC Performance Tuning
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
EOF
sysctl -p
echo -e "   ${GREEN}✅${NC} Kernel parameters optimized"

echo ""
echo "2. 🔄 BLOCKCHAIN PERFORMANCE TUNING"
echo "===================================="

# Optimize blockchain configuration
echo "Optimizing blockchain configuration..."
if [ -f "/etc/aitbc/blockchain.env" ]; then
    # Backup original config
    cp /etc/aitbc/blockchain.env /etc/aitbc/blockchain.env.backup.$(date +%Y%m%d_%H%M%S)
    
    # Optimize key parameters
    sed -i 's/block_time_seconds=10/block_time_seconds=2/' /etc/aitbc/blockchain.env
    sed -i 's/max_txs_per_block=100/max_txs_per_block=500/' /etc/aitbc/blockchain.env
    sed -i 's/max_block_size_bytes=1048576/max_block_size_bytes=2097152/' /etc/aitbc/blockchain.env
    
    echo -e "   ${GREEN}✅${NC} Blockchain configuration optimized"
    echo "   • Block time: 2 seconds"
    echo "   • Max transactions per block: 500"
    echo "   • Max block size: 2MB"
else
    echo -e "   ${YELLOW}⚠️${NC} Blockchain configuration not found"
fi

# Restart services to apply changes
echo "Restarting blockchain services..."
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
ssh aitbc 'systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc'
echo -e "   ${GREEN}✅${NC} Services restarted"

echo ""
echo "3. 💾 DATABASE OPTIMIZATION"
echo "==========================="

# Optimize SQLite database
echo "Optimizing SQLite database..."
if [ -f "/var/lib/aitbc/data/ait-mainnet/chain.db" ]; then
    sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "VACUUM;"
    sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "ANALYZE;"
    echo -e "   ${GREEN}✅${NC} Database optimized"
else
    echo -e "   ${YELLOW}⚠️${NC} Database not found"
fi

# Optimize mempool database
if [ -f "/var/lib/aitbc/data/mempool.db" ]; then
    sqlite3 /var/lib/aitbc/data/mempool.db "VACUUM;"
    sqlite3 /var/lib/aitbc/data/mempool.db "ANALYZE;"
    echo -e "   ${GREEN}✅${NC} Mempool database optimized"
else
    echo -e "   ${YELLOW}⚠️${NC} Mempool database not found"
fi

echo ""
echo "4. 🌐 NETWORK OPTIMIZATION"
echo "=========================="

# Optimize network settings
echo "Optimizing network settings..."
# Increase network buffer sizes
echo 'net.core.netdev_max_backlog = 5000' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_congestion_control = bbr' >> /etc/sysctl.conf
sysctl -p

# Optimize P2P settings if configured
if [ -f "/etc/aitbc/blockchain.env" ]; then
    sed -i 's/p2p_bind_port=7070/p2p_bind_port=7070/' /etc/aitbc/blockchain.env
    echo 'p2p_max_connections=50' >> /etc/aitbc/blockchain.env
    echo 'p2p_connection_timeout=30' >> /etc/aitbc/blockchain.env
    echo -e "   ${GREEN}✅${NC} P2P settings optimized"
fi

echo ""
echo "5. 📊 PERFORMANCE BASELINE"
echo "========================"

# Create performance baseline
echo "Creating performance baseline..."
mkdir -p /opt/aitbc/performance

# Get current performance metrics
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
MEM_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
BLOCK_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq -r .height 2>/dev/null || echo "0")
RPC_RESPONSE=$(curl -s -w "%{time_total}" -o /dev/null http://localhost:8006/rpc/info)

# Create baseline report
cat > /opt/aitbc/performance/baseline.txt << EOF
AITBC Performance Baseline
Generated: $(date)

System Metrics:
- CPU Usage: ${CPU_USAGE}%
- Memory Usage: ${MEM_USAGE}%
- Disk Usage: ${DISK_USAGE}%

Blockchain Metrics:
- Block Height: ${BLOCK_HEIGHT}
- RPC Response Time: ${RPC_RESPONSE}s

Configuration:
- Block Time: 2 seconds
- Max Txs per Block: 500
- Max Block Size: 2MB
- P2P Max Connections: 50

Optimizations Applied:
- CPU affinity configured
- Swap file created
- Kernel parameters optimized
- Database vacuumed and analyzed
- Network settings optimized
- Blockchain configuration tuned
EOF

echo -e "   ${GREEN}✅${NC} Performance baseline created"

echo ""
echo "6. 🧪 PERFORMANCE TESTING"
echo "======================"

# Test transaction throughput
echo "Testing transaction throughput..."
start_time=$(date +%s)
for i in {1..10}; do
    curl -s http://localhost:8006/rpc/info >/dev/null 2>&1
done
end_time=$(date +%s)
throughput=$((10 / (end_time - start_time)))

echo "RPC throughput: $throughput requests/second"

# Test blockchain sync
echo "Testing blockchain performance..."
current_height=$(curl -s http://localhost:8006/rpc/head | jq -r .height 2>/dev/null || echo "0")
echo "Current blockchain height: $current_height"

# Test memory usage
process_memory=$(ps aux | grep aitbc-blockchain-node | grep -v grep | awk '{sum+=$6} END {print sum/1024}')
echo "Blockchain node memory usage: ${process_memory}MB"

echo ""
echo "=== 🚀 PERFORMANCE TUNING COMPLETE ==="
echo ""
echo "Performance optimizations applied:"
echo "• CPU affinity configured"
echo "• Memory management optimized"
echo "• Kernel parameters tuned"
echo "• Database performance optimized"
echo "• Network settings optimized"
echo "• Blockchain configuration tuned"
echo ""
echo "Performance baseline saved to: /opt/aitbc/performance/baseline.txt"
echo ""
echo -e "${GREEN}✅ Performance tuning completed successfully!${NC}"
