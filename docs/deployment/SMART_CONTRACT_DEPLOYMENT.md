# Smart Contract Deployment Guide

**Level**: Intermediate  
**Prerequisites**: Familiarity with Solidity, Hardhat, and CI/CD workflows  
**Estimated Time**: 30-60 minutes  
**Last Updated**: 2026-04-29  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🚀 Deployment** → **📜 Smart Contract Deployment**

**breadcrumb**: Home → Deployment → Smart Contract Deployment

---

## 🎯 **See Also:**
- **🔧 [SETUP_PRODUCTION.md](SETUP_PRODUCTION.md)** - Production blockchain setup
- **📋 [Advanced Deployment](../advanced/04_deployment/0_index.md)** - Advanced deployment topics
- **📚 [Contracts Directory](../../contracts/)** - Contract source code
- **🔄 [CI/CD Workflows](../../.gitea/workflows/deploy-testnet.yml)** - Deployment automation

---

## 📦 **Contents**

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Testnet Deployment](#testnet-deployment)
- [Mainnet Deployment](#mainnet-deployment)
- [Contract Verification](#contract-verification)
- [Monitoring and Alerts](#monitoring-and-alerts)
- [Troubleshooting](#troubleshooting)

---

## 🧱 **Overview**

This guide covers the deployment of AITBC smart contracts to testnet and mainnet networks using automated CI/CD workflows. The deployment process includes:

- **Pre-deployment checks**: Security scans, contract tests, readiness verification
- **Contract deployment**: Automated deployment via Hardhat scripts
- **Contract verification**: Verification on block explorers (Etherscan for mainnet)
- **Monitoring setup**: Automated alerts for contract events and health
- **Smoke tests**: Post-deployment validation

---

## 📋 **Prerequisites**

### Required Tools
- Node.js 18+ and npm
- Hardhat framework
- Git repository access
- CI/CD runner access (gitea-runner)

### Required Secrets
Configure the following secrets in your CI/CD system:

**For Testnet:**
- `TESTNET_DEPLOYER_PRIVATE_KEY` - Private key for testnet deployment
- `TESTNET_RPC_URL` - RPC endpoint for testnet
- `TESTNET_EXPLORER_API_KEY` - API key for testnet block explorer

**For Mainnet:**
- `MAINNET_DEPLOYER_PRIVATE_KEY` - Private key for mainnet deployment
- `MAINNET_RPC_URL` - RPC endpoint for mainnet
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

## 🧪 **Testnet Deployment**

### Automated Deployment via CI/CD

The testnet deployment workflow is triggered by:
- Pushing to `main` branch
- Creating a tag matching `testnet-v*`
- Manual trigger via `workflow_dispatch`

**Workflow:** `.gitea/workflows/deploy-testnet.yml`

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
npx hardhat run scripts/deploy-testnet.js --network testnet
```

### Contract Addresses

After deployment, record the contract addresses:
- `PaymentProcessor` - Handles payment processing
- `AgentMarketplace` - Manages agent registration and job postings
- `StakingContract` - Handles staking and rewards

---

## 🚀 **Mainnet Deployment**

### Pre-deployment Checklist

Before deploying to mainnet, ensure:

- [ ] All security scans pass
- [ ] Contract tests pass
- [ ] Code reviewed by team
- [ ] Testnet deployment successful
- [ ] Monitoring configured
- [ ] Backup of deployment keys
- [ ] Rollback plan documented

### Automated Deployment via CI/CD

The mainnet deployment workflow is triggered by:
- Creating a tag matching `mainnet-v*`
- Manual trigger via `workflow_dispatch`

**Workflow:** `.gitea/workflows/deploy-mainnet.yml`

### Manual Deployment

```bash
cd /opt/aitbc/contracts

# Set environment variables
export HARDHAT_NETWORK=mainnet
export PRIVATE_KEY=<your-mainnet-private-key>
export MAINNET_RPC_URL=<mainnet-rpc-url>

# Compile contracts
npx hardhat compile

# Run security scan
bash scripts/ci/security-scan.sh

# Run contract tests
npx hardhat test

# Deploy contracts
npx hardhat run scripts/deploy-mainnet.js --network mainnet
```

### Deployment Safety

Mainnet deployment includes:
- Pre-deployment security checks
- Gas optimization
- Transaction confirmation monitoring
- Automatic rollback on failure

---

## ✅ **Contract Verification**

### Etherscan Verification (Mainnet)

Automated verification is performed during deployment using:

```bash
export ETHERSCAN_API_KEY=<your-etherscan-api-key>

# Verify PaymentProcessor
npx hardhat verify --network mainnet <PAYMENT_PROCESSOR_ADDRESS> --constructor-args scripts/deployment/args/payment-processor-args.js

# Verify AgentMarketplace
npx hardhat verify --network mainnet <AGENT_MARKETPLACE_ADDRESS> --constructor-args scripts/deployment/args/agent-marketplace-args.js

# Verify StakingContract
npx hardhat verify --network mainnet <STAKING_CONTRACT_ADDRESS> --constructor-args scripts/deployment/args/staking-contract-args.js
```

### Testnet Verification

Testnet verification uses the block explorer API:
```bash
export TESTNET_EXPLORER_API_KEY=<testnet-explorer-api-key>
export TESTNET_EXPLORER_URL=<testnet-explorer-url>

# Verification is handled by the deployment script
```

---

## 📊 **Monitoring and Alerts**

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
- Low marketplace activity
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

## 🔧 **Troubleshooting**

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
systemctl status aitbc-monitor.service

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

- **deploy-testnet.yml** - Automated testnet deployment
- **deploy-mainnet.yml** - Automated mainnet deployment
- **smart-contract-tests.yml** - Contract testing
- **security-scanning.yml** - Security scanning

---

*Last updated: 2026-04-29*  
*Version: 1.0*  
*Status: Active*
