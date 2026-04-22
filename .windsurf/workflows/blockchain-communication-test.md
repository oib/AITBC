---
description: Blockchain communication testing workflow for multi-node AITBC setup
title: Blockchain Communication Test
version: 1.0
---

# Blockchain Communication Test Workflow

## Purpose
Test and verify blockchain communication between aitbc (genesis) and aitbc1 (follower) nodes running on port 8006 on different physical machines.

## Prerequisites
- Both nodes (aitbc and aitbc1) must be running
- AITBC CLI accessible: `/opt/aitbc/aitbc-cli`
- Network connectivity between nodes
- Git repository access for synchronization

## Quick Start
```bash
# Run complete communication test
cd /opt/aitbc
./scripts/blockchain-communication-test.sh --full

# Run specific test type
./scripts/blockchain-communication-test.sh --type connectivity
./scripts/blockchain-communication-test.sh --type transaction
./scripts/blockchain-communication-test.sh --type sync

# Run with debug output
./scripts/blockchain-communication-test.sh --full --debug
```

## Test Types

### 1. Connectivity Test
Verify basic network connectivity and service availability.

```bash
# Test genesis node (aitbc)
curl http://10.1.223.40:8006/health

# Test follower node (aitbc1)
curl http://<aitbc1-ip>:8006/health

# Test P2P connectivity
./aitbc-cli network ping --node aitbc1 --host <aitbc1-ip> --port 8006 --verbose
./aitbc-cli network peers --verbose
```

### 2. Blockchain Status Test
Verify blockchain status and synchronization on both nodes.

```bash
# Check genesis node status
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli blockchain info --verbose
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli blockchain height --output json

# Check follower node status
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli blockchain info --verbose
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli blockchain height --output json

# Compare block heights
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli blockchain height --output json
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli blockchain height --output json
```

### 3. Transaction Test
Test transaction propagation between nodes.

```bash
# Create test wallets
./aitbc-cli wallet create --name test-sender --password test123 --yes --no-confirm
./aitbc-cli wallet create --name test-receiver --password test123 --yes --no-confirm

# Fund sender wallet (if needed)
./aitbc-cli wallet send --from genesis-ops --to test-sender --amount 100 --password <password> --yes

# Send transaction
./aitbc-cli wallet send --from test-sender --to test-receiver --amount 10 --password test123 --yes --verbose

# Verify on both nodes
./aitbc-cli wallet transactions --name test-sender --limit 5 --format table
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli wallet transactions --name test-receiver --limit 5 --format table
```

### 4. Agent Messaging Test
Test agent message propagation over blockchain.

```bash
# Send agent message
./aitbc-cli agent message --to <agent_id> --content "Test message from aitbc" --debug

# Check messages
./aitbc-cli agent messages --from <agent_id> --verbose

# Verify on follower node
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli agent messages --from <agent_id> --verbose
```

### 5. Synchronization Test
Verify git-based synchronization between nodes.

```bash
# Check git status on both nodes
cd /opt/aitbc && git status --verbose
ssh aitbc1 'cd /opt/aitbc && git status --verbose'

# Sync from Gitea
git pull origin main --verbose
ssh aitbc1 'cd /opt/aitbc && git pull origin main --verbose'

# Verify sync
git log --oneline -5 --decorate
ssh aitbc1 'cd /opt/aitbc && git log --oneline -5 --decorate'
```

## Automated Script

### Script Location
`/opt/aitbc/scripts/blockchain-communication-test.sh`

### Script Usage
```bash
# Full test suite
./scripts/blockchain-communication-test.sh --full

# Specific test types
./scripts/blockchain-communication-test.sh --type connectivity
./scripts/blockchain-communication-test.sh --type blockchain
./scripts/blockchain-communication-test.sh --type transaction
./scripts/blockchain-communication-test.sh --type sync

# Debug mode
./scripts/blockchain-communication-test.sh --full --debug

# Continuous monitoring
./scripts/blockchain-communication-test.sh --monitor --interval 300
```

### Script Features
- **Automated testing**: Runs all test types sequentially
- **Progress tracking**: Detailed logging of each test step
- **Error handling**: Graceful failure with diagnostic information
- **Report generation**: JSON and HTML test reports
- **Continuous monitoring**: Periodic testing with alerts

## Production Monitoring

### Monitoring Script
```bash
# Continuous monitoring with alerts
./scripts/blockchain-communication-test.sh --monitor --interval 300 --alert-email admin@example.com
```

### Monitoring Metrics
- Node availability (uptime)
- Block synchronization lag
- Transaction propagation time
- Network latency
- Git synchronization status

### Alert Conditions
- Node unreachable for > 5 minutes
- Block sync lag > 10 blocks
- Transaction timeout > 60 seconds
- Network latency > 100ms
- Git sync failure

## Training Integration

### Integration with Mastery Plan
This workflow integrates with Stage 2 (Intermediate Operations) of the OpenClaw AITBC Mastery Plan.

### Training Script
`/opt/aitbc/scripts/training/stage2_intermediate.sh` includes blockchain communication testing as part of the training curriculum.

## Troubleshooting

### Common Issues

#### Node Unreachable
```bash
# Check network connectivity
ping <aitbc1-ip>
curl http://<aitbc1-ip>:8006/health

# Check firewall
iptables -L | grep 8006

# Check service status
ssh aitbc1 'systemctl status aitbc-blockchain-rpc'
```

#### Block Sync Lag
```bash
# Check sync status
./aitbc-cli network sync status --verbose

# Force sync if needed
./aitbc-cli cluster sync --all --yes

# Restart services if needed
ssh aitbc1 'systemctl restart aitbc-blockchain-p2p'
```

#### Transaction Timeout
```bash
# Check wallet balance
./aitbc-cli wallet balance --name test-sender

# Check transaction status
./aitbc-cli wallet transactions --name test-sender --limit 10

# Verify network status
./aitbc-cli network status --verbose
```

#### P2P Identity Conflict (Duplicate Node IDs)
```bash
# Check current node IDs on all nodes
echo "=== aitbc node IDs ==="
grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env

echo "=== aitbc1 node IDs ==="
ssh aitbc1 'grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env'

echo "=== gitea-runner node IDs ==="
ssh gitea-runner 'grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env'

# Run unique ID generation on affected nodes
python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py
ssh aitbc1 'python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py'
ssh gitea-runner 'python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py'

# Restart P2P services on all nodes
systemctl restart aitbc-blockchain-p2p
ssh aitbc1 'systemctl restart aitbc-blockchain-p2p'
ssh gitea-runner 'systemctl restart aitbc-blockchain-p2p'

# Verify P2P connectivity
journalctl -u aitbc-blockchain-p2p -n 30 --no-pager
ssh aitbc1 'journalctl -u aitbc-blockchain-p2p -n 30 --no-pager'
ssh gitea-runner 'journalctl -u aitbc-blockchain-p2p -n 30 --no-pager'
```

## Success Criteria
- Both nodes respond to health checks
- Block heights match within 2 blocks
- Transactions propagate within 30 seconds
- Agent messages sync within 10 seconds
- Git synchronization completes successfully
- Network latency < 50ms between nodes

## Log Files
- Test logs: `/var/log/aitbc/blockchain-communication-test.log`
- Monitoring logs: `/var/log/aitbc/blockchain-monitor.log`
- Error logs: `/var/log/aitbc/blockchain-test-errors.log`

## Related Workflows
- [Multi-Node Operations](/multi-node-blockchain-operations.md)
- [Multi-Node Setup Core](/multi-node-blockchain-setup-core.md)
- [Ollama GPU Test OpenClaw](/ollama-gpu-test-openclaw.md)
