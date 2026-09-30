# Smart Contract Deployment Guide

**Level**: Intermediate
**Prerequisites**: Familiarity with Solidity, Hardhat, and CI/CD workflows
**Estimated Time**: 30-60 minutes
**Last Updated**: 2026-05-28
**Version**: 1.0

## Navigation Path

**🏠 [Documentation Home](../README.md)** → **🚀 Deployment** → **📜 Smart Contract Deployment**

**breadcrumb**: Home → Deployment → Smart Contract Deployment

---

## See Also

- **🔧 SETUP_PRODUCTION.md** - Production blockchain setup
- **📋 [Advanced Deployment](../deployment/0_index.md)** - Advanced deployment topics
- **📚 [Contracts Directory](../../contracts/)** - Contract source code

---

## Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Testnet Deployment](#testnet-deployment)
- [Mainnet Deployment](#mainnet-deployment)
- [Contract Verification](#contract-verification)
- [Monitoring and Alerts](#monitoring-and-alerts)
- [Troubleshooting](#troubleshooting)

---

## Overview

This guide covers the deployment of AITBC smart contracts to testnet and mainnet networks using automated CI/CD workflows. The deployment process includes:

- **Pre-deployment checks**: Security scans, contract tests, readiness verification
- **Contract deployment**: Automated deployment via Hardhat scripts
- **Contract verification**: Verification on block explorers (Etherscan for mainnet)
- **Monitoring setup**: Automated alerts for contract events and health
- **Smoke tests**: Post-deployment validation

---

## Prerequisites

### Required Tools

- Node.js 18+ and npm
- Hardhat framework
- Git repository access
- CI/CD runner access

### Required Secrets

> **Testnet only.** Deployer keys in CI secrets are acceptable for testnet
> deploys. **No private key for a mainnet deploy is ever stored in CI** —
> mainnet uses the disposable-deployer + multisig-owner procedure in the
> Mainnet Deployment section.

Configure the following secrets in your CI/CD system:

**For Testnet:**

- `TESTNET_DEPLOYER_PRIVATE_KEY` - Private key for testnet deployment
- `TESTNET_RPC_URL` - RPC endpoint for testnet
- `TESTNET_EXPLORER_API_KEY` - API key for testnet block explorer

**For Mainnet:** no deployer key in CI — see Mainnet Deployment below.

- `MAINNET_RPC_URL` - RPC endpoint for mainnet (verification only)
- `ETHERSCAN_API_KEY` - API key for Etherscan verification

**For Monitoring:**

- `SLACK_WEBHOOK_URL` - Slack webhook for notifications
- `ALERT_EMAIL` - Email address for alerts
- `PAGERDUTY_API_KEY` - PagerDuty API key for critical alerts

### Local Setup

```bash
cd /opt/aitbc/contracts
npm install
```

---

## Testnet Deployment

### Automated Deployment via CI/CD

The testnet deployment workflow is triggered by:

- Pushing to `main` branch
- Creating a tag matching `testnet-v*`
- Manual trigger via `workflow_dispatch`

**Workflow:** `.gitea/workflows/deploy-testnet.yml` — **planned, does not exist yet**; the only Gitea workflow is `ci.yml`. Deployments are run manually (below).

### Manual Deployment

```bash
cd /opt/aitbc/contracts

# Set environment variables
export HARDHAT_NETWORK=testnet
export PRIVATE_KEY=<your-testnet-private-key>
export TESTNET_RPC_URL=<testnet-rpc-url>

# Compile contracts
npx hardhat compile

# Run tests
npx hardhat test

# Deploy contracts
bash scripts/deploy-testnet.sh
```

### Contract Addresses

After deployment, record the contract addresses:

- `PaymentProcessor` - Handles payment processing
- `AgentMarket` - Manages agent registration and job postings
- `AgentStaking` / `StakingPoolFactory` - handle staking and rewards

---

## Mainnet Deployment

### Pre-deployment Checklist

Before deploying to mainnet, ensure:

- [ ] All security scans pass
- [ ] Contract tests pass
- [ ] Code reviewed by team
- [ ] Testnet deployment successful
- [ ] Monitoring configured
- [ ] Backup of deployment keys
- [ ] Rollback plan documented

### Deployment model — mainnet (all contracts, not just the bridge)

No mainnet deployer key lives in CI secrets or on a reused account.
Every mainnet deployment — bridge or otherwise — follows this procedure:

1. **Disposable deployer.** Generate a fresh keypair, fund it with just
   enough ETH for the deploy, use it once, then discard it. The deployer
   holds no authority after the deploy.
2. **Multisig owner.** Ownership transfers at deploy time to a multisig
   (the bridge uses a 2-of-3 Safe with three separate human signers —
   decision log `docs/decisions/README.md`). Never leave ownership on an
   externally-owned deployer account.
3. **Deployment record.** Record address, tx hash, deployer, owner,
   chain, and the `contracts/` commit hash — the same fields the bridge
   deployment records carry.

```bash
cd /opt/aitbc/contracts

export HARDHAT_NETWORK=mainnet
export PRIVATE_KEY=<disposable-deployer-key>   # fresh, single-use
export MAINNET_RPC_URL=<mainnet-rpc-url>

npx hardhat compile
bash contracts/scripts/security-analysis.sh
npx hardhat test
npx hardhat run scripts/deploy-mainnet.js --network mainnet
# then: transfer ownership to the multisig, discard the deployer key,
# and commit the deployment record
```

### Deployment Safety

Mainnet deployment includes:

- Pre-deployment security checks
- Gas optimization
- Transaction confirmation monitoring
- Automatic rollback on failure

---

## CrossChainBridge — separate deployment procedure (BR-1)

The bridge contract does **not** follow the CI-secret flow above:

- A frozen `CrossChainBridge` deployment on Sepolia is recorded in
  `contracts/deployments-bridge-sepolia.json` as deprecated — its owner key
  is unreachable. Do not send funds to it.
- The replacement deploys with a **disposable deployer key** (fresh,
  funded just for the deploy, discarded after), never a stored CI secret.
- Ownership transfers at deploy time to a **2-of-3 Safe** whose signers are
  three separate people/devices (decision log `docs/decisions/README.md`).
- Every deployment produces a full record: address, tx hash, deployer,
  owner, chain, and the commit hash of `contracts/`.

## Contract Verification

### Etherscan Verification (Mainnet)

Automated verification is performed during deployment using:

```bash
export ETHERSCAN_API_KEY=<your-etherscan-api-key>

# Verify PaymentProcessor
npx hardhat verify --network mainnet <PAYMENT_PROCESSOR_ADDRESS> --constructor-args <args-file.js>  # args files are written per-deploy; there is no tracked scripts/deployment/args/ dir

# Verify AgentMarket
npx hardhat verify --network mainnet <AGENT_MARKET_ADDRESS> --constructor-args <args-file.js>

# Verify the staking contract
npx hardhat verify --network mainnet <STAKING_CONTRACT_ADDRESS> --constructor-args <args-file.js>
```

### Testnet Verification

Testnet verification uses the block explorer API:

```bash
export TESTNET_EXPLORER_API_KEY=<testnet-explorer-api-key>
export TESTNET_EXPLORER_URL=<testnet-explorer-url>

# Verification is handled by the deployment script
```

---

## Monitoring and Alerts

### Contract Monitoring Setup

Automated monitoring is configured during deployment:

```bash
bash scripts/monitoring/setup-contract-monitoring.sh <network>
```

This creates:

- Prometheus metrics configuration
- Contract event monitoring
- Health check endpoints

### Alert Configuration

Automated alerts are configured for:

**Critical Alerts:**

- Contract downtime
- Critical balance low
- High failure rate

**Warning Alerts:**

- Unusual withdrawal activity
- Gas price spikes
- Reward distribution delays

**Info Alerts:**

- Low market activity
- Successful deployments

### Alert Channels

Alerts are sent to:

- Slack (configured channels)
- Email (ALERT_EMAIL)
- PagerDuty (critical alerts only)

### Monitoring Verification

Verify monitoring is working:

```bash
bash scripts/monitoring/verify-monitoring.sh <network>
```

---

## Troubleshooting

### Deployment Fails

**Check:**

- RPC endpoint is accessible
- Private key is correct and has sufficient funds
- Network is not congested (gas prices)
- Contract compilation successful

**Solution:**

```bash
# Check RPC connectivity
curl -X POST $RPC_URL -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'

# Check account balance
npx hardhat run scripts/check-balance.js --network <network>
```

### Verification Fails

**Check:**

- Contract address is correct
- Constructor arguments match deployment
- API key is valid
- Contract is already verified

**Solution:**

```bash
# Check if already verified
curl https://api.etherscan.io/api?module=contract&action=getabiaddress&address=<CONTRACT_ADDRESS>&apikey=<API_KEY>

# Re-verify with correct arguments
npx hardhat verify --network <network> <ADDRESS> <CONSTRUCTOR_ARGS>
```

### Monitoring Not Working

**Check:**

- Monitoring service is running
- Prometheus is accessible
- Alertmanager is running
- Configuration files are valid

**Solution:**

```bash
# Check service status
systemctl status aitbc-monitoring.service

# Check Prometheus
curl http://localhost:9090/-/healthy

# Check Alertmanager
curl http://localhost:9093/-/healthy
```

---

## 📝 **Deployment Checklist**

### Testnet

- [ ] Environment variables configured
- [ ] Contracts compile successfully
- [ ] Tests pass
- [ ] Manual deployment tested
- [ ] Monitoring configured
- [ ] Verification successful
- [ ] Smoke tests pass

### Mainnet

- [ ] All testnet checks pass
- [ ] Security scan clean
- [ ] Code review complete
- [ ] Team approval received
- [ ] Backup keys secured
- [ ] Rollback plan ready
- [ ] Monitoring configured
- [ ] Notification channels tested
- [ ] Deployment executed
- [ ] Verification complete
- [ ] Smoke tests pass
- [ ] Monitoring verified

---

## 🔄 **Related Workflows**

None of the workflows below exist — `.gitea/workflows/` and
`.github/workflows/` contain only `ci.yml`. Deploy, test, and scan steps are
run manually via `contracts/scripts/` (`deploy-testnet.sh`,
`deploy-mainnet.js`, `security-analysis.sh`, forge/hardhat tests in CI).

---

*Last updated: 2026-04-29*
*Version: 1.0*
*Status: Active*
