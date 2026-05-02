# OpenClaw AITBC Training Scripts

Complete training script suite for OpenClaw agents to master AITBC software operations from beginner to expert level.

## 📁 Training Scripts Overview

### 🚀 Master Training Launcher
- **File**: `master_training_launcher.sh`
- **Purpose**: Interactive orchestrator for all training stages
- **Features**: Progress tracking, system readiness checks, stage selection
- **Dependencies**: `training_lib.sh` (common utilities)

### 📚 Individual Stage Scripts

#### **Stage 1: Foundation** (`stage1_foundation.sh`)
- **Duration**: 15-30 minutes (automated)
- **Focus**: Basic CLI operations, wallet management, transactions
- **Dependencies**: `training_lib.sh`
- **Features**: Progress tracking, automatic validation, detailed logging
- **Commands**: CLI version, help, wallet creation, balance checking, basic transactions, service health

#### **Stage 2: Intermediate** (`stage2_intermediate.sh`)
- **Duration**: 20-40 minutes (automated)
- **Focus**: Advanced blockchain operations, smart contracts, networking
- **Dependencies**: `training_lib.sh`, Stage 1 completion
- **Features**: Multi-wallet testing, blockchain mining, contract interaction, network operations

#### **Stage 3: AI Operations** (`stage3_ai_operations.sh`)
- **Duration**: 30-60 minutes (automated)
- **Focus**: AI job submission, resource management, Ollama integration
- **Dependencies**: `training_lib.sh`, Stage 2 completion, Ollama service
- **Features**: AI job monitoring, resource allocation, Ollama model management

#### **Stage 4: Marketplace & Economics** (`stage4_marketplace_economics.sh`)
- **Duration**: 25-45 minutes (automated)
- **Focus**: Trading, economic modeling, distributed optimization
- **Dependencies**: `training_lib.sh`, Stage 3 completion
- **Features**: Marketplace operations, economic intelligence, distributed AI economics, analytics

#### **Stage 5: Expert Operations** (`stage5_expert_automation.sh`)
- **Duration**: 35-70 minutes (automated)
- **Focus**: Automation, multi-node coordination, security, performance optimization
- **Dependencies**: `training_lib.sh`, Stage 4 completion
- **Features**: Advanced automation, multi-node coordination, security audits, certification exam

### 🛠️ Training Library
- **File**: `training_lib.sh`
- **Purpose**: Common utilities and functions shared across all training scripts
- **Features**:
  - Logging with multiple levels (INFO, SUCCESS, ERROR, WARNING, DEBUG)
  - Color-coded output functions
  - Service health checking
  - Performance measurement and benchmarking
  - Node connectivity testing
  - Progress tracking
  - Command retry logic
  - Automatic cleanup and signal handling
  - Validation functions

## 🎯 Usage Instructions

### Quick Start
```bash
# Navigate to training directory
cd /opt/aitbc/scripts/training

# Run the master training launcher (recommended)
./master_training_launcher.sh

# Or run individual stages
./stage1_foundation.sh
./stage2_intermediate.sh
```

### Command Line Options
```bash
# Show training overview
./master_training_launcher.sh --overview

# Check system readiness
./master_training_launcher.sh --check

# Run specific stage
./master_training_launcher.sh --stage 3

# Run complete training program
./master_training_launcher.sh --complete

# Show help
./master_training_launcher.sh --help
```

## 🏗️ Two-Node Architecture Support

All scripts are designed to work with both AITBC nodes:
- **Genesis Node (aitbc)**: Port 8006 - Primary operations
- **Follower Node (aitbc1)**: Port 8006 - Secondary operations

### Node-Specific Operations
Each stage includes node-specific testing using the training library:
```bash
# Genesis node operations
NODE_URL="http://localhost:8006" ./aitbc-cli wallet balance wallet

# Follower node operations  
NODE_URL="http://localhost:8006" ./aitbc-cli wallet balance wallet

# Using training library functions
cli_cmd_node "$GENESIS_NODE" "balance --name $WALLET_NAME"
cli_cmd_node "$FOLLOWER_NODE" "blockchain --info"
```

## 📊 Training Features

### 🎓 Progressive Learning
- **Beginner → Expert**: 5 carefully designed stages
- **Hands-on Practice**: Real CLI commands with live system interaction
- **Performance Metrics**: Response time and success rate tracking via `training_lib.sh`
- **Validation Quizzes**: Knowledge checks at each stage completion
- **Progress Tracking**: Visual progress indicators and detailed logging

### 📈 Progress Tracking
- **Detailed Logging**: Every operation logged with timestamps to `/var/log/aitbc/training_*.log`
- **Success Metrics**: Command success rates and performance via `validate_stage()`
- **Stage Completion**: Automatic progress tracking with `init_progress()` and `update_progress()`
- **Performance Benchmarking**: Built-in timing functions via `measure_time()`
- **Log Analysis**: Structured logs for easy analysis and debugging

### 🔧 System Integration
- **Real Operations**: Uses actual AITBC CLI commands via `cli_cmd()` wrapper
- **Service Health**: Monitors all AITBC services via `check_all_services()`
- **Error Handling**: Graceful failure recovery with retry logic via `benchmark_with_retry()`
- **Resource Management**: CPU, memory, GPU optimization tracking
- **Automatic Cleanup**: Signal traps ensure clean exit via `setup_traps()`

## 📋 Prerequisites

### System Requirements
- **AITBC CLI**: `/opt/aitbc/aitbc-cli` accessible and executable
- **Services**: Ports 8001, 9001, 8006 running and accessible
- **Ollama**: Port 11434 for AI operations (Stage 3+)
- **Bash**: Version 4.0+ for associative array support
- **Standard Tools**: bc (for calculations), curl, timeout

### Environment Setup
```bash
# Training wallet (automatically created if not exists)
export WALLET_NAME="openclaw-trainee"
export WALLET_PASSWORD="trainee123"

# Log directories (created automatically)
export LOG_DIR="/var/log/aitbc"

# Timeouts (optional, defaults provided)
export TRAINING_TIMEOUT=300

# Debug mode (optional)
export DEBUG=true
```

## 🎯 Training Outcomes

### 🏆 Certification Requirements
- **Stage Completion**: All 5 stage scripts must complete successfully (>90% success rate)
- **Performance Benchmarks**: Meet response time targets measured by `measure_time()`
- **Cross-Node Proficiency**: Operations verified on both nodes via `compare_nodes()`
- **Log Validation**: Comprehensive log review via `validate_stage()`

### 🎓 Master Status Achieved
- **CLI Proficiency**: Expert-level command knowledge with retry logic
- **Multi-Node Operations**: Seamless coordination via `cli_cmd_node()`
- **AI Operations**: Job submission and resource management with monitoring
- **Economic Intelligence**: Marketplace and optimization with analytics
- **Automation**: Custom workflow implementation capabilities

## 📊 Performance Metrics

### Target Response Times (Automated Measurement)
| Stage | Command Success Rate | Operation Speed | Measured By |
|-------|-------------------|----------------|-------------|
| Stage 1 | >95% | <5s | `measure_time()` |
| Stage 2 | >95% | <10s | `measure_time()` |
| Stage 3 | >90% | <30s | `measure_time()` |
| Stage 4 | >90% | <60s | `measure_time()` |
| Stage 5 | >95% | <120s | `measure_time()` |

### Resource Utilization Targets
- **CPU Usage**: <70% during normal operations
- **Memory Usage**: <4GB during intensive operations
- **Network Latency**: <50ms between nodes
- **Disk I/O**: <80% utilization during operations

## 🔍 Troubleshooting

### Common Issues
1. **CLI Not Found**: `check_cli()` provides detailed diagnostics
2. **Service Unavailable**: `check_service()` with port testing
3. **Node Connectivity**: `test_node_connectivity()` validates both nodes
4. **Script Timeout**: Adjustable via `TRAINING_TIMEOUT` environment variable
5. **Permission Denied**: Automatic permission fixing via `check_cli()`

### Debug Mode
```bash
# Enable debug logging
export DEBUG=true
./stage1_foundation.sh

# Run with bash trace
bash -x ./stage1_foundation.sh

# Check detailed logs
tail -f /var/log/aitbc/training_stage1.log
```

### Recovery Procedures
```bash
# Resume from specific function
source ./stage1_foundation.sh
check_prerequisites
basic_wallet_operations

# Reset training logs
sudo rm /var/log/aitbc/training_*.log

# Restart services
systemctl restart aitbc-*
```

## 🚀 Advanced Features

### Performance Optimization
- **Command Retry Logic**: `benchmark_with_retry()` with exponential backoff
- **Parallel Operations**: Background process management
- **Caching**: Result caching for repeated operations
- **Resource Monitoring**: Real-time tracking via `check_all_services()`

### Custom Automation
Stage 5 includes custom Python automation scripts:
- **AI Job Pipeline**: Automated job submission and monitoring
- **Marketplace Bot**: Automated trading and monitoring
- **Performance Optimization**: Real-time system tuning
- **Custom Workflows**: Extensible via `training_lib.sh` functions

### Multi-Node Coordination
- **Cluster Management**: Node status and synchronization
- **Load Balancing**: Workload distribution
- **Failover Testing**: High availability validation
- **Cross-Node Comparison**: `compare_nodes()` for synchronization checking

## 🔧 Library Functions Reference

### Logging Functions
```bash
log_info "Message"      # Info level logging
log_success "Message"   # Success level logging  
log_error "Message"     # Error level logging
log_warning "Message"   # Warning level logging
log_debug "Message"     # Debug level (requires DEBUG=true)
```

### Print Functions
```bash
print_header "Title"    # Print formatted header
print_status "Message"  # Print status message
print_success "Message" # Print success message
print_error "Message"   # Print error message
print_warning "Message" # Print warning message
print_progress 3 10 "Step name"  # Print progress (current, total, name)
```

### System Check Functions
```bash
check_cli              # Verify CLI availability and permissions
check_wallet "name"    # Check if wallet exists
check_service 8001 "Exchange" 5  # Check Exchange service on port
check_service 9001 "Agent-Coordinator" 5  # Check Agent Coordinator service on port
check_all_services     # Check all required services
check_prerequisites_full  # Comprehensive prerequisites check
```

### Performance Functions
```bash
measure_time "command" "description"  # Measure execution time
benchmark_with_retry "command" 3      # Execute with retry logic
```

### Node Functions
```bash
run_on_node "$GENESIS_NODE" "command"  # Run command on specific node
test_node_connectivity "$GENESIS_NODE" "Genesis" 10  # Test connectivity
compare_nodes "balance --name wallet" "description"  # Compare node results
cli_cmd_node "$GENESIS_NODE" "balance --name wallet"  # CLI on node
```

### Validation Functions
```bash
validate_stage "Stage Name" "$CURRENT_LOG" 90  # Validate stage completion
init_progress 6   # Initialize progress (6 steps)
update_progress "Step name"  # Update progress tracker
```

### CLI Wrappers
```bash
cli_cmd "balance --name wallet"        # Safe CLI execution with retry
cli_cmd_output "list"                  # Execute and capture output
cli_cmd_node "$NODE" "balance --name wallet"  # CLI on specific node
```

## 📝 Recent Optimizations

### Version 1.1 Improvements
- **Common Library**: Created `training_lib.sh` for code reuse
- **Progress Tracking**: Added visual progress indicators
- **Error Handling**: Enhanced with retry logic and graceful failures
- **Performance Measurement**: Built-in timing and benchmarking
- **Service Checking**: Automated service health validation
- **Node Coordination**: Simplified multi-node operations
- **Logging**: Structured logging with multiple levels
- **Cleanup**: Automatic cleanup on exit or interruption
- **Validation**: Automated stage validation with success rate calculation
- **Documentation**: Comprehensive function reference and examples

## 📞 Support

### Training Assistance
- **Documentation**: Refer to AITBC documentation and this README
- **Logs**: Check training logs for detailed error information
- **System Status**: Use `./master_training_launcher.sh --check`
- **Library Reference**: See function documentation above

### Log Analysis
```bash
# Monitor real-time progress
tail -f /var/log/aitbc/training_master.log

# Check specific stage
tail -f /var/log/aitbc/training_stage3.log

# Search for errors
grep -i "error\|failed" /var/log/aitbc/training_*.log

# Performance analysis
grep "measure_time\|Performance benchmark" /var/log/aitbc/training_*.log
```

---

**Training Scripts Version**: 1.1  
**Last Updated**: 2026-04-02  
**Target Audience**: OpenClaw Agents  
**Difficulty**: Beginner to Expert (5 Stages)  
**Estimated Duration**: 2-4 hours (automated)  
**Certification**: OpenClaw AITBC Master  
**Library**: `training_lib.sh` - Common utilities and functions
