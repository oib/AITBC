---
description: Complete AITBC blockchain operations and integration
title: AITBC Blockchain Operations Skill
version: 1.0
---

# AITBC Blockchain Operations Skill

This skill provides comprehensive AITBC blockchain operations including wallet management, transactions, AI operations, marketplace participation, and node coordination.

## Prerequisites

- AITBC multi-node blockchain operational (aitbc genesis, aitbc1 follower)
- AITBC CLI accessible: `/opt/aitbc/aitbc-cli`
- SSH access between nodes for cross-node operations
- Systemd services: `aitbc-blockchain-node.service`, `aitbc-blockchain-rpc.service`
- Poetry 2.3.3+ for Python package management
- Wallet passwords known (default: 123 for new wallets)

## Critical: Correct CLI Syntax

### AITBC CLI Commands
```bash
# All commands run from /opt/aitbc with venv active
cd /opt/aitbc && source venv/bin/activate

# Basic Operations
./aitbc-cli create --name wallet-name        # Create wallet
./aitbc-cli list                              # List wallets
./aitbc-cli balance --name wallet-name        # Check balance
./aitbc-cli send --from w1 --to addr --amount 100 --password pass
./aitbc-cli chain                             # Blockchain info
./aitbc-cli network                           # Network status
./aitbc-cli analytics                         # Analytics data
```

### Cross-Node Operations
```bash
# Always activate venv on remote nodes
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli list'

# Cross-node transaction
./aitbc-cli send --from genesis-ops --to ait141b3bae6eea3a74273ef3961861ee58e12b6d855 --amount 100 --password 123
```

## Wallet Management

### Creating Wallets
```bash
# Create new wallet with password
./aitbc-cli create --name my-wallet --password 123

# List all wallets
./aitbc-cli list

# Check wallet balance
./aitbc-cli balance --name my-wallet
```

### Wallet Operations
```bash
# Send transaction
./aitbc-cli send --from wallet1 --to wallet2 --amount 100 --password 123

# Check transaction history
./aitbc-cli transactions --name my-wallet

# Import wallet from keystore
./aitbc-cli import --keystore /path/to/keystore.json --password 123
```

### Standard Wallet Addresses
```bash
# Genesis operations wallet
./aitbc-cli balance --name genesis-ops
# Address: ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871

# Follower operations wallet  
./aitbc-cli balance --name follower-ops
# Address: ait141b3bae6eea3a74273ef3961861ee58e12b6d855
```

## Blockchain Operations

### Chain Information
```bash
# Get blockchain status
./aitbc-cli chain

# Get network status
./aitbc-cli network

# Get analytics data
./aitbc-cli analytics

# Check block height
curl -s http://localhost:8006/rpc/head | jq .height
```

### Node Status
```bash
# Check health endpoint
curl -s http://localhost:8006/health | jq .

# Check both nodes
curl -s http://localhost:8006/health | jq .
ssh aitbc1 'curl -s http://localhost:8006/health | jq .'

# Check services
systemctl is-active aitbc-blockchain-node.service aitbc-blockchain-rpc.service
ssh aitbc1 'systemctl is-active aitbc-blockchain-node.service aitbc-blockchain-rpc.service'
```

### Synchronization Monitoring
```bash
# Check height difference
GENESIS_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FOLLOWER_HEIGHT=$(ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height')
echo "Height diff: $((FOLLOWER_HEIGHT - GENESIS_HEIGHT))"

# Comprehensive health check
python3 /tmp/aitbc1_heartbeat.py
```

## Agent Operations

### Creating Agents
```bash
# Create basic agent
./aitbc-cli agent create --name agent-name --description "Agent description"

# Create agent with full verification
./aitbc-cli agent create --name agent-name --description "Agent description" --verification full

# Create AI-specific agent
./aitbc-cli agent create --name ai-agent --description "AI processing agent" --verification full
```

### Managing Agents
```bash
# Execute agent
./aitbc-cli agent execute --name agent-name --wallet wallet --priority high

# Check agent status
./aitbc-cli agent status --name agent-name

# List all agents
./aitbc-cli agent list
```

## AI Operations

### AI Job Submission
```bash
# Inference job
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Generate image" --payment 100

# Training job
./aitbc-cli ai-submit --wallet genesis-ops --type training --model "gpt-3.5" --dataset "data.json" --payment 500

# Multimodal job
./aitbc-cli ai-submit --wallet genesis-ops --type multimodal --prompt "Analyze image" --image-path "/path/to/img.jpg" --payment 200
```

### AI Job Types
- **inference**: Image generation, text analysis, predictions
- **training**: Model training on datasets
- **processing**: Data transformation and analysis
- **multimodal**: Combined text, image, audio processing

### AI Job Monitoring
```bash
# Check job status
./aitbc-cli ai-status --job-id job_123

# Check job history
./aitbc-cli ai-history --wallet genesis-ops --limit 10

# Estimate job cost
./aitbc-cli ai-estimate --type inference --prompt-length 100 --resolution 512
```

## Resource Management

### Resource Allocation
```bash
# Allocate GPU resources
./aitbc-cli resource allocate --agent-id ai-agent --gpu 1 --memory 8192 --duration 3600

# Allocate CPU resources
./aitbc-cli resource allocate --agent-id data-processor --cpu 4 --memory 4096 --duration 1800

# Check resource status
./aitbc-cli resource status

# List allocated resources
./aitbc-cli resource list
```

### Resource Types
- **gpu**: GPU units for AI inference
- **cpu**: CPU cores for processing
- **memory**: RAM in megabytes
- **duration**: Reservation time in seconds

## Marketplace Operations

### Creating Services
```bash
# Create AI service
./aitbc-cli marketplace --action create --name "AI Image Generation" --type ai-inference --price 50 --wallet genesis-ops --description "Generate high-quality images"

# Create training service
./aitbc-cli marketplace --action create --name "Model Training" --type ai-training --price 200 --wallet genesis-ops --description "Train custom models"

# Create data processing service
./aitbc-cli marketplace --action create --name "Data Analysis" --type ai-processing --price 75 --wallet genesis-ops --description "Analyze datasets"
```

### Marketplace Interaction
```bash
# List available services
./aitbc-cli marketplace --action list

# Search for services
./aitbc-cli marketplace --action search --query "AI"

# Bid on service
./aitbc-cli marketplace --action bid --service-id service_123 --amount 60 --wallet genesis-ops

# Execute purchased service
./aitbc-cli marketplace --action execute --service-id service_123 --job-data "prompt:Generate landscape image"

# Check my listings
./aitbc-cli marketplace --action my-listings --wallet genesis-ops
```

## Mining Operations

### Mining Control
```bash
# Start mining
./aitbc-cli mine-start --wallet genesis-ops

# Stop mining
./aitbc-cli mine-stop

# Check mining status
./aitbc-cli mine-status
```

## Smart Contract Messaging

### Topic Management
```bash
# Create coordination topic
curl -X POST http://localhost:8006/rpc/messaging/topics/create \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent", "agent_address": "address", "title": "Topic", "description": "Description", "tags": ["coordination"]}'

# List topics
curl -s http://localhost:8006/rpc/messaging/topics

# Get topic messages
curl -s http://localhost:8006/rpc/messaging/topics/topic_id/messages
```

### Message Operations
```bash
# Post message to topic
curl -X POST http://localhost:8006/rpc/messaging/messages/post \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent", "agent_address": "address", "topic_id": "topic_id", "content": "Message content"}'

# Vote on message
curl -X POST http://localhost:8006/rpc/messaging/messages/message_id/vote \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent", "agent_address": "address", "vote_type": "upvote"}'

# Check agent reputation
curl -s http://localhost:8006/rpc/messaging/agents/agent_id/reputation
```

## Cross-Node Coordination

### Cross-Node Transactions
```bash
# Send from genesis to follower
./aitbc-cli send --from genesis-ops --to ait141b3bae6eea3a74273ef3961861ee58e12b6d855 --amount 100 --password 123

# Send from follower to genesis
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli send --from follower-ops --to ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871 --amount 50 --password 123'
```

### Cross-Node AI Operations
```bash
# Submit AI job to specific node
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Generate image" --target-node "aitbc1" --payment 100

# Distribute training across nodes
./aitbc-cli ai-submit --wallet genesis-ops --type training --model "distributed-model" --nodes "aitbc,aitbc1" --payment 500
```

## Configuration Management

### Environment Configuration
```bash
# Check current configuration
cat /etc/aitbc/.env

# Key configuration parameters
chain_id=ait-mainnet
proposer_id=ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871
enable_block_production=true
mempool_backend=database
gossip_backend=redis
gossip_broadcast_url=redis://10.1.223.40:6379
```

### Service Management
```bash
# Restart services
sudo systemctl restart aitbc-blockchain-node.service aitbc-blockchain-rpc.service

# Check service logs
sudo journalctl -u aitbc-blockchain-node.service -f
sudo journalctl -u aitbc-blockchain-rpc.service -f

# Cross-node service restart
ssh aitbc1 'sudo systemctl restart aitbc-blockchain-node.service aitbc-blockchain-rpc.service'
```

## Data Management

### Database Operations
```bash
# Check database files
ls -la /var/lib/aitbc/data/ait-mainnet/

# Backup database
sudo cp /var/lib/aitbc/data/ait-mainnet/chain.db /var/lib/aitbc/data/ait-mainnet/chain.db.backup.$(date +%s)

# Reset blockchain (genesis creation)
sudo systemctl stop aitbc-blockchain-node.service aitbc-blockchain-rpc.service
sudo mv /var/lib/aitbc/data/ait-mainnet/chain.db /var/lib/aitbc/data/ait-mainnet/chain.db.backup.$(date +%s)
sudo systemctl start aitbc-blockchain-node.service aitbc-blockchain-rpc.service
```

### Genesis Configuration
```bash
# Create genesis.json with allocations
cat << 'EOF' | sudo tee /var/lib/aitbc/data/ait-mainnet/genesis.json
{
  "allocations": [
    {
      "address": "ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871",
      "balance": 1000000,
      "nonce": 0
    }
  ],
  "authorities": [
    {
      "address": "ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871",
      "weight": 1
    }
  ]
}
EOF
```

## Monitoring and Analytics

### Health Monitoring
```bash
# Comprehensive health check
python3 /tmp/aitbc1_heartbeat.py

# Manual health checks
curl -s http://localhost:8006/health | jq .
ssh aitbc1 'curl -s http://localhost:8006/health | jq .'

# Check sync status
./aitbc-cli chain
./aitbc-cli network
```

### Performance Metrics
```bash
# Check block production rate
watch -n 10 './aitbc-cli chain | grep "Height:"'

# Monitor transaction throughput
./aitbc-cli analytics

# Check resource utilization
./aitbc-cli resource status
```

## Troubleshooting

### Common Issues and Solutions

#### Transactions Not Mining
```bash
# Check proposer status
curl -s http://localhost:8006/health | jq .proposer_id

# Check mempool status
curl -s http://localhost:8006/rpc/mempool

# Verify mempool configuration
grep mempool_backend /etc/aitbc/.env
```

#### RPC Connection Issues
```bash
# Check RPC service
systemctl status aitbc-blockchain-rpc.service

# Test RPC endpoint
curl -s http://localhost:8006/health

# Check port availability
netstat -tlnp | grep 8006
```

#### Wallet Issues
```bash
# Check wallet exists
./aitbc-cli list | grep wallet-name

# Test wallet password
./aitbc-cli balance --name wallet-name --password 123

# Create new wallet if needed
./aitbc-cli create --name new-wallet --password 123
```

#### Sync Issues
```bash
# Check both nodes' heights
curl -s http://localhost:8006/rpc/head | jq .height
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'

# Check gossip connectivity
grep gossip_broadcast_url /etc/aitbc/.env

# Restart services if needed
sudo systemctl restart aitbc-blockchain-node.service
```

## Standardized Paths

| Resource | Path |
|---|---|
| Blockchain data | `/var/lib/aitbc/data/ait-mainnet/` |
| Keystore | `/var/lib/aitbc/keystore/` |
| Environment config | `/etc/aitbc/.env` |
| CLI tool | `/opt/aitbc/aitbc-cli` |
| Scripts | `/opt/aitbc/scripts/` |
| Logs | `/var/log/aitbc/` |
| Services | `/etc/systemd/system/aitbc-*.service` |

## Best Practices

### Security
- Use strong wallet passwords
- Keep keystore files secure
- Monitor transaction activity
- Use proper authentication for RPC endpoints

### Performance
- Monitor resource utilization
- Optimize transaction batching
- Use appropriate thinking levels for AI operations
- Regular database maintenance

### Operations
- Regular health checks
- Backup critical data
- Monitor cross-node synchronization
- Keep documentation updated

### Development
- Test on development network first
- Use proper version control
- Document all changes
- Implement proper error handling

This AITBC Blockchain Operations skill provides comprehensive coverage of all blockchain operations, from basic wallet management to advanced AI operations and cross-node coordination.
