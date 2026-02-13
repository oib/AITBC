#!/bin/bash

# AITBC Development Services Manager
# Starts AITBC services for development and provides cleanup option

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$PROJECT_ROOT/.aitbc_dev_pids"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Services to manage
SERVICES=(
    "aitbc-blockchain-node.service"
    "aitbc-blockchain-rpc.service"
    "aitbc-gpu-miner.service"
    "aitbc-mock-coordinator.service"
)

start_services() {
    echo -e "${BLUE}Starting AITBC development services...${NC}"
    
    # Check if services are already running
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            echo -e "${YELLOW}Warning: $service is already running${NC}"
        fi
    done
    
    # Start all services
    for service in "${SERVICES[@]}"; do
        echo -e "Starting $service..."
        sudo systemctl start "$service"
        
        # Wait a moment and check if it started successfully
        sleep 2
        if systemctl is-active --quiet "$service"; then
            echo -e "${GREEN}✓ $service started successfully${NC}"
            echo "$service" >> "$PID_FILE"
        else
            echo -e "${RED}✗ Failed to start $service${NC}"
            echo -e "${RED}Check logs: sudo journalctl -u $service${NC}"
        fi
    done
    
    echo -e "\n${GREEN}AITBC services started!${NC}"
    echo -e "Use '$0 stop' to stop all services"
    echo -e "Use '$0 status' to check service status"
}

stop_services() {
    echo -e "${BLUE}Stopping AITBC development services...${NC}"
    
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            echo -e "Stopping $service..."
            sudo systemctl stop "$service"
            echo -e "${GREEN}✓ $service stopped${NC}"
        else
            echo -e "${YELLOW}$service was not running${NC}"
        fi
    done
    
    # Clean up PID file
    rm -f "$PID_FILE"
    echo -e "\n${GREEN}All AITBC services stopped${NC}"
}

show_status() {
    echo -e "${BLUE}AITBC Service Status:${NC}\n"
    
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            echo -e "${GREEN}● $service: RUNNING${NC}"
            # Show uptime
            uptime=$(systemctl show "$service" --property=ActiveEnterTimestamp --value)
            echo -e "  Running since: $uptime"
        else
            echo -e "${RED}● $service: STOPPED${NC}"
        fi
    done
    
    # Show recent logs if any services are running
    echo -e "\n${BLUE}Recent logs (last 10 lines each):${NC}"
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            echo -e "\n${YELLOW}--- $service ---${NC}"
            sudo journalctl -u "$service" -n 5 --no-pager | tail -n 5
        fi
    done
}

show_logs() {
    local service="$1"
    if [ -z "$service" ]; then
        echo -e "${BLUE}Following logs for all AITBC services...${NC}"
        sudo journalctl -f -u aitbc-blockchain-node.service -u aitbc-blockchain-rpc.service -u aitbc-gpu-miner.service -u aitbc-mock-coordinator.service
    else
        echo -e "${BLUE}Following logs for $service...${NC}"
        sudo journalctl -f -u "$service"
    fi
}

restart_services() {
    echo -e "${BLUE}Restarting AITBC services...${NC}"
    stop_services
    sleep 3
    start_services
}

cleanup() {
    echo -e "${BLUE}Performing cleanup...${NC}"
    stop_services
    
    # Additional cleanup
    echo -e "Cleaning up temporary files..."
    rm -f "$PROJECT_ROOT/.aitbc_dev_pids"
    
    # Clear any lingering processes (optional)
    echo -e "Checking for lingering processes..."
    pkill -f "aitbc" || echo "No lingering processes found"
    
    echo -e "${GREEN}Cleanup complete${NC}"
}

# Handle script interruption for Ctrl+C only
trap cleanup INT

# Main script logic
case "$1" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$2"
        ;;
    cleanup)
        cleanup
        ;;
    *)
        echo -e "${BLUE}AITBC Development Services Manager${NC}"
        echo -e "\nUsage: $0 {start|stop|restart|status|logs|cleanup}"
        echo -e "\nCommands:"
        echo -e "  start    - Start all AITBC services"
        echo -e "  stop     - Stop all AITBC services"
        echo -e "  restart  - Restart all AITBC services"
        echo -e "  status   - Show service status"
        echo -e "  logs     - Follow logs (optional: specify service name)"
        echo -e "  cleanup  - Stop services and clean up"
        echo -e "\nExamples:"
        echo -e "  $0 start           # Start all services"
        echo -e "  $0 logs            # Follow all logs"
        echo -e "  $0 logs node       # Follow node logs only"
        echo -e "  $0 stop            # Stop all services"
        exit 1
        ;;
esac
