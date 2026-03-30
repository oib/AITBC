#!/bin/bash
# OpenClaw AITBC Integration Setup & Health Check
# Field-tested setup and management for OpenClaw + AITBC integration
# Version: 5.0 — Updated 2026-03-30 with AI operations and advanced coordination

set -e

AITBC_DIR="/opt/aitbc"
AITBC_CLI="$AITBC_DIR/aitbc-cli"
DATA_DIR="/var/lib/aitbc/data"
ENV_FILE="/etc/aitbc/.env"
GENESIS_RPC="http://localhost:8006"
FOLLOWER_RPC="http://10.1.223.40:8006"
WALLET_PASSWORD="123"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Prerequisites ──────────────────────────────────────────────
check_prerequisites() {
    log_info "Checking prerequisites..."
    local fail=0

    command -v openclaw &>/dev/null  && log_success "OpenClaw CLI found"   || { log_error "OpenClaw not found"; fail=1; }
    [ -x "$AITBC_CLI" ]             && log_success "AITBC CLI found"       || { log_error "AITBC CLI not found at $AITBC_CLI"; fail=1; }

    if curl -sf http://localhost:8006/health &>/dev/null; then
        log_success "Genesis RPC (localhost:8006) healthy"
    else
        log_warning "Genesis RPC not responding — try: sudo systemctl start aitbc-blockchain-rpc.service"
    fi

    if ssh aitbc1 'curl -sf http://localhost:8006/health' &>/dev/null; then
        log_success "Follower RPC (aitbc1:8006) healthy"
    else
        log_warning "Follower RPC not responding — check aitbc1 services"
    fi

    [ -d "$DATA_DIR/ait-mainnet" ] && log_success "Data dir $DATA_DIR/ait-mainnet exists" || log_warning "Data dir missing"
    [ -f "$ENV_FILE" ]             && log_success "Env file $ENV_FILE exists"              || log_warning "Env file missing"

    [ $fail -eq 0 ] && log_success "Prerequisites satisfied" || { log_error "Prerequisites check failed"; exit 1; }
}

# ── OpenClaw Agent Test ────────────────────────────────────────
test_agent_communication() {
    log_info "Testing OpenClaw agent communication..."
    # IMPORTANT: use --message (long form), not -m
    local SESSION_ID="health-$(date +%s)"
    local GENESIS_HEIGHT
    GENESIS_HEIGHT=$(curl -sf http://localhost:8006/rpc/head | jq -r '.height // "unknown"')

    openclaw agent --agent main --session-id "$SESSION_ID" \
        --message "AITBC integration health check. Genesis height: $GENESIS_HEIGHT. Report status." \
        --thinking low \
    && log_success "Agent communication working" \
    || log_warning "Agent communication failed (non-fatal)"
}

# ── Blockchain Status ──────────────────────────────────────────
show_status() {
    log_info "=== OpenClaw AITBC Integration Status ==="

    echo ""
    echo "OpenClaw:"
    openclaw --version 2>/dev/null || echo "  (not available)"

    echo ""
    echo "Genesis Node (aitbc):"
    curl -sf http://localhost:8006/rpc/head | jq '{height, hash: .hash[0:18], timestamp}' 2>/dev/null \
        || echo "  RPC not responding"

    echo ""
    echo "Follower Node (aitbc1):"
    ssh aitbc1 'curl -sf http://localhost:8006/rpc/head' 2>/dev/null | jq '{height, hash: .hash[0:18], timestamp}' \
        || echo "  RPC not responding"

    echo ""
    echo "Wallets (aitbc):"
    cd "$AITBC_DIR" && source venv/bin/activate && ./aitbc-cli list 2>/dev/null || echo "  CLI error"

    echo ""
    echo "Wallets (aitbc1):"
    ssh aitbc1 "cd $AITBC_DIR && source venv/bin/activate && ./aitbc-cli list" 2>/dev/null || echo "  CLI error"

    echo ""
    echo "Services (aitbc):"
    systemctl is-active aitbc-blockchain-node.service 2>/dev/null | sed 's/^/  node: /'
    systemctl is-active aitbc-blockchain-rpc.service  2>/dev/null | sed 's/^/  rpc:  /'

    echo ""
    echo "Services (aitbc1):"
    ssh aitbc1 'systemctl is-active aitbc-blockchain-node.service' 2>/dev/null | sed 's/^/  node: /'
    ssh aitbc1 'systemctl is-active aitbc-blockchain-rpc.service'  2>/dev/null | sed 's/^/  rpc:  /'

    echo ""
    echo "Data Directory:"
    ls -lh "$DATA_DIR/ait-mainnet/" 2>/dev/null | head -5 || echo "  not found"
}

# ── Run Integration Test ───────────────────────────────────────
run_integration_test() {
    log_info "Running integration test..."

    local pass=0 total=0

    # Test 1: RPC health
    total=$((total+1))
    curl -sf http://localhost:8006/health &>/dev/null && { log_success "RPC health OK"; pass=$((pass+1)); } || log_error "RPC health FAIL"

    # Test 2: CLI works
    total=$((total+1))
    cd "$AITBC_DIR" && source venv/bin/activate && ./aitbc-cli list &>/dev/null && { log_success "CLI OK"; pass=$((pass+1)); } || log_error "CLI FAIL"

    # Test 3: Cross-node SSH
    total=$((total+1))
    ssh aitbc1 'echo ok' &>/dev/null && { log_success "SSH to aitbc1 OK"; pass=$((pass+1)); } || log_error "SSH FAIL"

    # Test 4: Agent communication
    total=$((total+1))
    openclaw agent --agent main --message "ping" --thinking minimal &>/dev/null && { log_success "Agent OK"; pass=$((pass+1)); } || log_warning "Agent FAIL (non-fatal)"

    echo ""
    log_info "Results: $pass/$total passed"
}

# ── Main ───────────────────────────────────────────────────────
main() {
    case "${1:-status}" in
        setup)
            check_prerequisites
            test_agent_communication
            show_status
            log_success "Setup verification complete"
            ;;
        test)
            run_integration_test
            ;;
        status)
            show_status
            ;;
        ai-setup)
            setup_ai_operations
            ;;
        ai-test)
            test_ai_operations
            ;;
        comprehensive)
            show_comprehensive_status
            ;;
        help)
            echo "Usage: $0 {setup|test|status|ai-setup|ai-test|comprehensive|help}"
            echo "  setup        — Verify prerequisites and test agent communication"
            echo "  test         — Run integration tests"
            echo "  status       — Show current multi-node status"
            echo "  ai-setup     — Setup AI operations and agents"
            echo "  ai-test      — Test AI operations functionality"
            echo "  comprehensive — Show comprehensive status including AI operations"
            echo "  help         — Show this help"
            ;;
        *)
            log_error "Unknown command: $1"
            main help
            exit 1
            ;;
    esac
}

# ── AI Operations Setup ───────────────────────────────────────────
setup_ai_operations() {
    log_info "Setting up AI operations..."
    
    cd "$AITBC_DIR"
    source venv/bin/activate
    
    # Create AI inference agent
    log_info "Creating AI inference agent..."
    if ./aitbc-cli agent create --name "ai-inference-worker" \
        --description "Specialized agent for AI inference tasks" \
        --verification full; then
        log_success "AI inference agent created"
    else
        log_warning "AI inference agent creation failed"
    fi
    
    # Allocate GPU resources
    log_info "Allocating GPU resources..."
    if ./aitbc-cli resource allocate --agent-id "ai-inference-worker" \
        --gpu 1 --memory 8192 --duration 3600; then
        log_success "GPU resources allocated"
    else
        log_warning "GPU resource allocation failed"
    fi
    
    # Create AI service marketplace listing
    log_info "Creating AI marketplace listing..."
    if ./aitbc-cli marketplace --action create \
        --name "AI Image Generation" \
        --type ai-inference \
        --price 50 \
        --wallet genesis-ops \
        --description "Generate high-quality images from text prompts"; then
        log_success "AI marketplace listing created"
    else
        log_warning "AI marketplace listing creation failed"
    fi
    
    # Setup follower AI operations
    log_info "Setting up follower AI operations..."
    if ssh aitbc1 "cd $AITBC_DIR && source venv/bin/activate && \
        ./aitbc-cli agent create --name 'ai-training-agent' \
        --description 'Specialized agent for AI model training' \
        --verification full && \
        ./aitbc-cli resource allocate --agent-id 'ai-training-agent' \
        --cpu 4 --memory 16384 --duration 7200"; then
        log_success "Follower AI operations setup completed"
    else
        log_warning "Follower AI operations setup failed"
    fi
    
    log_success "AI operations setup completed"
}

# ── AI Operations Test ──────────────────────────────────────────────
test_ai_operations() {
    log_info "Testing AI operations..."
    
    cd "$AITBC_DIR"
    source venv/bin/activate
    
    # Test AI job submission
    log_info "Testing AI job submission..."
    if ./aitbc-cli ai-submit --wallet genesis-ops \
        --type inference \
        --prompt "Test image generation" \
        --payment 10; then
        log_success "AI job submission test passed"
    else
        log_warning "AI job submission test failed"
    fi
    
    # Test smart contract messaging
    log_info "Testing smart contract messaging..."
    TOPIC_ID=$(curl -s -X POST "$GENESIS_RPC/rpc/messaging/topics/create" \
        -H "Content-Type: application/json" \
        -d '{"agent_id": "test-agent", "agent_address": "ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871", "title": "Test Topic", "description": "Test coordination"}' | \
        jq -r '.topic_id // "error"')
    
    if [ "$TOPIC_ID" != "error" ] && [ -n "$TOPIC_ID" ]; then
        log_success "Smart contract messaging test passed - Topic: $TOPIC_ID"
    else
        log_warning "Smart contract messaging test failed"
    fi
    
    log_success "AI operations testing completed"
}

# ── Comprehensive Status ───────────────────────────────────────────
show_comprehensive_status() {
    log_info "Comprehensive AITBC + OpenClaw + AI Operations Status"
    echo ""
    
    # Basic status
    show_multi_node_status
    echo ""
    
    # AI operations status
    log_info "AI Operations Status:"
    cd "$AITBC_DIR"
    source venv/bin/activate
    
    # Check AI agents
    AI_AGENTS=$(./aitbc-cli agent list 2>/dev/null | grep -c "agent_" || echo "0")
    echo "  AI Agents Created: $AI_AGENTS"
    
    # Check resource allocation
    if ./aitbc-cli resource status &>/dev/null; then
        echo "  Resource Management: Operational"
    else
        echo "  Resource Management: Not operational"
    fi
    
    # Check marketplace
    if ./aitbc-cli marketplace --action list &>/dev/null; then
        echo "  AI Marketplace: Operational"
    else
        echo "  AI Marketplace: Not operational"
    fi
    
    # Check smart contract messaging
    if curl -s "$GENESIS_RPC/rpc/messaging/topics" &>/dev/null; then
        TOPICS_COUNT=$(curl -s "$GENESIS_RPC/rpc/messaging/topics" | jq '.total_topics // 0' 2>/dev/null || echo "0")
        echo "  Smart Contract Messaging: Operational ($TOPICS_COUNT topics)"
    else
        echo "  Smart Contract Messaging: Not operational"
    fi
    
    echo ""
    log_info "Health Check:"
    if [ -f /tmp/aitbc1_heartbeat.py ]; then
        python3 /tmp/aitbc1_heartbeat.py
    else
        log_warning "Heartbeat script not found"
    fi
}

        ai-setup)
            setup_ai_operations
            ;;
        ai-test)
            test_ai_operations
            ;;
        comprehensive)
            show_comprehensive_status
            ;;
        help)
            echo "Usage: $0 {setup|test|status|ai-setup|ai-test|comprehensive|help}"
            echo "  setup        — Verify prerequisites and test agent communication"
            echo "  test         — Run integration tests"
            echo "  status       — Show current multi-node status"
            echo "  ai-setup     — Setup AI operations and agents"
            echo "  ai-test      — Test AI operations functionality"
            echo "  comprehensive — Show comprehensive status including AI operations"
            echo "  help         — Show this help"
            ;;
        *)
            log_error "Unknown command: $1"
            main help
            exit 1
            ;;
    esac
}

main "$@"
