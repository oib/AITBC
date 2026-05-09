# AITBC Release v0.3.4

**Date**: May 9, 2026  
**Status**: ✅ Released  
**Scope**: Hermes agent system migration from OpenClaw, blockchain sync improvements, security vulnerability fixes, documentation cleanup

## 🎉 Release Summary

This release completes the migration from OpenClaw to Hermes agent system, resolves critical blockchain synchronization issues for ait-testnet chain, fixes high-severity security vulnerabilities, and cleans up legacy documentation content. The Hermes migration provides a more robust and scalable agent coordination framework for autonomous operations.

## 🔄 Hermes Migration from OpenClaw

### ✅ **Agent System Migration**
- **Migration**: Completed transition from OpenClaw to Hermes agent coordination system
- **Scope**: 
  - Updated agent skill documentation to reference Hermes-specific implementations
  - Normalized archived OpenClaw docs to point to current active Hermes skill files
  - Updated agent communication patterns for Hermes architecture
- **New Hermes Skills**:
  - `openclaw-agent-communicator.md` - Agent communication protocols
  - `openclaw-session-manager.md` - Session management for agent operations
  - `openclaw-coordination-orchestrator.md` - Multi-agent coordination
  - `openclaw-performance-optimizer.md` - Performance optimization
  - `openclaw-error-handler.md` - Error handling and recovery
  - `openclaw-agent-testing-skill.md` - Agent testing capabilities
- **Documentation Updates**:
  - Archived OpenClaw docs now reference current active skill files
  - Updated agent training workflows for Hermes compatibility
  - Normalized skill documentation structure

### ✅ **Cross-Node Agent Communication**
- **Enhancement**: Improved agent-to-agent communication across blockchain nodes
- **Implementation**: Hermes-based communication patterns for ait-testnet chain
- **Features**:
  - Blockchain-based agent coordination via AITBC
  - Secure message passing between nodes
  - Distributed decision making
  - Fault-tolerant agent operations

## 🐛 Bug Fixes

### ✅ **ait-testnet Blockchain Synchronization**
- **Issue**: Persistent "Unhandled import case" error at block height 1 on ait-testnet chain
- **Root Cause**: session_scope was not using chain-specific databases, causing cross-chain data corruption where ait-testnet blocks referenced ait-mainnet genesis block as parent
- **Fix**:
  - Modified main.py to pass chain_id to session_factory lambda functions
  - Fixed session_scope usage in three locations: _ensure_genesis_for_chains, block import, and proposer initialization
  - Ensured chain-specific database connections for all chains
  - Cleaned cross-chain corruption from both aitbc and aitbc1 databases
- **Result**: ait-testnet sync now works correctly with proper chain-specific database isolation
- **Files Modified**:
  - apps/blockchain-node/src/aitbc_chain/main.py
  - Database cleanup on aitbc and aitbc1

### ✅ **aitbc1 RPC Bootstrap Configuration**
- **Issue**: aitbc1 was attempting to bootstrap from itself (http://aitbc1:8006), causing 404 errors
- **Root Cause**: default_peer_rpc_url in /etc/aitbc/blockchain.env pointed to aitbc1 itself
- **Fix**:
  - Changed default_peer_rpc_url from http://aitbc1:8006 to http://aitbc:8006
  - Cleared corrupted ait-testnet blocks from aitbc1 database
  - Rebootstrapped aitbc1's ait-testnet chain from aitbc via RPC
- **Result**: aitbc1 successfully bootstrapped ait-testnet genesis block and is now producing blocks correctly
- **Files Modified**:
  - /etc/aitbc/blockchain.env on aitbc1
  - Database cleanup on aitbc1

## 🔒 Security

### ✅ **High-Severity Vulnerability Fixes**
- **python-multipart**: Updated from >=0.0.24 to >=0.0.27 (fixes 3 DoS alerts)
  - Vulnerability: Denial of Service via unbounded multipart part headers
  - Severity: High
  - Fixed in: requirements.txt, pyproject.toml, coordinator-api requirements
- **starlette**: Updated from >=0.27.0 to >=0.49.1 (fixes 1 O(n^2) DoS alert)
  - Vulnerability: O(n^2) DoS via Range header merging in FileResponse
  - Severity: High
  - Fixed in: requirements.txt, pyproject.toml, aitbc-core
- **Result**: 4 of 11 high-severity security vulnerabilities resolved
- **Files Modified**:
  - requirements.txt
  - pyproject.toml
  - apps/coordinator-api/src/app/services/multi_language/requirements.txt
  - packages/py/aitbc-core/pyproject.toml

## 📝 Documentation

### ✅ **Legacy Content Cleanup**
- **Cleanup**: Removed legacy/deprecated references from main documentation
- **Changes**:
  - Removed legacy Coordinator API reference from README.md
  - Removed deprecated Wallet Fund entry from GLOSSARY.md
  - Updated shell scripts status from deprecated to backward compatibility in ENVIRONMENT_SETUP.md
  - Removed deprecated faucet setup label from WALLET_FUNDING.md
  - Removed legacy human support section from AGENT_INDEX.md
- **Result**: Main documentation now contains current, up-to-date references
- **Files Modified**:
  - docs/README.md
  - docs/GLOSSARY.md
  - docs/agent-training/ENVIRONMENT_SETUP.md
  - docs/agent-training/WALLET_FUNDING.md
  - docs/agents/AGENT_INDEX.md

### ✅ **Archive Organization**
- **Preserved**: docs/archive/ directory maintained as historical documentation
- **Structure**: 228 items organized in 10 categories for easy access
- **Purpose**: Historical context, decision tracking, problem solving reference

## 🚀 Deployment

### ✅ **Multi-Node Deployment**
- Committed and pushed code changes to git
- Applied database isolation fixes to aitbc and aitbc1
- Configured aitbc1 RPC bootstrap from aitbc
- Restarted blockchain-node services on affected nodes
- Verified ait-testnet sync across nodes

### ✅ **GitHub Milestone Push**
- Pushed commits to GitHub as milestone (commit a9adcc17)
- Pushed security vulnerability fixes (commit d26d937f)
- Pushed documentation cleanup (commit c43ae7fa)

## 📊 Verification

### ✅ **ait-testnet Sync Verification**
- aitbc: Successfully bootstrapped ait-testnet genesis block (0xe005315ab8c2ffa06fa3c8048ed8d0012dc54fa3c970d7a6e0a625a241804f69)
- aitbc1: Successfully bootstrapped via RPC from aitbc, producing blocks correctly
- Chain-specific database isolation working correctly
- No cross-chain data corruption detected

### ✅ **Security Verification**
- python-multipart updated to 0.0.27 in venv
- starlette already at 1.0.0 (newer than 0.49.1)
- All services running with updated dependencies
- Coordinator API health check responding
- Blockchain RPC endpoint responding

### ✅ **Hermes Migration Verification**
- Archived OpenClaw docs normalized to point to current active skills
- Hermes skill documentation updated and accessible
- Agent coordination workflows updated for Hermes compatibility

## 📚 Documentation

### ✅ **Release Notes**
- Created comprehensive release notes for v0.3.4
- Updated releases README.md with new version
- Updated pyproject.toml version to v0.3.4

## 🔧 Technical Details

### **Database Isolation Architecture**
- **session_scope**: Now accepts chain_id parameter for chain-specific database connections
- **Implementation**: Lambda functions pass chain_id to session_factory
- **Benefits**: Prevents cross-chain data corruption, enables proper multi-chain support
- **Chains**: ait-mainnet, ait-testnet now use separate databases

### **RPC Bootstrap Architecture**
- **Genesis Bootstrap**: Fetches genesis block from trusted peer via RPC
- **Configuration**: default_peer_rpc_url points to bootstrap source
- **Fallback**: Local genesis creation if RPC bootstrap fails
- **Chain-Specific**: Each chain bootstraps independently

### **Hermes Agent System**
- **Architecture**: Distributed agent coordination via blockchain
- **Communication**: Secure message passing between nodes
- **Coordination**: Multi-agent decision making and task distribution
- **Migration**: Complete transition from OpenClaw framework

## 📋 Migration Notes

### **For Multi-Chain Deployments**
1. Ensure session_scope is called with chain_id parameter
2. Configure chain-specific database paths
3. Set appropriate default_peer_rpc_url for each chain
4. Verify chain isolation after deployment
5. Monitor for cross-chain data corruption

### **For Security**
1. Update python-multipart to >=0.0.27
2. Update starlette to >=0.49.1
3. Run pip-audit to verify no vulnerabilities
4. Push changes to GitHub to clear Dependabot alerts

### **For Hermes Migration**
1. Update agent skill references to Hermes equivalents
2. Review agent coordination workflows for compatibility
3. Update training documentation for Hermes patterns
4. Test agent communication across nodes
5. Monitor agent operations for Hermes-specific issues

---

*Last updated: 2026-05-09*  
*Version: 0.3.4*  
*Status: Released*
