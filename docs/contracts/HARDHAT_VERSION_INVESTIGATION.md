# Hardhat Version Investigation

**Level**: Technical
**Prerequisites**: Understanding of Hardhat and package management
**Last Updated**: 2026-05-22
**Version**: 1.0

## Overview

AITBC uses two different Hardhat versions for its smart contract projects:
- **contracts/**: Hardhat `^2.22.0` (older, JavaScript-based)
- **aitbc-token/**: Hardhat `^3.3.0` (newer, TypeScript-based)

This document explains why this exists and the blockers for unifying on Hardhat 3.x.

## Current State

### contracts/ (Main Project)
```json
{
  "hardhat": "^2.22.0",
  "@openzeppelin/contracts": "^4.9.6",
  "@nomicfoundation/hardhat-toolbox": "^4.0.0",
  "hardhat-gas-reporter": "^1.0.10",
  "solidity-coverage": "^0.8.17"
}
```

**Characteristics:**
- JavaScript-based (hardhat.config.js)
- Uses OpenZeppelin Contracts v4.9.6
- Includes gas reporter and coverage plugins
- 30+ contract files using OpenZeppelin v4 APIs
- Solidity 0.8.19 with viaIR optimization

### aitbc-token/ (Token Project)
```json
{
  "hardhat": "^3.3.0",
  "@openzeppelin/contracts": "^5.0.2",
  "@nomicfoundation/hardhat-toolbox-mocha-ethers": "^3.0.2"
}
```

**Characteristics:**
- TypeScript-based (hardhat.config.ts)
- Uses OpenZeppelin Contracts v5.0.2
- Mocha-based testing framework
- 2 contract files (AIToken.sol, AITokenRegistry.sol)
- Solidity 0.8.25 with Cancun EVM

## Why Two Versions Exist

**Historical Context:**
- **contracts/** was created earlier with Hardhat 2.x ecosystem (stable, mature)
- **aitbc-token/** was created later with Hardhat 3.x ecosystem (newer features, TypeScript-first)
- They serve different purposes and evolved independently

**Technical Reasons:**
- contracts/ is a large, complex project with 30+ contracts and extensive testing
- aitbc-token is a focused token contract package with simpler requirements
- Different OpenZeppelin versions (v4 vs v5) have breaking changes
- Plugin ecosystem compatibility differs between Hardhat versions

## Blockers for Upgrading contracts/ to Hardhat 3.3.0

### Primary Blocker: OpenZeppelin v4 → v5

**Impact:** High
**Effort:** Significant

All 30+ contract files in contracts/ import from OpenZeppelin v4.9.6:
```solidity
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
// ... 30+ files with similar imports
```

**Required changes:**
1. Update all imports to OpenZeppelin v5 syntax
2. Test breaking changes in OpenZeppelin APIs
3. Update contract logic for v5 deprecations (e.g., SafeMath removal)
4. Verify Governor and other complex contracts work with v5

**Known breaking changes (v4 → v5):**
- SafeMath removed (Solidity 0.8+ has built-in overflow protection)
- Some Governor API changes
- Access control interface updates
- Utility library reorganizations

### Secondary Blocker: Plugin Compatibility

**Impact:** Medium
**Effort:** Moderate

**Plugins requiring verification:**
- `hardhat-gas-reporter@^1.0.10` - Not used in aitbc-token
- `solidity-coverage@^0.8.17` - Not used in aitbc-token

**Hardhat 3 plugin architecture changes:**
- Hardhat 3 changed how plugins are loaded and configured
- Some plugins may not have Hardhat 3 compatible versions
- Alternative plugins may need to be found

### Tertiary Blocker: Hardhat Toolbox Differences

**Impact:** Low
**Effort:** Low

- contracts/ uses `@nomicfoundation/hardhat-toolbox@^4.0.0`
- aitbc-token uses `@nomicfoundation/hardhat-toolbox-mocha-ethers@^3.0.2`
- Different approaches to tooling (all-in-one vs modular)

## Non-Blockers

The following are compatible with Hardhat 3.x:
- ES modules in hardhat.config.js ✅
- JavaScript scripts (Hardhat 3 supports both JS and TS) ✅
- TypeChain version ✅
- Ethers v6 (both projects use same version) ✅
- Solidity compiler settings ✅

## Upgrade Path (If Desired)

### Phase 1: OpenZeppelin v4 → v5
1. Update `@openzeppelin/contracts` to v5 in package.json
2. Update all 30+ contract imports
3. Remove SafeMath usage (built-in overflow protection)
4. Update Governor and other complex contracts
5. Run full test suite
6. Fix breaking changes

### Phase 2: Hardhat 2 → 3
1. Update `hardhat` to ^3.3.0
2. Update all Hardhat plugins to v3-compatible versions
3. Update hardhat.config.js to use new config format
4. Verify gas reporter and coverage plugins work
5. Update CI workflows if needed
6. Run full test suite

### Phase 3: Optional TypeScript Migration
1. Convert hardhat.config.js to hardhat.config.ts
2. Convert scripts to TypeScript (optional)
3. Update type definitions
4. Verify compilation

## Recommendation

**Current approach (maintain two versions):**
- ✅ Both projects work correctly as-is
- ✅ No risk of breaking changes
- ✅ Each project uses appropriate tooling for its complexity
- ❌ Inconsistent developer experience
- ❌ Duplicate dependency management overhead

**Alternative (unify on Hardhat 3):**
- ✅ Consistent tooling across projects
- ✅ Access to latest Hardhat features
- ✅ TypeScript-first development
- ❌ Significant effort (OpenZeppelin v4 → v5 migration)
- ❌ Risk of breaking contract logic
- ❌ Extensive testing required

**Suggested approach:**
Keep both versions for now. The cost of unifying (OpenZeppelin v4 → v5 migration + plugin compatibility) outweighs the benefits given that both projects work correctly independently. Revisit this decision when:
- Hardhat 2.x reaches end-of-life
- OpenZeppelin v4 becomes deprecated
- A major contract refactoring is already planned

## Related Documentation

- [PNPM_SETUP.md](PNPM_SETUP.md) - pnpm configuration for both projects
- [SMART_CONTRACT_DEPLOYMENT.md](../deployment/SMART_CONTRACT_DEPLOYMENT.md) - Deployment guide
- [architecture/8_codebase-structure.md](../architecture/8_codebase-structure.md) - Overall codebase structure

---

*Last updated: 2026-05-22*
*Version: 1.0*
*Status: Investigation complete, no action required*
