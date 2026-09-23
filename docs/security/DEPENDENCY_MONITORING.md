# Dependency Security Monitoring Strategy

## Overview

This document outlines the monitoring strategy for key dependencies in the AITBC project to manage security vulnerabilities effectively.

## Current Vulnerability Status

### Python Dependencies

- **Status**: 0 vulnerabilities found
- **Tool**: pip-audit in project virtual environment
- **Scope**: All Python packages in venv
- **Note**: Internal AITBC packages (aitbc, aitbc-agent-core, etc.) are not on PyPI and are excluded from audit

### npm/JavaScript Dependencies

- **Total**: 35 vulnerabilities (7 low, 15 moderate, 13 high)
- **Status**: Accepted as acceptable risk
- **Rationale**: Most vulnerabilities are in Hardhat/Ethers build tools (transitive dependencies), not production runtime code
- **Note**: npm audit fix attempted; both `contracts/` and
  `apps/zk-circuits/` are npm projects (`packageManager: npm@11.16.0`,
  `package-lock.json`) — the pnpm-workspace claim below is outdated

#### Breakdown by Package

- `/opt/aitbc/contracts`: 14 vulnerabilities (3 low, 7 moderate, 4 high)
- `/opt/aitbc/apps/zk-circuits`: 13 vulnerabilities (2 low, 4 moderate, 7 high)

#### Key Vulnerable Packages

- **elliptic** (low): Cryptographic primitive implementation risk in @ethersproject/signing-key
- **serialize-javascript** (moderate): CPU exhaustion DoS in mocha
- **tmp** (low): Arbitrary file write via symbolic link in solc
- **diff** (low): DoS in parsePatch/applyPatch in mocha
- **js-yaml** (high): Code execution in mocha
- **nanoid** (high): Predictable randomness in multiple paths
- **minimatch** (moderate): ReDoS in multiple paths
- **underscore** (moderate): Prototype pollution in multiple paths

### Rust Dependencies

- **Status**: 0 vulnerabilities found
- **Tool**: cargo-audit
- **Scope**: dev/gpu/gpu_zk_research (55 crate dependencies)
- **Note**: halo2_gadgets was pinned at 0.1.0 and carried CVE-2026-54496 (GHSA-ww9q-8r59-xv46,
  CVSS 9.3) until 2026-09-06; it is now on 0.5.0. The abandoned `halo2` umbrella crate
  (0.1.0-beta.2, no release since 2021) was dropped in favour of halo2_proofs + halo2_gadgets.

## Monitoring Strategy

### Automated Monitoring

#### GitHub Dependabot

- **Current**: Enabled on default branch
- **Frequency**: Continuous on push
- **Scope**: All dependency manifests
- **Action**: Review Dependabot alerts monthly

#### CI/CD Integration

- **Security scanning**: no dedicated workflow exists — the only CI is
  `ci.yml` (`.github` + `.gitea`), which runs tests, not dependency scans.
  Run `scripts/security/dependency-scan.sh` locally; Dependabot
  (`.github/dependabot.yml`) opens weekly update PRs.

### Manual Monitoring

#### Monthly Review

1. Run comprehensive vulnerability scans:

   ```bash
   # Python
   source /opt/aitbc/venv/bin/activate
   pip-audit

   # npm (pnpm)
   cd /opt/aitbc/contracts && pnpm audit
   cd /opt/aitbc/apps/zk-circuits && pnpm audit

   # Rust
   source ~/.cargo/env
   cd /opt/aitbc/dev/gpu/gpu_zk_research && cargo audit
   ```

2. Review GitHub Dependabot alerts
3. Check for security updates in key dependencies:
   - elliptic
   - serialize-javascript
   - ethers.js
   - hardhat
   - halo2 ecosystem

#### Quarterly Review

1. Evaluate major version updates for:
   - Hardhat (repo already on v3.x — `contracts/package.json` pins `^3.12.0`)
   - Ethers.js
   - Circom (note: `circom` npm package deprecated upstream)

2. Assess breaking changes vs security benefits
3. Plan upgrade testing in development environment

### npm Audit Fix Guidance

#### Limitations

- **npm workspaces**: `contracts/` and `apps/zk-circuits/` use npm
  (`package-lock.json` + top-level `"overrides"` in package.json)
- **Transitive dependencies**: Manual overrides may not catch all transitive dependency paths

#### Recommended Approach

1. **For npm-based packages**: Run `npm audit fix` first to auto-resolve fixable vulnerabilities
2. **For pnpm workspaces**: Use pnpm overrides in package.json (currently implemented)
3. **Consider Hardhat upgrade**: Hardhat v3.x may resolve many transitive dependency vulnerabilities but requires testing due to breaking changes
4. **Monitor**: Track Hardhat v3.x stability and adoption before upgrading

### Acceptance Criteria

#### Low Risk (Acceptable)

- Build-time only dependencies (devDependencies)
- Transitive dependencies in build tools
- Vulnerabilities requiring local code execution
- Vulnerabilities in test frameworks

#### Medium Risk (Monitor)

- Runtime dependencies with moderate severity
- Vulnerabilities in widely-used libraries
- Beta/preview dependencies

#### High Risk (Remediate)

- Runtime dependencies with high severity
- Vulnerabilities in cryptographic primitives
- Known exploited vulnerabilities (KEV)

## Remediation Procedures

### Immediate (Within 24 hours)

- **Trigger**: Critical/High severity in production runtime dependencies
- **Action**:
  1. Assess exploitability
  2. Apply patch or upgrade
  3. Deploy to production
  4. Verify fix

### Short-term (Within 1 week)

- **Trigger**: Moderate severity in production runtime dependencies
- **Action**:
  1. Schedule maintenance window
  2. Test upgrade in staging
  3. Deploy to production

### Long-term (Within 1 month)

- **Trigger**: Low severity or build-time dependencies
- **Action**:
  1. Include in regular dependency update cycle
  2. Coordinate with feature releases

## Dependency Overrides

### npm (pnpm)

The following packages have version overrides in package.json files to mitigate known vulnerabilities:

#### contracts/package.json

```json
"overrides": {
  "uuid": "^14.0.0",
  "serialize-javascript": "^7.1.0",
  "tmp": "^0.2.4",
  "diff": "^5.2.2",
  "js-yaml": "^4.3.2",
  "minimatch": "^9.0.0",
  "nanoid": "^3.3.12",
  "underscore": "^1.13.6",
  "bn.js": "^4.12.3",
  "cookie": "^0.7.0",
  "ws": "^8.21.3",
  "adm-zip": "^0.6.1"
}
```

#### apps/zk-circuits/package.json

```json
"overrides": {
  "circom_runtime": { "ffjavascript": "^0.3.1" },
  "underscore": "^1.13.8"
}
```

## Communication

### Internal

- **Monthly**: Security status update in team meeting
- **Quarterly**: Dependency health report
- **Ad-hoc**: Critical vulnerability notifications

### External

- **GitHub Security Advisories**: Publish security advisories for affected releases
- **Release Notes**: Document security updates in changelog

## References

- [GitHub Dependabot](https://github.com/oib/AITBC/security/dependabot)
- [RustSec Advisory Database](https://github.com/RustSec/advisory-db)
- [npm Audit Documentation](https://docs.npmjs.com/cli/v9/commands/npm-audit)
- [pip-audit Documentation](https://pypi.org/project/pip-audit/)

## Last Updated

2026-05-29
