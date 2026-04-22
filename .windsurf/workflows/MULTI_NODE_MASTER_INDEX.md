---
description: Master index for multi-node blockchain setup - links to all modules and provides navigation
title: Multi-Node Blockchain Setup - Master Index
version: 2.0 (100% Complete)
---

# Multi-Node Blockchain Setup - Master Index

**Project Status**: ✅ **100% COMPLETED** (v0.3.0 - April 2, 2026)

This master index provides navigation to all modules in the multi-node AITBC blockchain setup documentation and workflows. Each module focuses on specific aspects of the deployment, operation, and code quality. All workflows reflect the 100% project completion status.

## 🎉 **Project Completion Status**

### **✅ All 9 Major Systems: 100% Complete**
1. **System Architecture**: ✅ Complete FHS compliance
2. **Service Management**: ✅ Single marketplace service
3. **Basic Security**: ✅ Secure keystore implementation
4. **Agent Systems**: ✅ Multi-agent coordination
5. **API Functionality**: ✅ 17/17 endpoints working
6. **Test Suite**: ✅ 100% test success rate
7. **Advanced Security**: ✅ JWT auth and RBAC
8. **Production Monitoring**: ✅ Prometheus metrics and alerting
9. **Type Safety**: ✅ MyPy strict checking

---

## 📚 Module Overview

### 🏗️ Core Setup Module
**File**: `multi-node-blockchain-setup-core.md`
**Purpose**: Essential setup steps for two-node blockchain network
**Audience**: New deployments, initial setup
**Prerequisites**: None (base module)

**Key Topics**:
- Prerequisites and pre-flight setup
- Environment configuration
- Genesis block architecture
- Basic node setup (aitbc + aitbc1)
- Wallet creation and funding
- Cross-node transactions

**Quick Start**:
```bash
# Run core setup
/opt/aitbc/scripts/workflow/02_genesis_authority_setup.sh
ssh aitbc1 '/opt/aitbc/scripts/workflow/03_follower_node_setup.sh'
```

---

### 🔧 Code Quality Module
**File**: `code-quality.md`
**Purpose**: Comprehensive code quality assurance workflow
**Audience**: Developers, DevOps engineers
**Prerequisites**: Development environment setup

**Key Topics**:
- Pre-commit hooks configuration
- Code formatting (Black, isort)
- Linting and type checking (Flake8, MyPy)
- Security scanning (Bandit, Safety)
- Automated testing integration
- Quality metrics and reporting

**Quick Start**:
```bash
# Install pre-commit hooks
./venv/bin/pre-commit install

# Run all quality checks
./venv/bin/pre-commit run --all-files

# Check type coverage
./scripts/type-checking/check-coverage.sh
```

---

### 🔧 Type Checking CI/CD Module
**File**: `type-checking-ci-cd.md`
**Purpose**: Comprehensive type checking workflow with CI/CD integration
**Audience**: Developers, DevOps engineers, QA engineers
**Prerequisites**: Development environment setup, basic Git knowledge

**Key Topics**:
- Local development type checking workflow
- Pre-commit hooks integration
- GitHub Actions CI/CD pipeline
- Coverage reporting and analysis
- Quality gates and enforcement
- Progressive type safety implementation

**Quick Start**:
```bash
# Local type checking
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/

# Coverage analysis
./scripts/type-checking/check-coverage.sh

# Pre-commit hooks
./venv/bin/pre-commit run mypy-domain-core
```

---

### 🔧 Operations Module
**File**: `multi-node-blockchain-operations.md`
**Purpose**: Daily operations, monitoring, and troubleshooting
**Audience**: System administrators, operators
**Prerequisites**: Core Setup Module

**Key Topics**:
- Service management and health monitoring
- Daily operations and maintenance
- Performance monitoring and optimization
- Troubleshooting common issues
- Backup and recovery procedures
- Security operations

**Quick Start**:
```bash
# Check system health
systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service
python3 /tmp/aitbc1_heartbeat.py
```

---

### 🚀 Advanced Features Module
**File**: `multi-node-blockchain-advanced.md`
**Purpose**: Advanced blockchain features and testing
**Audience**: Advanced users, developers
**Prerequisites**: Core Setup + Operations Modules

**Key Topics**:
- Smart contract deployment and testing
- Security testing and hardening
- Performance optimization
- Advanced monitoring and analytics
- Consensus testing and validation
- Event monitoring and data analytics

**Quick Start**:
```bash
# Deploy smart contract
./aitbc-cli contract deploy --name "AgentMessagingContract" --wallet genesis-ops
```

---

### 🏭 Production Module
**File**: `multi-node-blockchain-production.md`
**Purpose**: Production deployment, security, and scaling
**Audience**: Production engineers, DevOps
**Prerequisites**: Core Setup + Operations + Advanced Modules

**Key Topics**:
- Production readiness and security hardening
- Monitoring, alerting, and observability
- Scaling strategies and load balancing
- CI/CD integration and automation
- Disaster recovery and backup procedures

**Quick Start**:
```bash
# Production deployment
sudo systemctl enable aitbc-blockchain-node-production.service
sudo systemctl start aitbc-blockchain-node-production.service
```

---

### 🛒 Marketplace Module
**File**: `multi-node-blockchain-marketplace.md`
**Purpose**: Marketplace testing and AI operations
**Audience**: Marketplace operators, AI service providers
**Prerequisites**: Core Setup + Operations + Advanced + Production Modules

**Key Topics**:
- Marketplace setup and service creation
- GPU provider testing and resource allocation
- AI operations and job management
- Transaction tracking and verification
- Performance testing and optimization

**Quick Start**:
```bash
# Create marketplace service
./aitbc-cli market create --type ai-inference --price 100 --description "AI Service" --wallet provider
```

---

### 📖 Reference Module
**File**: `multi-node-blockchain-reference.md`
**Purpose**: Configuration reference and verification commands
**Audience**: All users (reference material)
**Prerequisites**: None (independent reference)

**Key Topics**:
- Configuration overview and parameters
- Verification commands and health checks
- System overview and architecture
- Success metrics and KPIs
- Best practices and troubleshooting guide

**Quick Start**:
```bash
# Quick health check
./aitbc-cli chain && ./aitbc-cli network
```

## 🗺️ Module Dependencies

```
Core Setup (Foundation)
├── Operations (Daily Management)
├── Advanced Features (Complex Operations)
├── Production (Production Deployment)
│   └── Marketplace (AI Operations)
└── Reference (Independent Guide)
```

## 🚀 Recommended Learning Path

### For New Users
1. **Core Setup Module** - Learn basic deployment
2. **Operations Module** - Master daily operations
3. **Reference Module** - Keep as guide

### For System Administrators
1. **Core Setup Module** - Understand deployment
2. **Operations Module** - Master operations
3. **Advanced Features Module** - Learn advanced topics
4. **Reference Module** - Keep as reference

### For Production Engineers
1. **Core Setup Module** - Understand basics
2. **Operations Module** - Master operations
3. **Advanced Features Module** - Learn advanced features
4. **Production Module** - Master production deployment
5. **Marketplace Module** - Learn AI operations
6. **Reference Module** - Keep as reference

### For AI Service Providers
1. **Core Setup Module** - Understand blockchain
2. **Operations Module** - Master operations
3. **Advanced Features Module** - Learn smart contracts
4. **Marketplace Module** - Master AI operations
5. **Reference Module** - Keep as reference

## 🎯 Quick Navigation

### By Task

| Task | Recommended Module |
|---|---|
| **Initial Setup** | Core Setup |
| **Daily Operations** | Operations |
| **Troubleshooting** | Operations + Reference |
| **Security Hardening** | Advanced Features + Production |
| **Performance Optimization** | Advanced Features |
| **Production Deployment** | Production |
| **AI Operations** | Marketplace |
| **Configuration Reference** | Reference |

### By Role

| Role | Essential Modules |
|---|---|
| **Blockchain Developer** | Core Setup, Advanced Features, Reference |
| **System Administrator** | Core Setup, Operations, Reference |
| **DevOps Engineer** | Core Setup, Operations, Production, Reference |
| **AI Engineer** | Core Setup, Operations, Marketplace, Reference |
| **Security Engineer** | Advanced Features, Production, Reference |

### By Complexity

| Level | Modules |
|---|---|
| **Beginner** | Core Setup, Operations |
| **Intermediate** | Advanced Features, Reference |
| **Advanced** | Production, Marketplace |
| **Expert** | All modules |

## 🔍 Quick Reference Commands

### Essential Commands (From Core Module)
```bash
# Basic health check
curl -s http://localhost:8006/health | jq .

# Check blockchain height
curl -s http://localhost:8006/rpc/head | jq .height

# List wallets
./aitbc-cli wallet list

# Send transaction
./aitbc-cli wallet send wallet1 wallet2 100 123
```

### Operations Commands (From Operations Module)
```bash
# Service status
systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service

# Comprehensive health check
python3 /tmp/aitbc1_heartbeat.py

# Monitor sync
watch -n 10 'curl -s http://localhost:8006/rpc/head | jq .height'
```

### Advanced Commands (From Advanced Module)
```bash
# Deploy smart contract
./aitbc-cli contract deploy --name "ContractName" --wallet genesis-ops

# Test security
nmap -sV -p 8006,7070 localhost

# Performance test
./aitbc-cli contract benchmark --name "ContractName" --operations 1000
```

### Production Commands (From Production Module)
```bash
# Production services
sudo systemctl status aitbc-blockchain-node-production.service

# Backup database
sudo cp /var/lib/aitbc/data/ait-mainnet/chain.db /var/backups/aitbc/

# Monitor with Prometheus
curl -s http://localhost:9090/metrics
```

### Marketplace Commands (From Marketplace Module)
```bash
# Create service
./aitbc-cli market create --type ai-inference --price 100 --description "Service" --wallet provider

# Submit AI job
./aitbc-cli ai submit --wallet wallet --type inference --prompt "Generate image" --payment 100

# Check resource status
./aitbc-cli resource status
```

## 📊 System Overview

### Architecture Summary
```
Two-Node AITBC Blockchain:
├── Genesis Node (aitbc) - Primary development server
├── Follower Node (aitbc1) - Secondary node
├── RPC Services (port 8006) - API endpoints
├── P2P Network (port 7070) - Node communication
├── Gossip Network (Redis) - Data propagation
├── Smart Contracts - On-chain logic
├── AI Operations - Job processing and marketplace
└── Monitoring - Health checks and metrics
```

### Key Components
- **Blockchain Core**: Transaction processing and consensus
- **RPC Layer**: API interface for external access
- **Smart Contracts**: Agent messaging and governance
- **AI Services**: Job submission, resource allocation, marketplace
- **Monitoring**: Health checks, performance metrics, alerting

## 🎯 Success Metrics

### Deployment Success
- [ ] Both nodes operational and synchronized
- [ ] Cross-node transactions working
- [ ] Smart contracts deployed and functional
- [ ] AI operations and marketplace active
- [ ] Monitoring and alerting configured

### Operational Success
- [ ] Services running with >99% uptime
- [ ] Block production rate: 1 block/10s
- [ ] Transaction confirmation: <10s
- [ ] Network latency: <50ms
- [ ] Resource utilization: <80%

### Production Success
- [ ] Security hardening implemented
- [ ] Backup and recovery procedures tested
- [ ] Scaling strategies validated
- [ ] CI/CD pipeline operational
- [ ] Disaster recovery verified

## 🔧 Troubleshooting Quick Reference

### Common Issues
| Issue | Module | Solution |
|---|---|---|
| Services not starting | Core Setup | Check configuration, permissions |
| Nodes out of sync | Operations | Check network, restart services |
| Transactions stuck | Advanced | Check mempool, proposer status |
| Performance issues | Production | Check resources, optimize database |
| AI jobs failing | Marketplace | Check resources, wallet balance |

### Emergency Procedures
1. **Service Recovery**: Restart services, check logs
2. **Network Recovery**: Check connectivity, restart networking
3. **Database Recovery**: Restore from backup
4. **Security Incident**: Check logs, update security

## 📚 Additional Resources

### Documentation Files
- **AI Operations Reference**: `openclaw-aitbc/ai-operations-reference.md`
- **Agent Templates**: `openclaw-aitbc/agent-templates.md`
- **Workflow Templates**: `openclaw-aitbc/workflow-templates.md`
- **Setup Scripts**: `openclaw-aitbc/setup.sh`

### External Resources
- **AITBC Repository**: GitHub repository
- **API Documentation**: `/opt/aitbc/docs/api/`
- **Developer Guide**: `/opt/aitbc/docs/developer/`

## 🔄 Version History

### v1.0 (Current)
- Split monolithic workflow into 6 focused modules
- Added comprehensive navigation and cross-references
- Created learning paths for different user types
- Added quick reference commands and troubleshooting

### Archived Workflows
- **Archived Monolithic Workflow**: `archive/multi-node-blockchain-setup.md` (64KB, 2,098 lines)

## 🤝 Contributing

### Updating Documentation
1. Update specific module files
2. Update this master index if needed
3. Update cross-references between modules
4. Test all links and commands
5. Commit changes with descriptive message

### Module Creation
1. Follow established template structure
2. Include prerequisites and dependencies
3. Add quick start commands
4. Include troubleshooting section
5. Update this master index

---

**Note**: This master index is your starting point for all multi-node blockchain setup operations. Choose the appropriate module based on your current task and expertise level.

For immediate help, see the **Reference Module** for comprehensive commands and troubleshooting guidance.
