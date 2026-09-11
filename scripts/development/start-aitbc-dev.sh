#!/bin/bash

# AITBC Development Environment Startup Script
# Starts incus containers and all AITBC services on localhost

set -euo pipefail


# ssh target for the blockchain container on node1. This used to be a private
# ~/.ssh/config alias, so the script only worked on one operator's workstation.
NODE1_CONTAINER_SSH="${AITBC_NODE1_CONTAINER_SSH:?set AITBC_NODE1_CONTAINER_SSH to the ssh target for the container on node1}"

# Fleet node addresses.
#
# These used to be ssh aliases from one operator's ~/.ssh/config, which meant
# the script only ran on that workstation and named the fleet in a public
# repository. Set them for your own deployment; there is deliberately no
# default.
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

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

# Function to check if service exists in container
service_exists_in_container() {
    local container="$1"
    local service="$2"
    case $container in
        "aitbc")
            ssh "$NODE1_CONTAINER_SSH" 'systemctl list-unit-files 2>/dev/null | grep -q "^'"$service"'.service"' 2>/dev/null
            ;;
        "${NODE1_HOST}")
            ssh ${NODE1_CONTAINER_SSH} 'systemctl list-unit-files 2>/dev/null | grep -q "^'"$service"'.service"' 2>/dev/null
            ;;
        *)
            return 1
            ;;
    esac
}

# Function to check if service is running in container
is_service_running_in_container() {
    local container="$1"
    local service="$2"
    case $container in
        "aitbc")
            ssh "$NODE1_CONTAINER_SSH" 'systemctl is-active --quiet '\''"$service"'\'' 2>/dev/null' 2>/dev/null
            ;;
        "${NODE1_HOST}")
            ssh ${NODE1_CONTAINER_SSH} 'systemctl is-active --quiet '\''"$service"'\'' 2>/dev/null' 2>/dev/null
            ;;
        *)
            return 1
            ;;
    esac
}

# Function to get container IP
get_container_ip() {
    local container="$1"
    case $container in
        "aitbc")
            ssh "$NODE1_CONTAINER_SSH" "hostname -I | awk '{print \$1}'" 2>/dev/null || echo "N/A"
            ;;
        "${NODE1_HOST}")
            ssh ${NODE1_CONTAINER_SSH} "hostname -I | awk '{print \$1}'" 2>/dev/null || echo "N/A"
            ;;
        *)
            echo "N/A"
            ;;
    esac
}

print_status "Starting AITBC Development Environment..."

# Check prerequisites
if ! command_exists incus; then
    print_error "incus command not found. Please install incus first."
    exit 1
fi

if ! command_exists systemctl; then
    print_error "systemctl command not found. This script requires systemd."
    exit 1
fi

# Step 1: Check remote containers via SSH
print_status "Checking remote containers via SSH..."

containers=("aitbc" "${NODE1_HOST}")
for container in "${containers[@]}"; do
    print_status "Checking container: $container"

    case $container in
        "aitbc")
            if ssh "$NODE1_CONTAINER_SSH" "echo 'Container is accessible'" >/dev/null 2>&1; then
                print_success "Container $container is accessible via SSH"
            else
                print_error "Container $container is not accessible via SSH"
                exit 1
            fi
            ;;
        "${NODE1_HOST}")
            if ssh ${NODE1_CONTAINER_SSH} "echo 'Container is accessible'" >/dev/null 2>&1; then
                print_success "Container $container is accessible via SSH"
            else
                print_error "Container $container is not accessible via SSH"
                exit 1
            fi
            ;;
    esac
done

# Step 2: Wait for containers to be fully ready
print_status "Waiting for containers to be ready..."
sleep 5

# Step 3: Get container IPs for location detection
declare -A container_ips
for container in "${containers[@]}"; do
    container_ip=$(get_container_ip "$container")
    container_ips["$container"]="$container_ip"
done

# Step 3: Start AITBC systemd services on localhost
print_status "Starting AITBC systemd services on localhost..."

# Get all AITBC services (fixed to handle column alignment issues)
aitbc_services=$(systemctl list-units --all | grep "aitbc-" | awk '{print $2}' | grep "\.service$" | grep -v "not-found") || true

# Filter out invalid service names
filtered_services=""
for service in $aitbc_services; do
    # Skip invalid or malformed service names
    if [[ "$service" =~ [^a-zA-Z0-9\-\._] ]]; then
        print_warning "Skipping invalid service name: $service"
        continue
    fi
    filtered_services="$filtered_services $service"
done
aitbc_services="$filtered_services"

if [ -z "$aitbc_services" ]; then
    print_warning "No AITBC services found on localhost"
else
    print_status "Found AITBC services:"
    for svc in $aitbc_services; do
        echo "  - $svc"
    done

    # Start each service
    for service in $aitbc_services; do
        service_name=${service%.service}
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

# Step 4: Wait for services to initialize
print_status "Waiting for services to initialize..."
sleep 10

# Step 6: Check service status with location information
print_status "Checking service status with location information..."

# Check systemd services on localhost
if [ -n "$aitbc_services" ]; then
    print_status "Local Systemd Services Status:"
    for service in $aitbc_services; do
        service_name=${service%.service}
        if is_service_running "$service_name"; then
            print_success "$service_name: RUNNING (LOCAL)"
        else
            print_error "$service_name: NOT RUNNING (LOCAL)"
        fi
    done
fi

# Check services in containers
print_status "Container Services Status:"

# Define services to check in containers
container_services=("aitbc-coordinator-api" "aitbc-wallet-daemon" "aitbc-blockchain-node-1" "aitbc-blockchain-node-2" "aitbc-exchange-api" "aitbc-explorer")

for container in "${containers[@]}"; do
    container_ip="${container_ips[$container]}"
    print_status "Container $container (IP: $container_ip):"

    for service in "${container_services[@]}"; do
        if service_exists_in_container "$container" "$service"; then
            if is_service_running_in_container "$container" "$service"; then
                print_success "  $service: RUNNING (in $container)"
            else
                print_error "  $service: NOT RUNNING (in $container)"
            fi
        else
            print_warning "  $service: NOT FOUND (in $container)"
        fi
    done
done

# Check common AITBC ports with location detection
print_status "Checking AITBC service ports with location detection..."

ports=(
    "8201:API Gateway"
    "8202:Blockchain RPC"
    "8203:Coordinator API"
    "8100:Blockchain Explorer API"
    "8101:GPU Service"
    "8102:Marketplace Service"
    "8106:Exchange API"
    "8107:Agent Coordinator"
    "8108:Wallet Daemon"
    "8111:Edge Service"
    "8210:Pool Hub"
)

for port_info in "${ports[@]}"; do
    port=$(echo "$port_info" | cut -d: -f1)
    service_name=$(echo "$port_info" | cut -d: -f2)

    if is_port_in_use "$port"; then
        # Try to determine which process is using the port
        process_info=$(netstat -tlnp 2>/dev/null | grep ":$port " | head -1)
        if [ -n "$process_info" ]; then
            pid=$(echo "$process_info" | awk '{print $7}' | cut -d/ -f1)
            if [ -n "$pid" ] && [ "$pid" != "-" ]; then
                # Check if it's a local process
                if ps -p "$pid" -o command= 2>/dev/null | grep -q "python.*uvicorn"; then
                    print_success "$service_name (port $port): RUNNING (LOCAL - PID $pid)"
                else
                    print_success "$service_name (port $port): RUNNING (PID $pid)"
                fi
            else
                print_success "$service_name (port $port): RUNNING"
            fi
        else
            print_success "$service_name (port $port): RUNNING"
        fi
    else
        # Check if service might be running in a container
        found_in_container=false
        for container in "${containers[@]}"; do
            container_ip="${container_ips[$container]}"
            if [ "$container_ip" != "N/A" ]; then
                if timeout 3 bash -c "</dev/tcp/$container_ip/$port" 2>/dev/null; then
                    print_warning "$service_name (port $port): RUNNING (in container $container)"
                    found_in_container=true
                    break
                fi
            fi
        done

        if [ "$found_in_container" = false ]; then
            print_warning "$service_name (port $port): NOT RUNNING"
        fi
    fi
done

# Step 7: Test health endpoints with location detection
print_status "Testing health endpoints with location detection..."

health_endpoints=(
    "http://localhost:8201/health:API Gateway"
    "http://localhost:8202/health:Blockchain RPC"
    "http://localhost:8203/health:Coordinator API"
    "http://localhost:8100/health:Blockchain Explorer API"
    "http://localhost:8106/health:Exchange API"
    "http://localhost:8108/health:Wallet Daemon"
    "http://localhost:8210/health:Pool Hub"
)

for endpoint_info in "${health_endpoints[@]}"; do
    url=$(echo "$endpoint_info" | cut -d: -f1-3)
    service_name=$(echo "$endpoint_info" | cut -d: -f4)

    if curl -s --max-time 5 "$url" >/dev/null 2>&1; then
        print_success "$service_name: HEALTHY (LOCAL)"
    else
        # Check if service is available in containers
        found_in_container=false
        for container in "${containers[@]}"; do
            container_ip="${container_ips[$container]}"
            if [ "$container_ip" != "N/A" ]; then
                container_url="http://$container_ip:$(echo "$url" | cut -d: -f3)/health"
                if curl -s --max-time 3 "$container_url" >/dev/null 2>&1; then
                    print_success "$service_name: HEALTHY (in $container)"
                    found_in_container=true
                    break
                fi
            fi
        done

        if [ "$found_in_container" = false ]; then
            print_warning "$service_name: NOT RESPONDING"
        fi
    fi
done

# Step 7: Check remote container status
print_status "Checking remote container status..."
for container in "${containers[@]}"; do
    container_ip="${container_ips[$container]}"
    case $container in
        "aitbc")
            if ssh "$NODE1_CONTAINER_SSH" "echo 'Container is running'" >/dev/null 2>&1; then
                print_success "Container $container: RUNNING (SSH accessible)"
                print_status "  IP: $container_ip"
                print_status "  Access: ssh "$NODE1_CONTAINER_SSH""
            else
                print_error "Container $container: NOT ACCESSIBLE"
            fi
            ;;
        "${NODE1_HOST}")
            if ssh ${NODE1_CONTAINER_SSH} "echo 'Container is running'" >/dev/null 2>&1; then
                print_success "Container $container: RUNNING (SSH accessible)"
                print_status "  IP: $container_ip"
                print_status "  Access: ssh ${NODE1_CONTAINER_SSH}"
            else
                print_error "Container $container: NOT ACCESSIBLE"
            fi
            ;;
    esac
done

print_success "AITBC Development Environment startup complete!"
print_status "Summary:"
echo "  - Incus containers: ${#containers[@]} started"
echo "  - Systemd services: $(echo "$aitbc_services" | wc -l) found"
echo "  - Check individual service logs with: journalctl -u <service-name>"
echo "  - Access services at their respective ports"
echo ""
print_status "Useful commands:"
echo "  - Check all AITBC services: systemctl list-units | grep aitbc-"
echo "  - Access aitbc container: ssh ${NODE1_CONTAINER_SSH}"
echo "  - View local service logs: journalctl -f -u <service-name>"
echo "  - View container service logs: ssh ${NODE1_CONTAINER_SSH} 'journalctl -f -u <service-name>'"
echo "  - Check container services: ssh ${NODE1_CONTAINER_SSH} 'systemctl status <service-name>'"
echo "  - Check all services in aitbc: ssh ${NODE1_CONTAINER_SSH} 'systemctl list-units | grep aitbc-'"
echo "  - Stop all services: ./scripts/stop-aitbc-dev.sh"
echo ""
print_status "Debug specific issues:"
echo "  - Debug aitbc coordinator: ssh ${NODE1_CONTAINER_SSH} 'systemctl status aitbc-coordinator-api'"
echo "  - Debug aitbc wallet: ssh ${NODE1_CONTAINER_SSH} 'systemctl status aitbc-wallet-daemon'"
echo "  - Debug aitbc blockchain 1: ssh ${NODE1_CONTAINER_SSH} 'systemctl status aitbc-blockchain-node-1'"
echo "  - Debug local blockchain 2: systemctl status aitbc-blockchain-node-2"
echo "  - Debug aitbc exchange: ssh ${NODE1_CONTAINER_SSH} 'systemctl status aitbc-exchange-api'"
echo ""
print_status "Service URLs:"
echo "  - API Gateway:     http://localhost:8201"
echo "  - Blockchain RPC:  http://localhost:8202"
echo "  - Coordinator API: http://localhost:8203"
echo "  - Explorer API:    http://localhost:8100"
echo "  - Exchange API:    http://localhost:8106"
echo "  - Wallet Daemon:   http://localhost:8108"
echo "  - Pool Hub:        http://localhost:8210"
echo ""
echo "  Ports come from docs/reference/SERVICE_PORTS.md, which is the single"
echo "  source of truth. If you change one there, change it here too --"
echo "  scripts/docs/check_ports.py also reads the port array in this file."
