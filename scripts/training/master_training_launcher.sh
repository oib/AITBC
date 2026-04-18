#!/bin/bash

# Source training library
source "$(dirname "$0")/training_lib.sh"

# OpenClaw AITBC Training - Master Training Launcher
# Orchestrates all 5 training stages with progress tracking

set -e

# Training configuration
TRAINING_PROGRAM="OpenClaw AITBC Mastery Training"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/var/log/aitbc"
WALLET_NAME="openclaw-trainee"

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
TOTAL_STAGES=5
START_TIME=$(date +%s)

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_DIR/training_master.log"
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
    echo "• Achieve OpenClaw AITBC Master certification"
    echo
    
    echo -e "${BOLD}📋 Training Stages:${NC}"
    echo "1. Foundation - Basic CLI, wallet, and transaction operations"
    echo "2. Intermediate - Advanced blockchain and smart contract operations"
    echo "3. AI Operations - Job submission, resource management, Ollama integration"
    echo "4. Marketplace & Economics - Trading, economic modeling, distributed optimization"
    echo "5. Expert & Automation - Advanced workflows, multi-node coordination, security"
    echo
    
    echo -e "${BOLD}🏗️ Two-Node Architecture:${NC}"
    echo "• Genesis Node (aitbc) - Port 8006 - Primary operations"
    echo "• Follower Node (aitbc1) - Port 8007 - Secondary operations"
    echo "• CLI Tool: $CLI_PATH"
    echo
    
    echo -e "${BOLD}⏱️ Estimated Duration:${NC}"
    echo "• Total: 4 weeks (20 training days)"
    echo "• Per Stage: 2-5 days depending on complexity"
    echo
    
    echo -e "${BOLD}🎓 Certification:${NC}"
    echo "• OpenClaw AITBC Master upon successful completion"
    echo "• Requires 95%+ success rate on final exam"
    echo
    
    echo -e "${BOLD}📊 Prerequisites:${NC}"
    echo "• AITBC CLI accessible at $CLI_PATH"
    echo "• Services running on ports 8000, 8001, 8006, 8007"
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
    local services=("8001:Exchange" "8000:Coordinator" "8006:Genesis-Node" "8006:Follower-Node")
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
        return 0
    else
        print_error "Stage $stage_num failed"
        log "Stage $stage_num failed"
        return 1
    fi
}

# Show training menu
show_menu() {
    echo -e "${BOLD}📋 Training Menu:${NC}"
    echo "1. Run Complete Training Program (All Stages)"
    echo "2. Run Individual Stage"
    echo "3. Check System Readiness"
    echo "4. Review Training Progress"
    echo "5. View Training Logs"
    echo "6. Exit"
    echo
    echo -n "Select option [1-6]: "
    read -r choice
    echo
    
    case $choice in
        1)
            run_complete_training
            ;;
        2)
            run_individual_stage
            ;;
        3)
            check_system_readiness
            ;;
        4)
            review_progress
            ;;
        5)
            view_logs
            ;;
        6)
            print_success "Exiting training program"
            exit 0
            ;;
        *)
            print_error "Invalid option. Please select 1-6."
            show_menu
            ;;
    esac
}

# Run complete training program
run_complete_training() {
    print_header "Complete Training Program"
    
    print_status "Starting complete OpenClaw AITBC Mastery Training..."
    log "Starting complete training program"
    
    local completed_stages=0
    
    for stage in {1..5}; do
        echo
        print_progress $stage "Starting"
        
        if run_stage $stage; then
            ((completed_stages+=1))
            print_success "Stage $stage completed successfully"
            
            # Ask if user wants to continue
            if [ $stage -lt 5 ]; then
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
    echo
    echo -n "Select stage [1-5]: "
    read -r stage_choice
    
    if [[ "$stage_choice" =~ ^[1-5]$ ]]; then
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
    
    # Check completed stages
    local completed=0
    for stage in {1..5}; do
        local log_file="$LOG_DIR/training_stage${stage}.log"
        if [ -f "$log_file" ] && grep -q "completed successfully" "$log_file"; then
            (( completed += 1 )) || true
            echo "✅ Stage $stage: Completed"
        else
            echo "❌ Stage $stage: Not completed"
        fi
    done
    
    local progress=$((completed * 100 / 5))
    echo
    echo -e "${BOLD}Overall Progress: $completed/5 stages ($progress%)${NC}"
    
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
    echo "2. Stage 1: Foundation"
    echo "3. Stage 2: Intermediate"
    echo "4. Stage 3: AI Operations"
    echo "5. Stage 4: Marketplace & Economics"
    echo "6. Stage 5: Expert Operations"
    echo "7. Return to menu"
    echo
    echo -n "Select log to view [1-7]: "
    read -r log_choice
    
    case $log_choice in
        1)
            if [ -f "$LOG_DIR/training_master.log" ]; then
                less "$LOG_DIR/training_master.log"
            else
                print_error "Master log file not found"
            fi
            ;;
        2)
            if [ -f "$LOG_DIR/training_stage1.log" ]; then
                less "$LOG_DIR/training_stage1.log"
            else
                print_error "Stage 1 log file not found"
            fi
            ;;
        3)
            if [ -f "$LOG_DIR/training_stage2.log" ]; then
                less "$LOG_DIR/training_stage2.log"
            else
                print_error "Stage 2 log file not found"
            fi
            ;;
        4)
            if [ -f "$LOG_DIR/training_stage3.log" ]; then
                less "$LOG_DIR/training_stage3.log"
            else
                print_error "Stage 3 log file not found"
            fi
            ;;
        5)
            if [ -f "$LOG_DIR/training_stage4.log" ]; then
                less "$LOG_DIR/training_stage4.log"
            else
                print_error "Stage 4 log file not found"
            fi
            ;;
        6)
            if [ -f "$LOG_DIR/training_stage5.log" ]; then
                less "$LOG_DIR/training_stage5.log"
            else
                print_error "Stage 5 log file not found"
            fi
            ;;
        7)
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
        echo -e "${BOLD}🎓 OpenClaw AITBC Master Status:${NC}"
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
        echo "4. Train other OpenClaw agents"
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
    
    # Start logging
    log "OpenClaw AITBC Mastery Training Program started"
    
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
    read -r start_choice
    
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
        if [[ "$2" =~ ^[1-5]$ ]]; then
            run_stage "$2"
        else
            echo "Usage: $0 --stage [1-5]"
            exit 1
        fi
        ;;
    --complete)
        run_complete_training
        ;;
    --help|-h)
        echo "OpenClaw AITBC Mastery Training Launcher"
        echo
        echo "Usage: $0 [OPTION]"
        echo
        echo "Options:"
        echo "  --overview    Show training overview"
        echo "  --check       Check system readiness"
        echo "  --stage N     Run specific stage (1-5)"
        echo "  --complete    Run complete training program"
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
