#!/bin/bash

# AITBC Service Location Diagnostic Script
# Shows exactly where each AITBC service is running

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

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

print_container() {
    echo -e "${CYAN}[CONTAINER]${NC} $1"
}

print_local() {
    echo -e "${CYAN}[LOCAL]${NC} $1"
}

print_status "AITBC Service Location Diagnostic"

# Get container IPs
containers=("aitbc" "aitbc1")
declare -A container_ips

for container in "${containers[@]}"; do
    if incus info "$container" >/dev/null 2>&1; then
        if incus info "$container" | grep -q "Status: RUNNING"; then
            container_ip=$(incus exec "$container" -- ip addr show eth0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1 || echo "N/A")
            container_ips["$container"]="$container_ip"
        fi
    fi
done

# Check local services
print_local "Local AITBC Services:"
local_services=$(systemctl list-units --all | grep "aitbc-" | awk '{print $1}' | grep -v "not-found")

if [ -n "$local_services" ]; then
    for service in $local_services; do
        service_name=$(echo "$service" | sed 's/\.service$//')
        if systemctl is-active --quiet "$service_name" 2>/dev/null; then
            # Get port if possible
            port_info=""
            case $service_name in
                *coordinator-api*) port_info=" (port 8001)" ;;
                *wallet*) port_info=" (port 8002)" ;;
                *blockchain*) port_info=" (port 8003)" ;;
            esac
            print_success "  ✅ $service_name: RUNNING$port_info"
        else
            print_error "  ❌ $service_name: NOT RUNNING"
        fi
    done
else
    print_warning "  No AITBC services found locally"
fi

echo ""

# Check container services
for container in "${containers[@]}"; do
    if incus info "$container" >/dev/null 2>&1; then
        if incus info "$container" | grep -q "Status: RUNNING"; then
            container_ip="${container_ips[$container]}"
            print_container "Container $container (IP: $container_ip):"
            
            # Check common AITBC services in container
            services=("aitbc-coordinator-api" "aitbc-wallet-daemon" "aitbc-blockchain-node")
            
            for service in "${services[@]}"; do
                if incus exec "$container" -- systemctl list-unit-files 2>/dev/null | grep -q "^${service}.service"; then
                    if incus exec "$container" -- systemctl is-active --quiet "$service" 2>/dev/null; then
                        # Get port if possible
                        port_info=""
                        case $service in
                            *coordinator-api*) port_info=" (port 8001)" ;;
                            *wallet*) port_info=" (port 8002)" ;;
                            *blockchain*) port_info=" (port 8003)" ;;
                        esac
                        print_success "    ✅ $service: RUNNING$port_info"
                    else
                        print_error "    ❌ $service: NOT RUNNING"
                    fi
                else
                    print_warning "    ⚠️  $service: NOT INSTALLED"
                fi
            done
        else
            print_error "Container $container: NOT RUNNING"
        fi
    else
        print_error "Container $container: NOT FOUND"
    fi
    echo ""
done

# Port scan summary
print_status "Port Scan Summary:"
ports=("8001:Coordinator API" "8002:Wallet Daemon" "8003:Blockchain RPC" "8000:Coordinator API (alt)")

for port_info in "${ports[@]}"; do
    port=$(echo "$port_info" | cut -d: -f1)
    service_name=$(echo "$port_info" | cut -d: -f2)
    
    if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        process_info=$(netstat -tlnp 2>/dev/null | grep ":$port " | head -1)
        pid=$(echo "$process_info" | awk '{print $7}' | cut -d/ -f1)
        if [ -n "$pid" ] && [ "$pid" != "-" ]; then
            print_success "  ✅ Port $port ($service_name): LOCAL (PID $pid)"
        else
            print_success "  ✅ Port $port ($service_name): LOCAL"
        fi
    else
        # Check containers
        found=false
        for container in "${containers[@]}"; do
            container_ip="${container_ips[$container]}"
            if [ "$container_ip" != "N/A" ]; then
                if timeout 2 bash -c "</dev/tcp/$container_ip/$port" 2>/dev/null; then
                    print_success "  ✅ Port $port ($service_name): Container $container ($container_ip)"
                    found=true
                    break
                fi
            fi
        done
        
        if [ "$found" = false ]; then
            print_error "  ❌ Port $port ($service_name): NOT ACCESSIBLE"
        fi
    fi
done

echo ""
print_status "Health Check Summary:"
health_endpoints=(
    "http://localhost:8001/health:Coordinator API"
    "http://localhost:8002/health:Wallet Daemon"
    "http://localhost:8003/health:Blockchain RPC"
)

for endpoint_info in "${health_endpoints[@]}"; do
    url=$(echo "$endpoint_info" | cut -d: -f1-3)
    service_name=$(echo "$endpoint_info" | cut -d: -f4)
    
    if curl -s --max-time 3 "$url" >/dev/null 2>&1; then
        print_success "  ✅ $service_name: HEALTHY (LOCAL)"
    else
        # Check containers
        found=false
        for container in "${containers[@]}"; do
            container_ip="${container_ips[$container]}"
            if [ "$container_ip" != "N/A" ]; then
                container_url="http://$container_ip:$(echo "$url" | cut -d: -f3)/health"
                if curl -s --max-time 2 "$container_url" >/dev/null 2>&1; then
                    print_success "  ✅ $service_name: HEALTHY (Container $container)"
                    found=true
                    break
                fi
            fi
        done
        
        if [ "$found" = false ]; then
            print_error "  ❌ $service_name: NOT RESPONDING"
        fi
    fi
done

echo ""
print_status "Quick Debug Commands:"
echo "  - Check specific service: systemctl status <service-name>"
echo "  - Check container service: incus exec <container> -- systemctl status <service-name>"
echo "  - View service logs: journalctl -f -u <service-name>"
echo "  - View container logs: incus exec <container> -- journalctl -f -u <service-name>"
echo "  - Check port usage: netstat -tlnp | grep :800"
