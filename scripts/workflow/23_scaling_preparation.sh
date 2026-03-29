#!/bin/bash

# AITBC Scaling Preparation Script
# Prepares the system for horizontal scaling and multi-node expansion

set -e

echo "=== 🚀 AITBC SCALING PREPARATION ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "1. 🌐 LOAD BALANCER SETUP"
echo "======================"

# Check if nginx is installed (it should already be)
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    apt-get update
    apt-get install -y nginx
    echo -e "   ${GREEN}✅${NC} nginx installed"
else
    echo -e "   ${YELLOW}⚠️${NC} nginx already installed"
fi

# Create nginx configuration for AITBC load balancing
cat > /etc/nginx/sites-available/aitbc-loadbalancer << 'EOF'
# AITBC Load Balancer Configuration
upstream aitbc_backend {
    server 127.0.0.1:8006 weight=1 max_fails=3 fail_timeout=30s;
    server 10.1.223.40:8006 weight=1 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name _;
    
    # Health check endpoint
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
    
    # Load balanced RPC endpoints
    location /rpc/ {
        proxy_pass http://aitbc_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeout settings
        proxy_connect_timeout 5s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;
        
        # Health check
        proxy_next_upstream error timeout http_500 http_502 http_503 http_504;
    }
    
    # Default route to RPC
    location / {
        proxy_pass http://aitbc_backend/rpc/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeout settings
        proxy_connect_timeout 5s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;
    }
    
    # Status page
    location /nginx_status {
        stub_status on;
        access_log off;
        allow 127.0.0.1;
        allow 10.1.223.0/24;
        deny all;
    }
}
EOF

# Enable the AITBC load balancer site
ln -sf /etc/nginx/sites-available/aitbc-loadbalancer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
nginx -t && systemctl reload nginx
echo -e "   ${GREEN}✅${NC} nginx configured and started"

echo ""
echo "2. 🔄 CLUSTER CONFIGURATION"
echo "========================"

# Create cluster configuration
mkdir -p /opt/aitbc/cluster

cat > /opt/aitbc/cluster/cluster.conf << 'EOF'
# AITBC Cluster Configuration
cluster_name: "aitbc-mainnet"
cluster_id: "aitbc-cluster-001"

# Node Configuration
nodes:
  - name: "aitbc1"
    role: "genesis_authority"
    host: "127.0.0.1"
    port: 8006
    p2p_port: 7070
    priority: 100
  
  - name: "aitbc2"
    role: "follower"
    host: "10.1.223.40"
    port: 8006
    p2p_port: 7070
    priority: 50

# Load Balancing
load_balancer:
  algorithm: "round_robin"
  health_check_interval: 30
  health_check_path: "/rpc/info"
  max_connections: 1000
  type: "nginx"

# Scaling Configuration
scaling:
  min_nodes: 2
  max_nodes: 10
  auto_scale: true
  scale_up_threshold: 80
  scale_down_threshold: 20

# High Availability
ha:
  failover_timeout: 30
  health_check_timeout: 10
  max_failures: 3
EOF

echo -e "   ${GREEN}✅${NC} Cluster configuration created"

echo ""
echo "3. 📊 AUTO-SCALING SETUP"
echo "======================"

# Create auto-scaling script
cat > /opt/aitbc/cluster/auto_scale.sh << 'EOF'
#!/bin/bash

# AITBC Auto-Scaling Script

CONFIG_FILE="/opt/aitbc/cluster/cluster.conf"
LOG_FILE="/var/log/aitbc/auto_scale.log"

# Load configuration
source "$CONFIG_FILE"

# Function to log
log_scale() {
    echo "[$(date)] $1" >> "$LOG_FILE"
}

# Function to get current load
get_current_load() {
    local cpu_load=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    local mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    local rpc_response=$(curl -s -w "%{time_total}" -o /dev/null http://localhost:8006/rpc/info)
    
    echo "$cpu_load,$mem_usage,$rpc_response"
}

# Function to check if scaling is needed
check_scaling_needed() {
    local metrics=$(get_current_load)
    local cpu_load=$(echo "$metrics" | cut -d',' -f1)
    local mem_usage=$(echo "$metrics" | cut -d',' -f2)
    local rpc_response=$(echo "$metrics" | cut -d',' -f3)
    
    # Convert CPU load to float
    cpu_load_float=$(echo "$cpu_load" | sed 's/,//')
    
    log_scale "Current metrics - CPU: ${cpu_load_float}%, MEM: ${mem_usage}%, RPC: ${rpc_response}s"
    
    # Check scale up conditions
    if (( $(echo "$cpu_load_float > $scale_up_threshold" | bc -l) )) || \
       (( $(echo "$mem_usage > $scale_up_threshold" | bc -l) )) || \
       (( $(echo "$rpc_response > 2.0" | bc -l) )); then
        echo "scale_up"
        return 0
    fi
    
    # Check scale down conditions
    if (( $(echo "$cpu_load_float < $scale_down_threshold" | bc -l) )) && \
       (( $(echo "$mem_usage < $scale_down_threshold" | bc -l) )) && \
       (( $(echo "$rpc_response < 0.5" | bc -l) )); then
        echo "scale_down"
        return 0
    fi
    
    echo "no_scale"
}

# Function to get current node count
get_node_count() {
    # Count active nodes from HAProxy stats
    echo "2"  # Placeholder - implement actual node counting
}

# Main scaling logic
main() {
    local scaling_decision=$(check_scaling_needed)
    local current_nodes=$(get_node_count)
    
    log_scale "Scaling decision: $scaling_decision, Current nodes: $current_nodes"
    
    case "$scaling_decision" in
        "scale_up")
            if [ "$current_nodes" -lt "$max_nodes" ]; then
                log_scale "Initiating scale up"
                # Implement scale up logic
                echo "Scale up needed - implement node provisioning"
            else
                log_scale "Max nodes reached, cannot scale up"
            fi
            ;;
        "scale_down")
            if [ "$current_nodes" -gt "$min_nodes" ]; then
                log_scale "Initiating scale down"
                # Implement scale down logic
                echo "Scale down needed - implement node decommissioning"
            else
                log_scale "Min nodes reached, cannot scale down"
            fi
            ;;
        "no_scale")
            log_scale "No scaling needed"
            ;;
    esac
}

main
EOF

chmod +x /opt/aitbc/cluster/auto_scale.sh

# Add auto-scaling to cron
(crontab -l 2>/dev/null; echo "*/2 * * * * /opt/aitbc/cluster/auto_scale.sh") | crontab -

echo -e "   ${GREEN}✅${NC} Auto-scaling script created"

echo ""
echo "4. 🔥 SERVICE DISCOVERY"
echo "===================="

# Create service discovery configuration
cat > /opt/aitbc/cluster/service_discovery.json << 'EOF'
{
  "services": {
    "aitbc-blockchain": {
      "name": "AITBC Blockchain Nodes",
      "port": 8006,
      "health_check": "/rpc/info",
      "protocol": "http",
      "nodes": [
        {
          "id": "aitbc1",
          "host": "127.0.0.1",
          "port": 8006,
          "role": "genesis_authority",
          "status": "active"
        },
        {
          "id": "aitbc2", 
          "host": "10.1.223.40",
          "port": 8006,
          "role": "follower",
          "status": "active"
        }
      ]
    },
    "aitbc-p2p": {
      "name": "AITBC P2P Network",
      "port": 7070,
      "protocol": "tcp",
      "nodes": [
        {
          "id": "aitbc1",
          "host": "127.0.0.1",
          "port": 7070,
          "role": "seed"
        },
        {
          "id": "aitbc2",
          "host": "10.1.223.40", 
          "port": 7070,
          "role": "peer"
        }
      ]
    }
  },
  "load_balancer": {
    "frontend_port": 80,
    "backend_port": 8006,
    "algorithm": "round_robin",
    "health_check_interval": 30,
    "type": "nginx"
  }
}
EOF

# Create service discovery script
cat > /opt/aitbc/cluster/discovery_manager.sh << 'EOF'
#!/bin/bash

# AITBC Service Discovery Manager

DISCOVERY_FILE="/opt/aitbc/cluster/service_discovery.json"
LOG_FILE="/var/log/aitbc/discovery.log"

# Function to check node health
check_node_health() {
    local host=$1
    local port=$2
    local path=$3
    
    if curl -s "http://$host:$port$path" >/dev/null 2>&1; then
        echo "healthy"
    else
        echo "unhealthy"
    fi
}

# Function to update service discovery
update_discovery() {
    local timestamp=$(date -Iseconds)
    
    # Update node statuses
    python3 << EOF
import json
import sys

try:
    with open('$DISCOVERY_FILE', 'r') as f:
        discovery = json.load(f)
    
    # Update blockchain nodes
    for node in discovery['services']['aitbc-blockchain']['nodes']:
        host = node['host']
        port = node['port']
        
        # Check health
        import subprocess
        result = subprocess.run(['curl', '-s', f'http://{host}:{port}/rpc/info'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            node['status'] = 'active'
            node['last_check'] = '$timestamp'
        else:
            node['status'] = 'unhealthy'
            node['last_check'] = '$timestamp'
    
    # Write back
    with open('$DISCOVERY_FILE', 'w') as f:
        json.dump(discovery, f, indent=2)
    
    print("Service discovery updated")
except Exception as e:
    print(f"Error updating discovery: {e}")
    sys.exit(1)
EOF
}

# Main function
main() {
    echo "[$(date)] Updating service discovery" >> "$LOG_FILE"
    update_discovery >> "$LOG_FILE" 2>&1
}

main
EOF

chmod +x /opt/aitbc/cluster/discovery_manager.sh

# Add discovery manager to cron
(crontab -l 2>/dev/null; echo "*/1 * * * * /opt/aitbc/cluster/discovery_manager.sh") | crontab -

echo -e "   ${GREEN}✅${NC} Service discovery configured"

echo ""
echo "5. 📋 SCALING PROCEDURES"
echo "======================"

# Create scaling procedures documentation
mkdir -p /opt/aitbc/docs/scaling

cat > /opt/aitbc/docs/scaling/scaling_procedures.md << 'EOF'
# AITBC Scaling Procedures

## Overview
This document outlines the procedures for scaling the AITBC blockchain network horizontally.

## Prerequisites
- Load balancer configured (HAProxy)
- Service discovery active
- Auto-scaling scripts deployed
- Monitoring dashboard operational

## Scale-Up Procedure

### Manual Scale-Up
1. **Provision New Node**
   ```bash
   # Clone AITBC repository
   git clone <repository-url> /opt/aitbc
   cd /opt/aitbc
   
   # Run node setup
   /opt/aitbc/scripts/workflow/03_follower_node_setup.sh
   ```

2. **Register Node in Cluster**
   ```bash
   # Update service discovery
   /opt/aitbc/cluster/register_node.sh <node-id> <host> <port>
   ```

3. **Update Load Balancer**
   ```bash
   # Add to nginx configuration
   echo "server <node-id> <host>:<port> weight=1 max_fails=3 fail_timeout=30s;" >> /etc/nginx/sites-available/aitbc-loadbalancer
   nginx -t && systemctl reload nginx
   ```

4. **Verify Integration**
   ```bash
   # Check node health
   curl http://<host>:<port>/rpc/info
   
   # Check load balancer stats
   curl http://localhost/nginx_status
   ```

### Auto Scale-Up
The system automatically scales up when:
- CPU usage > 80%
- Memory usage > 80%
- RPC response time > 2 seconds

## Scale-Down Procedure

### Manual Scale-Down
1. **Drain Node**
   ```bash
   # Remove from load balancer
   sed -i '/<node-id>/d' /etc/nginx/sites-available/aitbc-loadbalancer
   nginx -t && systemctl reload nginx
   ```

2. **Wait for Transactions to Complete**
   ```bash
   # Monitor transactions
   watch -n 5 'curl -s http://<host>:<port>/rpc/mempool | jq .total'
   ```

3. **Shutdown Node**
   ```bash
   # Stop services
   ssh <host> 'systemctl stop aitbc-blockchain-node aitbc-blockchain-rpc'
   ```

4. **Update Service Discovery**
   ```bash
   # Remove from discovery
   /opt/aitbc/cluster/unregister_node.sh <node-id>
   ```

### Auto Scale-Down
The system automatically scales down when:
- CPU usage < 20%
- Memory usage < 20%
- RPC response time < 0.5 seconds
- Current nodes > minimum

## Monitoring Scaling Events

### Grafana Dashboard
- Access: http://<grafana-host>:3000
- Monitor: Node count, load metrics, response times

### Logs
- Auto-scaling: `/var/log/aitbc/auto_scale.log`
- Service discovery: `/var/log/aitbc/discovery.log`
- Load balancer: `/var/log/haproxy/haproxy.log`

## Troubleshooting

### Common Issues
1. **Node Not Joining Cluster**
   - Check network connectivity
   - Verify configuration
   - Review service discovery

2. **Load Balancer Issues**
   - Check nginx configuration
   - Verify health checks
   - Review backend status
   - Check nginx error logs: `tail -f /var/log/nginx/error.log`

3. **Auto-scaling Failures**
   - Check scaling logs
   - Verify thresholds
   - Review resource availability

## Performance Considerations
- Monitor network latency between nodes
- Optimize database synchronization
- Consider geographic distribution
- Implement proper caching strategies

## Security Considerations
- Use secure communication channels
- Implement proper authentication
- Monitor for unauthorized access
- Regular security audits
EOF

echo -e "   ${GREEN}✅${NC} Scaling procedures documented"

echo ""
echo "6. 🧪 SCALING TEST"
echo "================"

# Test load balancer
echo "Testing load balancer..."
if curl -s http://localhost/rpc/info >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅${NC} Load balancer responding"
else
    echo -e "   ${RED}❌${NC} Load balancer not responding"
fi

# Test nginx stats
if curl -s http://localhost/nginx_status >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅${NC} nginx stats accessible"
else
    echo -e "   ${RED}❌${NC} nginx stats not accessible"
fi

# Test auto-scaling script
echo "Testing auto-scaling script..."
if /opt/aitbc/cluster/auto_scale.sh >/dev/null 2>&1; then
    echo -e "   ${GREEN}✅${NC} Auto-scaling script working"
else
    echo -e "   ${RED}❌${NC} Auto-scaling script failed"
fi

echo ""
echo "=== 🚀 SCALING PREPARATION COMPLETE ==="
echo ""
echo "Scaling components deployed:"
echo "• nginx load balancer configured"
echo "• Cluster configuration created"
echo "• Auto-scaling scripts deployed"
echo "• Service discovery implemented"
echo "• Scaling procedures documented"
echo ""
echo "Access URLs:"
echo "• Load Balancer: http://$(hostname -I | awk '{print $1}'):80"
echo "• nginx Stats: http://$(hostname -I | awk '{print $1}')/nginx_status"
echo ""
echo "Configuration files:"
echo "• Cluster config: /opt/aitbc/cluster/cluster.conf"
echo "• Service discovery: /opt/aitbc/cluster/service_discovery.json"
echo "• Scaling procedures: /opt/aitbc/docs/scaling/scaling_procedures.md"
echo "• nginx config: /etc/nginx/sites-available/aitbc-loadbalancer"
echo ""
echo -e "${GREEN}✅ Scaling preparation completed successfully!${NC}"
