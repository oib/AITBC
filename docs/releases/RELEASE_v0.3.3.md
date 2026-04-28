# AITBC Release v0.3.3

**Date**: April 28, 2026  
**Status**: ✅ Released  
**Scope**: Blockchain synchronization fix, multi-node configuration, security vulnerability resolution

## 🎉 Release Summary

This release resolves critical blockchain synchronization issues across all nodes (aitbc, aitbc1, gitea-runner), fixes a high-severity security vulnerability (CVE-2024-23342), and standardizes multi-node configuration for improved reliability and security.

## 🐛 Bug Fixes

### ✅ **Blockchain Synchronization Fix**
- **Issue**: aitbc1 was not receiving blocks from aitbc via Redis gossip, causing sync gap to increase
- **Root Cause**: blockchain-node service was running `combined_main` which caused `app.py` to overwrite the gossip backend initialized by `main.py` after subscribers were set up
- **Fix**: 
  - Changed blockchain-node wrapper to run `main.py` only instead of `combined_main`
  - Separated blockchain-node (main.py - gossip subscribers) from blockchain-rpc (app.py - RPC API)
  - Applied fix to both aitbc1 and gitea-runner
- **Result**: All three nodes (aitbc, aitbc1, gitea-runner) now sync correctly at the same block height
- **Files Modified**:
  - scripts/wrappers/aitbc-blockchain-node-wrapper.py

### ✅ **Chain Sync Configuration Fixes**
- **Issue**: Chain sync wrapper defaults were incorrectly configured
- **Fix**: 
  - Fixed aitbc chain_sync wrapper defaults to use 127.0.0.1 (local) instead of 10.1.223.40
  - Fixed aitbc1 chain_sync wrapper import_host to use 127.0.0.1
- **Files Modified**:
  - scripts/wrappers/aitbc-blockchain-sync-wrapper.py

## 🔧 Multi-Node Configuration

### ✅ **Gitea-Runner Integration**
- **Issue**: gitea-runner was on ait-devnet chain (different from aitbc/aitbc1's ait-mainnet)
- **Fix**:
  - Updated gitea-runner configuration to use ait-mainnet chain
  - Set island_id to ait-mainnet-island (same as aitbc/aitbc1)
  - Added default_peer_rpc_url to point to aitbc
  - Copied database from aitbc to bootstrap sync
- **Result**: gitea-runner now syncs with aitbc/aitbc1 on the same chain and island
- **Files Modified**:
  - /etc/aitbc/.env on gitea-runner

### ✅ **P2P Connectivity Restoration**
- Restored P2P connectivity between nodes
- Configured both nodes to use same island ID for P2P sync
- Set default_peer_rpc_url on aitbc1 to point to aitbc

## 🔒 Security

### ✅ **High-Severity Vulnerability Fix (CVE-2024-23342)**
- **Issue**: python-ecdsa vulnerable to Minerva timing attack on P-256 curve
- **Severity**: High (CVSS 7.4)
- **Root Cause**: python-ecdsa project considers side channel attacks out of scope with no planned fix
- **Fix**:
  - Removed ecdsa dependency from requirements.txt (not installed or used in code)
  - Regenerated poetry.lock to clear transitive dependencies
- **Result**: Dependabot alert resolved, no vulnerability reported after fix
- **Files Modified**:
  - requirements.txt
  - poetry.lock

## 📝 Configuration

### ✅ **PoA Block Production**
- Added supported_chains to aitbc .env to enable PoA proposer
- Removed incorrect proposer_id from aitbc .env
- Added enable_block_production=true to .env to force enable PoA proposer
- Removed enable_block_production=false from RPC service file

### ✅ **Logging Enhancements**
- Added logging to PoA proposer to track broadcast calls
- Added logging to main.py to track block processing task
- Added logging to broadcast subscription task
- Added logging to subscribe method
- Added logging to RPC service for gossip backend initialization

## 🚀 Deployment

### ✅ **Multi-Node Deployment**
- Committed and pushed code changes to git
- Pulled code changes on aitbc1 and gitea-runner
- Restarted blockchain-node services on all nodes
- Verified block synchronization across all nodes

### ✅ **GitHub Milestone Push**
- Pushed commits to GitHub as milestone (commit 7314d2a3)
- Pushed vulnerability fix to GitHub (commit cb85a6ce)

## 📊 Verification

### ✅ **Sync Verification**
- All three nodes verified at same block height (20003483) with same hash
- Gap of 0 blocks between all nodes
- Stable sync maintained over multiple block production cycles

### ✅ **Security Verification**
- GitHub Dependabot alert 509 resolved
- No vulnerabilities reported after fix
- Local audits (pip-audit, npm-audit) confirmed no vulnerabilities

## 📚 Documentation

### ✅ **Release Notes**
- Created comprehensive release notes for v0.3.3
- Updated releases README.md with new version
- Updated pyproject.toml version to v0.3.3

## 🔧 Technical Details

### **Gossip Backend Architecture**
- **BroadcastGossipBackend**: Uses Redis Pub/Sub for cross-node communication
- **InMemoryGossipBackend**: Local in-memory gossip for single-node scenarios
- **Backend Conflict**: Running both main.py and app.py in same process causes backend overwrite
- **Solution**: Separate services - blockchain-node (main.py) and blockchain-rpc (app.py)

### **Node Configuration**
- **aitbc**: Leader node with PoA block production enabled
- **aitbc1**: Follower node with gossip subscribers
- **gitea-runner**: CI runner node with gossip subscribers
- **Chain**: ait-mainnet
- **Island**: ait-mainnet-island
- **Redis**: redis://10.1.223.93:6379

## 📋 Migration Notes

### **For Multi-Node Deployments**
1. Update blockchain-node wrapper to run main.py only
2. Restart blockchain-node service
3. Verify gossip backend initialization in logs
4. Verify block reception and import in logs
5. Check block height synchronization with leader node

### **For Security**
1. Remove ecdsa from requirements.txt if present
2. Regenerate poetry.lock
3. Run pip-audit to verify no vulnerabilities
4. Push changes to GitHub to clear Dependabot alerts

---

*Last updated: 2026-04-28*  
*Version: 0.3.3*  
*Status: Released*
