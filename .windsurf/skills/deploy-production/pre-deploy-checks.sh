#!/bin/bash

# Pre-deployment checks for AITBC production deployment
# This script validates system readiness before deployment

set -e

echo "=== AITBC Production Pre-deployment Checks ==="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1"
        exit 1
    fi
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 1. Check disk space
echo -e "\n1. Checking disk space..."
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $DISK_USAGE -lt 80 ]; then
    check_status "Disk space usage: ${DISK_USAGE}%"
else
    warning "Disk space usage is high: ${DISK_USAGE}%"
fi

# 2. Check memory usage
echo -e "\n2. Checking memory usage..."
MEM_AVAILABLE=$(free -m | awk 'NR==2{printf "%.0f", $7}')
if [ $MEM_AVAILABLE -gt 1024 ]; then
    check_status "Available memory: ${MEM_AVAILABLE}MB"
else
    warning "Low memory available: ${MEM_AVAILABLE}MB"
fi

# 3. Check service status
echo -e "\n3. Checking critical services..."
services=("nginx" "docker" "postgresql")
for service in "${services[@]}"; do
    if systemctl is-active --quiet $service; then
        check_status "$service is running"
    else
        echo -e "${RED}✗${NC} $service is not running"
    fi
done

# 4. Check SSL certificates
echo -e "\n4. Checking SSL certificates..."
if [ -f "/etc/letsencrypt/live/$(hostname)/fullchain.pem" ]; then
    EXPIRY=$(openssl x509 -in /etc/letsencrypt/live/$(hostname)/fullchain.pem -noout -enddate | cut -d= -f2)
    check_status "SSL certificate valid until: $EXPIRY"
else
    warning "SSL certificate not found"
fi

# 5. Check backup
echo -e "\n5. Checking recent backup..."
BACKUP_DIR="/var/backups/aitbc"
if [ -d "$BACKUP_DIR" ]; then
    LATEST_BACKUP=$(ls -lt $BACKUP_DIR | head -n 2 | tail -n 1 | awk '{print $9}')
    if [ -n "$LATEST_BACKUP" ]; then
        check_status "Latest backup: $LATEST_BACKUP"
    else
        warning "No recent backup found"
    fi
else
    warning "Backup directory not found"
fi

# 6. Check environment variables
echo -e "\n6. Checking environment configuration..."
if [ -f "/etc/environment" ] && grep -q "AITBC_ENV=production" /etc/environment; then
    check_status "Production environment configured"
else
    warning "Production environment not set"
fi

# 7. Check ports
echo -e "\n7. Checking required ports..."
ports=("80" "443" "8080" "8545")
for port in "${ports[@]}"; do
    if netstat -tuln | grep -q ":$port "; then
        check_status "Port $port is listening"
    else
        warning "Port $port is not listening"
    fi
done

echo -e "\n=== Pre-deployment checks completed ==="
echo -e "${GREEN}Ready for deployment!${NC}"
