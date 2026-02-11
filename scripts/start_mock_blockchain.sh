#!/bin/bash
# Start mock blockchain nodes for testing
# This script sets up the required mock servers on ports 8081 and 8082

set -e

echo "🚀 Starting Mock Blockchain Nodes for Testing"
echo "============================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check if required ports are available
check_port() {
    local port=$1
    if curl -s "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
        print_warning "Port $port is already in use"
        return 1
    fi
    return 0
}

# Stop any existing mock servers
stop_existing_servers() {
    print_status "Stopping existing mock servers..."
    pkill -f "mock_blockchain_node.py" 2>/dev/null || true
    sleep 1
}

# Start mock servers
start_mock_servers() {
    print_status "Starting mock blockchain node on port 8081..."
    cd "$(dirname "$0")/.."
    python3 tests/mock_blockchain_node.py 8081 > /tmp/mock_node_8081.log 2>&1 &
    local pid1=$!
    
    print_status "Starting mock blockchain node on port 8082..."
    python3 tests/mock_blockchain_node.py 8082 > /tmp/mock_node_8082.log 2>&1 &
    local pid2=$!
    
    # Wait for servers to start
    sleep 2
    
    # Verify servers are running
    if curl -s "http://127.0.0.1:8081/health" >/dev/null 2>&1 && \
       curl -s "http://127.0.0.1:8082/health" >/dev/null 2>&1; then
        print_status "✅ Mock blockchain nodes are running!"
        echo ""
        echo "Node 1: http://127.0.0.1:8082"
        echo "Node 2: http://127.0.0.1:8081"
        echo ""
        echo "To run tests:"
        echo "  python -m pytest tests/test_blockchain_nodes.py -v"
        echo ""
        echo "To stop servers:"
        echo "  pkill -f 'mock_blockchain_node.py'"
        echo ""
        echo "Log files:"
        echo "  Node 1: /tmp/mock_node_8082.log"
        echo "  Node 2: /tmp/mock_node_8081.log"
    else
        print_warning "❌ Failed to start mock servers"
        echo "Check log files:"
        echo "  Node 1: /tmp/mock_node_8082.log"
        echo "  Node 2: /tmp/mock_node_8081.log"
        exit 1
    fi
}

# Main execution
main() {
    stop_existing_servers
    start_mock_servers
}

# Run main function
main "$@"
