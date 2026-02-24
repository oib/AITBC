#!/bin/bash

# AITBC Enhanced Services Management Script
# Manages all enhanced AITBC services (start, stop, restart, status, logs)

set -e

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
    echo -e "${BLUE}[MANAGE]${NC} $1"
}

# Enhanced services configuration
declare -A SERVICES=(
    ["aitbc-multimodal"]="Multi-Modal Agent Service"
    ["aitbc-gpu-multimodal"]="GPU Multi-Modal Service"
    ["aitbc-modality-optimization"]="Modality Optimization Service"
    ["aitbc-adaptive-learning"]="Adaptive Learning Service"
    ["aitbc-marketplace-enhanced"]="Enhanced Marketplace Service"
    ["aitbc-openclaw-enhanced"]="OpenClaw Enhanced Service"
)

# Show usage
show_usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|enable|disable} [service_name]"
    echo
    echo "Commands:"
    echo "  start     - Start all enhanced services"
    echo "  stop      - Stop all enhanced services"
    echo "  restart   - Restart all enhanced services"
    echo "  status    - Show status of all services"
    echo "  logs      - Show logs for specific service"
    echo "  enable    - Enable services to start on boot"
    echo "  disable   - Disable services from starting on boot"
    echo
    echo "Service names:"
    for service in "${!SERVICES[@]}"; do
        echo "  $service - ${SERVICES[$service]}"
    done
    echo
    echo "Examples:"
    echo "  $0 start                    # Start all services"
    echo "  $0 logs aitbc-multimodal   # Show logs for multi-modal service"
    echo "  $0 status                   # Show all service status"
}

# Start services
start_services() {
    local service_name=$1
    print_header "Starting Enhanced Services..."
    
    if [ -n "$service_name" ]; then
        if [[ -n "${SERVICES[$service_name]}" ]]; then
            print_status "Starting $service_name..."
            sudo systemctl start "$service_name.service"
            print_status "$service_name started successfully!"
        else
            print_error "Unknown service: $service_name"
            return 1
        fi
    else
        for service in "${!SERVICES[@]}"; do
            print_status "Starting $service..."
            sudo systemctl start "$service.service"
        done
        print_status "All enhanced services started!"
    fi
}

# Stop services
stop_services() {
    local service_name=$1
    print_header "Stopping Enhanced Services..."
    
    if [ -n "$service_name" ]; then
        if [[ -n "${SERVICES[$service_name]}" ]]; then
            print_status "Stopping $service_name..."
            sudo systemctl stop "$service_name.service"
            print_status "$service_name stopped successfully!"
        else
            print_error "Unknown service: $service_name"
            return 1
        fi
    else
        for service in "${!SERVICES[@]}"; do
            print_status "Stopping $service..."
            sudo systemctl stop "$service.service"
        done
        print_status "All enhanced services stopped!"
    fi
}

# Restart services
restart_services() {
    local service_name=$1
    print_header "Restarting Enhanced Services..."
    
    if [ -n "$service_name" ]; then
        if [[ -n "${SERVICES[$service_name]}" ]]; then
            print_status "Restarting $service_name..."
            sudo systemctl restart "$service_name.service"
            print_status "$service_name restarted successfully!"
        else
            print_error "Unknown service: $service_name"
            return 1
        fi
    else
        for service in "${!SERVICES[@]}"; do
            print_status "Restarting $service..."
            sudo systemctl restart "$service.service"
        done
        print_status "All enhanced services restarted!"
    fi
}

# Show service status
show_status() {
    local service_name=$1
    print_header "Enhanced Services Status"
    
    if [ -n "$service_name" ]; then
        if [[ -n "${SERVICES[$service_name]}" ]]; then
            echo
            echo "Service: $service_name (${SERVICES[$service_name]})"
            echo "----------------------------------------"
            sudo systemctl status "$service_name.service" --no-pager
        else
            print_error "Unknown service: $service_name"
            return 1
        fi
    else
        echo
        for service in "${!SERVICES[@]}"; do
            echo "Service: $service (${SERVICES[$service]})"
            echo "----------------------------------------"
            if systemctl is-active --quiet "$service.service"; then
                echo -e "Status: ${GREEN}ACTIVE${NC}"
                port=$(echo "$service" | grep -o '[0-9]\+' | head -1)
                if [ -n "$port" ]; then
                    echo "Port: $port"
                fi
            else
                echo -e "Status: ${RED}INACTIVE${NC}"
            fi
            echo
        done
    fi
}

# Show service logs
show_logs() {
    local service_name=$1
    
    if [ -z "$service_name" ]; then
        print_error "Please specify a service name for logs"
        echo "Available services:"
        for service in "${!SERVICES[@]}"; do
            echo "  $service"
        done
        return 1
    fi
    
    if [[ -n "${SERVICES[$service_name]}" ]]; then
        print_header "Logs for $service_name (${SERVICES[$service_name]})"
        echo "Press Ctrl+C to exit logs"
        echo
        sudo journalctl -u "$service_name.service" -f
    else
        print_error "Unknown service: $service_name"
        return 1
    fi
}

# Enable services
enable_services() {
    local service_name=$1
    print_header "Enabling Enhanced Services..."
    
    if [ -n "$service_name" ]; then
        if [[ -n "${SERVICES[$service_name]}" ]]; then
            print_status "Enabling $service_name..."
            sudo systemctl enable "$service_name.service"
            print_status "$service_name enabled for auto-start!"
        else
            print_error "Unknown service: $service_name"
            return 1
        fi
    else
        for service in "${!SERVICES[@]}"; do
            print_status "Enabling $service..."
            sudo systemctl enable "$service.service"
        done
        print_status "All enhanced services enabled for auto-start!"
    fi
}

# Disable services
disable_services() {
    local service_name=$1
    print_header "Disabling Enhanced Services..."
    
    if [ -n "$service_name" ]; then
        if [[ -n "${SERVICES[$service_name]}" ]]; then
            print_status "Disabling $service_name..."
            sudo systemctl disable "$service_name.service"
            print_status "$service_name disabled from auto-start!"
        else
            print_error "Unknown service: $service_name"
            return 1
        fi
    else
        for service in "${!SERVICES[@]}"; do
            print_status "Disabling $service..."
            sudo systemctl disable "$service.service"
        done
        print_status "All enhanced services disabled from auto-start!"
    fi
}

# Main script logic
case "${1:-}" in
    start)
        start_services "$2"
        ;;
    stop)
        stop_services "$2"
        ;;
    restart)
        restart_services "$2"
        ;;
    status)
        show_status "$2"
        ;;
    logs)
        show_logs "$2"
        ;;
    enable)
        enable_services "$2"
        ;;
    disable)
        disable_services "$2"
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
