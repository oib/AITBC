#!/usr/bin/env bash

# AITBC Developer Ecosystem Deployment Script
# Deploys all smart contracts for the Developer Ecosystem & DAO Grants system
#
# Usage: ./deploy-developer-ecosystem.sh [network] [verify]
# Networks: localhost, sepolia, goerli, mainnet
# Verify: true/false - whether to verify contracts on Etherscan

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

# Parse arguments
NETWORK="${1:-localhost}"
VERIFY_CONTRACTS="${2:-false}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTRACTS_DIR="$(dirname "$SCRIPT_DIR")"
ROOT_DIR="$(dirname "$CONTRACTS_DIR")"

echo "🚀 AITBC Developer Ecosystem Deployment"
echo "=========================================="
echo "Network: $NETWORK"
echo "Verify Contracts: $VERIFY_CONTRACTS"
echo "Contracts Directory: $CONTRACTS_DIR"
echo ""

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if hardhat is available
    if ! command -v npx &>/dev/null; then
        print_error "npx not found. Please install Node.js and npm."
        exit 1
    fi
    
    # Check if we're in the contracts directory
    if [[ ! -f "$CONTRACTS_DIR/hardhat.config.js" ]]; then
        print_error "hardhat.config.js not found in $CONTRACTS_DIR"
        exit 1
    fi
    
    # Check if .env file exists for network configuration
    if [[ ! -f "$CONTRACTS_DIR/.env" ]]; then
        print_warning ".env file not found. Creating template..."
        cat > "$CONTRACTS_DIR/.env" << EOF
# Network Configuration
PRIVATE_KEY=your_private_key_here
INFURA_PROJECT_ID=your_infura_project_id
ETHERSCAN_API_KEY=your_etherscan_api_key

# Network URLs
SEPOLIA_URL=https://sepolia.infura.io/v3/\${INFURA_PROJECT_ID}
GOERLI_URL=https://goerli.infura.io/v3/\${INFURA_PROJECT_ID}
MAINNET_URL=https://mainnet.infura.io/v3/\${INFURA_PROJECT_ID}
EOF
        print_warning "Please update .env file with your credentials"
    fi
    
    print_success "Prerequisites check completed"
}

# Compile contracts
compile_contracts() {
    print_status "Compiling contracts..."
    
    cd "$CONTRACTS_DIR"
    
    if npx hardhat compile; then
        print_success "Contracts compiled successfully"
    else
        print_error "Contract compilation failed"
        exit 1
    fi
}

# Deploy contracts
deploy_contracts() {
    print_status "Deploying contracts to $NETWORK..."
    
    cd "$CONTRACTS_DIR"
    
    # Run deployment script
    if npx hardhat run scripts/deploy-developer-ecosystem.js --network "$NETWORK"; then
        print_success "Contracts deployed successfully"
    else
        print_error "Contract deployment failed"
        exit 1
    fi
}

# Verify contracts on Etherscan
verify_contracts() {
    if [[ "$VERIFY_CONTRACTS" != "true" ]]; then
        print_status "Contract verification skipped"
        return
    fi
    
    if [[ "$NETWORK" == "localhost" || "$NETWORK" == "hardhat" ]]; then
        print_status "Skipping verification for local network"
        return
    fi
    
    print_status "Verifying contracts on Etherscan..."
    
    cd "$CONTRACTS_DIR"
    
    # Read deployed addresses from deployment output
    if [[ -f "deployed-contracts-$NETWORK.json" ]]; then
        # Verify each contract
        npx hardhat run scripts/verify-contracts.js --network "$NETWORK"
        print_success "Contract verification completed"
    else
        print_warning "No deployed contracts file found. Skipping verification."
    fi
}

# Run post-deployment tests
run_post_deployment_tests() {
    print_status "Running post-deployment tests..."
    
    cd "$ROOT_DIR"
    
    # Run contract tests
    if npx hardhat test tests/contracts/ --network "$NETWORK"; then
        print_success "Post-deployment tests passed"
    else
        print_error "Post-deployment tests failed"
        exit 1
    fi
}

# Generate deployment report
generate_deployment_report() {
    print_status "Generating deployment report..."
    
    local report_file="$ROOT_DIR/deployment-report-$NETWORK-$(date +%Y%m%d-%H%M%S).json"
    
    cd "$CONTRACTS_DIR"
    
    if [[ -f "deployed-contracts-$NETWORK.json" ]]; then
        cp "deployed-contracts-$NETWORK.json" "$report_file"
        print_success "Deployment report saved to $report_file"
    else
        print_warning "No deployment data found for report generation"
    fi
}

# Main execution
main() {
    print_status "Starting Developer Ecosystem deployment..."
    
    # Check prerequisites
    check_prerequisites
    
    # Compile contracts
    compile_contracts
    
    # Deploy contracts
    deploy_contracts
    
    # Verify contracts (if requested)
    verify_contracts
    
    # Run post-deployment tests
    run_post_deployment_tests
    
    # Generate deployment report
    generate_deployment_report
    
    print_success "🎉 Developer Ecosystem deployment completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Update frontend environment variables with contract addresses"
    echo "2. Deploy the frontend application"
    echo "3. Configure API endpoints"
    echo "4. Run integration tests"
}

# Handle script interruption
trap 'print_error "Deployment interrupted"; exit 1' INT TERM

# Run main function
main "$@"
