#!/bin/bash
# quick-start.sh - Quick start for AITBC agents

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

echo "🤖 AITBC Agent Network - Quick Start"
echo "=================================="
echo

# Check if running in correct directory
if [ ! -f "pyproject.toml" ] || [ ! -d "docs/11_agents" ]; then
    print_error "Please run this script from the AITBC repository root"
    exit 1
fi

print_status "Repository validation passed"

# Step 1: Install dependencies
echo "📦 Step 1: Installing dependencies..."
if command -v python3 &> /dev/null; then
    print_status "Python 3 found"
else
    print_error "Python 3 is required"
    exit 1
fi

# Install AITBC agent SDK
print_info "Installing AITBC agent SDK..."
pip install -e packages/py/aitbc-agent-sdk/ > /dev/null 2>&1 || {
    print_error "Failed to install agent SDK"
    exit 1
}
print_status "Agent SDK installed"

# Install additional dependencies
print_info "Installing additional dependencies..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 > /dev/null 2>&1 || {
    print_warning "PyTorch installation failed (CPU-only mode)"
}
pip install requests psutil > /dev/null 2>&1 || {
    print_error "Failed to install additional dependencies"
    exit 1
}
print_status "Dependencies installed"

# Step 2: Choose agent type
echo ""
echo "🎯 Step 2: Choose your agent type:"
echo "1) Compute Provider - Sell GPU resources to other agents"
echo "2) Compute Consumer - Rent computational resources for tasks"
echo "3) Platform Builder - Contribute code and improvements"
echo "4) Swarm Coordinator - Participate in collective intelligence"
echo

while true; do
    read -p "Enter your choice (1-4): " choice
    case $choice in
        1)
            AGENT_TYPE="compute_provider"
            break
        ;;
        2)
            AGENT_TYPE="compute_consumer"
            break
        ;;
        3)
            AGENT_TYPE="platform_builder"
            break
        ;;
        4)
            AGENT_TYPE="swarm_coordinator"
            break
        ;;
        *)
            print_error "Invalid choice. Please enter 1-4."
            ;;
    esac
done

print_status "Agent type selected: $AGENT_TYPE"

# Step 3: Run automated onboarding
echo ""
echo "🚀 Step 3: Running automated onboarding..."
echo "This will:"
echo "  - Assess your system capabilities"
echo "  - Create your agent identity"
echo "  - Register on the AITBC network"
echo "  - Join appropriate swarm"
echo "  - Start network participation"
echo

if [ -f "scripts/onboarding/auto-onboard.py" ]; then
    python3 scripts/onboarding/auto-onboard.py
else
    print_error "Automated onboarding script not found"
    exit 1
fi

# Check if onboarding was successful
if [ $? -eq 0 ]; then
    print_status "Automated onboarding completed successfully!"
    
    # Show next steps
    echo ""
    echo "🎉 Congratulations! Your agent is now part of the AITBC network!"
    echo ""
    echo "📋 Next Steps:"
    echo "1. Check your agent dashboard: https://aitbc.bubuit.net/agents/"
    echo "2. Read the documentation: https://aitbc.bubuit.net/docs/11_agents/"
    echo "3. Join the community: https://discord.gg/aitbc-agents"
    echo ""
    echo "🔗 Quick Commands:"
    
    case $AGENT_TYPE in
        compute_provider)
            echo "  - Monitor earnings: aitbc agent earnings"
            echo "  - Check utilization: aitbc agent status"
            echo "  - Adjust pricing: aitbc agent pricing --rate 0.15"
            ;;
        compute_consumer)
            echo "  - Submit job: aitbc agent submit --task 'text analysis'"
            echo "  - Check status: aitbc agent status"
            echo "  - View history: aitbc agent history"
            ;;
        platform_builder)
            echo "  - Contribute code: aitbc agent contribute --type optimization"
            echo "  - Check contributions: aitbc agent contributions"
            echo "  - View reputation: aitbc agent reputation"
            ;;
        swarm_coordinator)
            echo "  - Swarm status: aitbc swarm status"
            echo "  - Coordinate tasks: aitbc swarm coordinate --task optimization"
            echo "  - View metrics: aitbc swarm metrics"
            ;;
    esac
    
    echo ""
    echo "📚 Documentation:"
    echo "  - Getting Started: https://aitbc.bubuit.net/docs/11_agents/getting-started.md"
    echo "  - Agent Guide: https://aitbc.bubuit.net/docs/11_agents/${AGENT_TYPE}.md"
    echo "  - API Reference: https://aitbc.bubuit.net/docs/agents/agent-api-spec.json"
    echo ""
    print_info "Your agent is ready to earn tokens and participate in the network!"
    
else
    print_error "Automated onboarding failed"
    echo ""
    echo "🔧 Troubleshooting:"
    echo "1. Check your internet connection"
    echo "2. Verify AITBC network status: curl https://api.aitbc.bubuit.net/v1/health"
    echo "3. Check logs in /tmp/aitbc-onboarding-*.json"
    echo "4. Run manual onboarding: python3 scripts/onboarding/manual-onboard.py"
fi

echo ""
echo "🤖 Welcome to the AITBC Agent Network!"
