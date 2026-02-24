#!/bin/bash

# Blockchain Synchronization Optimization Script
# Fixes common sync issues and optimizes cross-site synchronization

set -e

echo "🔧 Blockchain Synchronization Optimization"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if service is running
check_service() {
    local service=$1
    local host=$2
    
    if [ -z "$host" ]; then
        if systemctl is-active --quiet "$service"; then
            return 0
        else
            return 1
        fi
    else
        if ssh "$host" "systemctl is-active --quiet '$service'"; then
            return 0
        else
            return 1
        fi
    fi
}

# Function to restart service
restart_service() {
    local service=$1
    local host=$2
    
    if [ -z "$host" ]; then
        sudo systemctl restart "$service"
    else
        ssh "$host" "sudo systemctl restart '$service'"
    fi
}

# Function to get blockchain height
get_height() {
    local url=$1
    local host=$2
    
    if [ -z "$host" ]; then
        curl -s "$url/head" 2>/dev/null | grep -o '"height":[^,]*' | cut -d'"' -f2
    else
        ssh "$host" "curl -s '$url/head' 2>/dev/null | grep -o '\"height\":[^,]*' | cut -d'\"' -f2"
    fi
}

echo ""
echo "📊 Current Sync Status Analysis"
echo "=============================="

# Get current heights
echo "Checking current blockchain heights..."
NODE1_HEIGHT=$(get_height "http://localhost:8082/rpc" "aitbc-cascade")
NODE2_HEIGHT=$(get_height "http://localhost:8081/rpc" "aitbc-cascade")
NODE3_HEIGHT=$(get_height "http://192.168.100.10:8082/rpc" "ns3-root")

echo "Node 1 (aitbc-cascade): $NODE1_HEIGHT"
echo "Node 2 (aitbc-cascade): $NODE2_HEIGHT"
echo "Node 3 (ns3): $NODE3_HEIGHT"

# Calculate height differences
if [ -n "$NODE1_HEIGHT" ] && [ -n "$NODE2_HEIGHT" ]; then
    DIFF12=$((NODE2_HEIGHT - NODE1_HEIGHT))
    echo "Height difference (Node2 - Node1): $DIFF12"
fi

if [ -n "$NODE2_HEIGHT" ] && [ -n "$NODE3_HEIGHT" ]; then
    DIFF23=$((NODE2_HEIGHT - NODE3_HEIGHT))
    echo "Height difference (Node2 - Node3): $DIFF23"
fi

echo ""
echo "🔧 Step 1: Fix Node 1 Endpoint Configuration"
echo "============================================="

# Check Node 1 config for wrong endpoint
echo "Checking Node 1 configuration..."
NODE1_CONFIG=$(ssh aitbc-cascade "grep -n 'aitbc.bubuit.net/rpc2' /opt/blockchain-node/src/aitbc_chain/config.py 2>/dev/null || true")

if [ -n "$NODE1_CONFIG" ]; then
    print_warning "Found wrong endpoint /rpc2 in Node 1 config"
    echo "Fixing endpoint configuration..."
    
    # Backup original config
    ssh aitbc-cascade "sudo cp /opt/blockchain-node/src/aitbc_chain/config.py /opt/blockchain-node/src/aitbc_chain/config.py.backup"
    
    # Fix the endpoint
    ssh aitbc-cascade "sudo sed -i 's|https://aitbc.bubuit.net/rpc2|https://aitbc.bubuit.net/rpc|g' /opt/blockchain-node/src/aitbc_chain/config.py"
    
    print_status "Fixed Node 1 endpoint configuration"
    
    # Restart Node 1
    echo "Restarting Node 1 service..."
    restart_service "aitbc-blockchain-node-1.service" "aitbc-cascade"
    sleep 5
    
    if check_service "aitbc-blockchain-node-1.service" "aitbc-cascade"; then
        print_status "Node 1 service restarted successfully"
    else
        print_error "Node 1 service failed to restart"
    fi
else
    print_status "Node 1 endpoint configuration is correct"
fi

echo ""
echo "🔧 Step 2: Fix Node 3 Services"
echo "=============================="

# Check Node 3 service status
echo "Checking Node 3 services..."
NODE3_STATUS=$(ssh ns3-root "systemctl is-active blockchain-node-3.service 2>/dev/null || echo 'failed'")

if [ "$NODE3_STATUS" = "failed" ] || [ "$NODE3_STATUS" = "activating" ]; then
    print_warning "Node 3 service is in $NODE3_STATUS state"
    
    echo "Checking Node 3 service logs..."
    ssh ns3-root "journalctl -u blockchain-node-3.service --no-pager -n 10"
    
    echo "Attempting to fix Node 3 service..."
    
    # Stop and restart Node 3
    ssh ns3-root "sudo systemctl stop blockchain-node-3.service || true"
    sleep 2
    ssh ns3-root "sudo systemctl start blockchain-node-3.service"
    sleep 5
    
    # Check status again
    NODE3_NEW_STATUS=$(ssh ns3-root "systemctl is-active blockchain-node-3.service 2>/dev/null || echo 'failed'")
    
    if [ "$NODE3_NEW_STATUS" = "active" ]; then
        print_status "Node 3 service fixed and running"
    else
        print_error "Node 3 service still not working: $NODE3_NEW_STATUS"
        echo "Manual intervention required for Node 3"
    fi
else
    print_status "Node 3 service is running"
fi

echo ""
echo "🔧 Step 3: Optimize Sync Configuration"
echo "======================================"

# Function to optimize sync config
optimize_sync_config() {
    local host=$1
    local config_path=$2
    
    echo "Optimizing sync configuration on $host..."
    
    # Backup config
    ssh "$host" "sudo cp '$config_path' '$config_path.backup' 2>/dev/null || true"
    
    # Add/modify sync settings
    ssh "$host" "sudo tee -a '$config_path' > /dev/null << 'EOF'

# Sync optimization settings
sync_interval_seconds: int = 5  # Reduced from 10s
sync_retry_attempts: int = 3
sync_retry_delay_seconds: int = 2
sync_timeout_seconds: int = 10
max_sync_height_diff: int = 1000  # Alert if difference exceeds this
EOF"
    
    print_status "Sync configuration optimized on $host"
}

# Optimize sync configs
optimize_sync_config "aitbc-cascade" "/opt/blockchain-node/src/aitbc_chain/config.py"
optimize_sync_config "aitbc-cascade" "/opt/blockchain-node-2/src/aitbc_chain/config.py"
optimize_sync_config "ns3-root" "/opt/blockchain-node/src/aitbc_chain/config.py"

echo ""
echo "🔧 Step 4: Restart Services with New Config"
echo "=========================================="

# Restart all services
echo "Restarting blockchain services..."

for service in "aitbc-blockchain-node-1.service" "aitbc-blockchain-node-2.service"; do
    echo "Restarting $service on aitbc-cascade..."
    restart_service "$service" "aitbc-cascade"
    sleep 3
done

for service in "blockchain-node-3.service"; do
    echo "Restarting $service on ns3..."
    restart_service "$service" "ns3-root"
    sleep 3
done

echo ""
echo "📊 Step 5: Verify Sync Optimization"
echo "==================================="

# Wait for services to stabilize
echo "Waiting for services to stabilize..."
sleep 10

# Check new heights
echo "Checking new blockchain heights..."
NEW_NODE1_HEIGHT=$(get_height "http://localhost:8082/rpc" "aitbc-cascade")
NEW_NODE2_HEIGHT=$(get_height "http://localhost:8081/rpc" "aitbc-cascade")
NEW_NODE3_HEIGHT=$(get_height "http://192.168.100.10:8082/rpc" "ns3-root")

echo "New heights:"
echo "Node 1: $NEW_NODE1_HEIGHT"
echo "Node 2: $NEW_NODE2_HEIGHT"
echo "Node 3: $NEW_NODE3_HEIGHT"

# Calculate improvements
if [ -n "$NEW_NODE1_HEIGHT" ] && [ -n "$NEW_NODE2_HEIGHT" ] && [ -n "$NODE1_HEIGHT" ] && [ -n "$NODE2_HEIGHT" ]; then
    OLD_DIFF=$((NODE2_HEIGHT - NODE1_HEIGHT))
    NEW_DIFF=$((NEW_NODE2_HEIGHT - NEW_NODE1_HEIGHT))
    
    echo "Height difference improvement:"
    echo "Before: $OLD_DIFF"
    echo "After:  $NEW_DIFF"
    
    if [ $NEW_DIFF -lt $OLD_DIFF ]; then
        IMPROVEMENT=$((OLD_DIFF - NEW_DIFF))
        print_status "Sync improved by $IMPROVEMENT blocks"
    else
        print_warning "Sync did not improve or got worse"
    fi
fi

echo ""
echo "🔧 Step 6: Create Sync Monitoring Script"
echo "========================================="

# Create monitoring script
cat > /tmp/sync_monitor.sh << 'EOF'
#!/bin/bash

# Blockchain Sync Monitor
# Run this periodically to check sync health

echo "🔍 Blockchain Sync Monitor - $(date)"
echo "===================================="

# Get heights
NODE1=$(curl -s http://localhost:8082/rpc/head 2>/dev/null | grep -o '"height":[^,]*' | cut -d'"' -f2)
NODE2=$(curl -s http://localhost:8081/rpc/head 2>/dev/null | grep -o '"height":[^,]*' | cut -d'"' -f2)
NODE3=$(ssh ns3-root "curl -s http://192.168.100.10:8082/rpc/head 2>/dev/null | grep -o '\"height\":[^,]*' | cut -d'\"' -f2")

echo "Node 1: $NODE1"
echo "Node 2: $NODE2"
echo "Node 3: $NODE3"

# Check for issues
if [ -n "$NODE1" ] && [ -n "$NODE2" ]; then
    DIFF=$((NODE2 - NODE1))
    if [ $DIFF -gt 100 ]; then
        echo "⚠️  WARNING: Node 1 and Node 2 height difference: $DIFF"
    fi
fi

if [ -n "$NODE2" ] && [ -n "$NODE3" ]; then
    DIFF=$((NODE2 - NODE3))
    if [ $DIFF -gt 1000 ]; then
        echo "⚠️  WARNING: Node 2 and Node 3 height difference: $DIFF"
    fi
fi

echo "Sync check completed."
EOF

chmod +x /tmp/sync_monitor.sh
print_status "Created sync monitoring script: /tmp/sync_monitor.sh"

echo ""
echo "🎉 Sync Optimization Complete!"
echo "=============================="

echo ""
echo "📋 Summary of actions taken:"
echo "• Fixed Node 1 endpoint configuration"
echo "• Restarted problematic services"
echo "• Optimized sync intervals and retry logic"
echo "• Created monitoring script"
echo ""
echo "📊 Next steps:"
echo "1. Monitor sync performance with: /tmp/sync_monitor.sh"
echo "2. Set up cron job for periodic monitoring"
echo "3. Check logs for any remaining issues"
echo "4. Consider implementing P2P sync for better performance"
echo ""
echo "🔧 If issues persist:"
echo "• Check individual service logs: journalctl -u [service-name]"
echo "• Verify network connectivity between sites"
echo "• Consider manual block import for severely lagging nodes"
echo "• Review firewall and security group settings"

print_status "Blockchain synchronization optimization completed!"
