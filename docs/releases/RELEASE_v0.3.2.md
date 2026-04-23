# AITBC Release v0.3.2

**Date**: April 23, 2026  
**Status**: ✅ Released  
**Scope**: Test infrastructure improvements, CLI refactoring, documentation reorganization, CI/CD standardization, service consolidation, environment configuration unification

## 🎉 Release Summary

This release focuses on resolving pytest import conflicts through test file naming standardization, completing CLI handler refactoring, reorganizing documentation structure, standardizing CI/CD workflows, consolidating services, and unifying environment configuration for improved maintainability and operational efficiency.

## 🐛 Bug Fixes

### ✅ **Pytest Import Conflicts Resolution**
- **Issue**: Pytest failed to collect tests across all apps due to identical test filenames (test_unit.py, test_integration.py, test_edge_cases.py) causing module naming collisions
- **Root Cause**: Multiple apps with identical test file names resolved to the same module names during test discovery
- **Fix**: 
  - Renamed all 58 test files across 21 apps to use app-specific suffixes (e.g., test_unit_marketplace.py, test_integration_ai_engine.py)
  - Hyphenated app names converted to underscores (ai-engine → ai_engine)
  - Updated test infrastructure documentation with new naming convention
  - Fixed sys.path manipulation in all test files
- **Files Modified**:
  - All test files in apps/*/tests/ directories
  - docs/test-infrastructure.md
  - tests/conftest.py

## 🧪 Test Infrastructure

### ✅ **Test File Naming Standardization**
- **New Convention**: `test_<type>_<app_name>.py`
- **Benefits**: 
  - Resolves pytest module naming conflicts
  - Enables running all app tests simultaneously
  - Improves test discovery and organization
- **Coverage**: 58 test files renamed across 21 apps

### ✅ **Test Documentation Updates**
- Updated test infrastructure documentation with new naming convention
- Added import conflict resolution guidance
- Updated directory structure documentation
- Updated running tests examples

## 🔧 CLI Improvements

### ✅ **CLI Handler Refactoring Completion**
- **Bridge Handlers**: Moved bridge-related commands to cli/handlers/bridge.py
- **Account Handlers**: Moved account-related commands to cli/handlers/account.py
- **Benefits**: Improved modularity and maintainability of CLI code
- **Files Modified**:
  - cli/unified_cli.py
  - cli/handlers/bridge.py
  - cli/handlers/account.py

## 📚 Documentation Reorganization

### ✅ **Directory Structure Cleanup**
- **Merged**: security/ directory into docs/ (2 files moved)
- **Removed**: Empty static/ directory
- **Organized**: Documentation into logical subdirectories:
  - docs/releases/ - Release notes
  - docs/security/ - Security documentation
  - docs/testing/ - Testing documentation
  - docs/nodes/ - Node-specific documentation
  - docs/openclaw/ - OpenClaw documentation
- **Benefits**: Improved documentation organization and discoverability

## 🔒 Security

### ✅ **Security Documentation Consolidation**
- Moved SECURITY_FIXES_SUMMARY.md to docs/security/
- Moved SECURITY_VULNERABILITIES.md to docs/security/
- Moved SECURITY_VULNERABILITY_REPORT.md to docs/security/
- Removed redundant security/ directory

## 📝 Node Documentation

### ✅ **Node-Specific Documentation**
- Moved AITBC1_TEST_COMMANDS.md to docs/nodes/
- Moved AITBC1_UPDATED_COMMANDS.md to docs/nodes/
- Benefits: Clear separation of node-specific documentation

## 🤖 OpenClaw Documentation

### ✅ **OpenClaw Documentation Organization**
- Moved OPENCLAW_AITBC_MASTERY_PLAN_IMPLEMENTATION_STATUS.md to docs/openclaw/
- Benefits: Dedicated location for OpenClaw-related documentation

## 🔄 Testing Documentation

### ✅ **Testing Documentation Organization**
- Moved test-infrastructure.md to docs/testing/
- Benefits: Centralized testing documentation

## 🚀 CI/CD Improvements

### ✅ **CI/CD Standardization**
- **Standardized Python venv setup**: Created shared setup-python-venv.sh script for all workflows
- **Venv caching**: Implemented robust venv caching with corruption detection and auto-rebuild
- **Security scanning optimization**: Changed to only check changed files on push/PR for faster feedback
- **Service host discovery**: Added automatic API host detection for endpoint tests
- **Strict exit codes**: Enforced proper exit codes in all workflow tests
- **Workflow fixes**: Fixed venv activation, service lifecycle management, and dependency issues
- **Files Modified**:
  - scripts/ci/setup-python-venv.sh
  - .gitea/workflows/*.yml (multiple workflows updated)

### ✅ **Test Matrix Optimization**
- Removed zk-circuits from test matrix (reduces CI load)
- Made integration tests gracefully skip when services unavailable
- Added asyncio configuration to Python tests

## 🔧 Service Consolidation

### ✅ **Service Directory Restructuring**
- **Consolidated service scripts**: Moved all service scripts into apps directories
- **Removed legacy folders**: Removed legacy folder and rewired imports
- **GPU acceleration reorganization**: Moved gpu_acceleration to dev directory
- **GPU research reorganization**: Moved gpu_zk_research to dev directory
- **Marketplace unification**: Removed duplicate GPU marketplace, kept single marketplace on port 8007
- **Benefits**: Clearer service organization and reduced duplication

### ✅ **Environment Configuration Unification**
- **Unified environment files**: Split global (.env) from node-specific (node.env)
- **Removed redundant files**: Removed production.env and blockchain.env
- **Moved hardcoded variables**: Moved from systemd services to environment files
- **Benefits**: Single source of truth for configuration

## 🔧 Systemd Service Improvements

### ✅ **Systemd Configuration Standardization**
- **Venv Python interpreter**: Changed all services to use venv Python instead of system python3
- **Security settings adjustment**: Removed restrictive ProtectSystem settings for SQLite WAL mode compatibility
- **Environment consolidation**: Moved EnvironmentFile directives from drop-in files to main service files
- **Syslog identifiers**: Updated service names for better log identification
- **Database permissions**: Changed from restrictive owner-only to permissive read/write
- **Benefits**: Consistent service configuration and improved database compatibility

## 🏗️ Blockchain Node Improvements

### ✅ **Chain Import/Export Enhancements**
- **Duplicate filtering**: Added duplicate block filtering during import
- **Metadata preservation**: Added metadata fields preservation
- **Chain-scoped deletion**: Added chain-scoped deletion capability
- **Hash conflict detection**: Added hash conflict detection and cleanup
- **Account chain_id preservation**: Fixed chain import to preserve account chain_id
- **RPC endpoints**: Added manual chain export/import RPC endpoints
- **Files Modified**:
  - apps/blockchain-node/src/aitbc_chain/rpc/contract_service.py
  - apps/blockchain-node/src/aitbc_chain/sync.py

### ✅ **Consensus and State Root**
- **State root integration**: Integrated state root computation with state transition system
- **Error handling**: Added error handling for state root computation
- **Validation**: Added state root validation

### ✅ **Network and RPC Improvements**
- **Network command**: Added live RPC integration with multi-node probing
- **p2p_node_id configuration**: Added p2p_node_id configuration setting
- **Block production**: Fixed RPC block production override
- **PoA proposer**: Commented out mempool empty check for continuous block creation during testing

## 💰 CLI Enhancements

### ✅ **Marketplace Integration**
- **Buy/orders commands**: Added marketplace buy and orders commands
- **Marketplace transaction RPC**: Added marketplace transaction RPC endpoint
- **Password-free transactions**: Implemented password-free transactions for marketplace
- **Wallet balance fix**: Fixed CLI wallet balance to query blockchain database
- **RPC account endpoint**: Added RPC account endpoint for balance queries

### ✅ **Transaction Nonce Fix**
- **Blockchain account state**: Fixed CLI transaction nonce to use blockchain account state instead of timestamp

## 🔒 Security Improvements

### ✅ **Security Scanning**
- **Timeout additions**: Added timeouts to HTTP requests
- **Temp directory usage**: Fixed temp directory usage
- **High-severity fixes**: Fixed high-severity security issues
- **Medium-severity fixes**: Fixed medium-severity security issues
- **Optimized scanning**: Changed to only check changed files for faster feedback

### ✅ **Dependency Fixes**
- **Ethers conflict**: Removed @typechain/hardhat and typechain to resolve ethers v5/v6 conflict
- **Hardhat toolbox**: Pinned hardhat-toolbox to exact hh2 version
- **Manual installation**: Removed manual hardhat-ignition installation causing dependency conflict

## 📚 Documentation Updates

### ✅ **OpenClaw Documentation**
- **Master index**: Added OpenClaw master index
- **Coordination demo**: Added OpenClaw coordination demo
- **Mastery plan**: Updated mastery plan to v2.0 with multi-chain support, hub/follower topology, and workflow integration

### ✅ **Documentation Fixes**
- **Markdown formatting**: Fixed markdown formatting in DOTENV_DISCIPLINE.md
- **Version update**: Updated version to v0.3.1 in documentation
