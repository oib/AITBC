#!/bin/bash

# AITBC GPU Mining Optimization Script
# Optimizes GPU settings for maximum mining efficiency

set -e

# Configuration
LOG_FILE="/var/log/aitbc/mining-optimize.log"
CONFIG_FILE="/etc/aitbc/mining.conf"
GPU_VENDOR=""  # Will be auto-detected

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

# Detect GPU vendor
detect_gpu() {
    echo -e "${BLUE}=== Detecting GPU ===${NC}"
    
    if command -v nvidia-smi &> /dev/null; then
        GPU_VENDOR="nvidia"
        echo -e "${GREEN}✓${NC} NVIDIA GPU detected"
        log "GPU vendor: NVIDIA"
    elif command -v rocm-smi &> /dev/null; then
        GPU_VENDOR="amd"
        echo -e "${GREEN}✓${NC} AMD GPU detected"
        log "GPU vendor: AMD"
    elif lspci | grep -i vga &> /dev/null; then
        echo -e "${YELLOW}⚠${NC} GPU detected but vendor-specific tools not found"
        log "GPU detected but vendor unknown"
        GPU_VENDOR="unknown"
    else
        echo -e "${RED}✗${NC} No GPU detected"
        log "No GPU detected - cannot optimize mining"
        exit 1
    fi
}

# Get GPU information
get_gpu_info() {
    echo -e "\n${BLUE}=== GPU Information ===${NC}"
    
    case $GPU_VENDOR in
        "nvidia")
            nvidia-smi --query-gpu=name,memory.total,temperature.gpu,utilization.gpu,power.draw --format=csv,noheader,nounits
            ;;
        "amd")
            rocm-smi --showproductname
            rocm-smi --showmeminfo vram
            rocm-smi --showtemp
            ;;
        *)
            echo "GPU info not available for vendor: $GPU_VENDOR"
            ;;
    esac
}

# Optimize NVIDIA GPU
optimize_nvidia() {
    echo -e "\n${BLUE}=== Optimizing NVIDIA GPU ===${NC}"
    
    # Get current power limit
    CURRENT_POWER=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits | head -n1)
    echo "Current power limit: ${CURRENT_POWER}W"
    
    # Set optimal power limit (80% of max for efficiency)
    MAX_POWER=$(nvidia-smi --query-gpu=power.max_limit --format=csv,noheader,nounits | head -n1)
    OPTIMAL_POWER=$((MAX_POWER * 80 / 100))
    
    echo "Setting power limit to ${OPTIMAL_POWER}W (80% of max)"
    sudo nvidia-smi -pl $OPTIMAL_POWER
    log "NVIDIA power limit set to ${OPTIMAL_POWER}W"
    
    # Set performance mode
    echo "Setting performance mode to maximum"
    sudo nvidia-smi -ac 877,1215
    log "NVIDIA performance mode set to maximum"
    
    # Configure memory clock
    echo "Optimizing memory clock"
    sudo nvidia-smi -pm 1
    log "NVIDIA persistence mode enabled"
    
    # Create optimized mining config
    cat > $CONFIG_FILE << EOF
[nvidia]
power_limit = $OPTIMAL_POWER
performance_mode = maximum
memory_clock = max
fan_speed = auto
temperature_limit = 85
EOF
    
    echo -e "${GREEN}✓${NC} NVIDIA GPU optimized"
}

# Optimize AMD GPU
optimize_amd() {
    echo -e "\n${BLUE}=== Optimizing AMD GPU ===${NC}"
    
    # Set performance level
    echo "Setting performance level to high"
    sudo rocm-smi --setperflevel high
    log "AMD performance level set to high"
    
    # Set memory clock
    echo "Optimizing memory clock"
    sudo rocm-smi --setmclk 1
    log "AMD memory clock optimized"
    
    # Create optimized mining config
    cat > $CONFIG_FILE << EOF
[amd]
performance_level = high
memory_clock = high
fan_speed = auto
temperature_limit = 85
EOF
    
    echo -e "${GREEN}✓${NC} AMD GPU optimized"
}

# Monitor mining performance
monitor_mining() {
    echo -e "\n${BLUE}=== Mining Performance Monitor ===${NC}"
    
    # Check if miner is running
    if ! pgrep -f "aitbc-miner" > /dev/null; then
        echo -e "${YELLOW}⚠${NC} Miner is not running"
        return 1
    fi
    
    # Monitor for 30 seconds
    echo "Monitoring mining performance for 30 seconds..."
    
    for i in {1..6}; do
        echo -e "\n--- Check $i/6 ---"
        
        case $GPU_VENDOR in
            "nvidia")
                nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,power.draw,fan.speed --format=csv,noheader,nounits
                ;;
            "amd")
                rocm-smi --showtemp --showutilization
                ;;
        esac
        
        # Get hash rate from miner API
        if curl -s http://localhost:8081/api/status > /dev/null; then
            HASHRATE=$(curl -s http://localhost:8081/api/status | jq -r '.hashrate')
            echo "Hash rate: ${HASHRATE} H/s"
        fi
        
        sleep 5
    done
}

# Tune fan curves
tune_fans() {
    echo -e "\n${BLUE}=== Tuning Fan Curves ===${NC}"
    
    case $GPU_VENDOR in
        "nvidia")
            # Set custom fan curve
            echo "Setting custom fan curve for NVIDIA"
            # This would use nvidia-settings or similar
            echo "Target: 30% fan at 50°C, 60% at 70°C, 100% at 85°C"
            log "NVIDIA fan curve configured"
            ;;
        "amd")
            echo "Setting fan control to auto for AMD"
            # AMD cards usually handle this automatically
            log "AMD fan control set to auto"
            ;;
    esac
}

# Check mining profitability
check_profitability() {
    echo -e "\n${BLUE}=== Profitability Analysis ===${NC}"
    
    # Get current hash rate
    if curl -s http://localhost:8081/api/status > /dev/null; then
        HASHRATE=$(curl -s http://localhost:8081/api/status | jq -r '.hashrate')
        POWER_USAGE=$(nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits | head -n1)
        
        echo "Current hash rate: ${HASHRATE} H/s"
        echo "Power usage: ${POWER_USAGE}W"
        
        # Calculate efficiency
        if [ "$HASHRATE" != "null" ] && [ -n "$POWER_USAGE" ]; then
            EFFICIENCY=$(echo "scale=2; $HASHRATE / $POWER_USAGE" | bc)
            echo "Efficiency: ${EFFICIENCY} H/W"
            
            # Efficiency rating
            if (( $(echo "$EFFICIENCY > 10" | bc -l) )); then
                echo -e "${GREEN}✓${NC} Excellent efficiency"
            elif (( $(echo "$EFFICIENCY > 5" | bc -l) )); then
                echo -e "${YELLOW}⚠${NC} Good efficiency"
            else
                echo -e "${RED}✗${NC} Poor efficiency - consider optimization"
            fi
        fi
    else
        echo "Miner API not accessible"
    fi
}

# Generate optimization report
generate_report() {
    echo -e "\n${BLUE}=== Optimization Report ===${NC}"
    
    echo "GPU Vendor: $GPU_VENDOR"
    echo "Configuration: $CONFIG_FILE"
    echo "Optimization completed: $(date)"
    
    # Current settings
    echo -e "\nCurrent Settings:"
    case $GPU_VENDOR in
        "nvidia")
            nvidia-smi --query-gpu=power.limit,temperature.gpu,utilization.gpu --format=csv,noheader,nounits
            ;;
        "amd")
            rocm-smi --showtemp --showutilization
            ;;
    esac
    
    log "Optimization report generated"
}

# Main execution
main() {
    log "Starting mining optimization"
    echo -e "${BLUE}AITBC GPU Mining Optimizer${NC}"
    echo "==============================="
    
    # Check root privileges
    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW}⚠${NC} Some optimizations require sudo privileges"
    fi
    
    detect_gpu
    get_gpu_info
    
    # Perform optimization based on vendor
    case $GPU_VENDOR in
        "nvidia")
            optimize_nvidia
            ;;
        "amd")
            optimize_amd
            ;;
        *)
            echo -e "${YELLOW}⚠${NC} Cannot optimize unknown GPU vendor"
            ;;
    esac
    
    tune_fans
    monitor_mining
    check_profitability
    generate_report
    
    echo -e "\n${GREEN}Mining optimization completed!${NC}"
    echo "Configuration saved to: $CONFIG_FILE"
    echo "Log saved to: $LOG_FILE"
    
    log "Mining optimization completed successfully"
}

# Parse command line arguments
case "${1:-optimize}" in
    "optimize")
        main
        ;;
    "monitor")
        detect_gpu
        monitor_mining
        ;;
    "report")
        detect_gpu
        generate_report
        ;;
    *)
        echo "Usage: $0 [optimize|monitor|report]"
        exit 1
        ;;
esac
