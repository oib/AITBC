# AITBC Documentation

**AI Training Blockchain - Privacy-Preserving ML & Edge Computing Platform**

[![Roadmap](https://img.shields.io/badge/Roadmap-v0.2.0--blue.svg)](./ROADMAP.md)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Stars](https://img.shields.io/github/stars/oib/AITBC.svg?style=social)](https://github.com/oib/AITBC)

Welcome to the AITBC documentation! This guide will help you navigate the documentation based on your role.

AITBC now features **advanced privacy-preserving machine learning** with zero-knowledge proofs, **fully homomorphic encryption**, and **edge GPU optimization** for consumer hardware. The platform combines decentralized GPU computing with cutting-edge cryptographic techniques for secure, private AI inference and training.

## 📊 **Current Status: PRODUCTION READY - March 18, 2026**

### ✅ **Completed Features (100%)**
- **Core Infrastructure**: Coordinator API, Blockchain Node, Miner Node fully operational
- **Enhanced CLI System**: 100% test coverage with 67/67 tests passing
- **Exchange Infrastructure**: Complete exchange CLI commands and market integration
- **Oracle Systems**: Full price discovery mechanisms and market data
- **Market Making**: Complete market infrastructure components
- **Security**: Multi-sig, time-lock, and compliance features implemented
- **Testing**: Comprehensive test suite with full automation
- **Development Environment**: Complete setup with permission configuration
- **� Production Setup**: Complete production blockchain setup with encrypted keystores
- **🆕 AI Memory System**: Development knowledge base and agent documentation
- **🆕 Enhanced Security**: Secure pickle deserialization and vulnerability scanning
- **🆕 Repository Organization**: Professional structure with 200+ files organized

### 🎯 **Latest Achievements (March 18, 2026)**
- **Production Infrastructure**: Full production setup scripts and documentation
- **Security Enhancements**: Secure pickle handling and translation cache
- **AI Development Tools**: Memory system for agents and development tracking
- **Repository Cleanup**: Professional organization with clean root directory
- **Cross-Platform Sync**: GitHub ↔ Gitea fully synchronized

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
- [`18_explorer/`](./18_explorer/) - Explorer implementation with CLI parity
- [`19_marketplace/`](./19_marketplace/) - Global marketplace implementation
- [`20_phase_reports/`](./20_phase_reports/) - Comprehensive phase reports and guides
- [`21_reports/`](./21_reports/) - Project completion reports
- [`22_workflow/`](./22_workflow/) - Workflow completion summaries
- [`23_cli/`](./23_cli/) - **ENHANCED: Complete CLI Documentation**

### **🆕 Enhanced CLI Documentation**
- [`23_cli/README.md`](./23_cli/README.md) - Complete CLI reference with testing integration
- [`23_cli/permission-setup.md`](./23_cli/permission-setup.md) - Development environment setup
- [`23_cli/testing.md`](./23_cli/testing.md) - CLI testing procedures and results
- [`0_getting_started/3_cli.md`](./0_getting_started/3_cli.md) - CLI usage guide

### **🧪 Testing Documentation**
- [`23_cli/testing.md`](./23_cli/testing.md) - Complete CLI testing results (67/67 tests)
- [`tests/`](../tests/) - Complete test suite with automation
- [`cli/tests/`](../cli/tests/) - CLI-specific test suite

### **🆕 Production Infrastructure (March 18, 2026)**
- [`SETUP_PRODUCTION.md`](../SETUP_PRODUCTION.md) - Complete production setup guide
- [`scripts/init_production_genesis.py`](../scripts/init_production_genesis.py) - Production genesis initialization
- [`scripts/keystore.py`](../scripts/keystore.py) - Encrypted keystore management
- [`scripts/run_production_node.py`](../scripts/run_production_node.py) - Production node runner
- [`scripts/setup_production.py`](../scripts/setup_production.py) - Automated production setup
- [`ai-memory/`](../ai-memory/) - AI development memory system

### **🔒 Security Documentation**
- [`apps/coordinator-api/src/app/services/secure_pickle.py`](../apps/coordinator-api/src/app/services/secure_pickle.py) - Secure pickle handling
- [`9_security/`](./9_security/) - Comprehensive security documentation
- [`dev/scripts/dev_heartbeat.py`](../dev/scripts/dev_heartbeat.py) - Security vulnerability scanning

### **🔄 Exchange Infrastructure**
- [`19_marketplace/`](./19_marketplace/) - Exchange and marketplace documentation
- [`10_plan/01_core_planning/exchange_implementation_strategy.md`](./10_plan/01_core_planning/exchange_implementation_strategy.md) - Exchange implementation strategy
- [`10_plan/01_core_planning/trading_engine_analysis.md`](./10_plan/01_core_planning/trading_engine_analysis.md) - Trading engine documentation

### **🛠️ Development Environment**
- [`8_development/`](./8_development/) - Development setup and workflows
- [`23_cli/permission-setup.md`](./23_cli/permission-setup.md) - Permission configuration guide
- [`scripts/`](../scripts/) - Development and deployment scripts

## 🚀 **Quick Start**

### For Developers
1. **Setup Development Environment**:
   ```bash
   source /opt/aitbc/.env.dev
   ```

2. **Test CLI Installation**:
   ```bash
   aitbc --help
   aitbc version
   ```

3. **Run Service Management**:
   ```bash
   aitbc-services status
   ```

### For System Administrators
1. **Deploy Services**:
   ```bash
   sudo systemctl start aitbc-coordinator-api.service
   sudo systemctl start aitbc-blockchain-node.service
   ```

2. **Check Status**:
   ```bash
   sudo systemctl status aitbc-*
   ```

### For Users
1. **Create Wallet**:
   ```bash
   aitbc wallet create
   ```

2. **Check Balance**:
   ```bash
   aitbc wallet balance
   ```

3. **Start Trading**:
   ```bash
   aitbc exchange register --name "ExchangeName" --api-key <key>
   aitbc exchange create-pair AITBC/BTC
   ```

## 📈 **Implementation Status**

### ✅ **Completed (100%)**
- **Stage 1**: Blockchain Node Foundations ✅
- **Stage 2**: Core Services (MVP) ✅
- **CLI System**: Enhanced with 100% test coverage ✅
- **Exchange Infrastructure**: Complete implementation ✅
- **Security Features**: Multi-sig, compliance, surveillance ✅
- **Testing Suite**: 67/67 tests passing ✅

### 🎯 **In Progress (Q2 2026)**
- **Exchange Ecosystem**: Market making and liquidity
- **AI Agents**: Integration and SDK development
- **Cross-Chain**: Multi-chain functionality
- **Developer Ecosystem**: Enhanced tools and documentation

## 📚 **Key Documentation Sections**

### **🔧 CLI Operations**
- Complete command reference with examples
- Permission setup and development environment
- Testing procedures and troubleshooting
- Service management guides

### **💼 Exchange Integration**
- Exchange registration and configuration
- Trading pair management
- Oracle system integration
- Market making infrastructure

### **🛡️ Security & Compliance**
- Multi-signature wallet operations
- KYC/AML compliance procedures
- Transaction surveillance
- Regulatory reporting

### **🧪 Testing & Quality**
- Comprehensive test suite results
- CLI testing automation
- Performance testing
- Security testing procedures

## 🔗 **Related Resources**

- **GitHub Repository**: [AITBC Source Code](https://github.com/oib/AITBC)
- **CLI Reference**: [Complete CLI Documentation](./23_cli/)
- **Testing Suite**: [Test Results and Procedures](./23_cli/testing.md)
- **Development Setup**: [Environment Configuration](./23_cli/permission-setup.md)
- **Exchange Integration**: [Market and Trading Documentation](./19_marketplace/)

---

**Last Updated**: March 8, 2026  
**Infrastructure Status**: 100% Complete  
**CLI Test Coverage**: 67/67 tests passing  
**Next Milestone**: Q2 2026 Exchange Ecosystem  
**Documentation Version**: 2.0
