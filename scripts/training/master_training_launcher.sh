#!/bin/bash

# Source training library
source "$(dirname "$0")/training_lib.sh"

# hermes AITBC Training - Master Training Launcher
# Orchestrates all 5 training stages with progress tracking

set -e

# Training configuration
TRAINING_PROGRAM="hermes AITBC Mastery Training"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WALLET_NAME="hermes-trainee"

# Initialize logging for master launcher
CURRENT_LOG=$(init_logging "training_master")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Progress tracking
CURRENT_STAGE=0
TOTAL_STAGES=10
START_TIME=$(date +%s)
PROGRESS_FILE="$SCRIPT_DIR/.training_progress"
STATE_DIR="$SCRIPT_DIR/.training_state"
CERT_DIR="$STATE_DIR/certificates"

# Skill update flag (default: disabled)
ENABLE_SKILL_UPDATE="${ENABLE_SKILL_UPDATE:-false}"

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee "$CURRENT_LOG"
}

# Print colored output
print_header() {
    echo -e "${BOLD}${BLUE}========================================${NC}"
    echo -e "${BOLD}${BLUE}$1${NC}"
    echo -e "${BOLD}${BLUE}========================================${NC}"
}

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

print_progress() {
    local stage=$1
    local status=$2
    local progress=$((stage * 100 / TOTAL_STAGES))
    echo -e "${CYAN}[PROGRESS]${NC} Stage $stage/$TOTAL_STAGES ($progress%) - $status"
}

# Show training overview
show_overview() {
    clear
    print_header "$TRAINING_PROGRAM"
    
    echo -e "${BOLD}🎯 Training Objectives:${NC}"
    echo "• Master AITBC CLI operations on both nodes (aitbc & aitbc1)"
    echo "• Progress from beginner to expert level operations"
    echo "• Achieve hermes AITBC Master certification"
    echo
    
    echo -e "${BOLD}📋 Training Stages:${NC}"
    echo "0. Environment Setup - Genesis wallet validation, node connectivity"
    echo "1. Foundation - Basic CLI, wallet, and transaction operations"
    echo "2. Operations Mastery - Wallet operations, blockchain, mining, network"
    echo "3. AI Operations - Job submission, resource management, Ollama integration"
    echo "4. Marketplace & Economics - Trading, economic modeling, distributed optimization"
    echo "5. Expert Operations - Advanced workflows, multi-node coordination, security"
    echo "6. Agent Identity SDK - Agent registration, authentication, SDK usage"
    echo "7. Cross-Node Training - Multi-chain operations, distributed consensus"
    echo "8. Advanced Agent Specialization - Bounty, portfolio, knowledge graph, ZK proofs"
    echo "9. Multi-Chain Architecture - Island setup, gossip sync, multi-chain validator"
    echo
    
    echo -e "${BOLD}🏗️ Two-Node Architecture:${NC}"
    echo "• Genesis Node (aitbc) - Port 8006 - Primary operations"
    echo "• Follower Node (aitbc1) - Port 8006 - Secondary operations"
    echo "• CLI Tool: $CLI_PATH"
    echo
    
    echo -e "${BOLD}⏱️ Estimated Duration:${NC}"
    echo "• Total: 4 weeks (20 training days)"
    echo "• Per Stage: 2-5 days depending on complexity"
    echo
    
    echo -e "${BOLD}🎓 Certification:${NC}"
    echo "• hermes AITBC Master upon successful completion"
    echo "• Requires 95%+ success rate on final exam"
    echo
    
    echo -e "${BOLD}📊 Prerequisites:${NC}"
    echo "• AITBC CLI accessible at $CLI_PATH"
    echo "• Services running on ports 8001 (Exchange), 9001 (Agent-Coordinator), 8006 (Blockchain RPC)"
    echo "• Basic computer skills and command-line familiarity"
    echo
}

# Check system readiness
check_system_readiness() {
    print_status "Checking system readiness..."
    
    local issues=0
    
    # Check CLI availability
    if [ ! -f "$CLI_PATH" ]; then
        print_error "AITBC CLI not found at $CLI_PATH"
        (( issues += 1 )) || true
    else
        print_success "AITBC CLI found"
    fi
    
    # Check service availability
    local services=("8001:Exchange" "9001:Agent-Coordinator" "8006:Genesis-Node" "8006:Follower-Node")
    for service in "${services[@]}"; do
        local port=$(echo "$service" | cut -d: -f1)
        local name=$(echo "$service" | cut -d: -f2)
        
        if curl -s "http://localhost:$port/health" > /dev/null 2>&1 || 
           curl -s "http://localhost:$port" > /dev/null 2>&1; then
            print_success "$name service (port $port) is accessible"
        else
            print_warning "$name service (port $port) may not be running"
            (( issues += 1 )) || true
        fi
    done
    
    # Check Ollama service
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        print_success "Ollama service is running"
    else
        print_warning "Ollama service may not be running (needed for Stage 3)"
        (( issues += 1 )) || true
    fi
    
    # Check log directory
    if [ ! -d "$LOG_DIR" ]; then
        print_status "Creating log directory..."
        mkdir -p "$LOG_DIR"
    fi
    
    # Check training scripts
    if [ ! -d "$SCRIPT_DIR" ]; then
        print_error "Training scripts directory not found: $SCRIPT_DIR"
        (( issues += 1 )) || true
    fi
    
    if [ $issues -eq 0 ]; then
        print_success "System readiness check passed"
        return 0
    else
        print_warning "System readiness check found $issues potential issues"
        return 1
    fi
}

# Run individual stage
run_stage() {
    local stage_num=$1
    local stage_script="$SCRIPT_DIR/stage${stage_num}_*.sh"
    
    print_progress $stage_num "Starting"
    
    # Find the stage script
    local script_file=$(ls $stage_script 2>/dev/null | head -1)
    if [ ! -f "$script_file" ]; then
        print_error "Stage $stage_num script not found"
        return 1
    fi
    
    print_status "Running Stage $stage_num: $(basename "$script_file" .sh | sed 's/stage[0-9]_//')"
    
    # Make script executable
    chmod +x "$script_file"
    
    # Run the stage script
    if bash "$script_file"; then
        print_progress $stage_num "Completed successfully"
        log "Stage $stage_num completed successfully"
        
        # Generate certificate
        mkdir -p "$CERT_DIR"
        generate_certificate $stage_num
        display_badge $stage_num
        
        # Capture learnings for skill update
        local stage_name=$(get_stage_name $stage_num)
        capture_learnings $stage_num "$stage_name" "$ENABLE_SKILL_UPDATE"
        
        return 0
    else
        print_error "Stage $stage_num failed"
        log "Stage $stage_num failed"
        return 1
    fi
}

# Load progress from file
load_progress() {
    if [ -f "$PROGRESS_FILE" ]; then
        source "$PROGRESS_FILE"
    else
        COMPLETED_STAGES=()
    fi
}

# Save progress to file
save_progress() {
    local completed_stages_str=$(
        for stage in "${COMPLETED_STAGES[@]}"; do
            echo -n "$stage "
        done
    )
    echo "COMPLETED_STAGES=($completed_stages_str)" > "$PROGRESS_FILE"
    echo "LAST_UPDATE=$(date +%s)" >> "$PROGRESS_FILE"
}

# Reset training state
reset_training_state() {
    print_header "Reset Training State"
    
    echo -e "${YELLOW}⚠️  This will:${NC}"
    echo "• Clear all stage progress"
    echo "• Remove sandbox state directory"
    echo "• Remove all certificates"
    echo "• Reset progress tracking"
    echo
    echo -n "Are you sure you want to reset? [yes/NO]: "
    read -r confirm
    
    if [[ "$confirm" != "yes" ]]; then
        print_status "Reset cancelled"
        return 0
    fi
    
    print_status "Resetting training state..."
    
    # Clear progress file
    if [ -f "$PROGRESS_FILE" ]; then
        rm "$PROGRESS_FILE"
        print_success "Progress file cleared"
    fi
    
    # Remove state directory
    if [ -d "$STATE_DIR" ]; then
        rm -rf "$STATE_DIR"
        print_success "State directory cleared"
    fi
    
    # Recreate state directory
    mkdir -p "$STATE_DIR"
    mkdir -p "$CERT_DIR"
    
    log "Training state reset"
    print_success "Training state reset successfully"
}

# Check prerequisites using validation script
check_prerequisites() {
    local stage_num=$1
    local stage_name="stage${stage_num}_*"
    
    # Run prerequisite validation
    if [ -f "$SCRIPT_DIR/generate_prerequisite_checks.py" ]; then
        print_status "Checking prerequisites for Stage $stage_num..."
        if python3 "$SCRIPT_DIR/generate_prerequisite_checks.py" "$SCRIPT_DIR/../docs/agent-training" 2>/dev/null; then
            print_success "Prerequisites validated"
            return 0
        else
            print_warning "Prerequisite validation failed"
            return 1
        fi
    else
        print_warning "Prerequisite check script not found, skipping validation"
        return 0
    fi
}

# Get stage name
get_stage_name() {
    local stage_num=$1
    case $stage_num in
        0) echo "Environment Setup" ;;
        1) echo "Foundation" ;;
        2) echo "Operations Mastery" ;;
        3) echo "AI Operations" ;;
        4) echo "Marketplace & Economics" ;;
        5) echo "Expert Operations" ;;
        6) echo "Agent Identity SDK" ;;
        7) echo "Cross-Node Training" ;;
        8) echo "Advanced Agent Specialization" ;;
        9) echo "Multi-Chain Architecture" ;;
        *) echo "Unknown Stage" ;;
    esac
}

# Generate stage certificate
generate_certificate() {
    local stage_num=$1
    local stage_name=$(get_stage_name $stage_num)
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local cert_file="$CERT_DIR/stage${stage_num}_certificate.json"
    
    # Create certificate JSON
    cat > "$cert_file" << EOF
{
  "certificate_type": "stage_completion",
  "stage_number": $stage_num,
  "stage_name": "$stage_name",
  "completion_timestamp": "$timestamp",
  "training_program": "$TRAINING_PROGRAM",
  "wallet_name": "$WALLET_NAME",
  "certificate_id": "cert_$(date +%s)_$stage_num",
  "version": "1.0"
}
EOF
    
    log "Certificate generated for Stage $stage_num: $cert_file"
}

# Display ASCII art badge
display_badge() {
    local stage_num=$1
    local stage_name=$(get_stage_name $stage_num)
    
    echo
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║                                                  ║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}           ${CYAN}✨ STAGE COMPLETION ✨${NC}            ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║                                                  ║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}              Stage ${stage_num}: ${BOLD}${YELLOW}$stage_name${NC}            ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║                                                  ║${NC}"
    echo -e "${GREEN}${BOLD}║${NC}            ${BLUE}$(date '+%Y-%m-%d %H:%M:%S')${NC}            ${GREEN}${BOLD}║${NC}"
    echo -e "${GREEN}${BOLD}║                                                  ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
    echo
    echo -e "${BOLD}Certificate saved to:${NC} $CERT_DIR/stage${stage_num}_certificate.json"
    echo
}

# Capture learnings from completed stage for skill update
capture_learnings() {
    local stage_num=$1
    local stage_name=$2
    local enable_skill_update=$3
    local learnings_file="$STATE_DIR/learnings_stage${stage_num}.json"
    
    print_status "Capturing learnings from Stage $stage_num..."
    
    # Check if learnings file exists (generated by stage script)
    if [ ! -f "$learnings_file" ]; then
        print_warning "No learnings file found for Stage $stage_num at $learnings_file"
        return 0
    fi
    
    # Validate learnings JSON structure
    if ! python3 -c "import json; json.load(open('$learnings_file'))" 2>/dev/null; then
        print_error "Learnings file is not valid JSON: $learnings_file"
        return 1
    fi
    
    print_success "Learnings loaded from $learnings_file"
    
    # Trigger skill update if enabled and hermes-tools is available
    if [ "$enable_skill_update" = "true" ]; then
        if command -v hermes-tools &> /dev/null; then
            print_status "Updating AITBC skill with new learnings..."
            
            # Stage 1 creates skill, subsequent stages update it
            local skill_action="update"
            if [ "$stage_num" -eq 1 ]; then
                skill_action="create"
                print_status "Creating AITBC skill (Stage 1)..."
            fi
            
            # Call hermes-tools to update skill
            if hermes-tools skill-manage --skill aitbc-training --action "$skill_action" --update-from-file "$learnings_file" 2>&1; then
                print_success "AITBC skill $skill_action successful"
            else
                print_warning "Skill update failed - learnings saved for manual processing"
            fi
        else
            print_warning "hermes-tools not available - learnings saved for manual skill update"
        fi
    else
        print_status "Skill update disabled (--with-skill-update not set)"
    fi
    
    return 0
}

# View certificates
view_certificates() {
    print_header "Stage Completion Certificates"
    
    # Ensure directory exists
    mkdir -p "$CERT_DIR"
    
    # Debug: Show CERT_DIR
    echo "Certificate directory: $CERT_DIR"
    
    # Check for certificates
    local cert_files=()
    for cert_file in "$CERT_DIR"/stage*_certificate.json; do
        if [ -f "$cert_file" ]; then
            cert_files+=("$cert_file")
        fi
    done
    
    echo "Found ${#cert_files[@]} certificate file(s)"
    
    if [ ${#cert_files[@]} -eq 0 ]; then
        print_warning "No certificates found yet"
        echo "Complete stages to earn certificates"
        echo "Directory contents:"
        ls -la "$CERT_DIR" 2>/dev/null || echo "Directory not accessible"
        return 0
    fi
    
    echo -e "${BOLD}📜 Certificates Earned:${NC}"
    echo
    
    local cert_count=0
    for cert_file in "${cert_files[@]}"; do
        if [ -f "$cert_file" ]; then
            ((cert_count++))
            local stage_num=$(echo "$cert_file" | grep -o 'stage[0-9]' | grep -o '[0-9]')
            local stage_name=$(get_stage_name $stage_num)
            local timestamp=$(python3 -c "import json; print(json.load(open('$cert_file'))['completion_timestamp'])" 2>/dev/null || echo "Unknown")
            
            echo -e "${GREEN}✅${NC} Stage $stage_num: $stage_name"
            echo "   Completed: $timestamp"
            echo "   File: $cert_file"
            echo
        fi
    done
    
    echo -e "${BOLD}Total certificates: $cert_count${NC}"
    
    echo
    echo -n "View certificate details? [1-$cert_count/N]: "
    read -r view_choice || view_choice="N"
    
    if [[ "$view_choice" =~ ^[0-9]+$ ]] && [ "$view_choice" -ge 1 ] && [ "$view_choice" -le "$cert_count" ]; then
        local cert_file="${cert_files[$((view_choice-1))]}"
        if [ -f "$cert_file" ]; then
            echo
            echo -e "${BOLD}Certificate Details:${NC}"
            cat "$cert_file" | python3 -m json.tool 2>/dev/null || cat "$cert_file"
        fi
    fi
}

# Export certificate
export_certificate() {
    print_header "Export Certificate"
    
    if [ ! -d "$CERT_DIR" ] || [ -z "$(ls -A $CERT_DIR)" ]; then
        print_error "No certificates found to export"
        return 1
    fi
    
    echo "Available certificates:"
    local i=1
    for cert_file in "$CERT_DIR"/stage*_certificate.json; do
        if [ -f "$cert_file" ]; then
            local stage_num=$(echo "$cert_file" | grep -o 'stage[0-9]' | grep -o '[0-9]')
            local stage_name=$(get_stage_name $stage_num)
            echo "$i. Stage $stage_num: $stage_name"
            ((i++))
        fi
    done
    
    echo
    echo -n "Select certificate to export [1-$(($i-1))]: "
    read -r export_choice
    
    if [[ "$export_choice" =~ ^[0-9]+$ ]] && [ "$export_choice" -ge 1 ] && [ "$export_choice" -lt "$i" ]; then
        local cert_file=$(ls "$CERT_DIR"/stage*_certificate.json | head -"$export_choice" | tail -1)
        if [ -f "$cert_file" ]; then
            local export_path="$HOME/$(basename $cert_file)"
            cp "$cert_file" "$export_path"
            print_success "Certificate exported to: $export_path"
        fi
    else
        print_error "Invalid selection"
    fi
}

# Show playground menu
show_playground_menu() {
    clear
    print_header "Training Playground"
    
    echo -e "${BOLD}🎮 Playground Mode${NC}"
    echo "Interactive training with prerequisite validation and reset capability"
    echo
    
    # Load progress
    load_progress
    
    echo -e "${BOLD}📊 Progress:${NC}"
    if [ ${#COMPLETED_STAGES[@]} -gt 0 ]; then
        echo "Completed stages: ${COMPLETED_STAGES[*]}"
    else
        echo "No stages completed yet"
    fi
    echo
    
    echo -e "${BOLD}📋 Available Actions:${NC}"
    echo "1. Run Stage with Prerequisites Check"
    echo "2. Run Complete Training (Progressive)"
    echo "3. Reset Training State"
    echo "4. Check Prerequisites for All Stages"
    echo "5. View Progress"
    echo "6. View Certificates"
    echo "7. Export Certificate"
    echo "8. Return to Main Menu"
    echo
    echo -n "Select option [1-8]: "
    read -r choice
    echo
    
    case $choice in
        1)
            playground_run_stage
            ;;
        2)
            playground_run_complete
            ;;
        3)
            reset_training_state
            ;;
        4)
            check_all_prerequisites
            ;;
        5)
            review_progress
            ;;
        6)
            view_certificates
            ;;
        7)
            export_certificate
            ;;
        8)
            show_menu
            ;;
        *)
            print_error "Invalid option. Please select 1-8."
            show_playground_menu
            ;;
    esac
}

# Check prerequisites for all stages
check_all_prerequisites() {
    print_header "Prerequisites Check for All Stages"
    
    if [ -f "$SCRIPT_DIR/generate_prerequisite_checks.py" ]; then
        print_status "Running prerequisite validation..."
        python3 "$SCRIPT_DIR/generate_prerequisite_checks.py" "$SCRIPT_DIR/../docs/agent-training"
    else
        print_error "Prerequisite check script not found"
    fi
}

# Run stage with prerequisite check (playground mode)
playground_run_stage() {
    echo "Available Stages:"
    for i in {0..9}; do
        local stage_name=""
        case $i in
            0) stage_name="Environment Setup" ;;
            1) stage_name="Foundation" ;;
            2) stage_name="Operations Mastery" ;;
            3) stage_name="AI Operations" ;;
            4) stage_name="Marketplace & Economics" ;;
            5) stage_name="Expert Operations" ;;
            6) stage_name="Agent Identity SDK" ;;
            7) stage_name="Cross-Node Training" ;;
            8) stage_name="Advanced Agent Specialization" ;;
            9) stage_name="Multi-Chain Architecture" ;;
        esac
        echo "$i. $stage_name"
    done
    echo
    echo -n "Select stage [0-9]: "
    read -r stage_choice
    
    if [[ "$stage_choice" =~ ^[0-9]$ ]]; then
        echo
        check_prerequisites $stage_choice
        
        if [ $? -eq 0 ]; then
            echo -n "Proceed with Stage $stage_choice? [Y/n]: "
            read -r proceed
            if [[ ! "$proceed" =~ ^[Nn]$ ]]; then
                if run_stage $stage_choice; then
                    # Add to completed stages
                    COMPLETED_STAGES+=("$stage_choice")
                    save_progress
                    print_success "Stage $stage_choice marked as completed"
                fi
            fi
        else
            print_error "Prerequisites not satisfied, cannot proceed"
        fi
    else
        print_error "Invalid stage selection"
    fi
    
    show_playground_menu
}

# Run complete training progressively (playground mode)
playground_run_complete() {
    print_header "Progressive Complete Training"
    
    load_progress
    
    print_status "Starting progressive training from Stage 0..."
    local start_stage=0
    
    # Find first uncompleted stage
    for i in {0..9}; do
        local completed=false
        for stage in "${COMPLETED_STAGES[@]}"; do
            if [ "$stage" == "$i" ]; then
                completed=true
                break
            fi
        done
        if [ "$completed" = false ]; then
            start_stage=$i
            break
        fi
    done
    
    echo "Starting from Stage $start_stage"
    echo
    
    for stage in $(seq $start_stage 9); do
        print_progress $stage "Starting"
        
        check_prerequisites $stage
        if [ $? -ne 0 ]; then
            print_error "Prerequisites not satisfied for Stage $stage"
            break
        fi
        
        if run_stage $stage; then
            COMPLETED_STAGES+=("$stage")
            save_progress
            print_success "Stage $stage completed and saved"
            
            if [ $stage -lt 9 ]; then
                echo
                echo -n "Continue to next stage? [Y/n]: "
                read -r continue_choice
                if [[ "$continue_choice" =~ ^[Nn]$ ]]; then
                    print_status "Training paused by user"
                    break
                fi
            fi
        else
            print_error "Stage $stage failed"
            echo -n "Retry this stage? [Y/n]: "
            read -r retry_choice
            if [[ ! "$retry_choice" =~ ^[Nn]$ ]]; then
                stage=$((stage - 1))
            else
                break
            fi
        fi
    done
    
    show_training_summary ${#COMPLETED_STAGES[@]}
}

# Show training menu
show_menu() {
    echo -e "${BOLD}📋 Training Menu:${NC}"
    echo "1. Run Complete Training Program (All Stages)"
    echo "2. Run Individual Stage"
    echo "3. Training Playground (Interactive with Reset)"
    echo "4. Check System Readiness"
    echo "5. Review Training Progress"
    echo "6. View Training Logs"
    echo "7. View Certificates"
    echo "8. Exit"
    echo
    echo -n "Select option [1-8]: "
    read -r choice || choice=""
    echo
    
    case $choice in
        1)
            run_complete_training
            ;;
        2)
            run_individual_stage
            ;;
        3)
            show_playground_menu
            ;;
        4)
            check_system_readiness
            ;;
        5)
            review_progress
            ;;
        6)
            view_logs
            ;;
        7)
            view_certificates
            ;;
        8)
            print_success "Exiting training program"
            exit 0
            ;;
        *)
            print_error "Invalid option. Please select 1-8."
            show_menu
            ;;
    esac
}

# Run complete training program
run_complete_training() {
    print_header "Complete Training Program"
    
    print_status "Starting complete hermes AITBC Mastery Training..."
    log "Starting complete training program"
    
    local completed_stages=0
    
    for stage in {0..9}; do
        echo
        print_progress $stage "Starting"
        
        if run_stage $stage; then
            ((completed_stages+=1))
            print_success "Stage $stage completed successfully"
            
            # Ask if user wants to continue
            if [ $stage -lt 9 ]; then
                echo
                echo -n "Continue to next stage? [Y/n]: "
                read -r continue_choice
                if [[ "$continue_choice" =~ ^[Nn]$ ]]; then
                    print_status "Training paused by user"
                    break
                fi
            fi
        else
            print_error "Stage $stage failed. Training paused."
            echo -n "Retry this stage? [Y/n]: "
            read -r retry_choice
            if [[ ! "$retry_choice" =~ ^[Nn]$ ]]; then
                stage=$((stage - 1))  # Retry current stage
            else
                break
            fi
        fi
    done
    
    show_training_summary $completed_stages
}

# Run individual stage
run_individual_stage() {
    echo "Available Stages:"
    echo "1. Foundation (Beginner)"
    echo "2. Intermediate Operations"
    echo "3. AI Operations Mastery"
    echo "4. Marketplace & Economics"
    echo "5. Expert Operations & Automation"
    echo "6. hermes Master Agent Development"
    echo "7. Cross-Node Agent Training & Multi-Agent Orchestration"
    echo
    echo -n "Select stage [1-7]: "
    read -r stage_choice
    
    if [[ "$stage_choice" =~ ^[1-7]$ ]]; then
        echo
        run_stage $stage_choice
    else
        print_error "Invalid stage selection"
        show_menu
    fi
}

# Review training progress
review_progress() {
    print_header "Training Progress Review"
    
    echo -e "${BOLD}📊 Training Statistics:${NC}"
    
    # Load progress from file
    load_progress
    
    # Check completed stages from progress file
    if [ ${#COMPLETED_STAGES[@]} -gt 0 ]; then
        echo -e "${BOLD}Completed Stages (from progress file):${NC}"
        for stage in "${COMPLETED_STAGES[@]}"; do
            echo "✅ Stage $stage"
        done
    else
        echo -e "${BOLD}No stages completed yet${NC}"
    fi
    
    echo
    
    # Check log files for additional completion status
    local completed=0
    for stage in {0..9}; do
        local log_file="$LOG_DIR/training_stage${stage}.log"
        if [ -f "$log_file" ] && grep -q "completed successfully" "$log_file"; then
            (( completed += 1 )) || true
            echo "✅ Stage $stage: Log indicates completion"
        else
            echo "❌ Stage $stage: Not completed in logs"
        fi
    done
    
    local progress=$((completed * 100 / 10))
    echo
    echo -e "${BOLD}Overall Progress: $completed/10 stages ($progress%)${NC}"
    
    # Show time tracking
    local elapsed=$(($(date +%s) - START_TIME))
    local hours=$((elapsed / 3600))
    local minutes=$(((elapsed % 3600) / 60))
    
    echo "Time elapsed: ${hours}h ${minutes}m"
    
    # Show recent log entries
    echo
    echo -e "${BOLD}📋 Recent Activity:${NC}"
    if [ -f "$LOG_DIR/training_master.log" ]; then
        tail -10 "$LOG_DIR/training_master.log"
    else
        echo "No training activity recorded yet"
    fi
}

# View training logs
view_logs() {
    print_header "Training Logs"
    
    echo "Available log files:"
    echo "1. Master training log"
    echo "0. Stage 0: Environment Setup"
    echo "1. Stage 1: Foundation"
    echo "2. Stage 2: Operations Mastery"
    echo "3. Stage 3: AI Operations"
    echo "4. Stage 4: Marketplace & Economics"
    echo "5. Stage 5: Expert Operations"
    echo "6. Stage 6: Agent Identity SDK"
    echo "7. Stage 7: Cross-Node Training"
    echo "8. Stage 8: Advanced Agent Specialization"
    echo "9. Stage 9: Multi-Chain Architecture"
    echo "10. Return to menu"
    echo
    echo -n "Select log to view [0-10]: "
    read -r log_choice
    
    case $log_choice in
        1)
            if [ -f "$LOG_DIR/training_master.log" ]; then
                less "$LOG_DIR/training_master.log"
            else
                print_error "Master log file not found"
            fi
            ;;
        0)
            if [ -f "$LOG_DIR/training_stage0.log" ]; then
                less "$LOG_DIR/training_stage0.log"
            else
                print_error "Stage 0 log file not found"
            fi
            ;;
        2)
            if [ -f "$LOG_DIR/training_stage2.log" ]; then
                less "$LOG_DIR/training_stage2.log"
            else
                print_error "Stage 2 log file not found"
            fi
            ;;
        3)
            if [ -f "$LOG_DIR/training_stage3.log" ]; then
                less "$LOG_DIR/training_stage3.log"
            else
                print_error "Stage 3 log file not found"
            fi
            ;;
        4)
            if [ -f "$LOG_DIR/training_stage4.log" ]; then
                less "$LOG_DIR/training_stage4.log"
            else
                print_error "Stage 4 log file not found"
            fi
            ;;
        5)
            if [ -f "$LOG_DIR/training_stage5.log" ]; then
                less "$LOG_DIR/training_stage5.log"
            else
                print_error "Stage 5 log file not found"
            fi
            ;;
        6)
            if [ -f "$LOG_DIR/training_stage6_agent_identity_sdk.log" ]; then
                less "$LOG_DIR/training_stage6_agent_identity_sdk.log"
            else
                print_error "Stage 6 log file not found"
            fi
            ;;
        7)
            if [ -f "$LOG_DIR/training_stage7_cross_node_training.log" ]; then
                less "$LOG_DIR/training_stage7_cross_node_training.log"
            else
                print_error "Stage 7 log file not found"
            fi
            ;;
        8)
            if [ -f "$LOG_DIR/training_stage8_advanced_agent_specialization.log" ]; then
                less "$LOG_DIR/training_stage8_advanced_agent_specialization.log"
            else
                print_error "Stage 8 log file not found"
            fi
            ;;
        9)
            if [ -f "$LOG_DIR/training_stage9_multi_chain_architecture.log" ]; then
                less "$LOG_DIR/training_stage9_multi_chain_architecture.log"
            else
                print_error "Stage 9 log file not found"
            fi
            ;;
        10)
            return
            ;;
        *)
            print_error "Invalid selection"
            ;;
    esac
    
    view_logs
}

# Show training summary
show_training_summary() {
    local completed_stages=$1
    
    echo
    print_header "Training Summary"
    
    local progress=$((completed_stages * 100 / TOTAL_STAGES))
    
    echo -e "${BOLD}🎯 Training Results:${NC}"
    echo "Stages completed: $completed_stages/$TOTAL_STAGES"
    echo "Progress: $progress%"
    
    if [ $completed_stages -eq $TOTAL_STAGES ]; then
        echo -e "${GREEN}🎉 CONGRATULATIONS! TRAINING COMPLETED!${NC}"
        echo
        echo -e "${BOLD}🎓 hermes AITBC Master Status:${NC}"
        echo "✅ All 5 training stages completed"
        echo "✅ Expert-level CLI proficiency achieved"
        echo "✅ Multi-node operations mastered"
        echo "✅ AI operations and automation expertise"
        echo "✅ Ready for production deployment"
        echo
        echo -e "${BOLD}📋 Next Steps:${NC}"
        echo "1. Review all training logs for detailed performance"
        echo "2. Practice advanced operations regularly"
        echo "3. Implement custom automation solutions"
        echo "4. Train other hermes agents"
        echo "5. Monitor and optimize system performance"
    else
        echo -e "${YELLOW}Training In Progress${NC}"
        echo "Stages remaining: $((TOTAL_STAGES - completed_stages))"
        echo "Continue training to achieve mastery status"
    fi
    
    echo
    echo -e "${BOLD}📊 Training Logs:${NC}"
    for stage in $(seq 1 $completed_stages); do
        echo "• Stage $stage: $LOG_DIR/training_stage${stage}.log"
    done
    echo "• Master: $LOG_DIR/training_master.log"
    
    log "Training summary: $completed_stages/$TOTAL_STAGES stages completed ($progress%)"
}

# Main function
main() {
    # Create log directory
    mkdir -p "$LOG_DIR"
    
    # Create state directory
    mkdir -p "$STATE_DIR"
    mkdir -p "$CERT_DIR"
    
    # Start logging
    log "hermes AITBC Mastery Training Program started"
    
    # Show overview
    show_overview
    
    # Check system readiness
    if ! check_system_readiness; then
        echo
        print_warning "Some system checks failed. You may still proceed with training,"
        print_warning "but some features may not work correctly."
        echo
        echo -n "Continue anyway? [Y/n]: "
        read -r continue_choice
        if [[ "$continue_choice" =~ ^[Nn]$ ]]; then
            print_status "Training program exited"
            exit 1
        fi
    fi
    
    echo
    echo -n "Ready to start training? [Y/n]: "
    read -r start_choice || start_choice="y"
    
    if [[ ! "$start_choice" =~ ^[Nn]$ ]]; then
        show_menu
    else
        print_status "Training program exited"
    fi
}

# Handle command line arguments
case "${1:-}" in
        --overview)
            show_overview
            ;;
        --check)
            check_system_readiness
            ;;
        --stage)
            if [[ "$2" =~ ^[0-9]$ ]]; then
                run_stage "$2"
            else
                echo "Usage: $0 --stage [0-9]"
                exit 1
            fi
            ;;
        --complete)
            run_complete_training
            ;;
        --playground)
            show_playground_menu
            ;;
        --with-skill-update)
            ENABLE_SKILL_UPDATE=true
            # Shift and continue to next argument
            shift
            case "${1:-}" in
                --stage)
                    if [[ "$2" =~ ^[0-9]$ ]]; then
                        run_stage "$2"
                    else
                        echo "Usage: $0 --with-skill-update --stage [0-9]"
                        exit 1
                    fi
                    ;;
                --complete)
                    run_complete_training
                    ;;
                "")
                    main
                    ;;
                *)
                    echo "Unknown option: $1"
                    echo "Use --help for usage information"
                    exit 1
                    ;;
            esac
            ;;
        --help|-h)
            echo "hermes AITBC Mastery Training Launcher"
            echo
            echo "Usage: $0 [OPTION]"
            echo
            echo "Options:"
            echo "  --overview    Show training overview"
            echo "  --check       Check system readiness"
            echo "  --stage N     Run specific stage (0-9)"
            echo "  --complete    Run complete training program"
            echo "  --playground  Enter training playground mode"
            echo "  --with-skill-update  Enable skill update via hermes-tools"
            echo "  --help, -h    Show this help message"
            echo
            echo "Without arguments, starts interactive menu"
            ;;
        "")
            main
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
