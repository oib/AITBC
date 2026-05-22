# pnpm Setup for AITBC Contracts

**Level**: Intermediate  
**Prerequisites**: Node.js, familiarity with package managers  
**Estimated Time**: 5 minutes  
**Last Updated**: 2026-05-22  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **📜 Contracts** → **⚙️ pnpm Setup**

**breadcrumb**: Home → Contracts → pnpm Setup

---

## 🎯 **See Also:**
- **📦 Smart Contract Deployment**: [SMART_CONTRACT_DEPLOYMENT.md](../deployment/SMART_CONTRACT_DEPLOYMENT.md) - Deployment guide using pnpm
- **🔧 Development Guidelines**: [DEVELOPMENT_GUIDELINES.md](../development/DEVELOPMENT_GUIDELINES.md) - General development setup
- **📜 Contracts Overview**: [contracts/README.md](README.md) - Contract documentation index

---

## 📦 **Overview**

AITBC uses **pnpm** as the package manager for both smart contract projects:
- `/opt/aitbc/contracts/` - Main Hardhat project (JavaScript-based)
- `/opt/aitbc/packages/solidity/aitbc-token/` - Token contracts (TypeScript-based)

pnpm provides faster installations, better disk efficiency, and stricter dependency management compared to npm.

## 📋 **Configuration Files**

### `.npmrc`

**contracts/ directory:**
```ini
auto-install-peers=false
strict-peer-dependencies=true
prefer-frozen-lockfile=true
shamefully-hoist=true
```

**packages/solidity/aitbc-token/ directory:**
```ini
auto-install-peers=false
strict-peer-dependencies=true
prefer-frozen-lockfile=true
engine-strict=true
```

**Settings explained:**
- **auto-install-peers=false**: Don't automatically install peer dependencies - requires explicit installation
- **strict-peer-dependencies=true**: Fail if peer dependency requirements aren't met
- **prefer-frozen-lockfile=true**: Use exact versions from lockfile (recommended for CI)
- **shamefully-hoist=true** (contracts only): Hoist dependencies to node_modules root for compatibility with older Hardhat
- **engine-strict=true** (aitbc-token only): Enforce Node.js version requirement (>=24.14.0)

### `pnpm-lock.yaml`
The lockfile is automatically generated and should be committed to version control. It ensures reproducible installs across environments.

## 🚀 **Common Commands**

### Installation
```bash
# For main contracts
cd /opt/aitbc/contracts
pnpm install

# For aitbc-token
cd /opt/aitbc/packages/solidity/aitbc-token
pnpm install
```

### Development Commands

**contracts/ (JavaScript-based):**
```bash
cd /opt/aitbc/contracts
pnpm hardhat compile
pnpm hardhat test
pnpm hardhat run scripts/deploy.js --network localhost
pnpm hardhat verify --network mainnet <ADDRESS> <CONSTRUCTOR_ARGS>
```

**aitbc-token/ (TypeScript-based):**
```bash
cd /opt/aitbc/packages/solidity/aitbc-token
pnpm run build
pnpm run test
pnpm run lint
pnpm run format
pnpm run deploy
```

### CI/CD Commands
```bash
# Install with frozen lockfile (recommended for CI)
pnpm install --frozen-lockfile
```

## 🔧 **Migration from npm**

If you're migrating from npm to pnpm:

1. **Delete npm artifacts**:
   ```bash
   rm package-lock.json
   rm -rf node_modules
   ```

2. **Install pnpm** (if not already installed):
   ```bash
   npm install -g pnpm
   ```

3. **Install dependencies with pnpm**:
   ```bash
   pnpm install
   ```

4. **Update scripts**: Replace `npm` with `pnpm` and `npx` with `pnpm`

## 📊 **Benefits of pnpm**

- **Speed**: 2-3x faster installations than npm
- **Disk Space**: ~50% reduction through content-addressable storage
- **Strictness**: Better dependency resolution and peer dependency handling
- **Reproducibility**: More reliable lockfile behavior

## 🛠️ **Troubleshooting**

### Build scripts fail
If you encounter build script errors, you may need to approve specific packages:
```bash
pnpm approve-builds <package-name>
```

### Peer dependency errors
If strict peer dependency checking causes issues, you can temporarily disable it:
```bash
pnpm install --strict-peer-dependencies=false
```

### Cache issues
Clear the pnpm cache if you encounter unexpected behavior:
```bash
pnpm store prune
```

## 🔄 **CI/CD Integration**

All CI workflows have been updated to use pnpm:
- `smart-contract-tests.yml` - Tests both contracts/ and aitbc-token/
- `package-tests.yml` - Tests aitbc-token/ package
- `deploy-testnet.yml` - Testnet deployment
- `deploy-mainnet.yml` - Mainnet deployment
- `contract-benchmarks.yml` - Performance benchmarks
- `staking-tests.yml` - Staking contract tests

Workflows automatically install pnpm if not available on the runner.

---

*Last updated: 2026-05-22*  
*Version: 1.0*  
*Status: Active*
