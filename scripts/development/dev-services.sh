#!/bin/bash
# Enhanced AITBC Service Management for Development

case "${1:-help}" in
    "start")
        echo "🚀 Starting AITBC services..."
        sudo systemctl start aitbc-coordinator-api.service
        sudo systemctl start aitbc-blockchain-node.service
        sudo systemctl start aitbc-blockchain-rpc.service
        echo "✅ Services started"
        ;;
    "stop")
        echo "🛑 Stopping AITBC services..."
        sudo systemctl stop aitbc-coordinator-api.service
        sudo systemctl stop aitbc-blockchain-node.service
        sudo systemctl stop aitbc-blockchain-rpc.service
        echo "✅ Services stopped"
        ;;
    "restart")
        echo "🔄 Restarting AITBC services..."
        sudo systemctl restart aitbc-coordinator-api.service
        sudo systemctl restart aitbc-blockchain-node.service
        sudo systemctl restart aitbc-blockchain-rpc.service
        echo "✅ Services restarted"
        ;;
    "status")
        echo "📊 AITBC Services Status:"
        echo ""
        sudo systemctl status aitbc-coordinator-api.service --no-pager -l
        echo ""
        sudo systemctl status aitbc-blockchain-node.service --no-pager -l
        echo ""
        sudo systemctl status aitbc-blockchain-rpc.service --no-pager -l
        ;;
    "logs")
        echo "📋 AITBC Service Logs (Ctrl+C to exit):"
        sudo journalctl -u aitbc-coordinator-api.service -f
        ;;
    "logs-all")
        echo "📋 All AITBC Logs (Ctrl+C to exit):"
        sudo journalctl -u aitbc-* -f
        ;;
    "test")
        echo "🧪 Testing AITBC services..."
        echo "Testing Coordinator API..."
        curl -s http://localhost:8000/health || echo "❌ Coordinator API not responding"
        echo ""
        echo "Testing Blockchain RPC..."
        curl -s http://localhost:8006/health || echo "❌ Blockchain RPC not responding"
        echo ""
        echo "✅ Service test completed"
        ;;
    "help"|*)
        echo "🛠️  AITBC Development Service Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|logs-all|test|help}"
        echo ""
        echo "Commands:"
        echo "  start     - Start all AITBC services"
        echo "  stop      - Stop all AITBC services"
        echo "  restart   - Restart all AITBC services"
        echo "  status    - Show detailed service status"
        echo "  logs      - Follow coordinator API logs"
        echo "  logs-all  - Follow all AITBC service logs"
        echo "  test      - Test service endpoints"
        echo "  help      - Show this help message"
        ;;
esac
