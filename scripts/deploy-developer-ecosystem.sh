#!/usr/bin/env bash

# AITBC Developer Ecosystem Complete Deployment Orchestration
# Deploys the entire Developer Ecosystem system (contracts + frontend + API)
#
# Usage: ./deploy-developer-ecosystem.sh [environment] [skip-tests]
# Environment: testnet, mainnet
# Skip-Tests: true/false - whether to skip integration tests

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
ENVIRONMENT="${1:-testnet}"
SKIP_TESTS="${2:-false}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 AITBC Developer Ecosystem Complete Deployment"
echo "==============================================="
echo "Environment: $ENVIRONMENT"
echo "Skip Tests: $SKIP_TESTS"
echo "Root Directory: $ROOT_DIR"
echo ""

# Deployment phases
PHASES=("contracts" "frontend" "api" "integration-tests" "monitoring")

# Check prerequisites
check_prerequisites() {
    print_status "Checking deployment prerequisites..."
    
    # Check if required directories exist
    if [[ ! -d "$ROOT_DIR/contracts" ]]; then
        print_error "Contracts directory not found"
        exit 1
    fi
    
    if [[ ! -d "$ROOT_DIR/apps/marketplace-web" ]]; then
        print_error "Frontend directory not found"
        exit 1
    fi
    
    # Check if required scripts exist
    if [[ ! -f "$ROOT_DIR/contracts/scripts/deploy-developer-ecosystem.sh" ]]; then
        print_error "Contract deployment script not found"
        exit 1
    fi
    
    if [[ ! -f "$ROOT_DIR/apps/marketplace-web/scripts/deploy-frontend.sh" ]]; then
        print_error "Frontend deployment script not found"
        exit 1
    fi
    
    # Check SSH connection for frontend deployment
    if ! ssh -o ConnectTimeout=5 aitbc-cascade "echo 'SSH connection successful'" 2>/dev/null; then
        print_warning "Cannot connect to frontend server. Frontend deployment will be skipped."
        SKIP_FRONTEND=true
    else
        SKIP_FRONTEND=false
    fi
    
    print_success "Prerequisites check completed"
}

# Phase 1: Deploy Smart Contracts
deploy_contracts() {
    print_status "Phase 1: Deploying Smart Contracts"
    echo "====================================="
    
    cd "$ROOT_DIR/contracts"
    
    # Run contract deployment
    if ./scripts/deploy-developer-ecosystem.sh "$ENVIRONMENT" "true"; then
        print_success "Smart contracts deployed successfully"
        
        # Copy deployment info to root directory
        if [[ -f "deployed-contracts-$ENVIRONMENT.json" ]]; then
            cp "deployed-contracts-$ENVIRONMENT.json" "$ROOT_DIR/"
            print_success "Contract deployment info copied to root directory"
        fi
    else
        print_error "Smart contract deployment failed"
        return 1
    fi
    
    echo ""
}

# Phase 2: Deploy Frontend
deploy_frontend() {
    if [[ "$SKIP_FRONTEND" == "true" ]]; then
        print_warning "Skipping frontend deployment (SSH connection failed)"
        return 0
    fi
    
    print_status "Phase 2: Deploying Frontend"
    echo "============================"
    
    cd "$ROOT_DIR/apps/marketplace-web"
    
    # Update environment variables with contract addresses
    update_frontend_env
    
    # Build and deploy frontend
    if ./scripts/deploy-frontend.sh "production" "aitbc-cascade"; then
        print_success "Frontend deployed successfully"
    else
        print_error "Frontend deployment failed"
        return 1
    fi
    
    echo ""
}

# Update frontend environment variables
update_frontend_env() {
    print_status "Updating frontend environment variables..."
    
    local deployment_file="$ROOT_DIR/deployed-contracts-$ENVIRONMENT.json"
    
    if [[ ! -f "$deployment_file" ]]; then
        print_error "Contract deployment file not found: $deployment_file"
        return 1
    fi
    
    # Extract contract addresses
    local aitbc_token=$(jq -r '.contracts.AITBCToken.address' "$deployment_file")
    local agent_bounty=$(jq -r '.contracts.AgentBounty.address' "$deployment_file")
    local agent_staking=$(jq -r '.contracts.AgentStaking.address' "$deployment_file")
    local performance_verifier=$(jq -r '.contracts.PerformanceVerifier.address' "$deployment_file")
    local dispute_resolution=$(jq -r '.contracts.DisputeResolution.address' "$deployment_file")
    local escrow_service=$(jq -r '.contracts.EscrowService.address' "$deployment_file")
    
    # Create .env.local file
    cat > .env.local << EOF
# AITBC Developer Ecosystem - Frontend Environment
# Generated on $(date -Iseconds)

# Contract Addresses
VITE_AITBC_TOKEN_ADDRESS=$aitbc_token
VITE_AGENT_BOUNTY_ADDRESS=$agent_bounty
VITE_AGENT_STAKING_ADDRESS=$agent_staking
VITE_PERFORMANCE_VERIFIER_ADDRESS=$performance_verifier
VITE_DISPUTE_RESOLUTION_ADDRESS=$dispute_resolution
VITE_ESCROW_SERVICE_ADDRESS=$escrow_service

# API Configuration
VITE_API_BASE_URL=http://localhost:3001/api/v1
VITE_WS_URL=ws://localhost:3001

# Network Configuration
VITE_NETWORK_NAME=$ENVIRONMENT
VITE_CHAIN_ID=$(get_chain_id "$ENVIRONMENT")

# Application Configuration
VITE_APP_NAME=AITBC Developer Ecosystem
VITE_APP_VERSION=1.0.0
VITE_APP_DESCRIPTION=Developer Ecosystem & DAO Grants System
EOF
    
    print_success "Frontend environment variables updated"
}

# Get chain ID for environment
get_chain_id() {
    case "$1" in
        "localhost"|"hardhat")
            echo "31337"
            ;;
        "sepolia")
            echo "11155111"
            ;;
        "goerli")
            echo "5"
            ;;
        "mainnet")
            echo "1"
            ;;
        *)
            echo "1"
            ;;
    esac
}

# Phase 3: Deploy API Services
deploy_api() {
    print_status "Phase 3: Deploying API Services"
    echo "=================================="
    
    # Check if API deployment script exists
    if [[ -f "$ROOT_DIR/apps/coordinator-api/deploy_services.sh" ]]; then
        cd "$ROOT_DIR/apps/coordinator-api"
        
        if ./deploy_services.sh "$ENVIRONMENT"; then
            print_success "API services deployed successfully"
        else
            print_error "API services deployment failed"
            return 1
        fi
    else
        print_warning "API deployment script not found. Skipping API deployment."
    fi
    
    echo ""
}

# Phase 4: Run Integration Tests
run_integration_tests() {
    if [[ "$SKIP_TESTS" == "true" ]]; then
        print_warning "Skipping integration tests"
        return 0
    fi
    
    print_status "Phase 4: Running Integration Tests"
    echo "====================================="
    
    cd "$ROOT_DIR"
    
    # Update test configuration with deployed contracts
    update_test_config
    
    # Run comprehensive test suite
    if ./tests/run_all_tests.sh; then
        print_success "Integration tests passed"
    else
        print_error "Integration tests failed"
        return 1
    fi
    
    echo ""
}

# Update test configuration
update_test_config() {
    print_status "Updating test configuration..."
    
    local deployment_file="$ROOT_DIR/deployed-contracts-$ENVIRONMENT.json"
    
    if [[ ! -f "$deployment_file" ]]; then
        print_warning "Contract deployment file not found. Using default test configuration."
        return 0
    fi
    
    # Create test configuration
    cat > "$ROOT_DIR/tests/test-config-$ENVIRONMENT.json" << EOF
{
    "environment": "$ENVIRONMENT",
    "contracts": $(cat "$deployment_file"),
    "api": {
        "base_url": "http://localhost:3001/api/v1",
        "timeout": 30000
    },
    "frontend": {
        "base_url": "http://aitbc.bubuit.net/marketplace",
        "timeout": 10000
    }
}
EOF
    
    print_success "Test configuration updated"
}

# Phase 5: Setup Monitoring
setup_monitoring() {
    print_status "Phase 5: Setting up Monitoring"
    echo "==============================="
    
    # Create monitoring configuration
    create_monitoring_config
    
    # Setup health checks
    setup_health_checks
    
    print_success "Monitoring setup completed"
    echo ""
}

# Create monitoring configuration
create_monitoring_config() {
    print_status "Creating monitoring configuration..."
    
    local deployment_file="$ROOT_DIR/deployed-contracts-$ENVIRONMENT.json"
    
    cat > "$ROOT_DIR/monitoring-config-$ENVIRONMENT.json" << EOF
{
    "environment": "$ENVIRONMENT",
    "timestamp": "$(date -Iseconds)",
    "contracts": $(cat "$deployment_file"),
    "monitoring": {
        "enabled": true,
        "interval": 60,
        "endpoints": [
            {
                "name": "Frontend Health",
                "url": "http://aitbc.bubuit.net/marketplace/",
                "method": "GET",
                "expected_status": 200
            },
            {
                "name": "API Health",
                "url": "http://localhost:3001/api/v1/health",
                "method": "GET",
                "expected_status": 200
            }
        ],
        "alerts": {
            "email": "admin@aitbc.dev",
            "slack_webhook": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
        }
    }
}
EOF
    
    print_success "Monitoring configuration created"
}

# Setup health checks
setup_health_checks() {
    print_status "Setting up health checks..."
    
    # Create health check script
    cat > "$ROOT_DIR/scripts/health-check.sh" << 'EOF'
#!/bin/bash

# AITBC Developer Ecosystem Health Check Script

ENVIRONMENT="${1:-testnet}"
CONFIG_FILE="monitoring-config-$ENVIRONMENT.json"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "❌ Monitoring configuration not found: $CONFIG_FILE"
    exit 1
fi

echo "🔍 Running health checks for $ENVIRONMENT..."
echo "=========================================="

# Check frontend
FRONTEND_URL=$(jq -r '.monitoring.endpoints[0].url' "$CONFIG_FILE")
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" || echo "000")

if [[ "$FRONTEND_STATUS" == "200" ]]; then
    echo "✅ Frontend: $FRONTEND_URL (Status: $FRONTEND_STATUS)"
else
    echo "❌ Frontend: $FRONTEND_URL (Status: $FRONTEND_STATUS)"
fi

# Check API
API_URL=$(jq -r '.monitoring.endpoints[1].url' "$CONFIG_FILE")
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL" || echo "000")

if [[ "$API_STATUS" == "200" ]]; then
    echo "✅ API: $API_URL (Status: $API_STATUS)"
else
    echo "❌ API: $API_URL (Status: $API_STATUS)"
fi

echo ""
echo "Health check completed at $(date)"
EOF
    
    chmod +x "$ROOT_DIR/scripts/health-check.sh"
    
    print_success "Health check script created"
}

# Generate deployment report
generate_deployment_report() {
    print_status "Generating deployment report..."
    
    local report_file="$ROOT_DIR/deployment-report-$ENVIRONMENT-$(date +%Y%m%d-%H%M%S).json"
    
    cat > "$report_file" << EOF
{
    "deployment": {
        "environment": "$ENVIRONMENT",
        "timestamp": "$(date -Iseconds)",
        "skip_tests": "$SKIP_TESTS",
        "skip_frontend": "$SKIP_FRONTEND"
    },
    "phases": {
        "contracts": {
            "status": "$CONTRACTS_STATUS",
            "file": "deployed-contracts-$ENVIRONMENT.json"
        },
        "frontend": {
            "status": "$FRONTEND_STATUS",
            "url": "http://aitbc.bubuit.net/marketplace/"
        },
        "api": {
            "status": "$API_STATUS",
            "url": "http://localhost:3001/api/v1"
        },
        "tests": {
            "status": "$TESTS_STATUS",
            "skipped": "$SKIP_TESTS"
        },
        "monitoring": {
            "status": "completed",
            "config": "monitoring-config-$ENVIRONMENT.json"
        }
    },
    "urls": {
        "frontend": "http://aitbc.bubuit.net/marketplace/",
        "api": "http://localhost:3001/api/v1",
        "health_check": "./scripts/health-check.sh $ENVIRONMENT"
    }
}
EOF
    
    print_success "Deployment report saved to $report_file"
}

# Rollback function
rollback() {
    print_warning "Rolling back deployment..."
    
    # Rollback contracts (if needed)
    print_status "Contract rollback not implemented (manual intervention required)"
    
    # Rollback frontend
    if [[ "$SKIP_FRONTEND" != "true" ]]; then
        print_status "Rolling back frontend..."
        ssh aitbc-cascade "cp -r /var/www/aitbc.bubuit.net/marketplace.backup /var/www/aitbc.bubuit.net/marketplace" 2>/dev/null || true
        ssh aitbc-cascade "systemctl reload nginx" 2>/dev/null || true
    fi
    
    print_warning "Rollback completed. Please verify system status."
}

# Main execution
main() {
    print_status "Starting complete Developer Ecosystem deployment..."
    
    # Initialize status variables
    CONTRACTS_STATUS="pending"
    FRONTEND_STATUS="pending"
    API_STATUS="pending"
    TESTS_STATUS="pending"
    
    # Check prerequisites
    check_prerequisites
    
    # Execute deployment phases
    if deploy_contracts; then
        CONTRACTS_STATUS="success"
    else
        CONTRACTS_STATUS="failed"
        print_error "Contract deployment failed. Aborting."
        exit 1
    fi
    
    if deploy_frontend; then
        FRONTEND_STATUS="success"
    else
        FRONTEND_STATUS="failed"
        print_warning "Frontend deployment failed, but continuing..."
    fi
    
    if deploy_api; then
        API_STATUS="success"
    else
        API_STATUS="failed"
        print_warning "API deployment failed, but continuing..."
    fi
    
    if run_integration_tests; then
        TESTS_STATUS="success"
    else
        TESTS_STATUS="failed"
        if [[ "$SKIP_TESTS" != "true" ]]; then
            print_error "Integration tests failed. Deployment may be unstable."
        fi
    fi
    
    # Setup monitoring
    setup_monitoring
    
    # Generate deployment report
    generate_deployment_report
    
    print_success "🎉 Developer Ecosystem deployment completed!"
    echo ""
    echo "📊 Deployment Summary:"
    echo "  Contracts: $CONTRACTS_STATUS"
    echo "  Frontend: $FRONTEND_STATUS"
    echo "  API: $API_STATUS"
    echo "  Tests: $TESTS_STATUS"
    echo ""
    echo "🌐 Application URLs:"
    echo "  Frontend: http://aitbc.bubuit.net/marketplace/"
    echo "  API: http://localhost:3001/api/v1"
    echo ""
    echo "🔧 Management Commands:"
    echo "  Health Check: ./scripts/health-check.sh $ENVIRONMENT"
    echo "  View Report: cat deployment-report-$ENVIRONMENT-*.json"
    echo ""
    echo "📋 Next Steps:"
    echo "  1. Test the application in browser"
    echo "  2. Verify all functionality works"
    echo "  3. Monitor system health"
    echo "  4. Set up automated monitoring"
}

# Handle script interruption
trap 'print_error "Deployment interrupted"; rollback; exit 1' INT TERM

# Run main function
main "$@"
