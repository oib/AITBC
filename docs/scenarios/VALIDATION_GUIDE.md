# AITBC Scenario Validation Guide

**Last Updated:** 2026-05-09  
**Version:** 1.0  
**Purpose:** Automated validation procedures and checks for AITBC scenarios

---

## Overview

This guide provides validation procedures for verifying successful completion of AITBC scenarios. Each scenario includes specific validation criteria to ensure operations were executed correctly.

## Validation Framework

### Validation Command

```bash
# Validate a specific scenario
aitbc validate scenario <scenario-id>

# Validate all scenarios in a stage
aitbc validate stage <stage-number>

# Validate with detailed output
aitbc validate scenario <scenario-id> --verbose

# Validate with auto-fix (where applicable)
aitbc validate scenario <scenario-id> --auto-fix
```

### Validation Output Format

```json
{
  "scenario_id": "01_wallet_basics",
  "status": "passed",
  "checks": [
    {
      "name": "wallet_created",
      "status": "passed",
      "message": "Wallet test-wallet-001 created successfully"
    },
    {
      "name": "wallet_balance",
      "status": "passed",
      "message": "Wallet balance: 1000 AIT"
    }
  ],
  "timestamp": "2026-05-09T12:00:00Z"
}
```

## Scenario Validation Criteria

### Scenario 01: Wallet Basics

**Validation Checks:**
1. Wallet creation successful
2. Wallet keystore file exists
3. Wallet can be unlocked
4. Wallet balance is retrievable
5. Wallet address is valid

**Validation Commands:**
```bash
# Check wallet exists
test -f /var/lib/aitbc/keystore/<wallet-name>.json

# Verify wallet can be unlocked
aitbc wallet unlock <wallet-name> --password <password>

# Check wallet balance
aitbc wallet balance <wallet-name> | grep -q "^[0-9]"

# Validate wallet address format
aitbc wallet address <wallet-name> | grep -q "^0x[a-fA-F0-9]\{40\}$"
```

**Expected Results:**
- Wallet file exists in keystore directory
- Balance is non-negative number
- Address is valid Ethereum-style address
- Unlock operation succeeds without error

### Scenario 02: Transaction Sending

**Validation Checks:**
1. Transaction submitted successfully
2. Transaction hash is valid
3. Transaction confirms on blockchain
4. Sender balance decreases by amount + fee
5. Recipient balance increases by amount

**Validation Commands:**
```bash
# Submit test transaction
TX_HASH=$(aitbc transaction send <sender> <recipient> 10)

# Validate transaction hash format
echo $TX_HASH | grep -q "^0x[a-fA-F0-9]\{64\}$"

# Check transaction status
aitbc transaction status $TX_HASH | grep -q "confirmed"

# Verify balance changes
SENDER_BEFORE=$(aitbc wallet balance <sender>)
aitbc transaction send <sender> <recipient> 10
SENDER_AFTER=$(aitbc wallet balance <sender>)
# Verify: SENDER_BEFORE > SENDER_AFTER
```

**Expected Results:**
- Transaction hash is 64-character hex string
- Transaction status shows "confirmed"
- Balance changes reflect transaction amount and fees
- Transaction appears in blockchain explorer

### Scenario 03: Genesis Deployment

**Validation Checks:**
1. Genesis wallet configured
2. Genesis block deployed
3. Network initialized
4. Genesis block hash is valid
5. Network is syncable

**Validation Commands:**
```bash
# Check genesis wallet
test -f /var/lib/aitbc/keystore/genesis.json

# Verify genesis block
GENESIS_HASH=$(aitbc genesis hash)
echo $GENESIS_HASH | grep -q "^0x[a-fA-F0-9]\{64\}$"

# Check network status
aitbc blockchain status | grep -q "initialized"

# Verify block number is 0 for new network
aitbc blockchain block number | grep -q "^0$"
```

**Expected Results:**
- Genesis wallet exists with funds
- Genesis block hash is valid
- Network shows as initialized
- Block number starts at 0
- Peers can connect to genesis node

### Scenario 07: AI Job Submission

**Validation Checks:**
1. Job submitted successfully
2. Job ID is valid
3. Job parameters validated
4. Job enters queue
5. Job executes successfully

**Validation Commands:**
```bash
# Submit AI job
JOB_ID=$(aitbc ai job submit job-config.json)

# Validate job ID format
echo $JOB_ID | grep -q "^job-[a-fA-F0-9]\{32\}$"

# Check job status
aitbc ai job status $JOB_ID | grep -q "queued\|running\|completed"

# Monitor job completion
aitbc ai job wait $JOB_ID --timeout 300

# Verify results
aitbc ai job results $JOB_ID | test -s
```

**Expected Results:**
- Job ID follows expected format
- Job transitions through queue → running → completed
- Results are generated and retrievable
- No errors in job execution logs

### Scenario 08: Marketplace Bidding

**Validation Checks:**
1. Bid submitted successfully
2. Bid ID is valid
3. Bid appears in marketplace
4. Bid status is active
5. Bid can be accepted if winning

**Validation Commands:**
```bash
# Submit bid
BID_ID=$(aitbc marketplace bid <listing-id> <amount> <wallet>)

# Validate bid ID format
echo $BID_ID | grep -q "^bid-[a-fA-F0-9]\{32\}$"

# Check bid status
aitbc marketplace bid status $BID_ID | grep -q "active"

# Verify bid in marketplace
aitbc marketplace bids <listing-id> | grep -q $BID_ID

# Check wallet balance after bid (if bid accepted)
aitbc wallet balance <wallet>
```

**Expected Results:**
- Bid ID follows expected format
- Bid appears in marketplace listing
- Bid status shows as active/pending
- Wallet balance reflects bid if accepted
- Marketplace updates bid status correctly

### Scenario 13: Mining Setup

**Validation Checks:**
1. Mining service started
2. Mining node registered
3. Mining rewards received
4. Block production active
5. Mining statistics available

**Validation Commands:**
```bash
# Check mining service status
systemctl status aitbc-mining.service | grep -q "active (running)"

# Verify mining registration
aitbc mining status | grep -q "registered"

# Check mining rewards
aitbc mining rewards | grep -q "^[0-9]"

# Monitor block production
aitbc mining blocks | tail -1

# Check mining statistics
aitbc mining stats
```

**Expected Results:**
- Mining service is running
- Node is registered as miner
- Rewards are being earned
- Blocks are being produced
- Statistics show mining activity

### Scenario 14: Staking Basics

**Validation Checks:**
1. Staking operation successful
2. Staked amount locked
3. Staking rewards accruing
4. Unstaking works correctly
5. Validator status updated

**Validation Commands:**
```bash
# Stake tokens
aitbc staking stake <wallet> 1000

# Verify staked amount
aitbc staking balance <wallet> | grep -q "1000"

# Check rewards
aitbc staking rewards <wallet> | grep -q "^[0-9]"

# Unstake tokens
aitbc staking unstake <wallet> 500

# Verify unstaking
aitbc staking balance <wallet> | grep -q "500"
```

**Expected Results:**
- Staked tokens are locked
- Rewards accrue over time
- Unstaking releases tokens after unbonding period
- Balance reflects staking operations
- Validator status updates correctly

### Scenario 20: Cross Chain Transfer

**Validation Checks:**
1. Bridge initialized
2. Transfer submitted successfully
3. Transfer status trackable
4. Transfer completes on destination chain
5. Balances updated on both chains

**Validation Commands:**
```bash
# Check bridge status
aitbc cross-chain bridge status | grep -q "available"

# Submit cross-chain transfer
TRANSFER_ID=$(aitbc cross-chain transfer <source> <dest> 100)

# Track transfer status
aitbc cross-chain status $TRANSFER_ID | grep -q "pending\|completed"

# Verify destination chain balance
aitbc wallet balance <wallet> --chain <dest>

# Verify source chain balance decreased
aitbc wallet balance <wallet> --chain <source>
```

**Expected Results:**
- Bridge is operational
- Transfer ID is valid and trackable
- Transfer completes successfully
- Balances updated correctly on both chains
- No tokens lost in transfer

## Automated Validation Scripts

### Batch Validation Script

```bash
#!/bin/bash
# validate_scenarios.sh - Batch validate multiple scenarios

SCENARIOS=("01_wallet_basics" "02_transaction_sending" "03_genesis_deployment")
PASSED=0
FAILED=0

for scenario in "${SCENARIOS[@]}"; do
    echo "Validating $scenario..."
    if aitbc validate scenario $scenario; then
        ((PASSED++))
        echo "✓ $scenario passed"
    else
        ((FAILED++))
        echo "✗ $scenario failed"
    fi
done

echo ""
echo "Validation Summary:"
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo "Total: $((PASSED + FAILED))"

exit $FAILED
```

### Stage Validation Script

```bash
#!/bin/bash
# validate_stage.sh - Validate all scenarios in a stage

STAGE=$1

if [ -z "$STAGE" ]; then
    echo "Usage: $0 <stage-number>"
    exit 1
fi

echo "Validating Stage $STAGE scenarios..."
aitbc validate stage $STAGE --verbose

if [ $? -eq 0 ]; then
    echo "✓ Stage $STAGE validation passed"
else
    echo "✗ Stage $STAGE validation failed"
    exit 1
fi
```

### Continuous Validation

```bash
#!/bin/bash
# continuous_validation.sh - Run validation continuously

INTERVAL=300  # 5 minutes

while true; do
    echo "Running validation at $(date)"
    aitbc validate stage 1
    aitbc validate stage 2
    aitbc validate stage 3
    
    echo "Sleeping for $INTERVAL seconds..."
    sleep $INTERVAL
done
```

## Validation Best Practices

### Pre-Validation Checklist
- Ensure blockchain node is running and synced
- Verify wallet has sufficient funds
- Check network connectivity
- Confirm required services are active
- Review scenario prerequisites

### Validation Frequency
- **Development**: Run validation after each scenario completion
- **Testing**: Run full validation before deployment
- **Production**: Run validation daily or on schedule
- **CI/CD**: Integrate validation into pipeline

### Handling Validation Failures
1. Review validation output for specific failure
2. Check logs for error messages
3. Verify prerequisites are met
4. Re-run scenario if needed
5. Consult troubleshooting guide if persistent

### Validation Reporting
```bash
# Generate validation report
aitbc validate stage 1 --report > validation-report-$(date +%Y%m%d).json

# View validation history
aitbc validate history

# Compare validation results
aitbc validate compare report-20260508.json report-20260509.json
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Scenario Validation
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup AITBC
        run: |
          pip install -e .
          aitbc setup environment
      - name: Validate Stage 1
        run: aitbc validate stage 1
      - name: Validate Stage 2
        run: aitbc validate stage 2
      - name: Validate Stage 3
        run: aitbc validate stage 3
```

### Gitea Actions Example

```yaml
name: Scenario Validation
on: [push]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.13'
      - name: Install AITBC
        run: |
          pip install -e .
          aitbc setup environment
      - name: Run Validation
        run: |
          for stage in {1..3}; do
            aitbc validate stage $stage
          done
```

## Validation Metrics

### Key Metrics to Track
- Scenario pass rate
- Average validation time
- Common failure patterns
- Validation trend over time
- Resource utilization during validation

### Metrics Collection

```bash
# Collect validation metrics
aitbc validate metrics --period 7d

# Export metrics to CSV
aitbc validate metrics --format csv > metrics.csv

# Generate validation report
aitbc validate report --period 30d > report.html
```

---

**Related Documentation:**
- [Troubleshooting Guide](./TROUBLESHOOTING_GUIDE.md)
- [Agent Training README](../agent-training/README.md)
- [Interactive Learning Paths](../agent-training/INTERACTIVE_LEARNING_PATHS.md)
