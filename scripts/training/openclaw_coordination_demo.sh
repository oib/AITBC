#!/bin/bash
# OpenClaw Agent Coordination Demo Script
# Demonstrates multi-agent communication patterns, distributed decision making, and scalable architectures

set -e

SESSION_ID="coordination-demo-$(date +%s)"
echo "OpenClaw Agent Coordination Demo"
echo "Session ID: $SESSION_ID"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if OpenClaw is available
if ! command -v openclaw &> /dev/null; then
    log_error "OpenClaw not found. Please install OpenClaw 2026.3.24+"
    exit 1
fi

log_info "OpenClaw version: $(openclaw --version)"

# ============================================================================
# Pattern 1: Hierarchical Communication
# ============================================================================
log_info "=== Pattern 1: Hierarchical Communication ==="

log_info "Coordinator broadcasts to Level 2 agents..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "BROADCAST: Execute distributed AI workflow across all Level 2 agents" \
    --thinking high \
    --parameters "broadcast_type:hierarchical,target_level:2"

sleep 2

log_info "Level 2 agents respond to coordinator..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "Response to Coordinator: Ready for AI workflow execution with resource optimization" \
    --thinking medium

openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "Response to Coordinator: Ready for distributed task participation" \
    --thinking medium

openclaw agent --agent AIResourceAgent --session-id $SESSION_ID \
    --message "Response to Coordinator: Ready for resource allocation management" \
    --thinking medium

log_success "Hierarchical communication pattern demonstrated"

# ============================================================================
# Pattern 2: Peer-to-Peer Communication
# ============================================================================
log_info ""
log_info "=== Pattern 2: Peer-to-Peer Communication ==="

log_info "Direct agent-to-agent communication..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "P2P to FollowerAgent: Coordinate resource allocation for AI job batch" \
    --thinking medium

sleep 2

openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "P2P to GenesisAgent: Confirm resource availability and scheduling" \
    --thinking medium

log_success "Peer-to-peer communication pattern demonstrated"

# ============================================================================
# Pattern 3: Consensus-Based Decision Making
# ============================================================================
log_info ""
log_info "=== Pattern 3: Consensus-Based Decision Making ==="

PROPOSAL_ID="resource-strategy-$(date +%s)"

log_info "Coordinator presents proposal..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "VOTE PROPOSAL $PROPOSAL_ID: Implement dynamic GPU allocation with 70% utilization target" \
    --thinking high

sleep 2

log_info "Agents vote on proposal..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "VOTE $PROPOSAL_ID: YES - Dynamic allocation optimizes AI performance" \
    --thinking medium

openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "VOTE $PROPOSAL_ID: YES - Improves resource utilization" \
    --thinking medium

openclaw agent --agent AIResourceAgent --session-id $SESSION_ID \
    --message "VOTE $PROPOSAL_ID: YES - Aligns with optimization goals" \
    --thinking medium

sleep 2

log_info "Coordinator announces decision..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "DECISION: Proposal $PROPOSAL_ID APPROVED (3/3 votes) - Implementing dynamic GPU allocation" \
    --thinking high

log_success "Consensus-based decision making demonstrated"

# ============================================================================
# Pattern 4: Weighted Decision Making
# ============================================================================
log_info ""
log_info "=== Pattern 4: Weighted Decision Making ==="

log_info "Coordinator requests weighted recommendations..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "WEIGHTED DECISION: Select optimal AI model for medical diagnosis pipeline" \
    --thinking high

sleep 2

log_info "Agents provide weighted recommendations..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "RECOMMENDATION: ensemble_model (confidence: 0.9, weight: 3) - Best for accuracy" \
    --thinking high

openclaw agent --agent MultiModalAgent --session-id $SESSION_ID \
    --message "RECOMMENDATION: multimodal_model (confidence: 0.8, weight: 2) - Handles multiple data types" \
    --thinking high

openclaw agent --agent AIResourceAgent --session-id $SESSION_ID \
    --message "RECOMMENDATION: efficient_model (confidence: 0.7, weight: 1) - Best resource utilization" \
    --thinking medium

sleep 2

log_info "Coordinator calculates weighted decision..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "WEIGHTED DECISION: ensemble_model selected (weighted score: 2.7) - Highest confidence-weighted combination" \
    --thinking high

log_success "Weighted decision making demonstrated"

# ============================================================================
# Pattern 5: Microservices Architecture
# ============================================================================
log_info ""
log_info "=== Pattern 5: Microservices Architecture ==="

log_info "Specialized agents with specific responsibilities..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "SERVICE: Processing AI job queue with 5 concurrent jobs" \
    --thinking medium

openclaw agent --agent AIResourceAgent --session-id $SESSION_ID \
    --message "SERVICE: Allocating GPU resources with 85% utilization target" \
    --thinking medium

openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "SERVICE: Monitoring system health with 99.9% uptime target" \
    --thinking low

openclaw agent --agent MultiModalAgent --session-id $SESSION_ID \
    --message "SERVICE: Analyzing performance metrics and optimization opportunities" \
    --thinking medium

sleep 2

log_info "Service orchestration..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "ORCHESTRATION: Coordinating 4 microservices for optimal system performance" \
    --thinking high

log_success "Microservices architecture demonstrated"

# ============================================================================
# Pattern 6: Load Balancing
# ============================================================================
log_info ""
log_info "=== Pattern 6: Load Balancing Architecture ==="

log_info "Coordinator monitors agent loads..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "LOAD BALANCE: Monitoring agent loads and redistributing tasks" \
    --thinking high

sleep 2

log_info "Agents report current load..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "LOAD REPORT: Current load 75% - capacity for 5 more AI jobs" \
    --thinking low

openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "LOAD REPORT: Current load 45% - capacity for 10 more tasks" \
    --thinking low

openclaw agent --agent AIResourceAgent --session-id $SESSION_ID \
    --message "LOAD REPORT: Current load 60% - capacity for resource optimization tasks" \
    --thinking low

sleep 2

log_info "Coordinator redistributes load..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "REDISTRIBUTION: Routing new tasks to FollowerAgent (45% load) for optimal balance" \
    --thinking high

log_success "Load balancing architecture demonstrated"

# ============================================================================
# Pattern 7: Multi-Agent Task Orchestration
# ============================================================================
log_info ""
log_info "=== Pattern 7: Multi-Agent Task Orchestration ==="

log_info "Step 1: Task decomposition..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "ORCHESTRATION: Decomposing complex AI pipeline into 5 subtasks for agent allocation" \
    --thinking high

sleep 2

log_info "Step 2: Task assignment..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "ASSIGNMENT: Task 1->GenesisAgent, Task 2->MultiModalAgent, Task 3->AIResourceAgent, Task 4->FollowerAgent, Task 5->CoordinatorAgent" \
    --thinking high

sleep 2

log_info "Step 3: Parallel execution..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "EXECUTION: Starting assigned task with parallel processing" \
    --thinking medium

openclaw agent --agent MultiModalAgent --session-id $SESSION_ID \
    --message "EXECUTION: Starting assigned task with parallel processing" \
    --thinking medium

openclaw agent --agent AIResourceAgent --session-id $SESSION_ID \
    --message "EXECUTION: Starting assigned task with parallel processing" \
    --thinking medium

openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "EXECUTION: Starting assigned task with parallel processing" \
    --thinking medium

sleep 2

log_info "Step 4: Result aggregation..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "AGGREGATION: Collecting results from all agents for final synthesis" \
    --thinking high

log_success "Multi-agent task orchestration demonstrated"

# ============================================================================
# Performance Metrics
# ============================================================================
log_info ""
log_info "=== Performance Metrics ==="

log_info "Measuring communication latency..."
start_time=$(date +%s.%N)
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "LATENCY TEST: Measuring communication performance" \
    --thinking low
end_time=$(date +%s.%N)
latency=$(echo "$end_time - $start_time" | bc)
log_info "Message latency: ${latency}s"

log_success "Performance metrics collected"

# ============================================================================
# Summary
# ============================================================================
log_info ""
log_info "=== Demo Summary ==="
log_success "All coordination patterns demonstrated successfully:"
log_success "  1. Hierarchical Communication"
log_success "  2. Peer-to-Peer Communication"
log_success "  3. Consensus-Based Decision Making"
log_success "  4. Weighted Decision Making"
log_success "  5. Microservices Architecture"
log_success "  6. Load Balancing Architecture"
log_success "  7. Multi-Agent Task Orchestration"
log_success "  8. Performance Metrics"
log_info ""
log_info "Session ID: $SESSION_ID"
log_info "For detailed patterns and implementation guidelines, see:"
log_info "  .windsurf/workflows/agent-coordination-enhancement.md"
log_info "  .windsurf/workflows/OPENCLAW_MASTER_INDEX.md"
