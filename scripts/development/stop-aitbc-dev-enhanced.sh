#!/bin/bash

# AITBC Development Environment Enhanced Stop Script
# Stops incus containers and all AITBC services on localhost
# Enhanced to handle persistent services with auto-restart configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
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

print_persistent() {
    echo -e "${PURPLE}[PERSISTENT]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if service is running
is_service_running() {
    systemctl is-active --quiet "$1" 2>/dev/null
}

# Function to check if service has auto-restart configured
has_auto_restart() {
    systemctl show "$1" -p Restart | grep -q "Restart=yes\|Restart=always"
}

# Function to force stop a persistent service
force_stop_service() {
    local service_name="$1"
    local max_attempts=3
    local attempt=1
    
    print_persistent "Service $service_name has auto-restart - applying enhanced stop procedure..."
    
    # Disable auto-restart temporarily
    if systemctl show "$service_name" -p Restart | grep -q "Restart=always"; then
        print_status "Temporarily disabling auto-restart for $service_name"
        sudo systemctl kill -s SIGSTOP "$service_name" 2>/dev/null || true
    fi
    
    # Try to stop with increasing force
    while [ $attempt -le $max_attempts ]; do
        print_status "Attempt $attempt/$max_attempts to stop $service_name"
        
        case $attempt in
            1)
                # First attempt: normal stop
                systemctl stop "$service_name" 2>/dev/null || true
                ;;
            2)
                # Second attempt: kill main process
                main_pid=$(systemctl show "$service_name" -p MainPID | cut -d'=' -f2)
                if [ "$main_pid" != "0" ]; then
                    print_status "Killing main PID $main_pid for $service_name"
                    sudo kill -TERM "$main_pid" 2>/dev/null || true
                fi
                ;;
            3)
                # Third attempt: force kill
                print_status "Force killing all processes for $service_name"
                sudo pkill -f "$service_name" 2>/dev/null || true
                sudo systemctl kill -s SIGKILL "$service_name" 2>/dev/null || true
                ;;
        esac
        
        # Wait and check
        sleep 2
        if ! is_service_running "$service_name"; then
            print_success "Service $service_name stopped on attempt $attempt"
            return 0
        fi
        
        attempt=$((attempt + 1))
    done
    
    # If still running, try service masking
    print_persistent "Service $service_name still persistent - trying service masking..."
    service_file="/etc/systemd/system/$service_name.service"
    if [ -f "$service_file" ]; then
        sudo mv "$service_file" "${service_file}.bak" 2>/dev/null || true
        sudo systemctl daemon-reload 2>/dev/null || true
        systemctl stop "$service_name" 2>/dev/null || true
        sleep 2
        
        if ! is_service_running "$service_name"; then
            print_success "Service $service_name stopped via service masking"
            # Restore the service file
            sudo mv "${service_file}.bak" "$service_file" 2>/dev/null || true
            sudo systemctl daemon-reload 2>/dev/null || true
            return 0
        else
            # Restore the service file even if still running
            sudo mv "${service_file}.bak" "$service_file" 2>/dev/null || true
            sudo systemctl daemon-reload 2>/dev/null || true
        fi
    fi
    
    print_error "Failed to stop persistent service $service_name after $max_attempts attempts"
    return 1
}

print_status "Stopping AITBC Development Environment (Enhanced)..."

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
    
    # Categorize services
    normal_services=""
    persistent_services=""
    
    for service in $aitbc_services; do
        service_name=$(echo "$service" | sed 's/\.service$//')
        if has_auto_restart "$service_name"; then
            persistent_services="$persistent_services $service_name"
        else
            normal_services="$normal_services $service_name"
        fi
    done
    
    # Stop normal services first
    if [ -n "$normal_services" ]; then
        print_status "Stopping normal services..."
        for service_name in $normal_services; do
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
    
    # Stop persistent services with enhanced procedure
    if [ -n "$persistent_services" ]; then
        print_status "Stopping persistent services with enhanced procedure..."
        for service_name in $persistent_services; do
            print_status "Processing persistent service: $service_name"
            
            if is_service_running "$service_name"; then
                if force_stop_service "$service_name"; then
                    print_success "Persistent service $service_name stopped successfully"
                else
                    print_error "Failed to stop persistent service $service_name"
                fi
            else
                print_warning "Persistent service $service_name is already stopped"
            fi
        done
    fi
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
    stopped_count=0
    running_count=0
    
    for service in $aitbc_services; do
        service_name=$(echo "$service" | sed 's/\.service$//')
        if is_service_running "$service_name"; then
            print_error "$service_name: STILL RUNNING"
            running_count=$((running_count + 1))
        else
            print_success "$service_name: STOPPED"
            stopped_count=$((stopped_count + 1))
        fi
    done
    
    # Calculate success rate
    total_services=$((stopped_count + running_count))
    success_rate=$(( (stopped_count * 100) / total_services ))
    
    if [ $running_count -eq 0 ]; then
        print_success "All systemd services stopped successfully (100%)"
    elif [ $success_rate -ge 90 ]; then
        print_success "Most systemd services stopped successfully (${success_rate}%)"
    else
        print_warning "Some systemd services still running (${success_rate}% success)"
    fi
fi

# Check containers
print_status "Container Status:"
stopped_containers=0
running_containers=0

for container in "${containers[@]}"; do
    if incus info "$container" >/dev/null 2>&1; then
        if incus info "$container" | grep -q "Status: RUNNING"; then
            print_error "Container $container: STILL RUNNING"
            running_containers=$((running_containers + 1))
        else
            print_success "Container $container: STOPPED"
            stopped_containers=$((stopped_containers + 1))
        fi
    else
        print_warning "Container $container: NOT FOUND"
    fi
done

# Final summary
total_containers=$((stopped_containers + running_containers))
if [ -n "$aitbc_services" ]; then
    total_services=$(echo "$aitbc_services" | wc -l)
else
    total_services=0
fi

print_success "AITBC Development Environment shutdown complete!"
print_status "Summary:"
echo "  - Incus containers: ${stopped_containers}/${total_containers} stopped"
echo "  - Systemd services: ${stopped_count}/${total_services} stopped"

if [ $running_containers -gt 0 ] || [ $running_count -gt 0 ]; then
    echo ""
    print_warning "Some components are still running:"
    if [ $running_containers -gt 0 ]; then
        echo "  - $running_containers container(s) still running"
    fi
    if [ $running_count -gt 0 ]; then
        echo "  - $running_count service(s) still running (likely persistent services)"
    fi
    echo ""
    print_status "You may need to manually stop persistent services or use:"
    echo "  sudo systemctl kill --signal=SIGKILL <service-name>"
else
    echo ""
    print_success "All components stopped successfully (100%)"
fi

echo ""
print_status "To start again: ./scripts/start-aitbc-dev.sh"
