# AITBC v0.4.15 Release Notes

**Date**: June 9, 2026
**Status**: ✅ Released
**Scope**: Codebase Cleanup, Documentation Updates, UTF-8 Error Fix, API Updates, Bridge Enhancements
**Priority**: Medium
**Chain**: ait-hub.aitbc.bubuit.net

## 🎯 Overview

AITBC v0.4.15 focuses on codebase cleanup, infrastructure updates, and feature enhancements. This release removes unused package directories, updates documentation to reflect the current structure, fixes UTF-8 marshaling errors, updates the coordinator API port, enhances the wallet CLI to use the wallet service API, and improves the bridge API with price endpoints and deposit validation.

## 📊 Implementation Status

### ✅ Phase 1: Package Directory Cleanup

**1.1 Removed GitHub Packages Distribution**
- ✅ Deleted `/opt/aitbc/packages/github` directory
  - Removed installation scripts (install.sh, install-macos.sh, install-windows.sh)
  - Removed build scripts (build-*.sh)
  - Removed Debian packages directory (debian-packages/)
  - Removed macOS packages directory (macos-packages/)
  - Removed README and documentation
- ✅ Rationale: No longer providing binary packages for distribution

**1.2 Removed JavaScript SDK**
- ✅ Deleted `/opt/aitbc/packages/js/aitbc-sdk` directory
- ✅ Deleted empty `/opt/aitbc/packages/js` parent directory
- ✅ Rationale: Not actively used; only official frontend is `/opt/aitbc/website` (static HTML)
- ✅ JavaScript SDK was intended for external developers but not integrated into AITBC codebase

**1.3 Removed Solidity Token Package**
- ✅ Deleted `/opt/aitbc/packages/solidity/aitbc-token` directory
- ✅ Deleted empty `/opt/aitbc/packages/solidity` parent directory
- ✅ Rationale: Not used in production; `/opt/aitbc/contracts` is the active contract directory
- ✅ aitbc-token had different AIToken.sol (v0.8.24 with receipt-based minting) vs production v0.8.19
- ✅ Only referenced in documentation and CI/CD tests, not in deployments

### ✅ Phase 2: Documentation Updates

**2.1 Updated Package Documentation**
- ✅ `docs/reference/packages.md`
  - Removed references to `github/` and `js/` packages
  - Removed `solidity/` section
  - Now only lists `py/` packages (aitbc-agent-core, aitbc-agent-sdk, aitbc-crypto, aitbc-sdk)
  - Removed "Publishing guides for GitHub Packages" from purpose section

**2.2 Updated pnpm Setup Documentation**
- ✅ `docs/contracts/PNPM_SETUP.md`
  - Removed aitbc-token from overview
  - Removed aitbc-token-specific `.npmrc` configuration
  - Removed aitbc-token installation and build commands
  - Updated CI/CD section to remove aitbc-token references
  - Now documents only `/opt/aitbc/contracts` as the single Hardhat project

**2.3 Updated Architecture Documentation**
- ✅ `docs/architecture/8_codebase-structure.md`
  - Updated packages/ structure to show only `py/` packages
  - Added aitbc-agent-core and aitbc-agent-sdk to the list
  - Removed solidity/aitbc-token reference
  - Clarified that packages/ contains only Python shared libraries

**2.4 Updated Security Documentation**
- ✅ `docs/security/DEPENDENCY_MONITORING.md`
  - Removed aitbc-token from vulnerability breakdown
  - Updated pnpm workspace references to exclude aitbc-token
  - Removed aitbc-token from monthly review commands
  - Updated total vulnerability count (removed 8 vulnerabilities from aitbc-token)

**2.5 Updated Development Requirements**
- ✅ `docs/development/REQUIREMENTS.md`
  - Removed aitbc-token from monthly review commands
  - Updated npm audit commands to only include contracts/ and zk-circuits

### ✅ Phase 3: Coordinator API Port Update

**3.1 Port Change**
- ✅ Updated coordinator API port from 8011 to 8203
- ✅ Updated all references across codebase to use new port
- ✅ Updated documentation and configuration files
- ✅ Rationale: Port conflict resolution and infrastructure standardization

**3.2 Placeholder Methods**
- ✅ Implemented placeholder methods for coordinator API
- ✅ Updated service configuration to use new port
- ✅ Updated systemd service files and nginx configuration

### ✅ Phase 4: Wallet CLI Enhancements

**4.1 Wallet Service API Integration**
- ✅ Updated wallet CLI to use wallet service API instead of local wallet files
- ✅ Added `get_wallet_client()` helper function for HTTP client initialization
- ✅ Updated wallet balance commands to query wallet service API
- ✅ Updated wallet transactions commands to query wallet service API
- ✅ Renamed history command to transactions
- ✅ Fetch blockchain transactions via RPC using wallet address

**4.2 Bridge Exchange Rate Fix**
- ✅ Fixed bridge price endpoint to use correct `eth_ait_rate_usd` field name
- ✅ Updated bridge routes to use corrected field name
- ✅ 2 files changed, 69 insertions(+), 133 deletions(-)

### ✅ Phase 5: Bridge API Enhancements

**5.1 Price Endpoint**
- ✅ Added `/exchange/price.json` endpoint for AIT/USD price
- ✅ Integrated oracle support with fixed fallback
- ✅ Returns current ETH/USD and AIT/USD prices
- ✅ Provides price history and averages

**5.2 Deposit Validation**
- ✅ Enhanced bridge deposit endpoint with minimum amount validation
- ✅ Added detailed deposit instructions
- ✅ Added AIT amount estimation
- ✅ Improved error handling and validation messages

**5.3 Withdrawal Management**
- ✅ Disabled AIT→ETH withdrawals with 503 status
- ✅ Updated bridge status to show deposit-only direction
- ✅ Rationale: Security measure, withdrawals temporarily disabled

### ✅ Phase 6: Website Cleanup

**6.1 Removed Old Website Structure**
- ✅ Removed old website files (agent/, live_api.py, old CSS/JS)
- ✅ Removed unused 404.html and DEPLOYMENT.md files
- ✅ Removed old nginx-example.conf and systemd-example.service
- ✅ Removed old assets (font-awesome, axios, lucide.js, analytics)
- ✅ 28 files changed, 413 insertions(+), 22179 deletions(-)
- ✅ Rationale: Simplified website structure, removed legacy code

**6.2 Website Updates**
- ✅ Updated website/README.md
- ✅ Updated website/exchange.html with new features
- ✅ Simplified CSS and assets structure
- ✅ Updated favicon.svg

### ✅ Phase 7: UTF-8 Error Fix

**7.1 Removed Corrupted Files**
- ✅ Deleted corrupted files from `/opt/aitbc/contracts`:
  - `/opt/aitbc/contracts/\001` - corrupted filename
  - `/opt/aitbc/contracts/W\241\026...` - corrupted filename with invalid characters
- ✅ Rationale: These files caused "marshal message: string field contains invalid UTF-8" errors
- ✅ Files were likely filesystem artifacts or corrupted entries from previous operations

## 🔧 Files Changed

| File | Change |
|------|--------|
| `packages/github/` | Deleted entire directory (no longer providing packages) |
| `packages/js/aitbc-sdk/` | Deleted entire directory (not actively used) |
| `packages/js/` | Deleted empty parent directory |
| `packages/solidity/aitbc-token/` | Deleted entire directory (not used in production) |
| `packages/solidity/` | Deleted empty parent directory |
| `docs/reference/packages.md` | Removed github/, js/, solidity/ references |
| `docs/contracts/PNPM_SETUP.md` | Removed aitbc-token configuration and commands |
| `docs/architecture/8_codebase-structure.md` | Updated packages/ structure |
| `docs/security/DEPENDENCY_MONITORING.md` | Removed aitbc-token references |
| `docs/development/REQUIREMENTS.md` | Removed aitbc-token from audit commands |
| `contracts/\001` | Deleted corrupted file |
| `contracts/W\241\026...` | Deleted corrupted file |
| **253 files** | Updated coordinator API port from 8011 to 8203 |
| `cli/aitbc_cli/commands/wallet.py` | Updated to use wallet service API (69 insertions, 133 deletions) |
| `apps/wallet/src/app/bridge/bridge_routes.py` | Fixed bridge exchange rate field |
| `apps/exchange/simple_exchange_api.py` | Enhanced bridge API with price endpoint (130 insertions) |
| `website/` | Removed old website structure (28 files, 22179 deletions) |
| `website/exchange.html` | Updated with new features (126 insertions) |
| `website/README.md` | Updated documentation (184 insertions) |
| `website/assets/css/style.css` | Updated CSS (72 insertions) |

## 🗄️ System Status

### Packages Structure (After Cleanup)
```
packages/
└── py/
    ├── aitbc-agent-core/    # Agent integration service with protocol-based dependency injection
    ├── aitbc-agent-sdk/     # Agent SDK for external integrations
    ├── aitbc-crypto/        # Cryptographic primitives (signing, hashing, key derivation)
    └── aitbc-sdk/           # Python SDK for coordinator API (receipt fetching/verification)
```

### Active Contract Directory
- **Single source of truth**: `/opt/aitbc/contracts`
- **Used in**: All CI/CD workflows, production deployments, tests
- **Contains**: AIToken.sol, AgentStaking.sol, AgentMarketplaceV2.sol, TreasuryManager.sol
- **Deployment scripts**: contracts/scripts/deploy-*.js

### Coordinator API Configuration
- **Port**: 8203 (updated from 8011)
- **Purpose**: Main API for job coordination, marketplace, payments, ZK proofs
- **Status**: Running with placeholder methods implemented

### Wallet CLI Configuration
- **Integration**: Uses wallet service API instead of local files
- **Commands**: balance, transactions (renamed from history), bridge
- **API Client**: HTTP client with proper authentication

### Bridge API Configuration
- **Price Endpoint**: `/exchange/price.json` with oracle support
- **Deposit**: Enhanced validation, minimum amount checks, detailed instructions
- **Withdrawal**: Disabled (503 status) - deposit-only direction

### Frontend Structure
- **Official frontend**: `/opt/aitbc/website` (static HTML)
  - index.html - Main landing page
  - exchange.html - ETH-AIT bridge interface
  - assets/css/style.css - Stylesheet
- **No JavaScript SDK**: Removed (not actively used)

## 🔐 Security Summary

### UTF-8 Error Resolution
- **Problem**: "marshal message: string field contains invalid UTF-8" errors when marshaling messages
- **Root Cause**: Corrupted files with invalid UTF-8 characters in contracts directory
- **Fix**: Removed corrupted files (`\001`, `W\241\026...`)
- **Result**: UTF-8 marshaling errors resolved

### Vulnerability Count Update
- **Before**: 35 vulnerabilities (7 low, 15 moderate, 13 high) across contracts, aitbc-token, zk-circuits
- **After**: 27 vulnerabilities (5 low, 11 moderate, 11 high) across contracts, zk-circuits
- **Reduction**: 8 vulnerabilities removed (from deleted aitbc-token package)

### Bridge API Security
- **Withdrawal Disabled**: AIT→ETH withdrawals disabled with 503 status for security
- **Deposit Validation**: Enhanced validation with minimum amount checks
- **Price Oracle**: Integrated oracle support with fixed fallback for price reliability

## 🧪 Integration Tests Results

| Test | Result |
|------|--------|
| packages/ directory structure | ✅ Only py/ remains |
| Documentation consistency | ✅ All docs updated |
| UTF-8 file encoding check | ✅ No invalid UTF-8 files in contracts/ |
| Git ignore status | ✅ Deleted directories were already gitignored |
| Coordinator API port update | ✅ Port 8203 active |
| Wallet CLI API integration | ✅ Uses wallet service API |
| Bridge price endpoint | ✅ Returns prices with oracle support |
| Bridge deposit validation | ✅ Minimum amount checks working |
| Bridge withdrawal disabled | ✅ Returns 503 status |
| Website structure cleanup | ✅ Legacy files removed |

## 🔄 Upgrade Path

### From v0.4.14 to v0.4.15

**Required Actions:**

**1. Update Coordinator API Configuration**
```bash
# Update port references from 8011 to 8203
# Update nginx configuration
sudo sed -i 's/8011/8203/g' /etc/nginx/sites-enabled/aitbc
sudo systemctl reload nginx

# Update systemd service files (if needed)
sudo systemctl restart aitbc-coordinator-api.service
```

**2. Update Wallet CLI Usage**
```bash
# The wallet CLI now uses the wallet service API
# No action required if wallet service is running
# Ensure wallet service is accessible at http://127.0.0.1:8104
sudo systemctl status aitbc-wallet-daemon.service
```

**3. Verify Bridge API Changes**
```bash
# Test new price endpoint
curl http://localhost:8106/exchange/price.json

# Test bridge status (should show deposit-only direction)
curl http://localhost:8106/v1/bridge/status
```

**Optional: Update local clones**
```bash
# If you have local clones, remove deleted directories
rm -rf packages/github packages/js packages/solidity

# Pull latest changes
git pull origin main
```

**Verification**
```bash
# Verify packages structure
ls -la packages/
# Should show only: py/

# Verify coordinator API port
curl http://localhost:8203/health

# Verify contracts directory has no corrupted files
file contracts/* | grep -v "UTF-8"
# Should show no binary/corrupted files
```

## 🐛 Known Issues

- **Bridge Withdrawals Disabled**: AIT→ETH withdrawals are temporarily disabled (503 status) for security reasons. Deposit-only direction is active.
- **Coordinator API Port Change**: Services or clients configured to use port 8011 need to be updated to use port 8203.

## 📚 Documentation Updates

- ✅ `/opt/aitbc/docs/releases/RELEASE_v0.4.15.md` — this file
- ✅ `/opt/aitbc/docs/reference/packages.md` — updated package documentation
- ✅ `/opt/aitbc/docs/contracts/PNPM_SETUP.md` — updated pnpm setup guide
- ✅ `/opt/aitbc/docs/architecture/8_codebase-structure.md` — updated architecture documentation
- ✅ `/opt/aitbc/docs/security/DEPENDENCY_MONITORING.md` — updated security monitoring
- ✅ `/opt/aitbc/docs/development/REQUIREMENTS.md` — updated development requirements

## 📈 Performance Metrics

### Package Directory Size Reduction
- **Before**: ~2.5MB (packages/github, packages/js, packages/solidity)
- **After**: ~100KB (packages/py only)
- **Reduction**: ~96% size reduction

### Website Cleanup
- **Before**: Complex website structure with legacy code (22,179 lines of old code)
- **After**: Simplified structure with only essential files
- **Reduction**: ~98% reduction in website codebase

### Codebase Changes Summary
- **Total files changed**: 281 files across 3 commits
- **Lines added**: 1,695 insertions
- **Lines deleted**: 44,031 deletions
- **Net reduction**: ~42,336 lines of code

### Documentation Clarity
- **Before**: Confusion between multiple contract directories and package purposes
- **After**: Clear single source of truth for contracts (contracts/) and packages (py/ only)

### API Improvements
- **Coordinator API**: Port updated to 8203 for better infrastructure standardization
- **Wallet CLI**: Now uses wallet service API instead of local files (more reliable)
- **Bridge API**: Enhanced with price endpoint, deposit validation, improved security

---

**Release Status**: ✅ Released
**Implementation Date**: June 9, 2026
**Next Release**: v0.4.16
