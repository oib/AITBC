---
description: Basic CLI functionality and core operations testing module
title: Basic Testing Module - CLI and Core Operations
version: 1.0
---

# Basic Testing Module - CLI and Core Operations

This module covers basic CLI functionality testing, core blockchain operations, wallet operations, and service connectivity validation.

## Prerequisites

### Required Setup
- Working directory: `/opt/aitbc`
- Virtual environment: `/opt/aitbc/venv`
- CLI wrapper: `/opt/aitbc/aitbc-cli`
- Services running on correct ports (8000, 8001, 8006)

### Environment Setup
```bash
cd /opt/aitbc
source venv/bin/activate
./aitbc-cli --version
```

## 1. CLI Command Testing

### Basic CLI Commands
```bash
# Test CLI version and help
./aitbc-cli --version
./aitbc-cli --help

# Test core commands
./aitbc-cli create --name test-wallet --password test123
./aitbc-cli list
./aitbc-cli balance --wallet test-wallet

# Test blockchain operations
./aitbc-cli chain
./aitbc-cli network
```

### Expected Results
- CLI version should display without errors
- Help should show all available commands
- Wallet operations should complete successfully
- Blockchain operations should return current status

### Troubleshooting CLI Issues
```bash
# Check CLI installation
which aitbc-cli
ls -la /opt/aitbc/aitbc-cli

# Check virtual environment
source venv/bin/activate
python --version
pip list | grep aitbc

# Fix CLI issues
cd /opt/aitbc/cli
source venv/bin/activate
pip install -e .
```

## 2. Service Connectivity Testing

### Check Service Status
```bash
# Test Coordinator API (port 8000)
curl -sf http://localhost:8000/health || echo "Coordinator API not responding"

# Test Exchange API (port 8001)
curl -sf http://localhost:8001/health || echo "Exchange API not responding"

# Test Blockchain RPC (port 8006)
curl -sf http://localhost:8006/rpc/health || echo "Blockchain RPC not responding"

# Test Ollama (port 11434)
curl -sf http://localhost:11434/api/tags || echo "Ollama not responding"
```

### Service Restart Commands
```bash
# Restart services if needed
sudo systemctl restart aitbc-coordinator
sudo systemctl restart aitbc-exchange  
sudo systemctl restart aitbc-blockchain
sudo systemctl restart aitbc-ollama

# Check service status
sudo systemctl status aitbc-coordinator
sudo systemctl status aitbc-exchange
sudo systemctl status aitbc-blockchain
sudo systemctl status aitbc-ollama
```

## 3. Wallet Operations Testing

### Create and Test Wallets
```bash
# Create test wallet
./aitbc-cli create --name basic-test --password test123

# List wallets
./aitbc-cli list

# Check balance
./aitbc-cli balance --wallet basic-test

# Send test transaction (if funds available)
./aitbc-cli send --from basic-test --to $(./aitbc-cli list | jq -r '.[0].address') --amount 1 --fee 10 --password test123
```

### Wallet Validation
```bash
# Verify wallet files exist
ls -la /var/lib/aitbc/keystore/

# Check wallet permissions
ls -la /var/lib/aitbc/keystore/basic-test*

# Test wallet encryption
./aitbc-cli balance --wallet basic-test --password wrong-password 2>/dev/null && echo "ERROR: Wrong password accepted" || echo "✅ Password validation working"
```

## 4. Blockchain Operations Testing

### Basic Blockchain Tests
```bash
# Get blockchain info
./aitbc-cli chain

# Get network status
./aitbc-cli network

# Test transaction submission
./aitbc-cli send --from genesis-ops --to $(./aitbc-cli list | jq -r '.[0].address') --amount 0.1 --fee 1 --password 123

# Check transaction status
./aitbc-cli transactions --wallet genesis-ops --limit 5
```

### Blockchain Validation
```bash
# Check blockchain height
HEIGHT=$(./aitbc-cli chain | jq -r '.height // 0')
echo "Current height: $HEIGHT"

# Verify network connectivity
NODES=$(./aitbc-cli network | jq -r '.active_nodes // 0')
echo "Active nodes: $NODES"

# Check consensus status
CONSENSUS=$(./aitbc-cli chain | jq -r '.consensus // "unknown"')
echo "Consensus: $CONSENSUS"
```

## 5. Resource Management Testing

### Basic Resource Operations
```bash
# Check resource status
./aitbc-cli resource status

# Test resource allocation
./aitbc-cli resource allocate --agent-id test-agent --cpu 1 --memory 1024 --duration 1800

# Monitor resource usage
./aitbc-cli resource status
```

### Resource Validation
```bash
# Check system resources
free -h
df -h
nvidia-smi 2>/dev/null || echo "NVIDIA GPU not available"

# Check process resources
ps aux | grep aitbc
```

## 6. Analytics Testing

### Basic Analytics Operations
```bash
# Test analytics commands
./aitbc-cli analytics --action summary
./aitbc-cli analytics --action performance
./aitbc-cli analytics --action network-stats
```

### Analytics Validation
```bash
# Check analytics data
./aitbc-cli analytics --action summary | jq .
./aitbc-cli analytics --action performance | jq .
```

## 7. Mining Operations Testing

### Basic Mining Tests
```bash
# Check mining status
./aitbc-cli mine-status

# Start mining (if not running)
./aitbc-cli mine-start

# Stop mining
./aitbc-cli mine-stop
```

### Mining Validation
```bash
# Check mining process
ps aux | grep miner

# Check mining rewards
./aitbc-cli balance --wallet genesis-ops
```

## 8. Test Automation Script

### Automated Basic Tests
```bash
#!/bin/bash
# automated_basic_tests.sh

echo "=== Basic AITBC Tests ==="

# Test CLI
echo "Testing CLI..."
./aitbc-cli --version || exit 1
./aitbc-cli --help | grep -q "create" || exit 1

# Test Services
echo "Testing Services..."
curl -sf http://localhost:8000/health || exit 1
curl -sf http://localhost:8001/health || exit 1
curl -sf http://localhost:8006/rpc/health || exit 1

# Test Blockchain
echo "Testing Blockchain..."
./aitbc-cli chain | jq -r '.height' || exit 1

# Test Resources
echo "Testing Resources..."
./aitbc-cli resource status | jq -r '.cpu_utilization' || exit 1

echo "✅ All basic tests passed!"
```

## 9. Troubleshooting Guide

### Common Issues and Solutions

#### CLI Not Found
```bash
# Problem: aitbc-cli command not found
# Solution: Check installation and PATH
which aitbc-cli
export PATH="/opt/aitbc:$PATH"
```

#### Service Not Responding
```bash
# Problem: Service not responding on port
# Solution: Check service status and restart
sudo systemctl status aitbc-coordinator
sudo systemctl restart aitbc-coordinator
```

#### Wallet Issues
```bash
# Problem: Wallet operations failing
# Solution: Check keystore permissions
sudo chown -R aitbc:aitbc /var/lib/aitbc/keystore/
sudo chmod 700 /var/lib/aitbc/keystore/
```

#### Blockchain Sync Issues
```bash
# Problem: Blockchain not syncing
# Solution: Check network connectivity
./aitbc-cli network
sudo systemctl restart aitbc-blockchain
```

## 10. Success Criteria

### Pass/Fail Criteria
- ✅ CLI commands execute without errors
- ✅ All services respond to health checks
- ✅ Wallet operations complete successfully
- ✅ Blockchain operations return valid data
- ✅ Resource allocation works correctly
- ✅ Analytics data is accessible
- ✅ Mining operations can be controlled

### Performance Benchmarks
- CLI response time: <2 seconds
- Service health check: <1 second
- Wallet creation: <5 seconds
- Transaction submission: <3 seconds
- Resource status: <1 second

---

**Dependencies**: None (base module)  
**Next Module**: [OpenClaw Agent Testing](test-openclaw-agents.md) or [AI Operations Testing](test-ai-operations.md)
