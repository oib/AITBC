# AITBC Documentation

**AI Training Blockchain - Privacy-Preserving ML & Edge Computing Platform**

Welcome to the AITBC documentation! This guide will help you navigate the documentation based on your role.

AITBC now features **advanced privacy-preserving machine learning** with zero-knowledge proofs, **fully homomorphic encryption**, and **edge GPU optimization** for consumer hardware. The platform combines decentralized GPU computing with cutting-edge cryptographic techniques for secure, private AI inference and training.

## 📁 **Documentation Organization**

### **Main Documentation Categories**
- [`0_getting_started/`](./0_getting_started/) - Getting started guides with enhanced CLI
- [`1_project/`](./1_project/) - Project overview and architecture  
- [`2_clients/`](./2_clients/) - Enhanced client documentation
- [`3_miners/`](./3_miners/) - Enhanced miner documentation
- [`4_blockchain/`](./4_blockchain/) - Blockchain documentation
- [`5_reference/`](./5_reference/) - Reference materials
- [`6_architecture/`](./6_architecture/) - System architecture
- [`7_deployment/`](./7_deployment/) - Deployment guides
- [`8_development/`](./8_development/) - Development documentation
- [`9_security/`](./9_security/) - Security documentation
- [`10_plan/`](./10_plan/) - Development plans and roadmaps
- [`11_agents/`](./11_agents/) - AI agent documentation
- [`12_issues/`](./12_issues/) - Archived issues
- [`13_tasks/`](./13_tasks/) - Task documentation
- [`14_agent_sdk/`](./14_agent_sdk/) - Agent Identity SDK documentation
- [`15_completion/`](./15_completion/) - Phase implementation completion summaries
- [`16_cross_chain/`](./16_cross_chain/) - Cross-chain integration documentation
- [`17_developer_ecosystem/`](./17_developer_ecosystem/) - Developer ecosystem documentation
- [`18_explorer/`](./18_explorer/) - **ENHANCED: Explorer implementation with CLI parity**
- [`19_marketplace/`](./19_marketplace/) - Global marketplace implementation
- [`20_phase_reports/`](./20_phase_reports/) - Comprehensive phase reports and guides
- [`21_reports/`](./21_reports/) - Project completion reports
- [`22_workflow/`](./22_workflow/) - Workflow completion summaries
- [`23_cli/`](./23_cli/) - **NEW: Enhanced CLI Documentation**

### **Enhanced CLI Documentation** 🆕
- [`23_cli/README.md`](./23_cli/README.md) - Complete enhanced CLI reference with testing integration
- [`0_getting_started/3_cli.md`](./0_getting_started/3_cli.md) - CLI usage guide
- [`2_clients/`](./2_clients/) - Client operations with enhanced CLI
- [`3_miners/`](./3_miners/) - Miner operations with enhanced CLI

### **Testing Documentation** 🆕
- [`docs/10_plan/89_test.md`](./10_plan/89_test.md) - Multi-chain test scenarios with CLI integration
- [`tests/`](../tests/) - Complete test suite with CLI testing
- [`.windsurf/skills/test.md`](../.windsurf/skills/test.md) - Comprehensive testing skill
- [`.windsurf/workflows/test.md`](../.windsurf/workflows/test.md) - Testing workflow and procedures

### **Implementation Reports** (Recently Organized)
- [`21_reports/`](./21_reports/) - Project completion reports
- [`15_completion/`](./15_completion/) - Phase implementation completion summaries
- [`20_phase_reports/`](./20_phase_reports/) - Comprehensive phase reports and guides
- [`22_workflow/`](./22_workflow/) - Workflow completion summaries
- [`18_explorer/`](./18_explorer/) - Explorer implementation documentation
- [`14_agent_sdk/`](./14_agent_sdk/) - Agent Identity SDK documentation
- [`16_cross_chain/`](./16_cross_chain/) - Cross-chain integration documentation
- [`19_marketplace/`](./19_marketplace/) - Global marketplace implementation
- [`17_developer_ecosystem/`](./17_developer_ecosystem/) - Developer ecosystem documentation

## 🎯 **Current Status**

**✅ PHASE 6 COMPLETE** - Enterprise Integration APIs and Scalability Optimization  
**🔄 Q4 2026 PLANNING** - Global Marketplace Leadership Strategy  
**🆕 ENHANCED CLI** - Complete CLI overhaul with new features and capabilities

## 🚀 **Quick Start with Enhanced CLI**

### Installation
```bash
git clone https://github.com/oib/AITBC.git
cd aitbc
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Setup
```bash
# Configure CLI
aitbc config set coordinator_url http://localhost:8000
export AITBC_API_KEY=your-key

# Verify installation
aitbc --version
aitbc --debug
```

### Create Wallet
```bash
aitbc wallet create --name my-wallet
aitbc wallet balance
```

### Submit Job (Enhanced)
```bash
aitbc client submit \
  --prompt "What is AI?" \
  --model gpt2 \
  --priority normal \
  --timeout 3600
```

### Start Mining (Enhanced)
```bash
aitbc miner register \
  --name my-gpu \
  --gpu v100 \
  --count 1 \
  --region us-west \
  --price-per-hour 0.05

aitbc miner poll
```

## 🎯 **Quick Start by Role**

### **Compute Providers** → [../3_miners/1_quick-start.md](../3_miners/1_quick-start.md)
```bash
aitbc miner register --name "my-gpu-agent" --compute-type inference --gpu-memory 24GB
aitbc miner poll
aitbc marketplace offer create --miner-id my-gpu-agent --price-per-hour 0.1 AITBC
```

### **Compute Consumers** → [../2_clients/1_quick-start.md](../2_clients/1_quick-start.md)
```bash
aitbc client submit --prompt "Explain blockchain" --model gpt2 --priority normal
aitbc client status --job-id <JOB_ID>
aitbc client download --job-id <JOB_ID> --output ./results
```

### **Platform Builders** → [../8_development/](../8_development/)
```bash
git clone https://github.com/aitbc/aitbc.git
cd aitbc
pip install -e .
aitbc --version
```

### **Agent Developers** → [../11_agents/](../11_agents/)
```bash
aitbc agent workflow create --name "ai-agent" --description "Custom AI agent"
aitbc agent execute ai-agent --input '{"task": "process_data"}'
```

## 🔧 **Enhanced CLI Features**

### **New Command Groups**
- **Agent Operations**: `aitbc agent workflow create/execute/network/learning`
- **OpenClaw Deployment**: `aitbc openclaw deploy/optimize/edge/routing`
- **Optimization**: `aitbc optimize enable/recommendations/apply/predict/tune`
- **Enhanced Marketplace**: `aitbc marketplace gpu list/offer create/gpu rent`
- **Advanced Monitoring**: `aitbc monitor dashboard/metrics/alerts/webhooks`

### **Enhanced Capabilities**
- **Agent Workflows**: Create and execute complex AI agent workflows
- **GPU Optimization**: Automatic performance tuning and optimization
- **Marketplace Integration**: Seamless GPU renting and offering
- **Configuration Management**: Profiles, secrets, and advanced config
- **Real-time Monitoring**: Dashboard and metrics integration
- **Batch Operations**: Bulk job submission and management

## 📚 **Documentation Navigation**

### **For New Users**
1. [Getting Started](./0_getting_started/) - Installation and basic setup
2. [CLI Reference](./23_cli/) - Complete enhanced CLI guide
3. [Client Guide](./2_clients/) - Using the platform as a client
4. [Miner Guide](./3_miners/) - Setting up mining operations

### **For Developers**
1. [Development Guide](./8_development/) - Development setup and contribution
2. [Agent SDK](./14_agent_sdk/) - Building AI agents
3. [Architecture](./6_architecture/) - System architecture and design
4. [API Reference](./5_reference/) - Complete API documentation

### **For Operators**
1. [Deployment Guide](./7_deployment/) - Production deployment
2. [Security Guide](./9_security/) - Security best practices
3. [Monitoring](./23_cli/#monitoring-and-debugging) - System monitoring
4. [Troubleshooting](./23_cli/#troubleshooting) - Common issues and solutions

## 🔗 **Enhanced CLI Integration**

The enhanced AITBC CLI provides:
- **Unified Interface**: Single tool for all AITBC operations
- **Advanced Features**: Agent workflows, optimization, deployment
- **Better UX**: Improved commands, configuration, and output
- **Real-time Monitoring**: Dashboard and metrics integration
- **Automation Support**: Batch operations and scripting capabilities

## 🛡️ **Security**

**Security Status**: 🛡️ AUDITED & HARDENED  
- **0 vulnerabilities** in smart contracts (35 OpenZeppelin warnings only)
- **90 CVEs** fixed in dependencies
- **95/100 system hardening** index achieved

Run comprehensive security audit:
```bash
./scripts/comprehensive-security-audit.sh
```

## 🤝 **Contributing**

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with enhanced CLI
5. Submit a pull request

## 📞 **Support**

- **Documentation**: This comprehensive guide
- **CLI Help**: `aitbc --help` and `aitbc <command> --help`
- **Issues**: [GitHub Issues](https://github.com/aitbc/aitbc/issues)
- **Community**: [Discord/Forum links]

---

*This documentation covers the complete AITBC platform with enhanced CLI capabilities.*  
**📊 PRODUCTION READY** - Enterprise-grade platform with 99.99% uptime

## 📋 **Key Documents**

#### **Planning & Roadmap**
- [`10_plan/00_nextMileston.md`](./10_plan/00_nextMileston.md) - Next milestone planning (Q4 2026)
- [`10_plan/07_global_marketplace_leadership.md`](./10_plan/07_global_marketplace_leadership.md) - Global marketplace strategy

#### **Implementation Summaries**
- [`21_reports/PROJECT_COMPLETION_REPORT.md`](./21_reports/PROJECT_COMPLETION_REPORT.md) - Overall project completion
- [`15_completion/PHASE6_ENTERPRISE_INTEGRATION_COMPLETE.md`](./15_completion/PHASE6_ENTERPRISE_INTEGRATION_COMPLETE.md) - Phase 6 completion
- [`15_completion/PHASE5_ADVANCED_AI_IMPLEMENTATION_SUMMARY.md`](./15_completion/PHASE5_ADVANCED_AI_IMPLEMENTATION_SUMMARY.md) - Phase 5 completion
- [`20_phase_reports/COMPREHENSIVE_GUIDE.md`](./20_phase_reports/COMPREHENSIVE_GUIDE.md) - Comprehensive project guide
- [`20_phase_reports/AGENT_INDEX.md`](./20_phase_reports/AGENT_INDEX.md) - Agent system index
- [`19_marketplace/GLOBAL_MARKETPLACE_IMPLEMENTATION_COMPLETE.md`](./19_marketplace/GLOBAL_MARKETPLACE_IMPLEMENTATION_COMPLETE.md) - Marketplace implementation

#### **Technical Documentation**
- [`6_architecture/9_full-technical-reference.md`](./6_architecture/9_full-technical-reference.md) - Complete technical reference
- [`5_reference/6_enterprise-sla.md`](./5_reference/6_enterprise-sla.md) - Enterprise SLA documentation

---

## 📁 **Documentation Organization History**

### **Root Directory Cleanup - March 1, 2026**

The project root directory was cleaned and organized to maintain only essential files at the root level.

#### **Files Moved to Appropriate Directories**
- **Documentation Files** → `docs/` subdirectories:
  - `PROJECT_COMPLETION_REPORT.md` → `docs/reports/`
  - `EXPLORER_*.md` (5 files) → `docs/explorer/`
  - `AGENT_IDENTITY_SDK_*.md` (3 files) → `docs/agent-sdk/`
  - `CROSS_CHAIN_*.md` (5 files) → `docs/cross-chain/`
  - `GLOBAL_MARKETPLACE_*.md` (3 files) → `docs/marketplace/`
  - `DEVELOPER_ECOSYSTEM_*.md` (1 file) → `docs/developer-ecosystem/`

- **Python Scripts** → `scripts/` directory:
  - `test_explorer_*.py` (2 files) → `scripts/test/`
  - `verify_explorer.py` → `scripts/test/`
  - `definitive_explorer_proof.py` → `scripts/test/`
  - `parse_issues.py` → `scripts/`

#### **Root Directory Structure**
The root directory now contains only essential files:

**Configuration Files**
- `.aitbc.yaml`, `.editorconfig`, `.gitignore`, `pyproject.toml`
- `.env.example`, `package.json`, `poetry.lock`

**Project Files**
- `README.md`, `LICENSE`
- Core directories: `apps/`, `cli/`, `contracts/`, `docs/`, `tests/`
- Infrastructure: `infra/`, `systemd/`, `monitoring/`

### **Additional Documentation Organization**

Following the initial cleanup, additional documentation files were organized into specialized subdirectories:

#### **Phase Completion Reports → `docs/completion/`**
- `PHASE5_ADVANCED_AI_IMPLEMENTATION_SUMMARY.md` - Phase 5 implementation summary
- `PHASE6_ENTERPRISE_INTEGRATION_COMPLETE.md` - Phase 6 implementation summary

#### **Comprehensive Reports → `docs/phase-reports/`**
- `COMPREHENSIVE_GUIDE.md` - Complete project guide
- `AGENT_INDEX.md` - Agent system index

#### **Workflow Documentation → `docs/workflow/`**
- `DOCS_WORKFLOW_COMPLETION_SUMMARY.md` - Documentation workflow completion
- `documentation-updates-workflow-completion.md` - Documentation updates workflow
- `global-marketplace-planning-workflow-completion.md` - Global marketplace planning workflow
- `PLANNING_NEXT_MILESTONE_COMPLETION_SUMMARY.md` - Planning milestone completion

### **Complete Directory Structure**

```
docs/
├── 0_getting_started/       # Getting started guides
├── 1_project/               # Project overview and architecture
├── 2_clients/               # Client documentation
├── 3_miners/                # Miner documentation
├── 4_blockchain/            # Blockchain documentation
├── 5_reference/             # Reference materials
├── 6_architecture/          # System architecture
├── 7_deployment/            # Deployment guides
├── 8_development/           # Development documentation
├── 9_security/              # Security documentation
├── 10_plan/                 # Development plans and roadmaps
├── 11_agents/               # AI agent documentation
├── 12_issues/               # Archived issues
├── 13_tasks/                # Task documentation
├── 14_agent_sdk/            # Agent Identity SDK docs
├── 15_completion/           # Phase implementation completion summaries
├── 16_cross_chain/          # Cross-chain integration docs
├── 17_developer_ecosystem/  # Developer ecosystem docs
├── 18_explorer/             # Explorer implementation docs
├── 19_marketplace/          # Global marketplace implementation
├── 20_phase_reports/        # Comprehensive phase reports and guides
├── 21_reports/              # Project completion reports
└── 22_workflow/             # Workflow completion summaries

scripts/
└── test/                     # Test scripts
```

### **Organization Benefits**

- ✅ **Clean Root Directory**: Only essential project files remain
- ✅ **Logical Grouping**: Related documents grouped by type and purpose
- ✅ **Easy Navigation**: Clear directory structure with descriptive names
- ✅ **Maintainability**: Easy to find and manage specific documentation
- ✅ **Professional Structure**: Industry-standard documentation organization

### **Organization Summary**

**Status**: ✅ **DOCUMENTATION ORGANIZATION COMPLETE**  
**Date**: March 1, 2026  
**Files Organized**: 30+ files moved to appropriate subdirectories  
**Root Directory**: Clean and professional structure maintained  
**Documentation Structure**: Fully organized and professional

### 👤 New Users - Start Here!

Start with the **Getting Started** section to learn the basics:

| Order | Topic | Description |
|-------|-------|-------------|
| 1 | [0_getting_started/1_intro.md](./0_getting_started/1_intro.md) | What is AITBC? |
| 2 | [0_getting_started/2_installation.md](./0_getting_started/2_installation.md) | Install AITBC |
| 3 | [0_getting_started/3_cli.md](./0_getting_started/3_cli.md) | Use the CLI |

### 💻 Clients

If you're a **client** looking to rent GPU computing power:

| Order | Topic | Description |
|-------|-------|-------------|
| 1 | [2_clients/1_quick-start.md](./2_clients/1_quick-start.md) | Quick start guide |
| 2 | [2_clients/2_job-submission.md](./2_clients/2_job-submission.md) | Submit compute jobs |
| 3 | [2_clients/3_job-lifecycle.md](./2_clients/3_job-lifecycle.md) | Status, results, history, cancellation |
| 4 | [2_clients/4_wallet.md](./2_clients/4_wallet.md) | Manage tokens |
| 5 | [2_clients/5_pricing-billing.md](./2_clients/5_pricing-billing.md) | Costs & invoices |
| 6 | [2_clients/6_api-reference.md](./2_clients/6_api-reference.md) | Client API reference |

### ⛏️ Miners

If you're a **miner** providing GPU resources:

| Order | Topic | Description |
|-------|-------|-------------|
| 1 | [3_miners/1_quick-start.md](./3_miners/1_quick-start.md) | Quick start guide |
| 2 | [3_miners/2_registration.md](./3_miners/2_registration.md) | Register your miner |
| 3 | [3_miners/3_job-management.md](./3_miners/3_job-management.md) | Handle jobs |
| 4 | [3_miners/4_earnings.md](./3_miners/4_earnings.md) | Track earnings |
| 5 | [3_miners/5_gpu-setup.md](./3_miners/5_gpu-setup.md) | Configure GPUs |

### 🔗 Node Operators

If you're running a **blockchain node**:

| Order | Topic | Description |
|-------|-------|-------------|
| 1 | [4_blockchain/1_quick-start.md](./4_blockchain/1_quick-start.md) | Quick start guide |
| 2 | [4_blockchain/2_configuration.md](./4_blockchain/2_configuration.md) | Configure your node |
| 3 | [4_blockchain/3_operations.md](./4_blockchain/3_operations.md) | Day-to-day operations |
| 4 | [4_blockchain/4_consensus.md](./4_blockchain/4_consensus.md) | Consensus mechanism |
| 5 | [4_blockchain/7_monitoring.md](./4_blockchain/7_monitoring.md) | Monitor your node |

## Documentation Structure

```
docs/
├── 0_getting_started/          # New users start here
│   ├── 1_intro.md             # What is AITBC?
│   ├── 2_installation.md      # Installation guide
│   └── 3_cli.md               # CLI usage
├── 1_project/                  # Project management
│   ├── 1_files.md             # File reference
│   ├── 2_roadmap.md           # Future plans
│   ├── 3_currenttask.md       # Current task (gitignored)
│   ├── 4_currentissue.md      # Current issue (gitignored)
│   ├── 5_done.md              # Completed work
│   └── 6_cross-site-sync-resolved.md
├── 2_clients/                  # Client docs (beginner → advanced)
│   ├── 0_readme.md            # Overview
│   ├── 1_quick-start.md       # Get started
│   ├── 2_job-submission.md    # Submit jobs
│   ├── 3_job-lifecycle.md     # Status, results, history, cancel
│   ├── 4_wallet.md            # Token management
│   ├── 5_pricing-billing.md   # Costs & invoices
│   └── 6_api-reference.md     # API reference
├── 3_miners/                   # Miner docs (beginner → advanced)
│   ├── 0_readme.md            # Overview
│   ├── 1_quick-start.md  →  7_api-miner.md
├── 4_blockchain/              # Node operator docs (beginner → advanced)
│   ├── 0_readme.md            # Overview
│   ├── 1_quick-start.md  →  10_api-blockchain.md
├── 5_reference/               # Technical reference (17 files)
│   ├── 0_index.md
│   ├── 1_cli-reference.md  →  17_docs-gaps.md
├── 6_architecture/            # Architecture + component deep-dives
│   ├── 1_system-flow.md       # End-to-end flow
│   ├── 2_components-overview.md
│   ├── 3_coordinator-api.md   # Component docs
│   ├── 4_blockchain-node.md
│   ├── 5_marketplace-web.md
│   ├── 6_trade-exchange.md
│   ├── 7_wallet.md
│   ├── 8_codebase-structure.md
│   └── 9_full-technical-reference.md
├── 7_deployment/              # Deployment & ops
│   ├── 0_index.md
│   ├── 1_remote-deployment-guide.md  →  6_beta-release-plan.md
├── 8_development/             # Developer guides (17 files)
│   ├── 0_index.md
│   ├── 1_overview.md  →  17_windsurf-testing.md
├── 9_security/                # Security docs
│   ├── 1_security-cleanup-guide.md
│   └── 2_security-architecture.md
└── README.md                  # This navigation guide
```

## Common Tasks

| Task | Documentation |
|------|---------------|
| Install AITBC | [0_getting_started/2_installation.md](./0_getting_started/2_installation.md) |
| Submit a job | [2_clients/2_job-submission.md](./2_clients/2_job-submission.md) |
| Register as miner | [3_miners/2_registration.md](./3_miners/2_registration.md) |
| Set up a node | [4_blockchain/1_quick-start.md](./4_blockchain/1_quick-start.md) |
| Check balance | [2_clients/4_wallet.md](./2_clients/4_wallet.md) |
| Monitor node | [4_blockchain/7_monitoring.md](./4_blockchain/7_monitoring.md) |
| Troubleshooting | [4_blockchain/8_troubleshooting.md](./4_blockchain/8_troubleshooting.md) |

## Additional Resources

| Resource | Description |
|----------|-------------|
| [README.md](../README.md) | Project overview |
| [1_project/2_roadmap.md](./1_project/2_roadmap.md) | Development roadmap |
| [8_development/1_overview.md](./8_development/1_overview.md) | Network topology |
| [1_project/5_done.md](./1_project/5_done.md) | Completed features |
| [GitHub](https://github.com/oib/AITBC) | Source code |

## Component READMEs

Per-component documentation that lives alongside the source code:

### Apps

| Component | README |
|-----------|--------|
| Blockchain Node | [apps/blockchain-node/README.md](../apps/blockchain-node/README.md) |
| Blockchain Schema | [apps/blockchain-node/docs/SCHEMA.md](../apps/blockchain-node/docs/SCHEMA.md) |
| Observability | [apps/blockchain-node/observability/README.md](../apps/blockchain-node/observability/README.md) |
| Coordinator API | [apps/coordinator-api/README.md](../apps/coordinator-api/README.md) |
| Migrations | [apps/coordinator-api/migrations/README.md](../apps/coordinator-api/migrations/README.md) |
| Explorer Web | [apps/explorer-web/README.md](../apps/explorer-web/README.md) |
| Marketplace Web | [apps/marketplace-web/README.md](../apps/marketplace-web/README.md) |
| Pool Hub | [apps/pool-hub/README.md](../apps/pool-hub/README.md) |
| Wallet Daemon | [apps/wallet-daemon/README.md](../apps/wallet-daemon/README.md) |
| ZK Circuits | [apps/zk-circuits/README.md](../apps/zk-circuits/README.md) |

### Packages & Plugins

| Component | README |
|-----------|--------|
| CLI | [cli/README.md](../cli/README.md) |
| Ollama Plugin | [plugins/ollama/README.md](../plugins/ollama/README.md) |
| Firefox Wallet | [extensions/aitbc-wallet-firefox/README.md](../extensions/aitbc-wallet-firefox/README.md) |
| Extensions | [extensions/README.md](../extensions/README.md) |
| ZK Verification | [contracts/docs/ZK-VERIFICATION.md](../contracts/docs/ZK-VERIFICATION.md) |
| Token Deployment | [packages/solidity/aitbc-token/docs/DEPLOYMENT.md](../packages/solidity/aitbc-token/docs/DEPLOYMENT.md) |

### Infrastructure & Testing

| Component | README |
|-----------|--------|
| Infrastructure | [infra/README.md](../infra/README.md) |
| Tests | [tests/README.md](../tests/README.md) |
| Verification Scripts | [tests/verification/README.md](../tests/verification/README.md) |
| Example Scripts | [scripts/examples/README.md](../scripts/examples/README.md) |

## Support

- **Issues**: [GitHub Issues](https://github.com/oib/AITBC/issues)
- **Discord**: [Join our community](https://discord.gg/aitbc)
- **Email**: support@aitbc.io

---

**Version**: 1.0.0  
**Last Updated**: 2026-02-19  
**Security Status**: 🛡️ AUDITED & HARDENED  
**Maintainers**: AITBC Development Team
