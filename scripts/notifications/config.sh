#!/bin/bash
set -euo pipefail
# Notification configuration
# Copy this file to config.local.sh and set your values

# Slack webhook URL for deployment notifications
SLACK_WEBHOOK_URL=""

# Email address for deployment notifications
ALERT_EMAIL=""

# PagerDuty API key for critical alerts
PAGERDUTY_API_KEY=""

# Etherscan API key for contract verification
ETHERSCAN_API_KEY=""

# Testnet explorer API key
TESTNET_EXPLORER_API_KEY=""

# Testnet RPC URL
TESTNET_RPC_URL=""

# Mainnet RPC URL
MAINNET_RPC_URL=""

# Deployer private keys are NOT set here. contracts/hardhat.config.js
# reads TESTNET_DEPLOYER_PRIVATE_KEY / MAINNET_DEPLOYER_PRIVATE_KEY
# straight from the process environment — never write a key into a file
# inside the repo, gitignored or not.
