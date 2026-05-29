# AITBC v0.4.1 Release Notes

**Date**: May 27, 2026  
**Status**: ✅ Released  
**Scope**: Production Hardening & Infrastructure Improvements

## 🎯 Overview

AITBC v0.4.1 is a production hardening release that focuses on security improvements, infrastructure deployment, and operational readiness. This release includes critical fixes for payment integration, edge API deployment, miner bug fixes, and comprehensive agent skills setup. The platform is now ready for proof-of-concept deployment on GPU host machines.

## 🎯 Release Highlights

### Production Hardening
- ✅ Payment integration made non-blocking for proof-of-concept operations
- ✅ Edge API deployed with SQLite backend and proper configuration
- ✅ Miner job type inference added for compatibility
- ✅ Security hardening with JWT secret generation and auth enforcement
- ✅ Data directory standardization to `/var/lib/aitbc/data`

### Infrastructure Improvements
- ✅ Edge API service deployed and operational (port 8103)
- ✅ Agent skills setup infrastructure created
- ✅ GPU marketplace CLI simplified
- ✅ Miner PATH fixed for nvidia-smi access
- ✅ Coordinator API CORS fixes

### Code Quality
- ✅ Removed outdated Hermes documentation
- ✅ Fixed transaction signing and payload structure
- ✅ Implemented missing RPC endpoints
- ✅ Added 36 missing CLI subcommands
- ✅ Standardized configuration files

## 🔒 Security Improvements

### Authentication & Authorization
- **JWT Secret**: Generated secure 32-byte token for edge-api
- **Zero-Address Fallback**: Removed dev mode zero-address fallback in blockchain-node
- **Auth Enforcement**: Authentication now required even in dev mode
- **SSL Verification**: Added SSL verification option for HTTP clients

### Payment Security
- **Non-Blocking Payments**: Payment creation no longer blocks job submission
- **Payment Status**: Jobs proceed with "skipped" status if payment fails
- **Proof-of-Concept Ready**: System operational without full payment infrastructure

### Data Security
- **Data Directory**: Standardized to `/var/lib/aitbc/data` with proper permissions
- **Keystore**: Centralized keystore management
- **Secrets**: Improved secret loading and management

## 🔧 Infrastructure Improvements

### Edge API Deployment
- **Service**: Edge API deployed as systemd service
- **Database**: SQLite with async driver (aiosqlite)
- **Configuration**: Proper environment variables and paths
- **Health Endpoint**: Operational health check on port 8103
- **Schema Fixes**: Fixed NullType column definitions

### Miner Improvements
- **Job Type Inference**: Automatically infer job type from payload structure
- **PATH Fix**: Added `/usr/bin:/usr/local/bin` to miner service PATH
- **GPU Models**: Added Ollama models to miner registration payload
- **GPU Capabilities**: Refactored GPU capabilities structure

### Coordinator API
- **CORS Fix**: Fixed CORS function name
- **Marketplace Matching**: Added marketplace matching endpoints
- **Miner Poll**: Improved miner polling mechanism
- **Payment Integration**: Made payment creation optional and non-blocking

## 📚 Documentation & Skills

### Agent Skills Setup
- **Setup Script**: Automated script to symlink skills to agent directory
- **Frontmatter**: Added proper SKILL.yml frontmatter for agent discovery
- **Documentation**: Comprehensive setup guide for agent skills
- **White-Label**: Generic agent system terminology (not OWL-specific)

### Documentation Cleanup
- **Hermes Docs**: Removed outdated Hermes analysis and decomposition plans
- **Skills Directory**: Organized skills in `docs/hermes/skills/`
- **Setup Guide**: Created SETUP.md for agent skills configuration

## 🔧 CLI Improvements

### GPU Marketplace
- **Simplified List**: Simplified gpu_marketplace list command
- **Better Output**: Improved command output formatting
- **Error Handling**: Enhanced error handling and validation

### Missing Subcommands
- **36 Subcommands**: Implemented 36 missing CLI subcommands
- **Scenario Coverage**: Added CLI scenario coverage for crosschain, monitor, resource, simulate commands
- **Advanced Subcommands**: Updated existing scenarios with advanced subcommands

### Configuration Standardization
- **blockchain.env**: Standardized blockchain configuration
- **node.env**: Standardized node configuration
- **Consistent Paths**: All config files use consistent paths

## 🔧 Blockchain Improvements

### Transaction Signing
- **Payload Structure**: Fixed transaction payload structure
- **Signature Extraction**: Proper 64-byte signature extraction
- **Private Key**: Fixed 0x prefix stripping from private key
- **Wallet Decryption**: Skip decryption for unencrypted wallets

### RPC Endpoints
- **Missing Endpoints**: Implemented missing RPC endpoints
- **GPU Operations**: Fixed GPU operations
- **Genesis Sync**: Added genesis sync-from-hub CLI command
- **Genesis Block**: Added genesis block existence check

### Block Production
- **Production Check**: Added ENABLE_BLOCK_PRODUCTION check
- **Proposer Start**: Fixed PoA proposer start() method
- **Force Removal**: Removed force-enable block production from wrapper

## 🧪 Testing Improvements

### Test Fixes
- **Workflow Test**: Fixed test_workflow.py JSON parsing
- **CLI Tests**: Fixed Python test obj dicts (output_format → output)
- **Edge Test**: Fixed test_edge_advanced.sh island bridge positional arg
- **Monitor Import**: Fixed monitor.py console import

### Test Infrastructure
- **cli_runner Fixture**: Added for isolated CLI testing
- **ctx_obj Fixture**: Added for CLI test context mocking
- **Autouse Fixture**: Added to patch CliRunner.invoke
- **pytest Path**: Added cli/ to pytest path

## 🌐 Git Infrastructure

### Remote Configuration
- **GitHub Remote**: Added GitHub remote for milestone pushes
- **Gitea Remote**: Renamed to origin (default)
- **SSH Remotes**: Removed internal SSH remotes
- **Dual-Remote Strategy**: Gitea for daily ops, GitHub for milestones

## 📊 Platform Maturity

### Service Health
- **Coordinator API**: Active (port 8011) - payment integration non-blocking
- **Edge API**: Active (port 8103) - healthy and serving
- **Blockchain Node**: Active (port 8006)
- **Miner**: Active (polling and processing jobs)
- **Marketplace**: Operational with matching endpoints

### Feature Completion
- **Payment Integration**: ✅ Non-blocking for proof-of-concept
- **Edge API**: ✅ Deployed and operational
- **Miner**: ✅ Job type inference added
- **CLI**: ✅ 36 missing subcommands implemented
- **Configuration**: ✅ Standardized

## ⚠️ Breaking Changes

### Data Directory Paths
- **Old Path**: `/opt/aitbc/data`
- **New Path**: `/var/lib/aitbc/data`
- **Migration Required**: Update any hardcoded paths
- **Services Updated**: All services updated to use new path

### Edge API Database
- **Old**: PostgreSQL
- **New**: SQLite with async driver
- **Migration Required**: Update connection strings
- **Service Updated**: systemd service updated

### Git Remotes
- **SSH Remotes**: Removed internal SSH remotes
- **GitHub**: Added for milestone pushes
- **Gitea**: Renamed to origin (default)
- **Migration Required**: Update any remote references

## 🚀 Upgrade Instructions

### For New Installations
```bash
git clone <repository-url>
cd aitbc
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### For Existing Installations
```bash
cd /opt/aitbc
git pull origin main
source venv/bin/activate
pip install --upgrade -r requirements.txt
```

### Data Directory Migration
```bash
# Create new data directory
sudo mkdir -p /var/lib/aitbc/data
sudo chown -R aitbc:aitbc /var/lib/aitbc/data

# Copy existing data
sudo cp -r /opt/aitbc/data/* /var/lib/aitbc/data/

# Update service files (automatically done by this release)
sudo systemctl daemon-reload
```

### Edge API Migration
```bash
# Edge API now uses SQLite (no PostgreSQL required)
# Database location: /var/lib/aitbc/data/edge.db
# Service automatically uses new configuration
sudo systemctl restart aitbc-edge-api.service
```

## 📝 Migration Notes

### Data Directory
- All services updated to use `/var/lib/aitbc/data`
- Old `/opt/aitbc/data` can be removed after migration
- Check for any hardcoded paths in custom scripts

### Edge API
- PostgreSQL no longer required for edge-api
- SQLite database created automatically
- No data migration needed (fresh installation)

### Git Remotes
- Daily operations use `origin` (Gitea)
- Milestone pushes use `github` (GitHub)
- Update any scripts referencing old remotes

## 🔍 Known Issues

### Payment Integration
- Payment service requires exchange/wallet services
- Currently non-blocking for proof-of-concept
- Full payment integration requires additional infrastructure

### GPU Hardware
- nvidia-smi not available in current environment
- Miner reports GPU as N/A
- Requires actual GPU hardware for production

### Edge API
- Some endpoints may require GPU hardware
- Island bridge functionality requires GPU resources
- Currently operational in proof-of-concept mode

## 🎉 Milestone Achievement

**Production Hardening Complete**: AITBC v0.4.1 represents a production-hardened platform with security improvements, infrastructure deployment, and operational readiness. The platform is ready for proof-of-concept deployment on GPU host machines with ongoing development focused on full payment integration and GPU resource management.

## 📋 Release Series Summary

### v0.4.0 - Feature Complete Milestone
- Feature complete platform
- Security and stability improvements
- Public infrastructure deployment

### v0.4.1 - Production Hardening
- Payment integration non-blocking
- Edge API deployment
- Miner bug fixes
- Agent skills setup
- Data directory standardization

---

*Last updated: 2026-05-27*  
*Version: 0.4.1*  
*Status: Production Hardening Release*
