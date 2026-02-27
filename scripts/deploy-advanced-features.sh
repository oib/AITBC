#!/usr/bin/env bash

# AITBC Advanced Agent Features Deployment Script
# Deploys cross-chain reputation, agent communication, and advanced learning systems

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

echo "🚀 AITBC Advanced Agent Features Deployment"
echo "=========================================="
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
    print_status "Deploying advanced agent features contracts..."
    
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
            npx hardhat run scripts/deploy-advanced-contracts.js --network localhost
            ;;
        "sepolia"|"goerli")
            print_status "Deploying to $NETWORK..."
            npx hardhat run scripts/deploy-advanced-contracts.js --network $NETWORK
            ;;
        "mainnet")
            print_critical "DEPLOYING TO MAINNET - This will spend real ETH!"
            read -p "Type 'DEPLOY-ADVANCED-TO-MAINNET' to continue: " confirmation
            if [[ "$confirmation" != "DEPLOY-ADVANCED-TO-MAINNET" ]]; then
                print_error "Deployment cancelled"
                exit 1
            fi
            npx hardhat run scripts/deploy-advanced-contracts.js --network mainnet
            ;;
        *)
            print_error "Unsupported network: $NETWORK"
            exit 1
            ;;
    esac
    
    print_success "Advanced contracts deployed"
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
        if npx hardhat run scripts/verify-advanced-contracts.js --network $NETWORK; then
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
    cat > "$ROOT_DIR/apps/coordinator-api/config/advanced_features.json" << EOF
{
    "cross_chain_reputation": {
        "base_score": 1000,
        "success_bonus": 100,
        "failure_penalty": 50,
        "min_stake_amount": 100000000000000000000,
        "max_delegation_ratio": 1.0,
        "sync_cooldown": 3600,
        "supported_chains": {
            "ethereum": 1,
            "polygon": 137,
            "arbitrum": 42161,
            "optimism": 10,
            "bsc": 56,
            "avalanche": 43114,
            "fantom": 250
        },
        "tier_thresholds": {
            "bronze": 4500,
            "silver": 6000,
            "gold": 7500,
            "platinum": 9000,
            "diamond": 9500
        },
        "stake_rewards": {
            "bronze": 0.05,
            "silver": 0.08,
            "gold": 0.12,
            "platinum": 0.18,
            "diamond": 0.25
        }
    },
    "agent_communication": {
        "min_reputation_score": 1000,
        "base_message_price": 0.001,
        "max_message_size": 100000,
        "message_timeout": 86400,
        "channel_timeout": 2592000,
        "encryption_enabled": true,
        "supported_message_types": [
            "text",
            "data",
            "task_request",
            "task_response",
            "collaboration",
            "notification",
            "system",
            "urgent",
            "bulk"
        ],
        "channel_types": [
            "direct",
            "group",
            "broadcast",
            "private"
        ],
        "encryption_types": [
            "aes256",
            "rsa",
            "hybrid",
            "none"
        ]
    },
    "advanced_learning": {
        "max_model_size": 104857600,
        "max_training_time": 3600,
        "default_batch_size": 32,
        "default_learning_rate": 0.001,
        "convergence_threshold": 0.001,
        "early_stopping_patience": 10,
        "meta_learning_algorithms": [
            "MAML",
            "Reptile",
            "Meta-SGD"
        ],
        "federated_algorithms": [
            "FedAvg",
            "FedProx",
            "FedNova"
        ],
        "reinforcement_algorithms": [
            "DQN",
            "PPO",
            "A3C",
            "SAC"
        ],
        "model_types": [
            "task_planning",
            "bidding_strategy",
            "resource_allocation",
            "communication",
            "collaboration",
            "decision_making",
            "prediction",
            "classification"
        ]
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
    if [[ -f "tests/test_advanced_features.py" ]]; then
        python -m pytest tests/test_advanced_features.py -v
    fi
    
    # Run contract tests
    cd "$CONTRACTS_DIR"
    if [[ -f "test/CrossChainReputation.test.js" ]]; then
        npx hardhat test test/CrossChainReputation.test.js
    fi
    
    if [[ -f "test/AgentCommunication.test.js" ]]; then
        npx hardhat test test/AgentCommunication.test.js
    fi
    
    print_success "Integration tests completed"
}

# Generate deployment report
generate_report() {
    print_status "Generating deployment report..."
    
    local report_file="$ROOT_DIR/advanced-features-deployment-report-$(date +%Y%m%d-%H%M%S).json"
    
    cat > "$report_file" << EOF
{
    "deployment": {
        "timestamp": "$(date -Iseconds)",
        "network": "$NETWORK",
        "contracts_verified": "$VERIFY_CONTRACTS",
        "frontend_built": "$([[ "$SKIP_BUILD" == "true" ]] && echo "false" || echo "true")"
    },
    "contracts": {
        "CrossChainReputation": "deployed-contracts-$NETWORK.json",
        "AgentCommunication": "deployed-contracts-$NETWORK.json",
        "AgentCollaboration": "deployed-contracts-$NETWORK.json",
        "AgentLearning": "deployed-contracts-$NETWORK.json",
        "AgentMarketplaceV2": "deployed-contracts-$NETWORK.json",
        "ReputationNFT": "deployed-contracts-$NETWORK.json"
    },
    "services": {
        "cross_chain_reputation": "$SERVICES_DIR/cross_chain_reputation.py",
        "agent_communication": "$SERVICES_DIR/agent_communication.py",
        "agent_collaboration": "$SERVICES_DIR/agent_collaboration.py",
        "advanced_learning": "$SERVICES_DIR/advanced_learning.py",
        "agent_autonomy": "$SERVICES_DIR/agent_autonomy.py",
        "marketplace_v2": "$SERVICES_DIR/marketplace_v2.py"
    },
    "frontend": {
        "cross_chain_reputation": "$FRONTEND_DIR/CrossChainReputation.tsx",
        "agent_communication": "$FRONTEND_DIR/AgentCommunication.tsx",
        "agent_collaboration": "$FRONTEND_DIR/AgentCollaboration.tsx",
        "advanced_learning": "$FRONTEND_DIR/AdvancedLearning.tsx",
        "agent_autonomy": "$FRONTEND_DIR/AgentAutonomy.tsx",
        "marketplace_v2": "$FRONTEND_DIR/MarketplaceV2.tsx"
    },
    "next_steps": [
        "1. Initialize cross-chain reputation for existing agents",
        "2. Set up agent communication channels",
        "3. Configure advanced learning models",
        "4. Test agent collaboration protocols",
        "5. Monitor system performance and optimize"
    ]
}
EOF
    
    print_success "Deployment report saved to $report_file"
}

# Main execution
main() {
    print_critical "🚀 STARTING ADVANCED AGENT FEATURES DEPLOYMENT"
    
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
    
    print_success "🎉 ADVANCED AGENT FEATURES DEPLOYMENT COMPLETED!"
    echo ""
    echo "📊 Deployment Summary:"
    echo "  Network: $NETWORK"
    echo "  Contracts: CrossChainReputation, AgentCommunication, AgentCollaboration, AgentLearning, AgentMarketplaceV2, ReputationNFT"
    echo "  Services: Cross-Chain Reputation, Agent Communication, Advanced Learning, Agent Autonomy"
    echo "  Frontend: Cross-Chain Reputation, Agent Communication, Advanced Learning components"
    echo ""
    echo "🔧 Next Steps:"
    echo "  1. Initialize cross-chain reputation: python -m scripts/init_cross_chain_reputation.py"
    echo "  2. Set up agent communication: python -m scripts/setup_agent_communication.py"
    echo "  3. Configure learning models: python -m scripts/configure_learning_models.py"
    echo "  4. Test agent collaboration: python -m scripts/test_agent_collaboration.py"
    echo "  5. Monitor deployment: cat advanced-features-deployment-report-*.json"
    echo ""
    echo "⚠️  Important Notes:"
    echo "  - Cross-chain reputation requires multi-chain setup"
    echo "  - Agent communication needs proper encryption keys"
    echo "  - Advanced learning requires GPU resources for training"
    echo "  - Agent autonomy needs careful safety measures"
    echo "  - Contract addresses are in deployed-contracts-$NETWORK.json"
    echo "  - Frontend components are integrated into the main marketplace"
}

# Handle script interruption
trap 'print_critical "Deployment interrupted - please check partial deployment"; exit 1' INT TERM

# Run main function
main "$@"
