# AITBC v0.4.2 Release Notes

**Date**: June 1, 2026  
**Status**: ✅ Released  
**Scope**: Hermes Agent Integration & Configuration Hardening

## 🎯 Overview

AITBC v0.4.2 is a major release focused on Hermes agent integration, environment configuration hardening, and GPU resource tracking. This release implements comprehensive blockchain integrations for Hermes agents including staking, identity verification, governance, and GPU resource tracking. The platform now supports fully configurable chain_id, node_id, and island_id via environment variables, eliminating hardcoded values for multi-environment deployment.

## 🎯 Release Highlights

### Hermes Agent Integration
- ✅ Complete blockchain integration for Hermes agents (staking, identity, governance, GPU tracking)
- ✅ Hermes polling daemon integration to aitbc-agent-daemon service
- ✅ Modular handler system for Hermes message processing
- ✅ REQUEST_COINS handler for Hermes service
- ✅ Message deduplication for hub coordinator listener
- ✅ Coin approval mode switch system (manual/automatic/AI strategies)
- ✅ Comprehensive Hermes documentation split into topic files

### GPU Resource Tracking
- ✅ GPU registration, query, list, allocate, and allocations CLI commands
- ✅ GPU resource RPC endpoints on blockchain node
- ✅ Hybrid on-chain/off-chain GPU resource architecture
- ✅ GPU service integration with non-blocking blockchain registration
- ✅ GPU allocation history tracking on-chain

### Configuration Hardening
- ✅ Remove hardcoded chain_id - require explicit environment variable configuration
- ✅ Remove hardcoded node_id - require explicit environment variable configuration
- ✅ Remove hardcoded island_id - require explicit environment variable configuration
- ✅ chain_id validation to P2P handshake
- ✅ Enforce island_id matching for non-hub nodes
- ✅ Standardize config files: use blockchain.env and node.env instead of .env
- ✅ Update chain_id fallback from ait-testnet to ait-hub.aitbc.bubuit.net

### CLI Improvements
- ✅ Add 15 new CLI command groups (70+ total command groups)
- ✅ Add sync command group for bulk blockchain synchronization
- ✅ Re-enable analytics command
- ✅ Add requirements-minimal.txt for minimal dependency installation
- ✅ Fix CLI package structure and dependencies
- ✅ Update CLI reference documentation with enterprise and advanced features

### Security Improvements
- ✅ Remove development validator keys file containing test credentials
- ✅ Move JWT secret from inline environment variable to external secrets file
- ✅ Add argon2-cffi dependency and coordinator API key loading to keystore secrets
- ✅ Add graceful fallback to simulated data when RPC unavailable

### Documentation Updates
- ✅ Update documentation paths from /home/oib/windsurf/aitbc to /opt/aitbc
- ✅ Replace Gitea URLs with GitHub for public-facing docs
- ✅ Clarify CI/CD: GitHub for public, Gitea for dev
- ✅ Add comprehensive troubleshooting sections for services and GPU detection
- ✅ Fix log directory documentation: /var/log/aitbc/ (not symlink)
- ✅ Update port references across documentation to match SERVICE_PORTS.md
- ✅ Remove deprecated monolithic multi-node blockchain setup workflow
- ✅ Rename openclaw references to hermes across documentation
- ✅ Add devops skills for software setup, deployment, node setup, and management

### Infrastructure Improvements
- ✅ Replace Prometheus/S3 backup monitoring with systemd journal-based monitoring
- ✅ Add simple mail alert script for backup monitoring
- ✅ Update backup security practices to use GPG encryption and filesystem permissions
- ✅ Change backup configuration from S3 to local storage paths
- ✅ Update .gitignore paths from infra/ to scripts/deployment/
- ✅ Remove sudo from systemd commands across documentation
- ✅ Remove S3 storage references from client documentation
- ✅ Update setup script path references to scripts/deployment/setup.sh
- ✅ Integrate requirements management system into setup.sh
- ✅ Optimize setup.sh to use pre-configured example configs
- ✅ Fix P2P port in deploy-integrated-blockchain-node.sh from 8001 to 7070

### Code Quality
- ✅ Fix transaction service to remove ed25519 dependency for Python 3.13 compatibility
- ✅ Rename 'schema' field to 'graph_schema' in knowledge graph models (avoid Python keyword)
- ✅ Fix accounts.py: add missing fastapi status import
- ✅ Fix console.logger bug in utils error handling
- ✅ Add missing click import to unified_cli.py
- ✅ Rename FastAPI app instance from 'app' to 'wallet_app' in simple_daemon.py
- ✅ Fix sync_cli.py: remove invalid import_url kwarg and add logger init
- ✅ Update genesis verify to use chain-specific database path with legacy fallback
- ✅ Remove pytest from pre-commit hooks, run in CI instead
- ✅ Remove redundant requirements files and consolidate dependency management

## 🔒 Security Improvements

### Credential Management
- Removed development validator keys file containing test credentials
- Moved JWT secret from inline environment variable to external secrets file for edge-api service
- Added argon2-cffi dependency and coordinator API key loading to keystore secrets
- Updated backup security practices to use GPG encryption and filesystem permissions

### Configuration Security
- Removed hardcoded chain_id, node_id, and island_id values
- Require explicit environment variable configuration for multi-environment deployment
- chain_id validation to P2P handshake
- Enforce island_id matching for non-hub nodes

### Dependency Security
- Fixed transaction service to remove ed25519 dependency for Python 3.13 compatibility
- Removed pytest from pre-commit hooks to reduce attack surface

## 🤖 Hermes Agent Integration

### Blockchain Operations
Hermes agents can now perform on-chain operations via CLI commands:

**Staking:**
- `aitbc wallet stake <amount> --duration <days> --wallet <wallet>` - Stake tokens
- `aitbc wallet unstake <stake_id> --wallet <wallet>` - Unstake tokens
- `aitbc wallet staking-info --wallet <wallet>` - Query staking info

**Agent Identity:**
- `aitbc agent register-identity <agent_id> <agent_address> --display-name <name>` - Register identity
- `aitbc agent get-identity <agent_id>` - Query identity
- `aitbc agent verify-identity <agent_id> <verifier_address>` - Verify identity

**Governance:**
- `aitbc operations governance vote <proposal_id> --vote <for|against> --wallet <wallet>` - Cast vote
- `aitbc operations governance proposal --proposal-id <id> --title <title> --description <desc> --wallet <wallet>` - Create proposal
- `aitbc operations governance get-proposal <proposal_id>` - Query proposal

**GPU Resources:**
- `aitbc gpu-onchain register <gpu_id> --miner-id <id> --model <model> --memory-gb <gb> --price-per-hour <price> --wallet <wallet>` - Register GPU
- `aitbc gpu-onchain query <gpu_id>` - Query GPU registration
- `aitbc gpu-onchain list --status <status>` - List GPUs
- `aitbc gpu-onchain allocate <gpu_id> --client-id <address> --duration-hours <hours> --total-cost <cost> --wallet <wallet>` - Allocate GPU
- `aitbc gpu-onchain allocations <gpu_id>` - Query GPU allocations

### RPC Endpoints
All blockchain integrations use hub RPC at `hub.aitbc.bubuit.net:8006`:
- `/rpc/staking/stake`, `/rpc/staking/unstake`, `/rpc/staking/{address}`
- `/rpc/identity/register`, `/rpc/identity/{agent_id}`, `/rpc/identity/verify`
- `/rpc/governance/vote`, `/rpc/governance/proposal`, `/rpc/governance/proposal/{proposal_id}`
- `/rpc/gpu/register`, `/rpc/gpu/info/{gpu_id}`, `/rpc/gpus`, `/rpc/gpu/allocate`, `/rpc/gpu/allocations/{gpu_id}`

### Documentation
New Hermes blockchain documentation split into topic files:
- `/docs/hermes/blockchain/overview.md` - Main overview and getting started
- `/docs/hermes/blockchain/staking.md` - Staking integration details
- `/docs/hermes/blockchain/identity.md` - Agent identity integration details
- `/docs/hermes/blockchain/governance.md` - Governance integration details
- `/docs/hermes/blockchain/gpu-resources.md` - GPU resource tracking details
- `/docs/hermes/blockchain/verification.md` - Verification methods
- `/docs/hermes/blockchain/troubleshooting.md` - Common issues and solutions
- `/docs/hermes/blockchain/architecture.md` - System architecture notes
- `/docs/hermes/blockchain/best-practices.md` - Recommended practices

## 🔧 Configuration Changes

### Environment Variables
New required environment variables for production deployment:

**CHAIN_ID**
- Previously: Hardcoded default values (ait-testnet, ait-hub.aitbc.bubuit.net)
- Now: Required via environment variable with fallback to ait-hub.aitbc.bubuit.net
- Location: `/etc/aitbc/blockchain.env`

**NODE_ID**
- Previously: Hardcoded default value
- Now: Required via environment variable
- Location: `/etc/aitbc/node.env`

**ISLAND_ID**
- Previously: Hardcoded default value
- Now: Required via environment variable
- Location: `/etc/aitbc/node.env`

### Configuration Files
- Standardized to use `blockchain.env` and `node.env` instead of `.env`
- Updated config file path in README: .env -> blockchain.env
- Optimize setup.sh to use pre-configured example configs

## 📊 GPU Resource Tracking Architecture

### Hybrid Architecture
The GPU resource tracking uses a hybrid architecture:

**On-Chain (Immutable Proof):**
- GPU registration with immutable specs
- GPU allocation records
- Transaction history

**Off-Chain (Operational Data):**
- Real-time GPU status
- Performance metrics
- Heartbeat monitoring
- Dynamic availability updates

### GPU Service Integration
The GPU service registers GPUs locally first, then attempts blockchain registration asynchronously:
1. Register GPU in local database (GPURegistry table)
2. Asynchronously post registration to blockchain RPC
3. Log success or failure (non-blocking)
4. If blockchain registration fails, GPU remains operational locally
5. CLI can be used for explicit on-chain registration

## 📝 Documentation Updates

### Path Standardization
- Update documentation paths from `/home/oib/windsurf/aitbc` to `/opt/aitbc`
- Update setup script path references to `scripts/deployment/setup.sh`
- Update .gitignore paths from `infra/` to `scripts/deployment/`
- Update .gitignore paths from `scripts/deploy` to `scripts/deployment`

### GitHub Migration
- Replace Gitea URLs with GitHub for public-facing docs
- Clarify CI/CD: GitHub for public, Gitea for dev
- Update repository URLs from Gitea to GitHub

### Troubleshooting
- Add comprehensive troubleshooting sections for services not running
- Add GPU detection validation across AI operations, basic operations, and blockchain troubleshooting
- Fix log directory documentation: `/var/log/aitbc/` (not symlink to `/var/lib/aitbc/logs/`)

### Port References
- Update port references across documentation to match SERVICE_PORTS.md
- Fix P2P port in deploy-integrated-blockchain-node.sh from 8001 to 7070
- Update port references in setup.sh and SETUP.md

### Documentation Cleanup
- Remove deprecated monolithic multi-node blockchain setup workflow
- Rename openclaw references to hermes across documentation
- Remove docker-compose examples in favor of systemd service management
- Remove outdated environment setup and training materials
- Remove scenarios documentation references

## 🚀 Infrastructure Improvements

### Backup Monitoring
- Replace Prometheus/S3 backup monitoring with systemd journal-based monitoring
- Add simple mail alert script for backup monitoring
- Update backup security practices to use GPG encryption and filesystem permissions
- Change backup configuration from S3 to local storage paths

### Setup Script
- Integrate requirements management system into setup.sh
- Optimize setup.sh to use pre-configured example configs
- Remove redundant sudo commands from setup.sh
- Use sudo bash - for Node.js installation
- Add explicit progress logging to setup.sh for hermes agent visibility

### Documentation Structure
- Update codebase structure documentation to reflect deployment script reorganization
- Remove sudo from systemd commands across documentation
- Remove S3 storage references from client documentation
- Deprecate sudoers permission setup guide

## 🐛 Bug Fixes

### CLI Fixes
- Fix console.logger bug in utils error handling
- Add missing click import to unified_cli.py
- Fix CLI package structure and dependencies
- Fix sync_cli.py: remove invalid import_url kwarg and add logger init
- Rename FastAPI app instance from 'app' to 'wallet_app' in simple_daemon.py

### Blockchain Fixes
- Update genesis verify to use chain-specific database path with legacy fallback
- Fix accounts.py: add missing fastapi status import
- Add graceful fallback to simulated data for account and network commands when RPC unavailable

### Documentation Fixes
- Fix config file path in README: .env -> blockchain.env
- Fix log directory symlink misconceptions
- Fix port references in setup.sh and SETUP.md
- Fix false ignored files: track pre-commit and yamllint configs

### Code Quality Fixes
- Fix transaction service to remove ed25519 dependency for Python 3.13 compatibility
- Rename 'schema' field to 'graph_schema' in knowledge graph models to avoid Python keyword conflict
- Fix P2P port in deploy-integrated-blockchain-node.sh from 8001 to 7070

## 📦 Dependency Management

### Requirements Consolidation
- Remove redundant requirements files and consolidate dependency management to central system
- Add requirements-minimal.txt for minimal dependency installation
- Integrate requirements management system into setup.sh
- Add reference to requirements-dev.txt in testing optional dependencies to avoid duplication
- Remove zk-circuits package-lock.json file

### Pre-commit Hooks
- Remove pytest from pre-commit hooks, run in CI instead
- Fix false ignored files: track pre-commit and yamllint configs

## 🔄 Breaking Changes

### Configuration
- **CHAIN_ID, NODE_ID, ISLAND_ID now required via environment variables** - Previously had hardcoded defaults
- **Config file names changed** - Use `blockchain.env` and `node.env` instead of `.env`
- **chain_id fallback changed** - From `ait-testnet` to `ait-hub.aitbc.bubuit.net`

### Documentation
- **Documentation paths changed** - From `/home/oib/windsurf/aitbc` to `/opt/aitbc`
- **Setup script path changed** - From `scripts/setup.sh` to `scripts/deployment/setup.sh`
- **Deprecated workflows removed** - Monolithic multi-node blockchain setup workflow

### CLI
- **CLI package structure updated** - May require CLI reinstallation or path updates

## 📈 Migration Guide

### Configuration Migration
1. Update `/etc/aitbc/blockchain.env` to include CHAIN_ID
2. Update `/etc/aitbc/node.env` to include NODE_ID and ISLAND_ID
3. Rename `.env` files to `blockchain.env` or `node.env` as appropriate
4. Restart services after configuration changes

### Documentation Migration
1. Update any hardcoded paths from `/home/oib/windsurf/aitbc` to `/opt/aitbc`
2. Update setup script references to `scripts/deployment/setup.sh`
3. Use modular documentation structure instead of monolithic multi-node setup workflow

### CLI Migration
1. Reinstall CLI if package structure changes affect your installation
2. Update any scripts using hardcoded chain_id to use environment variables

## ✅ Testing

### Manual Testing
- Test Hermes agent blockchain integrations (staking, identity, governance, GPU tracking)
- Verify environment variable configuration for chain_id, node_id, island_id
- Test GPU registration and allocation on blockchain
- Verify P2P handshake with chain_id validation
- Test CLI command groups (70+ total)
- Verify setup.sh with new requirements management system

### Automated Testing
- CI/CD pipeline updated to run pytest instead of pre-commit hooks
- Pre-commit hooks simplified to reduce attack surface

## 🎯 Success Criteria

- ✅ Hermes agents can perform on-chain operations via CLI
- ✅ All hardcoded configuration values replaced with environment variables
- ✅ GPU resource tracking functional with hybrid architecture
- ✅ Documentation updated and cross-referenced
- ✅ Security improvements implemented (credential removal, JWT secrets)
- ✅ Setup script improved with requirements management
- ✅ CLI expanded to 70+ command groups
- ✅ Breaking changes documented and migration guide provided

## 🚀 Next Steps

### v0.4.3 Planning
- Enhanced Hermes agent autonomy features
- Advanced GPU marketplace features
- Additional security hardening

### Documentation
- Continue expanding Hermes agent documentation
- Add more troubleshooting guides
- Create video tutorials for key features
- Update API documentation

---

*Last Updated: 2026-06-01*  
*Version: 0.4.2*  
*Status: Released*
