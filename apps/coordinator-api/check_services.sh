#!/bin/bash

# AITBC Enhanced Services Status Check Script
# Checks the status of all enhanced AITBC services

set -e

echo "🔍 Checking AITBC Enhanced Services Status..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[HEADER]${NC} $1"
}

# Enhanced services configuration
declare -A SERVICES=(
    ["aitbc-multimodal"]="8002:Multi-Modal Agent Service"
    ["aitbc-gpu-multimodal"]="8003:GPU Multi-Modal Service"
    ["aitbc-modality-optimization"]="8004:Modality Optimization Service"
    ["aitbc-adaptive-learning"]="8005:Adaptive Learning Service"
    ["aitbc-marketplace-enhanced"]="8006:Enhanced Marketplace Service"
    ["aitbc-openclaw-enhanced"]="8007:OpenClaw Enhanced Service"
)

print_header "=== AITBC Enhanced Services Status ==="
echo

# Check systemd services
print_header "Systemd Service Status:"
for service in "${!SERVICES[@]}"; do
    if systemctl is-active --quiet "$service.service"; then
        status="${GREEN}ACTIVE${NC}"
        port_info="${SERVICES[$service]}"
        echo -e "  ${service:6}: $status | $port_info"
    else
        status="${RED}INACTIVE${NC}"
        port_info="${SERVICES[$service]}"
        echo -e "  ${service:6}: $status | $port_info"
    fi
done
echo

# Check port availability
print_header "Port Availability Check:"
for service in "${!SERVICES[@]}"; do
    IFS=':' read -r port description <<< "${SERVICES[$service]}"
    if netstat -tuln 2>/dev/null | grep -q ":$port "; then
        echo -e "  Port $port: ${GREEN}OPEN${NC} ($description)"
    else
        echo -e "  Port $port: ${RED}CLOSED${NC} ($description)"
    fi
done
echo

# Health check endpoints
print_header "Health Check Endpoints:"
for service in "${!SERVICES[@]}"; do
    IFS=':' read -r port description <<< "${SERVICES[$service]}"
    health_url="http://localhost:$port/health"
    
    if curl -s --max-time 5 "$health_url" > /dev/null 2>&1; then
        echo -e "  $health_url: ${GREEN}OK${NC}"
    else
        echo -e "  $health_url: ${RED}FAILED${NC}"
    fi
done
echo

# GPU availability check
print_header "GPU Availability:"
if command -v nvidia-smi &> /dev/null; then
    if nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader,nounits 2>/dev/null; then
        echo -e "  GPU Status: ${GREEN}AVAILABLE${NC}"
        nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | while read utilization; do
            echo -e "  GPU Utilization: ${utilization}%"
        done
    else
        echo -e "  GPU Status: ${YELLOW}NVIDIA DRIVER ISSUES${NC}"
    fi
else
    echo -e "  GPU Status: ${RED}NOT AVAILABLE${NC}"
fi
echo

# Python environment check
print_header "Python Environment:"
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version 2>&1)
    echo -e "  Python Version: $python_version"
    
    if python3 -c "import sys; print('Python 3.13+:', sys.version_info >= (3, 13))" 2>/dev/null; then
        echo -e "  Python 3.13+: ${GREEN}COMPATIBLE${NC}"
    else
        echo -e "  Python 3.13+: ${YELLOW}NOT DETECTED${NC}"
    fi
else
    echo -e "  Python: ${RED}NOT FOUND${NC}"
fi
echo

# Summary
print_header "Summary:"
active_services=0
total_services=${#SERVICES[@]}

for service in "${!SERVICES[@]}"; do
    if systemctl is-active --quiet "$service.service"; then
        ((active_services++))
    fi
done

echo -e "  Active Services: $active_services/$total_services"
echo -e "  Deployment Status: $([ $active_services -eq $total_services ] && echo "${GREEN}COMPLETE${NC}" || echo "${YELLOW}PARTIAL${NC}")"

if [ $active_services -eq $total_services ]; then
    print_status "🎉 All enhanced services are running!"
    exit 0
else
    print_warning "⚠️  Some services are not running. Check logs for details."
    exit 1
fi
