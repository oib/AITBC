---
description: Comprehensive OpenClaw agent training plan for AITBC software mastery from beginner to expert level
title: OPENCLAW_AITBC_MASTERY_PLAN
version: 1.0
---

# OpenClaw AITBC Mastery Plan

## Quick Navigation
- [Purpose](#purpose)
- [Overview](#overview)
- [Training Scripts Suite](#training-scripts-suite)
- [Training Stages](#training-stages)
  - [Stage 1: Foundation](#stage-1-foundation-beginner-level)
  - [Stage 2: Intermediate](#stage-2-intermediate-operations)
  - [Stage 3: AI Operations](#stage-3-ai-operations-mastery)
  - [Stage 4: Marketplace](#stage-4-marketplace--economic-intelligence)
  - [Stage 5: Expert](#stage-5-expert-operations--automation)
- [Training Validation](#training-validation)
- [Performance Metrics](#performance-metrics)
- [Environment Setup](#environment-setup)
- [Advanced Modules](#advanced-training-modules)
- [Training Schedule](#training-schedule)
- [Certification](#certification--recognition)
- [Troubleshooting](#troubleshooting)

---

## Purpose
Comprehensive training plan for OpenClaw agents to master AITBC software on both nodes (aitbc and aitbc1) using CLI tools, progressing from basic operations to expert-level blockchain and AI operations.

## Overview

### 🎯 **Training Objectives**
- **Node Mastery**: Operate on both aitbc (genesis) and aitbc1 (follower) nodes
- **CLI Proficiency**: Master all AITBC CLI commands and workflows
- **Blockchain Operations**: Complete understanding of multi-node blockchain operations
- **AI Job Management**: Expert-level AI job submission and resource management
- **Marketplace Operations**: Full marketplace participation and economic intelligence

### 🏗️ **Two-Node Architecture**
```
AITBC Multi-Node Setup:
├── Genesis Node (aitbc) - Port 8006 (Primary, IP: 10.1.223.40)
├── Follower Node (aitbc1) - Port 8006 (Secondary, different IP)
├── CLI Tool: /opt/aitbc/aitbc-cli
├── Services: Coordinator (8001), Exchange (8000), Blockchain RPC (8006 on both nodes)
├── AI Operations: Ollama integration, job processing, marketplace
└── Node Synchronization: Gitea-based git pull/push (NOT SCP)
```

**Important**: Both nodes run services on the **same port (8006)** because they are on **different physical machines** with different IP addresses. This is standard distributed blockchain architecture where each node uses the same port locally but on different IPs.

### 🔄 **Gitea-Based Node Synchronization**
**Important**: Node synchronization between aitbc and aitbc1 uses **Gitea git repository**, NOT SCP file transfers.

```bash
# Sync aitbc1 from Gitea (non-interactive)
ssh aitbc1 'cd /opt/aitbc && git pull origin main --yes --no-confirm'

# Sync both nodes from Gitea (debug mode)
cd /opt/aitbc && git pull origin main --verbose --debug
ssh aitbc1 'cd /opt/aitbc && git pull origin main --verbose'

# Push changes to Gitea (non-interactive)
git push origin main --yes
git push github main --yes

# Check git sync status (debug mode)
git status --verbose
git log --oneline -5 --decorate
ssh aitbc1 'cd /opt/aitbc && git status --verbose'

# Force sync if needed (use with caution)
ssh aitbc1 'cd /opt/aitbc && git reset --hard origin/main'
```

**Gitea Repository**: `http://gitea.bubuit.net:3000/oib/aitbc.git`
**GitHub Mirror**: `https://github.com/oib/AITBC.git` (push only after milestones)

### 🚀 **Training Scripts Suite**
**Location**: `/opt/aitbc/scripts/training/`

#### **Master Training Launcher**
- **File**: `master_training_launcher.sh`
- **Purpose**: Interactive orchestrator for all training stages
- **Features**: Progress tracking, system readiness checks, stage selection
- **Usage**: `./master_training_launcher.sh`

#### **Individual Stage Scripts**
- **Stage 1**: `stage1_foundation.sh` - Basic CLI operations and wallet management
- **Stage 2**: `stage2_intermediate.sh` - Advanced blockchain and smart contracts
- **Stage 3**: `stage3_ai_operations.sh` - AI job submission and resource management
- **Stage 4**: `stage4_marketplace_economics.sh` - Trading and economic intelligence
- **Stage 5**: `stage5_expert_automation.sh` - Automation and multi-node coordination

#### **Script Features**
- **Hands-on Practice**: Real CLI commands with live system interaction
- **Progress Tracking**: Detailed logging and success metrics
- **Performance Validation**: Response time and success rate monitoring
- **Node-Specific Operations**: Dual-node testing (aitbc & aitbc1)
- **Error Handling**: Graceful failure recovery with detailed diagnostics
- **Validation Quizzes**: Knowledge checks at each stage completion

#### **Quick Start Commands**
```bash
# Run complete training program
cd /opt/aitbc/scripts/training
./master_training_launcher.sh

# Run individual stages
./stage1_foundation.sh    # Start here
./stage2_intermediate.sh  # After Stage 1
./stage3_ai_operations.sh # After Stage 2
./stage4_marketplace_economics.sh # After Stage 3
./stage5_expert_automation.sh # After Stage 4

# Command line options
./master_training_launcher.sh --overview    # Show training overview
./master_training_launcher.sh --check       # Check system readiness
./master_training_launcher.sh --stage 3     # Run specific stage
./master_training_launcher.sh --complete    # Run complete training
```

---

## 📈 **Training Stages**

### **Stage 1: Foundation (Beginner Level)**
**Duration**: 2-3 days | **Prerequisites**: None

#### **1.1 Basic System Orientation**
- **Objective**: Understand AITBC architecture and node structure
- **CLI Commands**:
  ```bash
  # System overview (debug mode)
  ./aitbc-cli --version --verbose
  ./aitbc-cli --help --debug
  ./aitbc-cli system --status --verbose

  # Node identification (non-interactive)
  ./aitbc-cli node --info --output json
  ./aitbc-cli node --list --format table
  ./aitbc-cli node --info --debug
  ```

#### **1.2 Basic Wallet Operations**
- **Objective**: Create and manage wallets on both nodes
- **CLI Commands**:
  ```bash
  # Wallet creation (non-interactive)
  ./aitbc-cli wallet create --name openclaw-wallet --password <password> --yes --no-confirm
  ./aitbc-cli wallet list --output json

  # Balance checking (debug mode)
  ./aitbc-cli wallet balance --name openclaw-wallet --verbose
  ./aitbc-cli wallet balance --all --format table

  # Node-specific operations (with debug)
  NODE_URL=http://10.1.223.40:8006 ./aitbc-cli wallet balance --name openclaw-wallet --verbose  # Genesis node
  NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli wallet balance --name openclaw-wallet --debug  # Follower node
  ```

#### **1.3 Basic Transaction Operations**
- **Objective**: Send transactions between wallets on both nodes
- **CLI Commands**:
  ```bash
  # Basic transactions (non-interactive)
  ./aitbc-cli wallet send --from openclaw-wallet --to recipient --amount 100 --password <password> --yes --no-confirm
  ./aitbc-cli wallet transactions --name openclaw-wallet --limit 10 --output json

  # Cross-node transactions (debug mode)
  NODE_URL=http://10.1.223.40:8006 ./aitbc-cli wallet send --from wallet1 --to wallet2 --amount 50 --verbose --dry-run
  ```

#### **1.4 Service Health Monitoring**
- **Objective**: Monitor health of all AITBC services
- **CLI Commands**:
  ```bash
  # Service status (debug mode)
  ./aitbc-cli service status --verbose
  ./aitbc-cli service health --debug --output json

  # Node connectivity (non-interactive)
  ./aitbc-cli network status --format table
  ./aitbc-cli network peers --verbose
  ./aitbc-cli network ping --node aitbc1 --host <aitbc1-ip> --port 8006 --debug
  ```

**Stage 1 Validation**: Successfully create wallet, check balance, send transaction, verify service health on both nodes

**🚀 Training Script**: Execute `./stage1_foundation.sh` for hands-on practice
- **Cross-Reference**: [`/opt/aitbc/scripts/training/stage1_foundation.sh`](../scripts/training/stage1_foundation.sh)
- **Log File**: `/var/log/aitbc/training_stage1.log`
- **Estimated Time**: 15-30 minutes with script

---

### **Stage 2: Intermediate Operations**
**Duration**: 3-4 days | **Prerequisites**: Stage 1 completion

#### **2.1 Advanced Wallet Management**
- **Objective**: Multi-wallet operations and backup strategies
- **CLI Commands**:
  ```bash
  # Advanced wallet operations (non-interactive)
  ./aitbc-cli wallet backup --name openclaw-wallet --yes --no-confirm
  ./aitbc-cli wallet restore --name backup-wallet --force --yes
  ./aitbc-cli wallet export --name openclaw-wallet --output json

  # Multi-wallet coordination (debug mode)
  ./aitbc-cli wallet sync --all --verbose
  ./aitbc-cli wallet balance --all --format table --debug
  ```

#### **2.2 Blockchain Operations**
- **Objective**: Deep blockchain interaction and mining operations
- **CLI Commands**:
  ```bash
  # Blockchain information (debug mode)
  ./aitbc-cli blockchain info --verbose
  ./aitbc-cli blockchain height --output json
  ./aitbc-cli blockchain block --number <block_number> --debug

  # Mining operations (non-interactive)
  ./aitbc-cli blockchain mining start --yes --no-confirm
  ./aitbc-cli blockchain mining status --verbose
  ./aitbc-cli blockchain mining stop --yes

  # Node-specific blockchain operations
  NODE_URL=http://10.1.223.40:8006 ./aitbc-cli blockchain info --verbose  # Genesis
  NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli blockchain info --debug  # Follower
  ```

#### **2.3 Smart Contract Interaction**
- **Objective**: Interact with AITBC smart contracts
- **CLI Commands**:
  ```bash
  # Contract operations (non-interactive)
  ./aitbc-cli blockchain contract list --format table
  ./aitbc-cli blockchain contract deploy --name <contract_name> --yes --no-confirm
  ./aitbc-cli blockchain contract call --address <address> --method <method> --verbose

  # Agent messaging contracts (debug mode)
  ./aitbc-cli agent message --to <agent_id> --content "Hello from OpenClaw" --debug
  ./aitbc-cli agent messages --from <agent_id> --output json
  ```

#### **2.4 Network Operations**
- **Objective**: Network management and peer operations
- **CLI Commands**:
  ```bash
  # Network management (non-interactive)
  ./aitbc-cli network connect --peer <peer_address> --yes --no-confirm
  ./aitbc-cli network disconnect --peer <peer_address> --yes
  ./aitbc-cli network sync status --verbose

  # Cross-node communication (debug mode)
  ./aitbc-cli network ping --node aitbc1 --verbose --debug
  ./aitbc-cli network propagate --data <data> --dry-run
  ```

**Stage 2 Validation**: Successful multi-wallet management, blockchain mining, contract interaction, and network operations on both nodes

**🚀 Training Script**: Execute `./stage2_intermediate.sh` for hands-on practice
- **Cross-Reference**: [`/opt/aitbc/scripts/training/stage2_intermediate.sh`](../scripts/training/stage2_intermediate.sh)
- **Log File**: `/var/log/aitbc/training_stage2.log`
- **Estimated Time**: 20-40 minutes with script
- **Prerequisites**: Complete Stage 1 training script successfully

---

### **Stage 3: AI Operations Mastery**
**Duration**: 4-5 days | **Prerequisites**: Stage 2 completion

#### **3.1 AI Job Submission**
- **Objective**: Master AI job submission and monitoring
- **CLI Commands**:
  ```bash
  # AI job operations (non-interactive)
  ./aitbc-cli ai job submit --type inference --prompt "Analyze this data" --yes --no-confirm
  ./aitbc-cli ai job status --id <job_id> --output json
  ./aitbc-cli ai job result --id <job_id> --verbose

  # Job monitoring (debug mode)
  ./aitbc-cli ai job list --status all --format table --debug
  ./aitbc-cli ai job cancel --id <job_id> --yes

  # Node-specific AI operations
  NODE_URL=http://10.1.223.40:8006 ./aitbc-cli ai job submit --type inference --verbose
  NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli ai job submit --type parallel --debug
  ```

#### **3.2 Resource Management**
- **Objective**: Optimize resource allocation and utilization
- **CLI Commands**:
  ```bash
  # Resource operations (debug mode)
  ./aitbc-cli resource status --verbose --output json
  ./aitbc-cli resource allocate --type gpu --amount 50% --yes --no-confirm
  ./aitbc-cli resource monitor --interval 30 --debug

  # Performance optimization (non-interactive)
  ./aitbc-cli resource optimize --target cpu --yes --dry-run
  ./aitbc-cli resource benchmark --type inference --verbose
  ```

#### **3.3 Ollama Integration**
- **Objective**: Master Ollama model management and operations
- **CLI Commands**:
  ```bash
  # Ollama operations (non-interactive)
  ./aitbc-cli ollama models --format table
  ./aitbc-cli ollama pull --model llama2 --yes --no-confirm
  ./aitbc-cli ollama run --model llama2 --prompt "Test prompt" --verbose

  # Model management (debug mode)
  ./aitbc-cli ollama status --debug
  ./aitbc-cli ollama delete --model <model_name> --yes --force
  ./aitbc-cli ollama benchmark --model <model_name> --verbose
  ```

#### **3.4 AI Service Integration**
- **Objective**: Integrate with multiple AI services and APIs
- **CLI Commands**:
  ```bash
  # AI service operations (debug mode)
  ./aitbc-cli ai service list --verbose --output json
  ./aitbc-cli ai service status --name ollama --debug
  ./aitbc-cli ai service test --name coordinator --verbose

  # API integration (non-interactive)
  ./aitbc-cli api test --endpoint /ai/job --yes --no-confirm
  ./aitbc-cli api monitor --endpoint /ai/status --format json
  ```

**Stage 3 Validation**: Successful AI job submission, resource optimization, Ollama integration, and AI service management on both nodes

**🚀 Training Script**: Execute `./stage3_ai_operations.sh` for hands-on practice
- **Cross-Reference**: [`/opt/aitbc/scripts/training/stage3_ai_operations.sh`](../scripts/training/stage3_ai_operations.sh)
- **Log File**: `/var/log/aitbc/training_stage3.log`
- **Estimated Time**: 30-60 minutes with script
- **Prerequisites**: Complete Stage 2 training script successfully
- **Special Requirements**: Ollama service running on port 11434

---

### **Stage 4: Marketplace & Economic Intelligence**
**Duration**: 3-4 days | **Prerequisites**: Stage 3 completion

#### **4.1 Marketplace Operations**
- **Objective**: Master marketplace participation and trading
- **CLI Commands**:
  ```bash
  # Marketplace operations (debug mode)
  ./aitbc-cli market list --verbose --format table
  ./aitbc-cli market buy --item <item_id> --price <price> --yes --no-confirm
  ./aitbc-cli market sell --item <item_id> --price <price> --yes

  # Order management (non-interactive)
  ./aitbc-cli market orders --status active --output json
  ./aitbc-cli market cancel --order <order_id> --yes

  # Node-specific marketplace operations
  NODE_URL=http://10.1.223.40:8006 ./aitbc-cli market list --verbose
  NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli market list --debug
  ```

#### **4.2 Economic Intelligence**
- **Objective**: Implement economic modeling and optimization
- **CLI Commands**:
  ```bash
  # Economic operations (non-interactive)
  ./aitbc-cli economics model --type cost-optimization --yes --no-confirm
  ./aitbc-cli economics forecast --period 7d --output json
  ./aitbc-cli economics optimize --target revenue --dry-run

  # Market analysis (debug mode)
  ./aitbc-cli economics market analyze --verbose
  ./aitbc-cli economics trends --period 30d --format table
  ```

#### **4.3 Distributed AI Economics**
- **Objective**: Cross-node economic optimization and revenue sharing
- **CLI Commands**:
  ```bash
  # Distributed economics (debug mode)
  ./aitbc-cli economics distributed cost-optimize --verbose
  ./aitbc-cli economics revenue share --node aitbc1 --yes
  ./aitbc-cli economics workload balance --nodes aitbc,aitbc1 --debug

  # Cross-node coordination (non-interactive)
  ./aitbc-cli economics sync --nodes aitbc,aitbc1 --yes --no-confirm
  ./aitbc-cli economics strategy optimize --global --dry-run
  ```

#### **4.4 Advanced Analytics**
- **Objective**: Comprehensive analytics and reporting
- **CLI Commands**:
  ```bash
  # Analytics operations (non-interactive)
  ./aitbc-cli analytics report --type performance --output json
  ./aitbc-cli analytics metrics --period 24h --format table
  ./aitbc-cli analytics export --format csv --yes

  # Predictive analytics (debug mode)
  ./aitbc-cli analytics predict --model lstm --target job-completion --verbose
  ./aitbc-cli analytics optimize parameters --target efficiency --debug
  ```

**Stage 4 Validation**: Successful marketplace operations, economic modeling, distributed optimization, and advanced analytics

**🚀 Training Script**: Execute `./stage4_marketplace_economics.sh` for hands-on practice
- **Cross-Reference**: [`/opt/aitbc/scripts/training/stage4_marketplace_economics.sh`](../scripts/training/stage4_marketplace_economics.sh)
- **Log File**: `/var/log/aitbc/training_stage4.log`
- **Estimated Time**: 25-45 minutes with script
- **Prerequisites**: Complete Stage 3 training script successfully
- **Cross-Node Focus**: Economic coordination between aitbc and aitbc1

---

### **Stage 5: Expert Operations & Automation**
**Duration**: 4-5 days | **Prerequisites**: Stage 4 completion

#### **5.1 Advanced Automation**
- **Objective**: Automate complex workflows and operations
- **CLI Commands**:
  ```bash
  # Automation operations (non-interactive)
  ./aitbc-cli workflow create --name ai-job-pipeline --yes --no-confirm
  ./aitbc-cli workflow schedule --cron "0 */6 * * *" --command "./aitbc-cli ai job submit" --yes
  ./aitbc-cli workflow monitor --name marketplace-bot --verbose

  # Script execution (debug mode)
  ./aitbc-cli script run --file custom_script.py --verbose --debug
  ./aitbc-cli script schedule --file maintenance_script.sh --dry-run
  ```

#### **5.2 Multi-Node Coordination**
- **Objective**: Advanced coordination across both nodes using Gitea
- **CLI Commands**:
  ```bash
  # Multi-node operations (debug mode)
  ./aitbc-cli cluster status --nodes aitbc,aitbc1 --verbose
  ./aitbc-cli cluster sync --all --yes --no-confirm
  ./aitbc-cli cluster balance workload --debug

  # Node-specific coordination (non-interactive)
  NODE_URL=http://10.1.223.40:8006 ./aitbc-cli cluster coordinate --action failover --yes
  NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli cluster coordinate --action recovery --yes

  # Gitea-based sync (instead of SCP)
  ssh aitbc1 'cd /opt/aitbc && git pull origin main --yes --no-confirm'
  git push origin main --yes
  git status --verbose
  ```

#### **5.3 Performance Optimization**
- **Objective**: System-wide performance tuning and optimization
- **CLI Commands**:
  ```bash
  # Performance operations (non-interactive)
  ./aitbc-cli performance benchmark --suite comprehensive --yes --no-confirm
  ./aitbc-cli performance optimize --target latency --dry-run
  ./aitbc-cli performance tune parameters --aggressive --yes

  # Resource optimization (debug mode)
  ./aitbc-cli performance resource optimize --global --verbose
  ./aitbc-cli performance cache optimize --strategy lru --debug
  ```

#### **5.4 Security & Compliance**
- **Objective**: Advanced security operations and compliance management
- **CLI Commands**:
  ```bash
  # Security operations (debug mode)
  ./aitbc-cli security audit --comprehensive --verbose --output json
  ./aitbc-cli security scan --vulnerabilities --debug
  ./aitbc-cli security patch --critical --yes --no-confirm

  # Compliance operations (non-interactive)
  ./aitbc-cli compliance check --standard gdpr --yes
  ./aitbc-cli compliance report --format detailed --output json
  ```

**Stage 5 Validation**: Successful automation implementation, multi-node coordination, performance optimization, and security management

**🚀 Training Script**: Execute `./stage5_expert_automation.sh` for hands-on practice and certification
- **Cross-Reference**: [`/opt/aitbc/scripts/training/stage5_expert_automation.sh`](../scripts/training/stage5_expert_automation.sh)
- **Log File**: `/var/log/aitbc/training_stage5.log`
- **Estimated Time**: 35-70 minutes with script
- **Prerequisites**: Complete Stage 4 training script successfully
- **Certification**: Includes automated certification exam simulation
- **Advanced Features**: Custom Python automation scripts, multi-node orchestration

---

## 🎯 **Training Validation**

### **Stage Completion Criteria**
Each stage must achieve:
- **100% Command Success Rate**: All CLI commands execute successfully
- **Cross-Node Proficiency**: Operations work on both aitbc and aitbc1 nodes
- **Performance Benchmarks**: Meet or exceed performance targets
- **Error Recovery**: Demonstrate proper error handling and recovery

### **Final Certification Criteria**
- **Comprehensive Exam**: 3-hour practical exam covering all stages
- **Performance Test**: Achieve >95% success rate on complex operations
- **Cross-Node Integration**: Seamless operations across both nodes
- **Economic Intelligence**: Demonstrate advanced economic modeling
- **Automation Mastery**: Implement complex automated workflows

---

## 📊 **Performance Metrics**

### **Expected Performance Targets**
| Stage | Command Success Rate | Operation Speed | Error Recovery | Cross-Node Sync |
|-------|-------------------|----------------|----------------|----------------|
| Stage 1 | >95% | <5s | <30s | <10s |
| Stage 2 | >95% | <10s | <60s | <15s |
| Stage 3 | >90% | <30s | <120s | <20s |
| Stage 4 | >90% | <60s | <180s | <30s |
| Stage 5 | >95% | <120s | <300s | <45s |

### **Resource Utilization Targets**
- **CPU Usage**: <70% during normal operations
- **Memory Usage**: <4GB during intensive operations
- **Network Latency**: <50ms between nodes
- **Disk I/O**: <80% utilization during operations

---

## 🔧 **Environment Setup**

### **Required Environment Variables**
```bash
# Node configuration
export NODE_URL=http://10.1.223.40:8006  # Genesis node
export NODE_URL=http://<aitbc1-ip>:8006  # Follower node
export CLI_PATH=/opt/aitbc/aitbc-cli

# Service endpoints
export COORDINATOR_URL=http://localhost:8001
export EXCHANGE_URL=http://localhost:8000
export OLLAMA_URL=http://localhost:11434

# Authentication
export WALLET_NAME=openclaw-wallet
export WALLET_PASSWORD=<secure_password>
```

### **Service Dependencies**
- **AITBC CLI**: `/opt/aitbc/aitbc-cli` accessible
- **Blockchain Services**: Port 8006 on both nodes (different IPs)
- **AI Services**: Ollama (11434), Coordinator (8001), Exchange (8000)
- **Network Connectivity**: Both nodes can communicate
- **Sufficient Balance**: Test wallet with adequate AIT tokens

---

## 🚀 **Advanced Training Modules**

### **Specialization Tracks**
After Stage 5 completion, agents can specialize in:

#### **AI Operations Specialist**
- Advanced AI job optimization
- Resource allocation algorithms
- Performance tuning for AI workloads

#### **Blockchain Expert**
- Advanced smart contract development
- Cross-chain operations
- Blockchain security and auditing

#### **Economic Intelligence Master**
- Advanced economic modeling
- Market strategy optimization
- Distributed economic systems

#### **Systems Automation Expert**
- Complex workflow automation
- Multi-node orchestration
- DevOps and monitoring automation

---

## 📝 **Training Schedule**

### **Daily Training Structure**
- **Morning (2 hours)**: Theory and concept review
- **Afternoon (3 hours)**: Hands-on CLI practice with training scripts
- **Evening (1 hour)**: Performance analysis and optimization

### **Script-Based Training Workflow**
1. **System Check**: Run `./master_training_launcher.sh --check`
2. **Stage Execution**: Execute stage script sequentially
3. **Progress Review**: Analyze logs in `/var/log/aitbc/training_*.log`
4. **Validation**: Complete stage quizzes and practical exercises
5. **Certification**: Pass final exam with 95%+ success rate

### **Weekly Milestones**
- **Week 1**: Complete Stages 1-2 (Foundation & Intermediate)
  - Execute: `./stage1_foundation.sh` → `./stage2_intermediate.sh`
- **Week 2**: Complete Stage 3 (AI Operations Mastery)
  - Execute: `./stage3_ai_operations.sh`
- **Week 3**: Complete Stage 4 (Marketplace & Economics)
  - Execute: `./stage4_marketplace_economics.sh`
- **Week 4**: Complete Stage 5 (Expert Operations) and Certification
  - Execute: `./stage5_expert_automation.sh` → Final exam

### **Assessment Schedule**
- **Daily**: Script success rate and performance metrics from logs
- **Weekly**: Stage completion validation via script output
- **Final**: Comprehensive certification exam simulation

### **Training Log Analysis**
```bash
# Monitor training progress
tail -f /var/log/aitbc/training_master.log

# Check specific stage performance
grep "SUCCESS" /var/log/aitbc/training_stage*.log

# Analyze performance metrics
grep "Performance benchmark" /var/log/aitbc/training_stage*.log
```

---

## 🎓 **Certification & Recognition**

### **OpenClaw AITBC Master Certification**
**Requirements**:
- Complete all 5 training stages via script execution
- Pass final certification exam (>95% score) simulated in Stage 5
- Demonstrate expert-level CLI proficiency on both nodes
- Achieve target performance metrics in script benchmarks
- Successfully complete automation and multi-node coordination tasks

### **Script-Based Certification Process**
1. **Stage Completion**: All 5 stage scripts must complete successfully
2. **Performance Validation**: Meet response time targets in each stage
3. **Final Exam**: Automated certification simulation in `stage5_expert_automation.sh`
4. **Practical Assessment**: Hands-on operations on both aitbc and aitbc1 nodes
5. **Log Review**: Comprehensive analysis of training performance logs

### **Certification Benefits**
- **Expert Recognition**: Certified OpenClaw AITBC Master
- **Advanced Access**: Full system access and permissions
- **Economic Authority**: Economic modeling and optimization rights
- **Teaching Authority**: Qualified to train other OpenClaw agents
- **Automation Privileges**: Ability to create custom training scripts

### **Post-Certification Training**
- **Advanced Modules**: Specialization tracks for expert-level operations
- **Script Development**: Create custom automation workflows
- **Performance Tuning**: Optimize training scripts for specific use cases
- **Knowledge Transfer**: Train other agents using developed scripts

---

## 🔧 **Troubleshooting**

### **Common Training Issues**

#### **CLI Not Found**
**Problem**: `./aitbc-cli: command not found`
**Solution**: 
```bash
# Verify CLI path
ls -la /opt/aitbc/aitbc-cli

# Check permissions
chmod +x /opt/aitbc/aitbc-cli

# Use full path
/opt/aitbc/aitbc-cli --version
```

#### **Service Connection Failed**
**Problem**: Services not accessible on expected ports
**Solution**:
```bash
# Check service status
systemctl status aitbc-blockchain-rpc
systemctl status aitbc-coordinator

# Restart services if needed
systemctl restart aitbc-blockchain-rpc
systemctl restart aitbc-coordinator

# Verify ports
netstat -tlnp | grep -E '800[0167]|11434'
```

#### **Node Connectivity Issues**
**Problem**: Cannot connect to aitbc1 node
**Solution**:
```bash
# Test node connectivity
curl http://<aitbc1-ip>:8006/health
curl http://10.1.223.40:8006/health

# Check network configuration
cat /opt/aitbc/config/edge-node-aitbc1.yaml

# Verify firewall settings
iptables -L | grep 8006
```

#### **AI Job Submission Failed**
**Problem**: AI job submission returns error
**Solution**:
```bash
# Check Ollama service
curl http://localhost:11434/api/tags

# Verify wallet balance
/opt/aitbc/aitbc-cli balance --name openclaw-trainee

# Check AI service status
/opt/aitbc/aitbc-cli ai --service --status --name coordinator
```

#### **Script Execution Timeout**
**Problem**: Training script times out
**Solution**:
```bash
# Increase timeout in scripts
export TRAINING_TIMEOUT=300

# Run individual functions
source /opt/aitbc/scripts/training/stage1_foundation.sh
check_prerequisites  # Run specific function

# Check system load
top -bn1 | head -20
```

#### **Wallet Creation Failed**
**Problem**: Cannot create training wallet
**Solution**:
```bash
# Check existing wallets
/opt/aitbc/aitbc-cli list

# Remove existing wallet if needed
# WARNING: Only for training wallets
rm -rf /var/lib/aitbc/keystore/openclaw-trainee*

# Recreate with verbose output
/opt/aitbc/aitbc-cli create --name openclaw-trainee --password trainee123 --verbose
```

### **Performance Optimization**

#### **Slow Response Times**
```bash
# Optimize system performance
sudo sysctl -w vm.swappiness=10
sudo sysctl -w vm.dirty_ratio=15

# Check disk I/O
iostat -x 1 5

# Monitor resource usage
htop &
```

#### **High Memory Usage**
```bash
# Clear caches
sudo sync && sudo echo 3 > /proc/sys/vm/drop_caches

# Monitor memory
free -h
vmstat 1 5
```

### **Script Recovery**

#### **Resume Failed Stage**
```bash
# Check last completed operation
tail -50 /var/log/aitbc/training_stage1.log

# Retry specific stage function
source /opt/aitbc/scripts/training/stage1_foundation.sh
basic_wallet_operations

# Run with debug mode
bash -x /opt/aitbc/scripts/training/stage1_foundation.sh
```

### **Cross-Node Issues**

#### **Node Synchronization Problems (Gitea-Based)**
```bash
# Force node sync using Gitea (NOT SCP)
cd /opt/aitbc && git pull origin main --verbose --debug
ssh aitbc1 'cd /opt/aitbc && git pull origin main --verbose'

# Check git sync status on both nodes
git status --verbose
git log --oneline -5 --decorate
ssh aitbc1 'cd /opt/aitbc && git status --verbose'

# Force sync if needed (use with caution)
ssh aitbc1 'cd /opt/aitbc && git reset --hard origin/main'

# Check node status on both nodes
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli node info --verbose
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli node info --debug

# Restart follower node if needed
systemctl restart aitbc-blockchain-p2p
```

### **Getting Help**

#### **Log Analysis**
```bash
# Collect all training logs
tar -czf training_logs_$(date +%Y%m%d).tar.gz /var/log/aitbc/training*.log

# Check for errors
grep -i "error\|failed\|warning" /var/log/aitbc/training*.log

# Monitor real-time progress
tail -f /var/log/aitbc/training_master.log
```

#### **System Diagnostics**
```bash
# Generate system report
echo "=== System Status ===" > diagnostics.txt
date >> diagnostics.txt
echo "" >> diagnostics.txt
echo "=== Services ===" >> diagnostics.txt
systemctl status aitbc-* >> diagnostics.txt 2>&1
echo "" >> diagnostics.txt
echo "=== Ports ===" >> diagnostics.txt
netstat -tlnp | grep -E '800[0167]|11434' >> diagnostics.txt 2>&1
echo "" >> diagnostics.txt
echo "=== Disk Usage ===" >> diagnostics.txt
df -h >> diagnostics.txt
echo "" >> diagnostics.txt
echo "=== Memory ===" >> diagnostics.txt
free -h >> diagnostics.txt
```

#### **Emergency Procedures**
```bash
# Reset training environment
/opt/aitbc/scripts/training/master_training_launcher.sh --check

# Clean training logs
sudo rm /var/log/aitbc/training*.log

# Restart all services
systemctl restart aitbc-*

# Verify system health
curl http://10.1.223.40:8006/health
curl http://<aitbc1-ip>:8006/health
curl http://10.1.223.40:8001/health
curl http://10.1.223.40:8000/health
```

---

**Training Plan Version**: 1.1  
**Last Updated**: 2026-04-02  
**Target Audience**: OpenClaw Agents  
**Difficulty**: Beginner to Expert (5 Stages)  
**Estimated Duration**: 4 weeks  
**Certification**: OpenClaw AITBC Master  
**Training Scripts**: Complete automation suite available at `/opt/aitbc/scripts/training/`

---

## 🔄 **Integration with Training Scripts**

### **Script Availability**
All training stages are now fully automated with executable scripts:
- **Location**: `/opt/aitbc/scripts/training/`
- **Master Launcher**: `master_training_launcher.sh`
- **Stage Scripts**: `stage1_foundation.sh` through `stage5_expert_automation.sh`
- **Documentation**: Complete README with usage instructions

### **Enhanced Learning Experience**
- **Interactive Training**: Guided script execution with real-time feedback
- **Performance Monitoring**: Automated benchmarking and success tracking
- **Error Recovery**: Graceful handling of system issues with detailed diagnostics
- **Progress Validation**: Automated quizzes and practical assessments
- **Log Analysis**: Comprehensive performance tracking and optimization

### **Immediate Deployment**
OpenClaw agents can begin training immediately using:
```bash
cd /opt/aitbc/scripts/training
./master_training_launcher.sh
```

This integration provides a complete, hands-on learning experience that complements the theoretical knowledge outlined in this mastery plan.
