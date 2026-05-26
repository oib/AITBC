# AITBC Scenario Troubleshooting Guide

**Last Updated:** 2026-05-09  
**Version:** 1.0  
**Purpose:** Common failure points and solutions for AITBC scenarios

---

## Overview

This guide provides troubleshooting information for common issues encountered when working through AITBC scenarios. Each scenario may have specific failure points, but many issues follow common patterns across the system.

## Common Failure Patterns

### Wallet-Related Issues

#### Issue: Wallet Creation Fails
**Symptoms:**
- Error: "Wallet already exists"
- Error: "Invalid password"
- Error: "Keystore directory not accessible"

**Solutions:**
```bash
# Check if wallet already exists
ls -la /var/lib/aitbc/keystore/

# Remove existing wallet if needed (CAUTION: loses funds)
rm /var/lib/aitbc/keystore/<wallet-name>.json

# Verify keystore directory permissions
chmod 700 /var/lib/aitbc/keystore/
chown aitbc:aitbc /var/lib/aitbc/keystore/
```

**Prevention:**
- Use deterministic wallet naming (e.g., test-wallet-001, test-wallet-002)
- Always check for existing wallets before creation
- Use strong passwords and store them securely

#### Issue: Insufficient Funds
**Symptoms:**
- Error: "Insufficient funds for transaction"
- Transaction rejected by blockchain

**Solutions:**
```bash
# Check wallet balance
aitbc wallet balance <wallet-name>

# Fund wallet from genesis wallet if available
aitbc transaction send genesis <wallet-name> 1000

# Or use faucet if available
curl -X POST http://faucet.aitbc.local/fund \
  -H "Content-Type: application/json" \
  -d '{"address": "<wallet-address>", "amount": 1000}'
```

**Prevention:**
- Always check balance before transactions
- Use testnet faucets for development
- Maintain a funding wallet for test operations

### Blockchain Node Issues

#### Issue: Node Not Running
**Symptoms:**
- Error: "Connection refused"
- Error: "Node not responding"
- CLI commands timeout

**Solutions:**
```bash
# Check node status
systemctl status aitbc-blockchain-node.service

# Start node if stopped
systemctl start aitbc-blockchain-node.service

# Check node logs
journalctl -u aitbc-blockchain-node.service -f

# Verify node connectivity
aitbc blockchain status
```

**Prevention:**
- Monitor node health regularly
- Set up automated restart on failure
- Use systemd auto-restart configuration

#### Issue: Node Out of Sync
**Symptoms:**
- Transactions not confirming
- Balance showing incorrect values
- Block height mismatch

**Solutions:**
```bash
# Check sync status
aitbc blockchain sync status

# Force sync if needed
aitbc blockchain sync force

# Enable auto-sync in /etc/aitbc/.env
echo "auto_sync_enabled=true" >> /etc/aitbc/.env
systemctl restart aitbc-blockchain-node.service
```

**Prevention:**
- Enable auto-sync in configuration
- Monitor sync status regularly
- Use stable network connections

### Marketplace Issues

#### Issue: Bid Not Accepted
**Symptoms:**
- Bid rejected by marketplace
- Error: "Insufficient balance for bid"
- Error: "Invalid bid amount"

**Solutions:**
```bash
# Check marketplace status
aitbc marketplace status

# Verify wallet balance
aitbc wallet balance <wallet-name>

# Check current market rates
aitbc marketplace rates

# Retry with valid bid amount
aitbc marketplace bid <listing-id> <amount> <wallet-name>
```

**Prevention:**
- Check market rates before bidding
- Ensure sufficient balance including fees
- Use bid validation before submission

#### Issue: GPU Listing Not Appearing
**Symptoms:**
- GPU not visible in marketplace
- Listing creation fails
- Error: "Invalid GPU configuration"

**Solutions:**
```bash
# Verify GPU availability
nvidia-smi

# Check GPU service status
systemctl status aitbc-gpu-service.service

# Re-list GPU with correct configuration
aitbc marketplace gpu list --gpu-id <gpu-id> --price <price>
```

**Prevention:**
- Verify GPU hardware before listing
- Test GPU service independently
- Use standard pricing models

### AI Job Issues

#### Issue: Job Submission Fails
**Symptoms:**
- Error: "Invalid job parameters"
- Error: "Insufficient compute resources"
- Job stuck in "pending" state

**Solutions:**
```bash
# Check AI service status
systemctl status aitbc-ai.service

# Verify job parameters
aitbc ai job validate --file <job-config.json>

# Check available compute resources
aitbc marketplace resources available

# Retry job submission
aitbc ai job submit <job-config.json>
```

**Prevention:**
- Validate job configuration before submission
- Check resource availability first
- Use job templates for common tasks

#### Issue: Job Execution Timeout
**Symptoms:**
- Job runs longer than expected
- Job marked as "failed" due to timeout
- No results returned

**Solutions:**
```bash
# Check job status
aitbc ai job status <job-id>

# Extend timeout if needed
aitbc ai job update <job-id> --timeout <new-timeout>

# Check compute provider logs
journalctl -u aitbc-gpu-service.service -f
```

**Prevention:**
- Set realistic timeout values
- Monitor job progress actively
- Use checkpointing for long-running jobs

### Cross-Chain Issues

#### Issue: Bridge Transfer Fails
**Symptoms:**
- Error: "Bridge not available"
- Error: "Invalid bridge configuration"
- Transfer stuck in "pending" state

**Solutions:**
```bash
# Check bridge status
aitbc cross-chain bridge status

# Verify bridge configuration
aitbc cross-chain bridge config

# Retry transfer
aitbc cross-chain transfer <source-chain> <dest-chain> <amount>
```

**Prevention:**
- Verify bridge availability before transfer
- Use testnet for initial cross-chain tests
- Monitor bridge health regularly

### Network Issues

#### Issue: Peer Connection Failed
**Symptoms:**
- Error: "No peers available"
- Network not syncing
- Gossip messages not delivered

**Solutions:**
```bash
# Check peer connectivity
aitbc network peers

# Add bootstrap peers manually
aitbc network peers add <peer-address>

# Check network configuration
cat /etc/aitbc/node.env | grep PEER

# Restart network service
systemctl restart aitbc-blockchain-p2p.service
```

**Prevention:**
- Configure bootstrap peers
- Monitor peer count regularly
- Use reliable peer sources

### Security Issues

#### Issue: Authentication Failed
**Symptoms:**
- Error: "Invalid JWT token"
- Error: "Authentication required"
- API calls rejected

**Solutions:**
```bash
# Check JWT token
aitbc auth token verify <token>

# Generate new token
aitbc auth token generate <wallet-name>

# Check API key configuration
cat /etc/aitbc/.env | grep API_KEY
```

**Prevention:**
- Use secure token storage
- Rotate tokens regularly
- Implement token refresh logic

#### Issue: Permission Denied
**Symptoms:**
- Error: "Permission denied"
- Cannot access resources
- Operations rejected

**Solutions:**
```bash
# Check file permissions
ls -la /var/lib/aitbc/

# Fix permissions
chmod 755 /var/lib/aitbc/
chown -R aitbc:aitbc /var/lib/aitbc/

# Check user permissions
aitbc auth permissions <wallet-name>
```

**Prevention:**
- Use principle of least privilege
- Regular permission audits
- Document permission requirements

## Scenario-Specific Troubleshooting

### Scenario 01: Wallet Basics
**Common Issues:**
- Wallet creation fails due to existing wallet
- Password too weak or forgotten
- Keystore permission errors

**Quick Fix:**
```bash
# Use unique wallet names
aitbc wallet create test-wallet-$(date +%s)

# Use strong passwords
aitbc wallet create test-wallet --password "$(openssl rand -base64 32)"
```

### Scenario 02: Transaction Sending
**Common Issues:**
- Insufficient funds
- Transaction not confirming
- Invalid recipient address

**Quick Fix:**
```bash
# Verify balance first
aitbc wallet balance <wallet-name>

# Check transaction status
aitbc transaction status <tx-hash>

# Use test addresses for development
aitbc transaction send <wallet> 0x0000000000000000000000000000000000000000 1
```

### Scenario 03: Genesis Deployment
**Common Issues:**
- Genesis wallet not configured
- Invalid genesis parameters
- Network already initialized

**Quick Fix:**
```bash
# Check genesis wallet
ls -la /var/lib/aitbc/keystore/genesis.json

# Verify genesis configuration
aitbc genesis validate

# Reset network if needed (CAUTION: destroys data)
aitbc genesis reset --force
```

### Scenario 07: AI Job Submission
**Common Issues:**
- Invalid job parameters
- No available compute resources
- Job stuck in queue

**Quick Fix:**
```bash
# Validate job config
aitbc ai job validate --file job.json

# Check resource availability
aitbc marketplace resources available

# Monitor job queue
aitbc ai job queue
```

## General Debugging Tips

### Enable Verbose Logging
```bash
# Enable verbose CLI output
export AITBC_LOG_LEVEL=DEBUG

# Enable service debug logging
echo "LOG_LEVEL=DEBUG" >> /etc/aitbc/.env
systemctl restart aitbc-*.service
```

### Check System Logs
```bash
# View recent logs
journalctl -u aitbc-* -n 100

# Follow logs in real-time
journalctl -u aitbc-* -f

# Filter by error level
journalctl -u aitbc-* -p err
```

### Verify Configuration
```bash
# Check all AITBC configuration
aitbc config show

# Validate configuration files
aitbc config validate

# Check environment variables
env | grep AITBC
```

### Network Diagnostics
```bash
# Check connectivity to blockchain node
curl -X POST http://localhost:8006 -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'

# Check peer connections
aitbc network peers

# Test gossip protocol
aitbc gossip test
```

## Getting Help

### Documentation Resources
- [Agent Training Documentation](../agent-training/README.md)
- [Scenario Documentation](./README.md)
- [Master Glossary](../GLOSSARY.md)

### Community Support
- Check existing issues in the repository
- Search forums for similar problems
- Contact AITBC development team

### Reporting Issues
When reporting issues, include:
1. Scenario being worked on
2. Exact error messages
3. Steps to reproduce
4. System configuration
5. Relevant log output

---

**Related Documentation:**
- [Agent Training README](../agent-training/README.md)
- [Interactive Learning Paths](../agent-training/INTERACTIVE_LEARNING_PATHS.md)
- [Operations Audit](../agent-training/OPERATIONS_AUDIT.md)
