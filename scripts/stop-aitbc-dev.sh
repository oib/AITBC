#!/bin/bash

# AITBC Development Environment Stop Script
# Stops incus containers and all AITBC services on localhost

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

print_status "Stopping AITBC Development Environment..."

# Check prerequisites
if ! command_exists incus; then
    print_error "incus command not found. Please install incus first."
    exit 1
fi

if ! command_exists systemctl; then
    print_error "systemctl command not found. This script requires systemd."
    exit 1
fi

# Step 1: Stop AITBC systemd services on localhost
print_status "Stopping AITBC systemd services on localhost..."

# Get all AITBC services
aitbc_services=$(systemctl list-units --all | grep "aitbc-" | awk '{print $1}' | grep -v "not-found")

if [ -z "$aitbc_services" ]; then
    print_warning "No AITBC services found on localhost"
else
    print_status "Found AITBC services:"
    echo "$aitbc_services" | sed 's/^/  - /'
    
    # Stop each service
    for service in $aitbc_services; do
        service_name=$(echo "$service" | sed 's/\.service$//')
        print_status "Stopping service: $service_name"
        
        if is_service_running "$service_name"; then
            if systemctl stop "$service_name"; then
                print_success "Service $service_name stopped successfully"
            else
                print_error "Failed to stop service $service_name"
            fi
        else
            print_warning "Service $service_name is already stopped"
        fi
    done
fi

# Step 2: Stop incus containers
print_status "Stopping incus containers..."

containers=("aitbc" "aitbc1")
for container in "${containers[@]}"; do
    print_status "Stopping container: $container"
    
    if incus info "$container" >/dev/null 2>&1; then
        # Check if container is running
        if incus info "$container" | grep -q "Status: RUNNING"; then
            if incus stop "$container"; then
                print_success "Container $container stopped successfully"
            else
                print_error "Failed to stop container $container"
            fi
        else
            print_warning "Container $container is already stopped"
        fi
    else
        print_warning "Container $container not found"
    fi
done

# Step 3: Verify services are stopped
print_status "Verifying services are stopped..."

# Check systemd services
if [ -n "$aitbc_services" ]; then
    print_status "Systemd Services Status:"
    for service in $aitbc_services; do
        service_name=$(echo "$service" | sed 's/\.service$//')
        if is_service_running "$service_name"; then
            print_error "$service_name: STILL RUNNING"
        else
            print_success "$service_name: STOPPED"
        fi
    done
fi

# Check containers
print_status "Container Status:"
for container in "${containers[@]}"; do
    if incus info "$container" >/dev/null 2>&1; then
        if incus info "$container" | grep -q "Status: RUNNING"; then
            print_error "Container $container: STILL RUNNING"
        else
            print_success "Container $container: STOPPED"
        fi
    else
        print_warning "Container $container: NOT FOUND"
    fi
done

print_success "AITBC Development Environment shutdown complete!"
print_status "Summary:"
echo "  - Incus containers: ${#containers[@]} stopped"
echo "  - Systemd services: $(echo "$aitbc_services" | wc -l) stopped"
echo ""
print_status "To start again: ./scripts/start-aitbc-dev.sh"
