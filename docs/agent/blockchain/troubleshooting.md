# Troubleshooting Guide

This guide helps diagnose and resolve common issues with Agent blockchain integrations.

## Common Issues

### Connection refused

**Symptoms:**
- RPC calls fail with connection refused
- Cannot reach hub blockchain node

**Solutions:**
- Check hub node is running: `systemctl status aitbc-blockchain-node`
- Verify HUB_DISCOVERY_URL in `/etc/aitbc/blockchain.env`
- Test RPC connectivity: `curl http://hub.aitbc.bubuit.net:8202/rpc/head`

### Insufficient balance

**Symptoms:**
- Staking operations fail
- GPU allocation operations fail

**Solutions:**
- Ensure wallet has enough AITBC tokens for staking
- Request tokens from faucet: `aitbc wallet faucet --wallet <wallet>`
- Check wallet balance: `aitbc wallet balance --wallet <wallet>`

### Already voted

**Symptoms:**
- Governance vote fails
- Error message indicates already voted

**Solutions:**
- Each address can only vote once per proposal
- Check existing votes: `aitbc operations governance get-proposal <proposal_id>`
- Use a different wallet address if needed

### Proposal not found

**Symptoms:**
- Query proposal returns 404
- Vote operations fail

**Solutions:**
- Ensure proposal_id matches exactly what was created
- Query all proposals to verify
- Check chain_id matches expected value

### GPU not found

**Symptoms:**
- GPU query returns 404
- Allocation operations fail

**Solutions:**
- Verify GPU was registered on-chain: `aitbc gpu-onchain query <gpu_id>`
- Check chain_id matches expected value
- Re-register GPU if needed

### Wallet not found

**Symptoms:**
- Operations fail with wallet not found error
- Cannot load wallet

**Solutions:**
- Check wallet exists: `aitbc wallet list`
- Verify wallet path: `ls ~/.aitbc/wallets/`
- Create wallet if needed: `aitbc wallet create <wallet-name>`

## Debug Commands

```bash
# Check blockchain node status
systemctl status aitbc-blockchain-node

# Check blockchain logs
journalctl -u aitbc-blockchain-node -f

# Check environment variables
cat /etc/aitbc/blockchain.env | grep HUB_DISCOVERY_URL

# Test RPC connectivity
curl http://hub.aitbc.bubuit.net:8202/rpc/head

# Check wallet configuration
cat ~/.aitbc/config.yaml

# List available wallets
aitbc wallet list

# Check database integrity
sqlite3 /var/lib/aitbc/blockchain.db "PRAGMA integrity_check;"
```

## Log Locations

- **Blockchain node**: `journalctl -u aitbc-blockchain-node`
- **GPU service**: `journalctl -u aitbc-gpu-service`
- **CLI operations**: Check terminal output or enable verbose mode with `-v` flag

## Getting Help

If issues persist after troubleshooting:
1. Check the [Architecture Notes](./architecture.md) for system design details
2. Review [Best Practices](./best-practices.md) for recommended usage patterns
3. Consult the main AITBC documentation for broader system issues
4. Report issues with detailed logs and reproduction steps
