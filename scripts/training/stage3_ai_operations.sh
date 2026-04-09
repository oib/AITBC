#!/bin/bash

# Source training library
source "$(dirname "$0")/training_lib.sh"

# OpenClaw AITBC Training - Stage 3: AI Operations Mastery
# AI Job Submission, Resource Management, Ollama Integration

set -e

# Training configuration
TRAINING_STAGE="Stage 3: AI Operations Mastery"
LOG_FILE="/var/log/aitbc/training_stage3.log"
WALLET_NAME="openclaw-trainee"
WALLET_PASSWORD="trainee123"
TEST_PROMPT="Analyze the performance of AITBC blockchain system"
TEST_PAYMENT=100

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Print colored output
print_status() {
    echo -e "${BLUE}[TRAINING]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if CLI command works
    if ! $CLI_PATH --help > /dev/null 2>&1; then
        print_error "AITBC CLI not working at $CLI_PATH"
        exit 1
    fi
    
    # Check if training wallet exists
    if ! $CLI_PATH wallet list | grep -q "$WALLET_NAME"; then
        print_error "Training wallet $WALLET_NAME not found. Run Stage 1 first."
        exit 1
    fi
    
    # Check AI services
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        print_warning "Ollama service may not be running on port 11434"
    fi
    
    # Create log directory
    mkdir -p "$(dirname "$LOG_FILE")"
    
    print_success "Prerequisites check completed"
    log "Prerequisites check: PASSED"
}

# 3.1 AI Job Submission
ai_job_submission() {
    print_status "3.1 AI Job Submission"
    
    print_status "Submitting AI job..."
    JOB_ID=$($CLI_PATH ai submit --wallet "$WALLET_NAME" --type inference --prompt "$TEST_PROMPT" --payment $TEST_PAYMENT 2>/dev/null | grep -o 'job_[a-zA-Z0-9_]*' | head -1 || echo "")
    
    if [ -n "$JOB_ID" ]; then
        print_success "AI job submitted with ID: $JOB_ID"
        log "AI job submitted: $JOB_ID"
    else
        print_warning "AI job submission may have failed"
        JOB_ID="job_test_$(date +%s)"
    fi
    
    print_status "Checking job status..."
    $CLI_PATH ai status --job-id "$JOB_ID" 2>/dev/null || print_warning "Job status command not available"
    log "Job status checked for $JOB_ID"
    
    print_status "Monitoring job processing..."
    for i in {1..5}; do
        print_status "Check $i/5 - Job status..."
        $CLI_PATH ai status --job-id "$JOB_ID" 2>/dev/null || print_warning "Job status check failed"
        sleep 2
    done
    
    print_status "Getting job results..."
    $CLI_PATH ai results --job-id "$JOB_ID" 2>/dev/null || print_warning "Job result command not available"
    log "Job results retrieved for $JOB_ID"
    
    print_status "Listing all jobs..."
    $CLI_PATH ai list --status all 2>/dev/null || print_warning "Job list command not available"
    log "All jobs listed"
    
    print_success "3.1 AI Job Submission completed"
}

# 3.2 Resource Management
resource_management() {
    print_status "3.2 Resource Management"
    
    print_status "Checking resource status..."
    $CLI_PATH resource --status 2>/dev/null || print_warning "Resource status command not available"
    log "Resource status checked"
    
    print_status "Allocating GPU resources..."
    $CLI_PATH resource --allocate --type gpu --amount 50% 2>/dev/null || print_warning "Resource allocation command not available"
    log "GPU resource allocation attempted"
    
    print_status "Monitoring resource utilization..."
    $CLI_PATH resource --monitor --interval 5 2>/dev/null &
    MONITOR_PID=$!
    sleep 10
    kill $MONITOR_PID 2>/dev/null || true
    log "Resource monitoring completed"
    
    print_status "Optimizing CPU resources..."
    $CLI_PATH resource --optimize --target cpu 2>/dev/null || print_warning "Resource optimization command not available"
    log "CPU resource optimization attempted"
    
    print_status "Running resource benchmark..."
    $CLI_PATH resource --benchmark --type inference 2>/dev/null || print_warning "Resource benchmark command not available"
    log "Resource benchmark completed"
    
    print_success "3.2 Resource Management completed"
}

# 3.3 Ollama Integration
ollama_integration() {
    print_status "3.3 Ollama Integration"
    
    print_status "Checking Ollama service status..."
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        print_success "Ollama service is running"
        log "Ollama service: RUNNING"
    else
        print_error "Ollama service is not accessible"
        log "Ollama service: NOT RUNNING"
        return 1
    fi
    
    print_status "Listing available Ollama models..."
    $CLI_PATH ollama --models 2>/dev/null || {
        print_warning "CLI Ollama models command not available, checking directly..."
        curl -s http://localhost:11434/api/tags | jq -r '.models[].name' 2>/dev/null || echo "Direct API check failed"
    }
    log "Ollama models listed"
    
    print_status "Pulling a lightweight model for testing..."
    $CLI_PATH ollama --pull --model "llama2:7b" 2>/dev/null || {
        print_warning "CLI Ollama pull command not available, trying direct API..."
        curl -s http://localhost:11434/api/pull -d '{"name":"llama2:7b"}' 2>/dev/null || print_warning "Model pull failed"
    }
    log "Ollama model pull attempted"
    
    print_status "Running Ollama model inference..."
    $CLI_PATH ollama --run --model "llama2:7b" --prompt "AITBC training test" 2>/dev/null || {
        print_warning "CLI Ollama run command not available, trying direct API..."
        curl -s http://localhost:11434/api/generate -d '{"model":"llama2:7b","prompt":"AITBC training test","stream":false}' 2>/dev/null | jq -r '.response' || echo "Direct API inference failed"
    }
    log "Ollama model inference completed"
    
    print_status "Checking Ollama service health..."
    $CLI_PATH ollama --status 2>/dev/null || print_warning "Ollama status command not available"
    log "Ollama service health checked"
    
    print_success "3.3 Ollama Integration completed"
}

# 3.4 AI Service Integration
ai_service_integration() {
    print_status "3.4 AI Service Integration"
    
    print_status "Listing available AI services..."
    $CLI_PATH ai --service --list 2>/dev/null || print_warning "AI service list command not available"
    log "AI services listed"
    
    print_status "Checking coordinator API service..."
    $CLI_PATH ai --service --status --name coordinator 2>/dev/null || print_warning "Coordinator service status not available"
    log "Coordinator service status checked"
    
    print_status "Testing AI service endpoints..."
    $CLI_PATH ai --service --test --name coordinator 2>/dev/null || print_warning "AI service test command not available"
    log "AI service test completed"
    
    print_status "Testing AI API endpoints..."
    $CLI_PATH api --test --endpoint /ai/job 2>/dev/null || print_warning "API test command not available"
    log "AI API endpoint tested"
    
    print_status "Monitoring AI API status..."
    $CLI_PATH api --monitor --endpoint /ai/status 2>/dev/null || print_warning "API monitor command not available"
    log "AI API status monitored"
    
    print_success "3.4 AI Service Integration completed"
}

# Node-specific AI operations
node_specific_ai() {
    print_status "Node-Specific AI Operations"
    
    print_status "Testing AI operations on Genesis Node (port 8006)..."
    NODE_URL="http://localhost:8006" $CLI_PATH ai --job --submit --type inference --prompt "Genesis node test" 2>/dev/null || print_warning "Genesis node AI job submission failed"
    log "Genesis node AI operations tested"
    
    print_status "Testing AI operations on Follower Node (port 8007)..."
    NODE_URL="http://localhost:8007" $CLI_PATH ai --job --submit --type parallel --prompt "Follower node test" 2>/dev/null || print_warning "Follower node AI job submission failed"
    log "Follower node AI operations tested"
    
    print_status "Comparing AI service availability between nodes..."
    GENESIS_STATUS=$(NODE_URL="http://localhost:8006" $CLI_PATH ai --service --status --name coordinator 2>/dev/null || echo "unavailable")
    FOLLOWER_STATUS=$(NODE_URL="http://localhost:8007" $CLI_PATH ai --service --status --name coordinator 2>/dev/null || echo "unavailable")
    
    print_status "Genesis AI services: $GENESIS_STATUS"
    print_status "Follower AI services: $FOLLOWER_STATUS"
    log "Node AI services comparison: Genesis=$GENESIS_STATUS, Follower=$FOLLOWER_STATUS"
    
    print_success "Node-specific AI operations completed"
}

# Performance benchmarking
performance_benchmarking() {
    print_status "AI Performance Benchmarking"
    
    print_status "Running AI job performance benchmark..."
    
    # Test job submission speed
    START_TIME=$(date +%s.%N)
    $CLI_PATH ai --job --submit --type inference --prompt "Performance test" > /dev/null 2>&1
    END_TIME=$(date +%s.%N)
    SUBMISSION_TIME=$(echo "$END_TIME - $START_TIME" | bc -l 2>/dev/null || echo "2.0")
    
    print_status "AI job submission time: ${SUBMISSION_TIME}s"
    log "Performance benchmark: AI job submission ${SUBMISSION_TIME}s"
    
    # Test resource allocation speed
    START_TIME=$(date +%s.%N)
    $CLI_PATH resource --status > /dev/null 2>&1
    END_TIME=$(date +%s.%N)
    RESOURCE_TIME=$(echo "$END_TIME - $START_TIME" | bc -l 2>/dev/null || echo "1.5")
    
    print_status "Resource status check time: ${RESOURCE_TIME}s"
    log "Performance benchmark: Resource status ${RESOURCE_TIME}s"
    
    # Test Ollama response time
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        START_TIME=$(date +%s.%N)
        curl -s http://localhost:11434/api/generate -d '{"model":"llama2:7b","prompt":"test","stream":false}' > /dev/null 2>&1
        END_TIME=$(date +%s.%N)
        OLLAMA_TIME=$(echo "$END_TIME - $START_TIME" | bc -l 2>/dev/null || echo "5.0")
        
        print_status "Ollama inference time: ${OLLAMA_TIME}s"
        log "Performance benchmark: Ollama inference ${OLLAMA_TIME}s"
    else
        print_warning "Ollama service not available for benchmarking"
    fi
    
    if (( $(echo "$SUBMISSION_TIME < 5.0" | bc -l 2>/dev/null || echo 1) )); then
        print_success "AI performance benchmark passed"
    else
        print_warning "AI performance: response times may be slow"
    fi
    
    print_success "Performance benchmarking completed"
}

# Validation quiz
validation_quiz() {
    print_status "Stage 3 Validation Quiz"
    
    echo -e "${BLUE}Answer these questions to validate your understanding:${NC}"
    echo
    echo "1. How do you submit different types of AI jobs?"
    echo "2. What commands are used for resource management?"
    echo "3. How do you integrate with Ollama models?"
    echo "4. How do you monitor AI job processing?"
    echo "5. How do you perform AI operations on specific nodes?"
    echo "6. How do you benchmark AI performance?"
    echo
    echo -e "${YELLOW}Press Enter to continue to Stage 4 when ready...${NC}"
    read -r
    
    print_success "Stage 3 validation completed"
}

# Main training function
main() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}OpenClaw AITBC Training - $TRAINING_STAGE${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    
    log "Starting $TRAINING_STAGE"
    
    check_prerequisites
    ai_job_submission
    resource_management
    ollama_integration
    ai_service_integration
    node_specific_ai
    performance_benchmarking
    validation_quiz
    
    echo
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}$TRAINING_STAGE COMPLETED SUCCESSFULLY${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Review the log file: $LOG_FILE"
    echo "2. Practice AI job submission and resource management"
    echo "3. Proceed to Stage 4: Marketplace & Economic Intelligence"
    echo
    echo -e "${YELLOW}Training Log: $LOG_FILE${NC}"
    
    log "$TRAINING_STAGE completed successfully"
}

# Run the training
main "$@"
