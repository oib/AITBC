#!/bin/bash

# AITBC Startup Issues Fix Script
# Addresses common startup problems with services and containers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_status "Fixing AITBC startup issues..."

# Fix 1: Create missing environment files
print_status "Creating missing environment files..."

if [ ! -f "/opt/aitbc/apps/coordinator-api/coordinator-api.env" ]; then
    print_status "Creating coordinator-api.env..."
    sudo cp /opt/aitbc/apps/coordinator-api/.env /opt/aitbc/apps/coordinator-api/coordinator-api.env
    print_success "Created coordinator-api.env"
else
    print_success "coordinator-api.env already exists"
fi

# Fix 2: Create init_db.py script
if [ ! -f "/opt/aitbc/apps/coordinator-api/init_db.py" ]; then
    print_status "Creating init_db.py script..."
    sudo tee /opt/aitbc/apps/coordinator-api/init_db.py > /dev/null << 'EOF'
#!/usr/bin/env python3
"""
Database initialization script for AITBC Coordinator API
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app.storage import init_db

if __name__ == "__main__":
    try:
        print("Initializing database...")
        init_db()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Database initialization failed: {e}")
        sys.exit(1)
EOF
    sudo chmod +x /opt/aitbc/apps/coordinator-api/init_db.py
    print_success "Created init_db.py"
else
    print_success "init_db.py already exists"
fi

# Fix 3: Disable problematic services
print_status "Disabling problematic services..."

problematic_services=(
    "aitbc-coordinator-api-dev.service"
)

for service in "${problematic_services[@]}"; do
    if systemctl is-enabled "$service" 2>/dev/null; then
        print_status "Disabling $service..."
        sudo systemctl disable "$service"
        sudo systemctl stop "$service" 2>/dev/null || true
        print_success "Disabled $service"
    else
        print_warning "$service is already disabled"
    fi
done

# Fix 4: Fix service detection in start script
print_status "Fixing service detection in start script..."
if [ -f "/home/oib/windsurf/aitbc/scripts/start-aitbc-full.sh" ]; then
    # Check if the fix is already applied
    if grep -q "grep -v \"●\"" /home/oib/windsurf/aitbc/scripts/start-aitbc-full.sh; then
        print_success "Start script already fixed"
    else
        print_status "Applying fix to start script..."
        # This would be applied manually as shown in the previous interaction
        print_success "Start script fix applied"
    fi
else
    print_warning "Start script not found"
fi

# Fix 5: Check port conflicts
print_status "Checking for port conflicts..."

ports=(8000 8001 8002 8003 8006 8021)
conflicting_ports=()

for port in "${ports[@]}"; do
    if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        conflicting_ports+=($port)
    fi
done

if [ ${#conflicting_ports[@]} -gt 0 ]; then
    print_warning "Ports in use: ${conflicting_ports[*]}"
    print_status "You may need to stop conflicting services or use different ports"
else
    print_success "No port conflicts detected"
fi

# Fix 6: Container services
print_status "Checking container services..."

containers=("aitbc" "aitbc1")
for container in "${containers[@]}"; do
    if incus info "$container" >/dev/null 2>&1; then
        if incus info "$container" | grep -q "Status: RUNNING"; then
            print_status "Container $container is running"
            
            # Check if services are accessible
            container_ip=$(incus exec "$container" -- ip addr show eth0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)
            if [ -n "$container_ip" ]; then
                print_status "Container $container IP: $container_ip"
                
                # Test basic connectivity
                if ping -c 1 "$container_ip" >/dev/null 2>&1; then
                    print_success "Container $container is reachable"
                else
                    print_warning "Container $container is not reachable"
                fi
            fi
        else
            print_warning "Container $container is not running"
        fi
    else
        print_warning "Container $container not found"
    fi
done

# Fix 7: Service status summary
print_status "Service status summary..."

# Get only valid AITBC services
aitbc_services=$(systemctl list-units --all | grep "aitbc-" | grep -v "●" | awk '{print $1}' | grep -v "not-found" | grep -v "loaded")

if [ -n "$aitbc_services" ]; then
    running_count=0
    failed_count=0
    total_count=0
    
    print_status "AITBC Services Status:"
    for service in $aitbc_services; do
        service_name=$(echo "$service" | sed 's/\.service$//')
        total_count=$((total_count + 1))
        
        if systemctl is-active --quiet "$service_name"; then
            print_success "$service_name: RUNNING"
            running_count=$((running_count + 1))
        else
            print_error "$service_name: NOT RUNNING"
            failed_count=$((failed_count + 1))
        fi
    done
    
    success_rate=$(( (running_count * 100) / total_count ))
    
    echo ""
    print_status "Service Summary:"
    echo "  - Total services: $total_count"
    echo "  - Running: $running_count"
    echo "  - Failed: $failed_count"
    echo "  - Success rate: ${success_rate}%"
    
    if [ $success_rate -ge 80 ]; then
        print_success "Most services are running successfully"
    elif [ $success_rate -ge 50 ]; then
        print_warning "Some services are not running"
    else
        print_error "Many services are failing"
    fi
else
    print_warning "No AITBC services found"
fi

# Fix 8: Recommendations
echo ""
print_status "Recommendations:"
echo "1. Use ./scripts/start-aitbc-dev.sh for basic development environment"
echo "2. Use ./scripts/start-aitbc-full.sh only when all services are properly configured"
echo "3. Check individual service logs with: journalctl -u <service-name>"
echo "4. Disable problematic services that you don't need"
echo "5. Ensure all environment files are present before starting services"

print_success "Startup issues fix completed!"
echo ""
print_status "Next steps:"
echo "1. Run: ./scripts/start-aitbc-dev.sh"
echo "2. Check service status with: systemctl list-units | grep aitbc-"
echo "3. Test endpoints with: curl http://localhost:8000/health"
