#!/bin/bash
# AITBC Service Management Script - No sudo required

case "${1:-help}" in
    "start")
        echo "Starting AITBC services..."
        sudo systemctl start aitbc-coordinator-api.service
        sudo systemctl start aitbc-blockchain-node.service
        sudo systemctl start aitbc-blockchain-rpc.service
        echo "Services started"
        ;;
    "stop")
        echo "Stopping AITBC services..."
        sudo systemctl stop aitbc-coordinator-api.service
        sudo systemctl stop aitbc-blockchain-node.service
        sudo systemctl stop aitbc-blockchain-rpc.service
        echo "Services stopped"
        ;;
    "restart")
        echo "Restarting AITBC services..."
        sudo systemctl restart aitbc-coordinator-api.service
        sudo systemctl restart aitbc-blockchain-node.service
        sudo systemctl restart aitbc-blockchain-rpc.service
        echo "Services restarted"
        ;;
    "status")
        echo "=== AITBC Services Status ==="
        sudo systemctl status aitbc-coordinator-api.service --no-pager
        sudo systemctl status aitbc-blockchain-node.service --no-pager
        sudo systemctl status aitbc-blockchain-rpc.service --no-pager
        ;;
    "logs")
        echo "=== AITBC Service Logs ==="
        sudo journalctl -u aitbc-coordinator-api.service -f
        ;;
    "help"|*)
        echo "AITBC Service Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|help}"
        echo ""
        echo "Commands:"
        echo "  start   - Start all AITBC services"
        echo "  stop    - Stop all AITBC services"
        echo "  restart - Restart all AITBC services"
        echo "  status  - Show service status"
        echo "  logs    - Follow service logs"
        echo "  help    - Show this help message"
        ;;
esac
