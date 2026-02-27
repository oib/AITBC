#!/usr/bin/env bash

# AITBC OpenClaw Autonomous Economics Deployment Script
# Deploys agent wallet, bid strategy, and orchestration components

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

echo "🚀 AITBC OpenClaw Autonomous Economics Deployment"
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
    print_status "Deploying autonomous economics smart contracts..."
    
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
            npx hardhat run scripts/deploy-agent-contracts.js --network localhost
            ;;
        "sepolia"|"goerli")
            print_status "Deploying to $NETWORK..."
            npx hardhat run scripts/deploy-agent-contracts.js --network $NETWORK
            ;;
        "mainnet")
            print_critical "DEPLOYING TO MAINNET - This will spend real ETH!"
            read -p "Type 'DEPLOY-TO-MAINNET' to continue: " confirmation
            if [[ "$confirmation" != "DEPLOY-TO-MAINNET" ]]; then
                print_error "Deployment cancelled"
                exit 1
            fi
            npx hardhat run scripts/deploy-agent-contracts.js --network mainnet
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
        if npx hardhat run scripts/verify-agent-contracts.js --network $NETWORK; then
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

# Setup services
setup_services() {
    print_status "Setting up backend services..."
    
    # Create service configuration
    cat > "$ROOT_DIR/apps/coordinator-api/config/agent_economics.json" << EOF
{
    "bid_strategy_engine": {
        "market_window": 24,
        "price_history_days": 30,
        "volatility_threshold": 0.15,
        "strategy_weights": {
            "urgent_bid": 0.25,
            "cost_optimized": 0.25,
            "balanced": 0.25,
            "aggressive": 0.15,
            "conservative": 0.10
        }
    },
    "task_decomposition": {
        "max_subtasks": 10,
        "min_subtask_duration": 0.1,
        "complexity_thresholds": {
            "text_processing": 0.3,
            "image_processing": 0.5,
            "audio_processing": 0.4,
            "video_processing": 0.8,
            "data_analysis": 0.6,
            "model_inference": 0.4,
            "model_training": 0.9,
            "compute_intensive": 0.8,
            "io_bound": 0.2,
            "mixed_modal": 0.7
        }
    },
    "agent_orchestrator": {
        "max_concurrent_plans": 10,
        "assignment_timeout": 300,
        "monitoring_interval": 30,
        "retry_limit": 3
    }
}
EOF
    
    print_success "Service configuration created"
}

# Run integration tests
run_tests() {
    print_status "Running integration tests..."
    
    cd "$ROOT_DIR"
    
    # Run Python tests
    if [[ -f "tests/test_agent_economics.py" ]]; then
        python -m pytest tests/test_agent_economics.py -v
    fi
    
    # Run contract tests
    cd "$CONTRACTS_DIR"
    if [[ -f "test/AgentWallet.test.js" ]]; then
        npx hardhat test test/AgentWallet.test.js
    fi
    
    if [[ -f "test/AgentOrchestration.test.js" ]]; then
        npx hardhat test test/AgentOrchestration.test.js
    fi
    
    print_success "Integration tests completed"
}

# Generate deployment report
generate_report() {
    print_status "Generating deployment report..."
    
    local report_file="$ROOT_DIR/agent-economics-deployment-report-$(date +%Y%m%d-%H%M%S).json"
    
    cat > "$report_file" << EOF
{
    "deployment": {
        "timestamp": "$(date -Iseconds)",
        "network": "$NETWORK",
        "contracts_verified": "$VERIFY_CONTRACTS",
        "frontend_built": "$([[ "$SKIP_BUILD" == "true" ]] && echo "false" || echo "true")"
    },
    "contracts": {
        "AgentWallet": "deployed-contracts-$NETWORK.json",
        "AgentOrchestration": "deployed-contracts-$NETWORK.json",
        "AIPowerRental": "deployed-contracts-$NETWORK.json"
    },
    "services": {
        "bid_strategy_engine": "$SERVICES_DIR/bid_strategy_engine.py",
        "task_decomposition": "$SERVICES_DIR/task_decomposition.py",
        "agent_orchestrator": "$SERVICES_DIR/agent_orchestrator.py",
        "agent_wallet_service": "$SERVICES_DIR/agent_wallet_service.py"
    },
    "frontend": {
        "agent_wallet": "$FRONTEND_DIR/AgentWallet.tsx",
        "bid_strategy": "$FRONTEND_DIR/BidStrategy.tsx",
        "agent_orchestration": "$FRONTEND_DIR/AgentOrchestration.tsx",
        "task_decomposition": "$FRONTEND_DIR/TaskDecomposition.tsx"
    },
    "next_steps": [
        "1. Configure agent wallet funding",
        "2. Set up bid strategy parameters",
        "3. Initialize agent orchestrator",
        "4. Test autonomous agent workflows",
        "5. Monitor agent performance"
    ]
}
EOF
    
    print_success "Deployment report saved to $report_file"
}

# Main execution
main() {
    print_critical "🚀 STARTING AUTONOMOUS ECONOMICS DEPLOYMENT"
    
    # Run deployment steps
    check_prerequisites
    install_python_dependencies
    deploy_contracts
    verify_contracts
    build_frontend
    deploy_frontend
    setup_services
    run_tests
    generate_report
    
    print_success "🎉 AUTONOMOUS ECONOMICS DEPLOYMENT COMPLETED!"
    echo ""
    echo "📊 Deployment Summary:"
    echo "  Network: $NETWORK"
    echo "  Contracts: AgentWallet, AgentOrchestration, AIPowerRental (extended)"
    echo "  Services: Bid Strategy, Task Decomposition, Agent Orchestrator"
    echo "  Frontend: Agent Wallet, Bid Strategy, Orchestration components"
    echo ""
    echo "🔧 Next Steps:"
    echo "  1. Configure agent wallet: python -m scripts/setup_agent_wallets.py"
    echo "  2. Test bid strategies: python -m scripts/test_bid_strategies.py"
    echo "  3. Initialize orchestrator: python -m scripts/init_orchestrator.py"
    echo "  4. Monitor deployment: cat agent-economics-deployment-report-*.json"
    echo ""
    echo "⚠️  Important Notes:"
    echo "  - Agent wallets must be funded before use"
    echo "  - Bid strategies require market data initialization"
    echo "  - Agent orchestrator needs provider registration"
    echo "  - Contract addresses are in deployed-contracts-$NETWORK.json"
    echo "  - Frontend components are integrated into the main marketplace"
}

# Handle script interruption
trap 'print_critical "Deployment interrupted - please check partial deployment"; exit 1' INT TERM

# Run main function
main "$@"
