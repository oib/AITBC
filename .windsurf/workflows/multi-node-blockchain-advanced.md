---
description: Advanced blockchain features including smart contracts, security testing, and performance optimization
title: Multi-Node Blockchain Setup - Advanced Features Module
version: 1.0
---

# Multi-Node Blockchain Setup - Advanced Features Module

This module covers advanced blockchain features including smart contract testing, security testing, performance optimization, and complex operations.

## Prerequisites

- Complete [Core Setup Module](multi-node-blockchain-setup-core.md)
- Complete [Operations Module](multi-node-blockchain-operations.md)
- Stable blockchain network with active nodes
- Basic understanding of blockchain concepts

## Smart Contract Operations

### Smart Contract Deployment

```bash
cd /opt/aitbc && source venv/bin/activate

# Deploy Agent Messaging Contract
./aitbc-cli contract deploy --name "AgentMessagingContract" \
    --code "/opt/aitbc/apps/blockchain-node/src/aitbc_chain/contracts/agent_messaging_contract.py" \
    --wallet genesis-ops --password 123

# Verify deployment
./aitbc-cli contract list
./aitbc-cli contract status --name "AgentMessagingContract"
```

### Smart Contract Interaction

```bash
# Create governance topic via smart contract
curl -X POST http://localhost:8006/rpc/messaging/topics/create \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "governance-agent",
    "agent_address": "ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871",
    "title": "Network Governance",
    "description": "Decentralized governance for network upgrades",
    "tags": ["governance", "voting", "upgrades"]
  }'

# Post proposal message
curl -X POST http://localhost:8006/rpc/messaging/messages/post \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "governance-agent",
    "agent_address": "ait158ec7a0713f30ccfb1aac6bfbab71f36271c5871",
    "topic_id": "topic_id",
    "content": "Proposal: Reduce block time from 10s to 5s for higher throughput",
    "message_type": "proposal"
  }'

# Vote on proposal
curl -X POST http://localhost:8006/rpc/messaging/messages/message_id/vote \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "voter-agent",
    "agent_address": "ait141b3bae6eea3a74273ef3961861ee58e12b6d855",
    "vote_type": "upvote",
    "reason": "Supports network performance improvement"
  }'
```

### Contract Testing

```bash
# Test contract functionality
./aitbc-cli contract test --name "AgentMessagingContract" \
    --test-case "create_topic" \
    --parameters "title:Test Topic,description:Test Description"

# Test contract performance
./aitbc-cli contract benchmark --name "AgentMessagingContract" \
    --operations 1000 --concurrent 10

# Verify contract state
./aitbc-cli contract state --name "AgentMessagingContract"
```

## Security Testing

### Penetration Testing

```bash
# Test RPC endpoint security
curl -X POST http://localhost:8006/rpc/transaction \
  -H "Content-Type: application/json" \
  -d '{"from": "invalid_address", "to": "invalid_address", "amount": -100}'

# Test authentication bypass attempts
curl -X POST http://localhost:8006/rpc/admin/reset \
  -H "Content-Type: application/json" \
  -d '{"force": true}'

# Test rate limiting
for i in {1..100}; do
    curl -s http://localhost:8006/rpc/head > /dev/null &
done
wait
```

### Vulnerability Assessment

```bash
# Check for common vulnerabilities
nmap -sV -p 8006,7070 localhost

# Test wallet encryption
./aitbc-cli wallet test --name genesis-ops --encryption-check

# Test transaction validation
./aitbc-cli transaction test --invalid-signature
./aitbc-cli transaction test --double-spend
./aitbc-cli transaction test --invalid-nonce
```

### Security Hardening

```bash
# Enable TLS for RPC (if supported)
# Edit /etc/aitbc/.env
echo "RPC_TLS_ENABLED=true" | sudo tee -a /etc/aitbc/.env
echo "RPC_TLS_CERT=/etc/aitbc/certs/server.crt" | sudo tee -a /etc/aitbc/.env
echo "RPC_TLS_KEY=/etc/aitbc/certs/server.key" | sudo tee -a /etc/aitbc/.env

# Configure firewall rules
sudo ufw allow 8006/tcp
sudo ufw allow 7070/tcp
sudo ufw deny 8006/tcp from 10.0.0.0/8  # Restrict to local network

# Enable audit logging
echo "AUDIT_LOG_ENABLED=true" | sudo tee -a /etc/aitbc/.env
echo "AUDIT_LOG_PATH=/var/log/aitbc/audit.log" | sudo tee -a /etc/aitbc/.env
```

## Performance Optimization

### Database Optimization

```bash
# Analyze database performance
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "EXPLAIN QUERY PLAN SELECT * FROM blocks WHERE height > 1000;"

# Optimize database indexes
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(height);"
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp);"

# Compact database
sudo systemctl stop aitbc-blockchain-node.service aitbc-blockchain-rpc.service
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "VACUUM;"
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "ANALYZE;"
sudo systemctl start aitbc-blockchain-node.service aitbc-blockchain-rpc.service
```

### Network Optimization

```bash
# Tune network parameters
echo "net.core.rmem_max = 134217728" | sudo tee -a /etc/sysctl.conf
echo "net.core.wmem_max = 134217728" | sudo tee -a /etc/sysctl.conf
echo "net.ipv4.tcp_rmem = 4096 87380 134217728" | sudo tee -a /etc/sysctl.conf
echo "net.ipv4.tcp_wmem = 4096 65536 134217728" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Optimize Redis for gossip
echo "maxmemory 256mb" | sudo tee -a /etc/redis/redis.conf
echo "maxmemory-policy allkeys-lru" | sudo tee -a /etc/redis/redis.conf
sudo systemctl restart redis
```

### Consensus Optimization

```bash
# Tune block production parameters
echo "BLOCK_TIME_SECONDS=5" | sudo tee -a /etc/aitbc/.env
echo "MAX_TXS_PER_BLOCK=1000" | sudo tee -a /etc/aitbc/.env
echo "MAX_BLOCK_SIZE_BYTES=2097152" | sudo tee -a /etc/aitbc/.env

# Optimize mempool
echo "MEMPOOL_MAX_SIZE=10000" | sudo tee -a /etc/aitbc/.env
echo "MEMPOOL_MIN_FEE=1" | sudo tee -a /etc/aitbc/.env

# Restart services with new parameters
sudo systemctl restart aitbc-blockchain-node.service aitbc-blockchain-rpc.service
```

## Advanced Monitoring

### Performance Metrics Collection

```bash
# Create performance monitoring script
cat > /opt/aitbc/scripts/performance_monitor.sh << 'EOF'
#!/bin/bash

METRICS_FILE="/var/log/aitbc/performance_$(date +%Y%m%d).log"

while true; do
    TIMESTAMP=$(date +%Y-%m-%d_%H:%M:%S)
    
    # Blockchain metrics
    HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
    TX_COUNT=$(curl -s http://localhost:8006/rpc/head | jq .tx_count)
    
    # System metrics
    CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    MEM_USAGE=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    
    # Network metrics
    NET_LATENCY=$(ping -c 1 aitbc1 | tail -1 | awk '{print $4}' | sed 's/ms=//')
    
    # Log metrics
    echo "$TIMESTAMP,height:$HEIGHT,tx_count:$TX_COUNT,cpu:$CPU_USAGE,memory:$MEM_USAGE,latency:$NET_LATENCY" >> $METRICS_FILE
    
    sleep 60
done
EOF

chmod +x /opt/aitbc/scripts/performance_monitor.sh
nohup /opt/aitbc/scripts/performance_monitor.sh > /dev/null 2>&1 &
```

### Real-time Analytics

```bash
# Analyze performance trends
tail -1000 /var/log/aitbc/performance_$(date +%Y%m%d).log | \
  awk -F',' '{print $2}' | sed 's/height://' | sort -n | \
  awk 'BEGIN{prev=0} {if($1>prev+1) print "Height gap detected at " $1; prev=$1}'

# Monitor transaction throughput
tail -1000 /var/log/aitbc/performance_$(date +%Y%m%d).log | \
  awk -F',' '{tx_count[$1] += $3} END {for (time in tx_count) print time, tx_count[time]}'

# Detect performance anomalies
tail -1000 /var/log/aitbc/performance_$(date +%Y%m%d).log | \
  awk -F',' '{cpu=$4; mem=$5; if(cpu>80 || mem>90) print "High resource usage at " $1}'
```

## Event Monitoring

### Blockchain Events

```bash
# Monitor block creation events
tail -f /var/log/aitbc/blockchain-node.log | grep "Block proposed"

# Monitor transaction events
tail -f /var/log/aitbc/blockchain-node.log | grep "Transaction"

# Monitor consensus events
tail -f /var/log/aitbc/blockchain-node.log | grep "Consensus"
```

### Smart Contract Events

```bash
# Monitor contract deployment
tail -f /var/log/aitbc/blockchain-node.log | grep "Contract deployed"

# Monitor contract calls
tail -f /var/log/aitbc/blockchain-node.log | grep "Contract call"

# Monitor messaging events
tail -f /var/log/aitbc/blockchain-node.log | grep "Messaging"
```

### System Events

```bash
# Monitor service events
journalctl -u aitbc-blockchain-node.service -f

# Monitor RPC events
journalctl -u aitbc-blockchain-rpc.service -f

# Monitor system events
dmesg -w | grep -E "(error|warning|fail)"
```

## Data Analytics

### Blockchain Analytics

```bash
# Generate blockchain statistics
./aitbc-cli analytics --period "24h" --output json > /tmp/blockchain_stats.json

# Analyze transaction patterns
./aitbc-cli analytics --transactions --group-by hour --output csv > /tmp/tx_patterns.csv

# Analyze wallet activity
./aitbc-cli analytics --wallets --top 10 --output json > /tmp/wallet_activity.json
```

### Performance Analytics

```bash
# Analyze block production rate
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as blocks_produced,
    AVG(JULIANDAY(timestamp) - JULIANDAY(LAG(timestamp) OVER (ORDER BY timestamp))) * 86400 as avg_block_time
FROM blocks 
WHERE timestamp > datetime('now', '-7 days')
GROUP BY DATE(timestamp)
ORDER BY date;
"

# Analyze transaction volume
sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db "
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as tx_count,
    SUM(amount) as total_volume
FROM transactions 
WHERE timestamp > datetime('now', '-7 days')
GROUP BY DATE(timestamp)
ORDER BY date;
"
```

## Consensus Testing

### Consensus Failure Scenarios

```bash
# Test proposer failure
sudo systemctl stop aitbc-blockchain-node.service
sleep 30
sudo systemctl start aitbc-blockchain-node.service

# Test network partition
sudo iptables -A INPUT -s 10.1.223.40 -j DROP
sudo iptables -A OUTPUT -d 10.1.223.40 -j DROP
sleep 60
sudo iptables -D INPUT -s 10.1.223.40 -j DROP
sudo iptables -D OUTPUT -d 10.1.223.40 -j DROP

# Test double-spending prevention
./aitbc-cli send --from genesis-ops --to user-wallet --amount 100 --password 123 &
./aitbc-cli send --from genesis-ops --to user-wallet --amount 100 --password 123
wait
```

### Consensus Performance Testing

```bash
# Test high transaction volume
for i in {1..1000}; do
    ./aitbc-cli send --from genesis-ops --to user-wallet --amount 1 --password 123 &
done
wait

# Test block production under load
time ./aitbc-cli send --from genesis-ops --to user-wallet --amount 1000 --password 123

# Test consensus recovery
sudo systemctl stop aitbc-blockchain-node.service
sleep 60
sudo systemctl start aitbc-blockchain-node.service
```

## Advanced Troubleshooting

### Complex Failure Scenarios

```bash
# Diagnose split-brain scenarios
GENESIS_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FOLLOWER_HEIGHT=$(ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height')

if [ $GENESIS_HEIGHT -ne $FOLLOWER_HEIGHT ]; then
    echo "Potential split-brain detected"
    echo "Genesis height: $GENESIS_HEIGHT"
    echo "Follower height: $FOLLOWER_HEIGHT"
    
    # Check which chain is longer
    if [ $GENESIS_HEIGHT -gt $FOLLOWER_HEIGHT ]; then
        echo "Genesis chain is longer - follower needs to sync"
    else
        echo "Follower chain is longer - potential consensus issue"
    fi
fi
```

### Performance Bottleneck Analysis

```bash
# Profile blockchain node performance
sudo perf top -p $(pgrep aitbc-blockchain)

# Analyze memory usage
sudo pmap -d $(pgrep aitbc-blockchain)

# Check I/O bottlenecks
sudo iotop -p $(pgrep aitbc-blockchain)

# Analyze network performance
sudo tcpdump -i eth0 -w /tmp/network_capture.pcap port 8006 or port 7070
```

## Dependencies

This advanced features module depends on:
- **[Core Setup Module](multi-node-blockchain-setup-core.md)** - Basic node setup
- **[Operations Module](multi-node-blockchain-operations.md)** - Daily operations knowledge

## Next Steps

After mastering advanced features, proceed to:
- **[Production Module](multi-node-blockchain-production.md)** - Production deployment and scaling
- **[Marketplace Module](multi-node-blockchain-marketplace.md)** - Marketplace testing and verification

## Safety Notes

⚠️ **Warning**: Advanced features can impact network stability. Test in development environment first.

- Always backup data before performance optimization
- Monitor system resources during security testing
- Use test wallets for consensus failure scenarios
- Document all configuration changes
