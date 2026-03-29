#!/bin/bash

# AITBC Basic Monitoring Setup
# Creates simple monitoring without Grafana/Prometheus

set -e

echo "=== 📊 AITBC BASIC MONITORING SETUP ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "1. 📈 SIMPLE MONITORING SETUP"
echo "============================"

# Create basic monitoring directory
mkdir -p /opt/aitbc/monitoring
mkdir -p /var/log/aitbc/monitoring

# Create simple health check script
cat > /opt/aitbc/monitoring/health_monitor.sh << 'EOF'
#!/bin/bash

# Basic health monitoring script
LOG_FILE="/var/log/aitbc/monitoring/health.log"
mkdir -p $(dirname "$LOG_FILE")

# Function to log
log_health() {
    echo "[$(date)] $1" >> "$LOG_FILE"
}

# Check blockchain health
check_blockchain() {
    local height=$(curl -s http://localhost:8006/rpc/head | jq -r .height 2>/dev/null || echo "0")
    local status=$(curl -s http://localhost:8006/rpc/info >/dev/null 2>&1 && echo "healthy" || echo "unhealthy")
    echo "$height,$status"
}

# Check system resources
check_system() {
    local cpu=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    local mem=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    local disk=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    echo "$cpu,$mem,$disk"
}

# Main monitoring
log_health "Starting health check"

# Blockchain status
blockchain_status=$(check_blockchain)
height=$(echo "$blockchain_status" | cut -d',' -f1)
health=$(echo "$blockchain_status" | cut -d',' -f2)
log_health "Blockchain height: $height, status: $health"

# System status
system_status=$(check_system)
cpu=$(echo "$system_status" | cut -d',' -f1)
mem=$(echo "$system_status" | cut -d',' -f2)
disk=$(echo "$system_status" | cut -d',' -f3)
log_health "System: CPU=${cpu}%, MEM=${mem}%, DISK=${disk}%"

log_health "Health check completed"
EOF

chmod +x /opt/aitbc/monitoring/health_monitor.sh

echo -e "   ${GREEN}✅${NC} Basic monitoring script created"

echo ""
echo "2. 📊 MONITORING DASHBOARD"
echo "========================"

# Create simple web dashboard
cat > /opt/aitbc/monitoring/dashboard.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>AITBC Monitoring Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .metric { margin: 10px 0; padding: 10px; border: 1px solid #ddd; }
        .healthy { color: green; }
        .unhealthy { color: red; }
    </style>
</head>
<body>
    <h1>AITBC Monitoring Dashboard</h1>
    <div id="metrics">
        <p>Loading metrics...</p>
    </div>
    
    <script>
        function updateMetrics() {
            fetch('/metrics')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('metrics').innerHTML = `
                        <div class="metric">
                            <h3>Blockchain</h3>
                            <p>Height: ${data.height}</p>
                            <p>Status: <span class="${data.health}">${data.health}</span></p>
                        </div>
                        <div class="metric">
                            <h3>System</h3>
                            <p>CPU: ${data.cpu}%</p>
                            <p>Memory: ${data.memory}%</p>
                            <p>Disk: ${data.disk}%</p>
                        </div>
                        <div class="metric">
                            <h3>Last Updated</h3>
                            <p>${new Date().toLocaleString()}</p>
                        </div>
                    `;
                })
                .catch(error => {
                    document.getElementById('metrics').innerHTML = '<p>Error loading metrics</p>';
                });
        }
        
        updateMetrics();
        setInterval(updateMetrics, 10000); // Update every 10 seconds
    </script>
</body>
</html>
EOF

echo -e "   ${GREEN}✅${NC} Simple dashboard created"

echo ""
echo "3. � MONITORING AUTOMATION"
echo "=========================="

# Create metrics API endpoint
cat > /opt/aitbc/monitoring/metrics_api.py << 'EOF'
#!/usr/bin/env python3

import json
import subprocess
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/metrics')
def get_metrics():
    try:
        # Get blockchain height
        height = subprocess.getoutput("curl -s http://localhost:8006/rpc/head | jq -r .height 2>/dev/null || echo 0")
        
        # Check blockchain health
        health = "healthy" if subprocess.getoutput("curl -s http://localhost:8006/rpc/info >/dev/null 2>&1 && echo healthy || echo unhealthy").strip() == "healthy"
        
        # Get system metrics
        cpu = subprocess.getoutput("top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | sed 's/%us,//'")
        memory = subprocess.getoutput("free | grep Mem | awk '{printf \"%.1f\", $3/$2 * 100.0}'")
        disk = subprocess.getoutput("df / | awk 'NR==2 {print $5}' | sed 's/%//'")
        
        return jsonify({
            'height': int(height),
            'health': health,
            'cpu': cpu,
            'memory': memory,
            'disk': int(disk)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
EOF

chmod +x /opt/aitbc/monitoring/metrics_api.py

echo -e "   ${GREEN}✅${NC} Metrics API created"

echo ""
echo "4. � MONITORING SCHEDULE"
echo "======================"

# Add health monitoring to cron
(crontab -l 2>/dev/null; echo "*/2 * * * * /opt/aitbc/monitoring/health_monitor.sh") | crontab -

echo -e "   ${GREEN}✅${NC} Health monitoring scheduled (every 2 minutes)"

echo ""
echo "5. 🧪 MONITORING VERIFICATION"
echo "=========================="

# Test health monitor
echo "Testing health monitor..."
/opt/aitbc/monitoring/health_monitor.sh

# Check log file
if [ -f "/var/log/aitbc/monitoring/health.log" ]; then
    echo -e "   ${GREEN}✅${NC} Health log created"
    echo "   Recent entries:"
    tail -3 /var/log/aitbc/monitoring/health.log
else
    echo -e "   ${RED}❌${NC} Health log not found"
fi

echo ""
echo "6. 📊 MONITORING ACCESS"
echo "===================="

echo "Basic monitoring components deployed:"
echo "• Health monitor script: /opt/aitbc/monitoring/health_monitor.sh"
echo "• Dashboard: /opt/aitbc/monitoring/dashboard.html"
echo "• Metrics API: /opt/aitbc/monitoring/metrics_api.py"
echo "• Health logs: /var/log/aitbc/monitoring/health.log"
echo ""
echo "To start metrics API:"
echo "  python3 /opt/aitbc/monitoring/metrics_api.py"
echo ""
echo "Then access dashboard at:"
echo "  http://$(hostname -I | awk '{print $1}'):8080"

echo ""
echo "=== 📊 BASIC MONITORING SETUP COMPLETE ==="
echo ""
echo "Basic monitoring deployed without Grafana/Prometheus:"
echo "• Health monitoring script"
echo "• Simple web dashboard"
echo "• Metrics API endpoint"
echo "• Automated health checks"
echo ""
echo -e "${GREEN}✅ Basic monitoring setup completed!${NC}"
