#!/usr/bin/env bash

# AITBC Decentralized Memory & Storage Deployment Script
# Deploys IPFS/Filecoin integration, smart contracts, and frontend components

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_critical() {
    echo -e "${RED}[CRITICAL]${NC} $1"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
CONTRACTS_DIR="$ROOT_DIR/contracts"
SERVICES_DIR="$ROOT_DIR/apps/coordinator-api/src/app/services"
FRONTEND_DIR="$ROOT_DIR/apps/marketplace-web/src/components"

# Network configuration
NETWORK=${1:-"localhost"}
VERIFY_CONTRACTS=${2:-"true"}
SKIP_BUILD=${3:-"false"}

echo "🚀 AITBC Decentralized Memory & Storage Deployment"
echo "=============================================="
echo "Network: $NETWORK"
echo "Verify Contracts: $VERIFY_CONTRACTS"
echo "Skip Build: $SKIP_BUILD"
echo "Timestamp: $(date -Iseconds)"
echo ""

# Pre-deployment checks
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if Node.js is installed
    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed"
        exit 1
    fi
    
    # Check if Python is installed
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    
    # Check if IPFS is installed (optional)
    if command -v ipfs &> /dev/null; then
        print_success "IPFS is installed"
    else
        print_warning "IPFS is not installed - some features may not work"
    fi
    
    # Check if required directories exist
    if [[ ! -d "$CONTRACTS_DIR" ]]; then
        print_error "Contracts directory not found: $CONTRACTS_DIR"
        exit 1
    fi
    
    if [[ ! -d "$SERVICES_DIR" ]]; then
        print_error "Services directory not found: $SERVICES_DIR"
        exit 1
    fi
    
    print_success "Prerequisites check completed"
}

# Install Python dependencies
install_python_dependencies() {
    print_status "Installing Python dependencies..."
    
    cd "$ROOT_DIR/apps/coordinator-api"
    
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
        print_success "Python dependencies installed"
    else
        print_error "requirements.txt not found"
        exit 1
    fi
}

# Deploy smart contracts
deploy_contracts() {
    print_status "Deploying decentralized memory smart contracts..."
    
    cd "$CONTRACTS_DIR"
    
    # Check if .env file exists
    if [[ ! -f ".env" ]]; then
        print_warning ".env file not found, creating from example..."
        if [[ -f ".env.example" ]]; then
            cp .env.example .env
            print_warning "Please update .env file with your configuration"
        else
            print_error ".env.example file not found"
            exit 1
        fi
    fi
    
    # Compile contracts
    print_status "Compiling contracts..."
    npx hardhat compile
    
    # Deploy contracts based on network
    case $NETWORK in
        "localhost")
            print_status "Deploying to localhost..."
            npx hardhat run scripts/deploy-memory-contracts.js --network localhost
            ;;
        "sepolia"|"goerli")
            print_status "Deploying to $NETWORK..."
            npx hardhat run scripts/deploy-memory-contracts.js --network $NETWORK
            ;;
        "mainnet")
            print_critical "DEPLOYING TO MAINNET - This will spend real ETH!"
            read -p "Type 'DEPLOY-TO-MAINNET' to continue: " confirmation
            if [[ "$confirmation" != "DEPLOY-TO-MAINNET" ]]; then
                print_error "Deployment cancelled"
                exit 1
            fi
            npx hardhat run scripts/deploy-memory-contracts.js --network mainnet
            ;;
        *)
            print_error "Unsupported network: $NETWORK"
            exit 1
            ;;
    esac
    
    print_success "Smart contracts deployed"
}

# Verify contracts
verify_contracts() {
    if [[ "$VERIFY_CONTRACTS" == "true" ]]; then
        print_status "Verifying contracts on Etherscan..."
        
        cd "$CONTRACTS_DIR"
        
        # Wait for block confirmations
        print_status "Waiting for block confirmations..."
        sleep 30
        
        # Run verification
        if npx hardhat run scripts/verify-memory-contracts.js --network $NETWORK; then
            print_success "Contracts verified on Etherscan"
        else
            print_warning "Contract verification failed - manual verification may be required"
        fi
    else
        print_status "Skipping contract verification"
    fi
}

# Build frontend components
build_frontend() {
    if [[ "$SKIP_BUILD" == "true" ]]; then
        print_status "Skipping frontend build"
        return
    fi
    
    print_status "Building frontend components..."
    
    cd "$ROOT_DIR/apps/marketplace-web"
    
    # Install dependencies if needed
    if [[ ! -d "node_modules" ]]; then
        print_status "Installing frontend dependencies..."
        npm install
    fi
    
    # Build the application
    npm run build
    
    print_success "Frontend built successfully"
}

# Deploy frontend
deploy_frontend() {
    print_status "Deploying frontend components..."
    
    # The frontend is already built and deployed as part of the main marketplace
    print_success "Frontend deployment completed"
}

# Setup IPFS node
setup_ipfs() {
    print_status "Setting up IPFS node..."
    
    # Check if IPFS is running
    if command -v ipfs &> /dev/null; then
        if ipfs swarm peers &> /dev/null; then
            print_success "IPFS node is running"
        else
            print_status "Starting IPFS daemon..."
            ipfs daemon --init &
            sleep 5
            print_success "IPFS daemon started"
        fi
    else
        print_warning "IPFS not installed - skipping IPFS setup"
    fi
}

# Run integration tests
run_tests() {
    print_status "Running integration tests..."
    
    cd "$ROOT_DIR"
    
    # Run Python tests
    if [[ -f "tests/test_memory_integration.py" ]]; then
        python -m pytest tests/test_memory_integration.py -v
    fi
    
    # Run contract tests
    cd "$CONTRACTS_DIR"
    if [[ -f "test/AgentMemory.test.js" ]]; then
        npx hardhat test test/AgentMemory.test.js
    fi
    
    if [[ -f "test/KnowledgeGraphMarket.test.js" ]]; then
        npx hardhat test test/KnowledgeGraphMarket.test.js
    fi
    
    print_success "Integration tests completed"
}

# Generate deployment report
generate_report() {
    print_status "Generating deployment report..."
    
    local report_file="$ROOT_DIR/decentralized-memory-deployment-report-$(date +%Y%m%d-%H%M%S).json"
    
    cat > "$report_file" << EOF
{
    "deployment": {
        "timestamp": "$(date -Iseconds)",
        "network": "$NETWORK",
        "contracts_verified": "$VERIFY_CONTRACTS",
        "frontend_built": "$([[ "$SKIP_BUILD" == "true" ]] && echo "false" || echo "true")"
    },
    "contracts": {
        "AgentMemory": "deployed-contracts-$NETWORK.json",
        "KnowledgeGraphMarket": "deployed-contracts-$NETWORK.json",
        "MemoryVerifier": "deployed-contracts-$NETWORK.json"
    },
    "services": {
        "ipfs_storage_service": "$SERVICES_DIR/ipfs_storage_service.py",
        "memory_manager": "$SERVICES_DIR/memory_manager.py",
        "knowledge_graph_market": "$SERVICES_DIR/knowledge_graph_market.py"
    },
    "frontend": {
        "knowledge_marketplace": "$FRONTEND_DIR/KnowledgeMarketplace.tsx",
        "memory_manager": "$FRONTEND_DIR/MemoryManager.tsx"
    },
    "next_steps": [
        "1. Configure IPFS node settings",
        "2. Set up Filecoin storage deals",
        "3. Test memory upload/retrieval functionality",
        "4. Verify knowledge graph marketplace functionality",
        "5. Monitor system performance"
    ]
}
EOF
    
    print_success "Deployment report saved to $report_file"
}

# Main execution
main() {
    print_critical "🚀 STARTING DECENTRALIZED MEMORY DEPLOYMENT"
    
    # Run deployment steps
    check_prerequisites
    install_python_dependencies
    deploy_contracts
    verify_contracts
    build_frontend
    deploy_frontend
    setup_ipfs
    run_tests
    generate_report
    
    print_success "🎉 DECENTRALIZED MEMORY DEPLOYMENT COMPLETED!"
    echo ""
    echo "📊 Deployment Summary:"
    echo "  Network: $NETWORK"
    echo "  Contracts: AgentMemory, KnowledgeGraphMarket, MemoryVerifier"
    echo "  Services: IPFS Storage, Memory Manager, Knowledge Graph Market"
    echo "  Frontend: Knowledge Marketplace, Memory Manager"
    echo ""
    echo "🔧 Next Steps:"
    echo "  1. Configure IPFS node: ipfs config show"
    echo "  2. Test memory functionality: python -m pytest tests/"
    echo "  3. Access frontend: http://localhost:3000/marketplace/"
    echo "  4. Monitor deployment: cat decentralized-memory-deployment-report-*.json"
    echo ""
    echo "⚠️  Important Notes:"
    echo "  - IPFS node should be running for full functionality"
    echo "  - Filecoin storage deals require additional configuration"
    echo "  - Smart contract addresses are in deployed-contracts-$NETWORK.json"
    echo "  - Frontend components are integrated into the main marketplace"
}

# Handle script interruption
trap 'print_critical "Deployment interrupted - please check partial deployment"; exit 1' INT TERM

# Run main function
main "$@"
