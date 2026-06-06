#!/bin/bash

# AITBC Full Development Environment Startup Script
# Starts incus containers, services inside containers, and all AITBC services on localhost

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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if service is running
is_service_running() {
    systemctl is-active --quiet "$1" 2>/dev/null
}

# Function to check if port is in use
is_port_in_use() {
    netstat -tlnp 2>/dev/null | grep -q ":$1 "
}

print_status "Starting AITBC Full Development Environment..."

# Check prerequisites
if ! command_exists incus; then
    print_error "incus command not found. Please install incus first."
    exit 1
fi

if ! command_exists systemctl; then
    print_error "systemctl command not found. This script requires systemd."
    exit 1
fi

# Step 1: Start incus containers
print_status "Starting incus containers..."

containers=("aitbc" "aitbc1")
for container in "${containers[@]}"; do
    print_status "Starting container: $container"
    
    if incus info "$container" >/dev/null 2>&1; then
        if incus info "$container" | grep -q "Status: RUNNING"; then
            print_warning "Container $container is already running"
        else
            if incus start "$container"; then
                print_success "Container $container started successfully"
            else
                print_error "Failed to start container $container"
                exit 1
            fi
        fi
    else
        print_error "Container $container not found. Please create it first."
        exit 1
    fi
done

# Step 2: Wait for containers to be fully ready
print_status "Waiting for containers to be ready..."
sleep 10

# Step 3: Start services inside containers
print_status "Starting AITBC services inside containers..."

container_services=(
    "aitbc:aitbc-coordinator-api"
    "aitbc:aitbc-wallet-daemon"
    "aitbc:aitbc-blockchain-node"
    "aitbc1:aitbc-coordinator-api"
    "aitbc1:aitbc-wallet-daemon"
    "aitbc1:aitbc-blockchain-node"
)

for service_info in "${container_services[@]}"; do
    container=$(echo "$service_info" | cut -d: -f1)
    service=$(echo "$service_info" | cut -d: -f2)
    
    print_status "Starting $service in container $container"
    
    # Check if service exists in container
    if incus exec "$container" -- systemctl list-unit-files | grep -q "$service.service"; then
        # Start the service inside container
        if incus exec "$container" -- systemctl start "$service"; then
            print_success "$service started in $container"
        else
            print_warning "Failed to start $service in $container (may not be installed)"
        fi
    else
        print_warning "$service not found in $container"
    fi
done

# Step 4: Start AITBC systemd services on localhost
print_status "Starting AITBC systemd services on localhost..."

# Get all AITBC services (filter out invalid characters)
aitbc_services=$(systemctl list-units --all | grep "aitbc-" | grep -v "●" | awk '{print $1}' | grep -v "not-found" | grep -v "loaded")

if [ -z "$aitbc_services" ]; then
    print_warning "No AITBC services found on localhost"
else
    print_status "Found AITBC services:"
    echo "$aitbc_services" | sed 's/^/  - /'
    
    # Start each service
    for service in $aitbc_services; do
        service_name=$(echo "$service" | sed 's/\.service$//')
        print_status "Starting service: $service_name"
        
        if is_service_running "$service_name"; then
            print_warning "Service $service_name is already running"
        else
            if systemctl start "$service_name"; then
                print_success "Service $service_name started successfully"
            else
                print_error "Failed to start service $service_name"
            fi
        fi
    done
fi

# Step 5: Wait for services to initialize
print_status "Waiting for services to initialize..."
sleep 15

# Step 6: Check service status
print_status "Checking service status..."

# Check systemd services on localhost
if [ -n "$aitbc_services" ]; then
    print_status "Local Systemd Services Status:"
    for service in $aitbc_services; do
        service_name=$(echo "$service" | sed 's/\.service$//')
        if is_service_running "$service_name"; then
            print_success "$service_name: RUNNING"
        else
            print_error "$service_name: NOT RUNNING"
        fi
    done
fi

# Check services in containers
print_status "Container Services Status:"
for service_info in "${container_services[@]}"; do
    container=$(echo "$service_info" | cut -d: -f1)
    service=$(echo "$service_info" | cut -d: -f2)
    
    if incus exec "$container" -- systemctl is-active --quiet "$service" 2>/dev/null; then
        print_success "$service in $container: RUNNING"
    else
        print_warning "$service in $container: NOT RUNNING"
    fi
done

# Check common AITBC ports
print_status "Checking AITBC service ports..."

ports=(
    "8001:Coordinator API"
    "8002:Wallet Daemon"
    "8003:Blockchain RPC"
    "8000:Coordinator API (alt)"
    "8081:Blockchain Node 1"
    "8082:Blockchain Node 2"
    "8006:Coordinator API (dev)"
)

for port_info in "${ports[@]}"; do
    port=$(echo "$port_info" | cut -d: -f1)
    service_name=$(echo "$port_info" | cut -d: -f2)
    
    if is_port_in_use "$port"; then
        print_success "$service_name (port $port): RUNNING"
    else
        print_warning "$service_name (port $port): NOT RUNNING"
    fi
done

# Step 7: Test health endpoints
print_status "Testing health endpoints..."

health_endpoints=(
    "http://localhost:8001/health:Coordinator API"
    "http://localhost:8002/health:Wallet Daemon"
    "http://localhost:8003/health:Blockchain RPC"
)

for endpoint_info in "${health_endpoints[@]}"; do
    url=$(echo "$endpoint_info" | cut -d: -f1-3)
    service_name=$(echo "$endpoint_info" | cut -d: -f4)
    
    if curl -s --max-time 5 "$url" >/dev/null 2>&1; then
        print_success "$service_name: HEALTHY"
    else
        print_warning "$service_name: NOT RESPONDING"
    fi
done

# Step 8: Container status and IPs
print_status "Container status and network information..."

for container in "${containers[@]}"; do
    if incus info "$container" | grep -q "Status: RUNNING"; then
        print_success "Container $container: RUNNING"
        
        # Get container IP
        container_ip=$(incus exec "$container" -- ip addr show eth0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1 || echo "N/A")
        if [ "$container_ip" != "N/A" ]; then
            print_status "  IP: $container_ip"
            
            # Test connectivity to container services
            print_status "  Testing container services:"
            for service_info in "${container_services[@]}"; do
                cont=$(echo "$service_info" | cut -d: -f1)
                serv=$(echo "$service_info" | cut -d: -f2)
                
                if [ "$cont" = "$container" ]; then
                    case $serv in
                        "aitbc-coordinator-api")
                            if curl -s --max-time 3 "http://$container_ip:8001/health" >/dev/null 2>&1; then
                                print_success "    Coordinator API: HEALTHY"
                            else
                                print_warning "    Coordinator API: NOT RESPONDING"
                            fi
                            ;;
                        "aitbc-wallet-daemon")
                            if curl -s --max-time 3 "http://$container_ip:8002/health" >/dev/null 2>&1; then
                                print_success "    Wallet Daemon: HEALTHY"
                            else
                                print_warning "    Wallet Daemon: NOT RESPONDING"
                            fi
                            ;;
                        "aitbc-blockchain-node")
                            if curl -s --max-time 3 "http://$container_ip:8003/health" >/dev/null 2>&1; then
                                print_success "    Blockchain Node: HEALTHY"
                            else
                                print_warning "    Blockchain Node: NOT RESPONDING"
                            fi
                            ;;
                    esac
                fi
            done
        fi
    else
        print_error "Container $container: NOT RUNNING"
    fi
done

print_success "AITBC Full Development Environment startup complete!"
print_status "Summary:"
echo "  - Incus containers: ${#containers[@]} started"
echo "  - Local systemd services: $(echo "$aitbc_services" | wc -l) found"
echo "  - Container services: ${#container_services[@]} attempted"
echo ""
print_status "Useful commands:"
echo "  - Check all AITBC services: systemctl list-units | grep aitbc-"
echo "  - Check container status: incus list"
echo "  - View service logs: journalctl -f -u aitbc-coordinator-api"
echo "  - View container logs: incus exec aitbc -- journalctl -f -u aitbc-coordinator-api"
echo "  - Stop all services: ./scripts/stop-aitbc-full.sh"
echo ""
print_status "Service URLs:"
echo "  - Coordinator API: http://localhost:8001"
echo "  - Wallet Daemon: http://localhost:8002"
echo "  - Blockchain RPC: http://localhost:8003"
