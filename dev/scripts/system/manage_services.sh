#!/bin/bash

# AITBC Service Management Script

case "$1" in
    status)
        echo "=== AITBC Service Status ==="
        for service in aitbc-coordinator-api aitbc-exchange-api aitbc-exchange-frontend aitbc-wallet aitbc-node; do
            status=$(sudo systemctl is-active $service 2>/dev/null || echo "inactive")
            enabled=$(sudo systemctl is-enabled $service 2>/dev/null || echo "disabled")
            echo "$service: $status ($enabled)"
        done
        ;;
    
    start)
        echo "Starting AITBC services..."
        sudo systemctl start aitbc-coordinator-api
        sudo systemctl start aitbc-exchange-api
        sudo systemctl start aitbc-exchange-frontend
        sudo systemctl start aitbc-wallet
        sudo systemctl start aitbc-node
        echo "Done!"
        ;;
    
    stop)
        echo "Stopping AITBC services..."
        sudo systemctl stop aitbc-coordinator-api
        sudo systemctl stop aitbc-exchange-api
        sudo systemctl stop aitbc-exchange-frontend
        sudo systemctl stop aitbc-wallet
        sudo systemctl stop aitbc-node
        echo "Done!"
        ;;
    
    restart)
        echo "Restarting AITBC services..."
        sudo systemctl restart aitbc-coordinator-api
        sudo systemctl restart aitbc-exchange-api
        sudo systemctl restart aitbc-exchange-frontend
        sudo systemctl restart aitbc-wallet
        sudo systemctl restart aitbc-node
        echo "Done!"
        ;;
    
    logs)
        if [ -z "$2" ]; then
            echo "Usage: $0 logs <service-name>"
            echo "Available services: coordinator-api, exchange-api, exchange-frontend, wallet, node"
            exit 1
        fi
        case "$2" in
            coordinator-api) sudo journalctl -u aitbc-coordinator-api -f ;;
            exchange-api) sudo journalctl -u aitbc-exchange-api -f ;;
            exchange-frontend) sudo journalctl -u aitbc-exchange-frontend -f ;;
            wallet) sudo journalctl -u aitbc-wallet -f ;;
            node) sudo journalctl -u aitbc-node -f ;;
            *) echo "Unknown service: $2" ;;
        esac
        ;;
    
    enable)
        echo "Enabling AITBC services to start on boot..."
        sudo systemctl enable aitbc-coordinator-api
        sudo systemctl enable aitbc-exchange-api
        sudo systemctl enable aitbc-exchange-frontend
        sudo systemctl enable aitbc-wallet
        sudo systemctl enable aitbc-node
        echo "Done!"
        ;;
    
    disable)
        echo "Disabling AITBC services from starting on boot..."
        sudo systemctl disable aitbc-coordinator-api
        sudo systemctl disable aitbc-exchange-api
        sudo systemctl disable aitbc-exchange-frontend
        sudo systemctl disable aitbc-wallet
        sudo systemctl disable aitbc-node
        echo "Done!"
        ;;
    
    *)
        echo "Usage: $0 {status|start|stop|restart|logs|enable|disable}"
        echo ""
        echo "Commands:"
        echo "  status  - Show status of all AITBC services"
        echo "  start   - Start all AITBC services"
        echo "  stop    - Stop all AITBC services"
        echo "  restart - Restart all AITBC services"
        echo "  logs    - View logs for a specific service"
        echo "  enable  - Enable services to start on boot"
        echo "  disable - Disable services from starting on boot"
        echo ""
        echo "Examples:"
        echo "  $0 status"
        echo "  $0 logs exchange-api"
        exit 1
        ;;
esac
