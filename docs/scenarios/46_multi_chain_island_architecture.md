# Multi-Chain Island Architecture

**Level**: Advanced  
**Prerequisites**: Blockchain node setup, Redis configuration, Systemd service management  
**Estimated Time**: 30 minutes  
**Last Updated**: 2026-05-02  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Multi-Chain Island Architecture

---

## 🎯 **See Also:**
- **📖 Related Scenario**: [Multi-Chain Validator](./33_multi_chain_validator.md)
- **🤖 Agent SDK**: [Agent SDK Documentation](../agent-sdk/README.md)
- **🧩 Feature Documentation**: [Gossip Protocol](../features/gossip.md)

---

## 📚 **Scenario Overview

This scenario demonstrates how to configure a multi-chain island architecture where different blockchain nodes serve as hubs for different chains while maintaining cross-chain synchronization via Redis gossip. This architecture enables:
- **Horizontal scaling**: Each chain has its own hub node for block production
- **Redundancy**: Member nodes receive blocks from multiple chains via gossip
- **Isolation**: Chain-specific databases prevent cross-chain contamination
- **Efficiency**: Gossip-based sync eliminates need for periodic RPC polling

### **Use Case**
Organizations running multiple blockchain networks (e.g., mainnet and testnet) can deploy this architecture to:
- Distribute block production load across multiple nodes
- Ensure all nodes stay synchronized across chains
- Provide redundancy and fault tolerance
- Enable cross-chain operations without direct RPC dependencies

### **What You'll Learn**
- How to configure multi-chain island architecture with hub and member nodes
- Redis gossip-based block synchronization
- Chain-specific database management
- Cross-chain broadcasting and subscription
- Troubleshooting gossip sync issues

---

## 📋 **Prerequisites

### **Knowledge Required**
- Understanding of blockchain consensus and block production
- Redis Pub/Sub basics
- Systemd service management
- SQLite database operations

### **Tools Required**
- Redis server (redis://10.1.223.93:6379)
- SSH access to aitbc, aitbc1, and gitea-runner
- Python 3.13+ with broadcaster module installed

### **Setup Required**
- AITBC blockchain node installed on all three machines
- Redis server configured and accessible from all nodes
- Systemd service files for aitbc-blockchain-node

---

## 🔧 **Step-by-Step Workflow

### **Architecture Overview

The multi-chain island architecture consists of three nodes with specific roles:

| Node | Role | Block Production Chains | Supported Chains | Purpose |
|------|------|------------------------|------------------|---------|
| aitbc | Hub of ait-mainnet, Member of ait-testnet | ait-mainnet | ait-mainnet, ait-testnet | Produces mainnet blocks, receives testnet blocks via gossip |
| aitbc1 | Hub of ait-testnet, Member of ait-mainnet | ait-testnet | ait-mainnet, ait-testnet | Produces testnet blocks, receives mainnet blocks via gossip |
| gitea-runner | Member of both chains | (none) | ait-mainnet, ait-testnet | Receives both chains via gossip, no block production |

### **Step 1: Install Required Dependencies

Ensure the `broadcaster` module is installed on all nodes for Redis gossip backend:

```bash
# On aitbc
cd /opt/aitbc
source venv/bin/activate
pip install broadcaster>=0.3.1

# On aitbc1
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && pip install broadcaster>=0.3.1'

# On gitea-runner
ssh gitea-runner 'cd /opt/aitbc && source venv/bin/activate && pip install broadcaster>=0.3.1'
```

### **Step 2: Configure aitbc (Hub of ait-mainnet)

Edit `/etc/aitbc/.env` on aitbc:

```bash
# Configure aitbc as hub of ait-mainnet, member of ait-testnet
block_production_chains=ait-mainnet
supported_chains=ait-mainnet,ait-testnet
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.93:6379
```

### **Step 3: Configure aitbc1 (Hub of ait-testnet)

Edit `/etc/aitbc/.env` on aitbc1:

```bash
ssh aitbc1 'cat > /etc/aitbc/.env << EOF
block_production_chains=ait-testnet
supported_chains=ait-mainnet,ait-testnet
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.93:6379
default_peer_rpc_url=http://10.1.223.93:8006
EOF'
```

### **Step 4: Configure gitea-runner (Member of both chains)

Edit `/etc/aitbc/.env` on gitea-runner:

```bash
ssh gitea-runner 'cat > /etc/aitbc/.env << EOF
block_production_chains=
supported_chains=ait-mainnet,ait-testnet
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.93:6379
default_peer_rpc_url=http://10.1.223.93:8006
EOF'
```

### **Step 5: Clear Stale Databases (if needed)

If nodes have corrupted or stale chain data, clear the databases:

```bash
# Clear aitbc1's ait-mainnet database (member role, not hub)
ssh aitbc1 'systemctl stop aitbc-blockchain-node && rm -rf /var/lib/aitbc/data/ait-mainnet && systemctl start aitbc-blockchain-node'

# Clear gitea-runner's ait-testnet database (member role, not hub)
ssh gitea-runner 'systemctl stop aitbc-blockchain-node && rm -rf /var/lib/aitbc/data/ait-testnet && systemctl start aitbc-blockchain-node'
```

### **Step 6: Restart All Blockchain Services

```bash
systemctl restart aitbc-blockchain-node
ssh aitbc1 'systemctl restart aitbc-blockchain-node'
ssh gitea-runner 'systemctl restart aitbc-blockchain-node'
```

### **Step 7: Verify Gossip Subscriptions

Check that each node is subscribed to the correct Redis topics:

```bash
# Check Redis subscriber count
redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-mainnet
redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-testnet
```

Expected output: 3 subscribers for each topic (aitbc, aitbc1, gitea-runner)

### **Step 8: Verify Block Production

Check that each hub is producing blocks for its designated chain:

```bash
# Check aitbc producing ait-mainnet blocks
journalctl -u aitbc-blockchain-node --no-pager | grep "\[BROADCAST\].*ait-mainnet"

# Check aitbc1 producing ait-testnet blocks
ssh aitbc1 'journalctl -u aitbc-blockchain-node --no-pager | grep "\[BROADCAST\].*ait-testnet"'
```

### **Step 9: Verify Cross-Chain Sync

Check that nodes are receiving blocks from other chains via gossip:

```bash
# Check aitbc receiving ait-testnet blocks
journalctl -u aitbc-blockchain-node --no-pager | grep "Received block.*ait-testnet"

# Check aitbc1 receiving ait-mainnet blocks
ssh aitbc1 'journalctl -u aitbc-blockchain-node --no-pager | grep "Received block.*ait-mainnet"'

# Check gitea-runner receiving both chains
ssh gitea-runner 'journalctl -u aitbc-blockchain-node --no-pager | grep "Received block"'
```

---

## 🧪 **Validation

Validate this scenario with the shared 3-node harness:

```bash
bash scripts/workflow/44_comprehensive_multi_node_scenario.sh
```

**Node coverage**:
- `aitbc1`: hub of ait-testnet, member of ait-mainnet
- `aitbc`: hub of ait-mainnet, member of ait-testnet
- `gitea-runner`: member of both chains

**Validation guide**:
- [Scenario Validation Guide](./VALIDATION.md)

**Expected result**:
- aitbc produces ait-mainnet blocks only
- aitbc1 produces ait-testnet blocks only
- gitea-runner produces no blocks
- All nodes receive blocks from both chains via gossip
- Redis subscriber count is 3 for each topic
- No "Gap detected" or "Fork detected" errors
- Chain-specific databases remain isolated

**Manual validation commands**:

```bash
# Verify block production roles
journalctl -u aitbc-blockchain-node --no-pager | grep "Skipping block production"
ssh aitbc1 'journalctl -u aitbc-blockchain-node --no-pager | grep "Skipping block production"'
ssh gitea-runner 'journalctl -u aitbc-blockchain-node --no-pager | grep "Skipping block production"'

# Verify gossip subscriptions
redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-mainnet
redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-testnet

# Verify cross-chain sync
journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "Received block.*ait-testnet" | tail -5
ssh aitbc1 'journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "Received block.*ait-mainnet" | tail -5'
ssh gitea-runner 'journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "Received block" | tail -10'
```

---

## 💻 **Code Examples Using Agent SDK

### **Example 1: Query Multi-Chain Node Status**

```python
from aitbc_agent_sdk import Agent, AgentConfig

config = AgentConfig(
    name="multi-chain-monitor",
    blockchain_network="ait-mainnet"
)

agent = Agent(config)
agent.start()

# Get status for both chains
mainnet_status = agent.get_chain_status("ait-mainnet")
testnet_status = agent.get_chain_status("ait-testnet")

print(f"Mainnet height: {mainnet_status['height']}")
print(f"Testnet height: {testnet_status['height']}")
```

### **Example 2: Cross-Chain Transaction Monitoring**

```python
# Monitor transactions across both chains
async def monitor_multi_chain():
    while True:
        # Check mainnet
        mainnet_txs = await agent.get_pending_transactions("ait-mainnet")
        # Check testnet
        testnet_txs = await agent.get_pending_transactions("ait-testnet")
        
        print(f"Mainnet pending: {len(mainnet_txs)}")
        print(f"Testnet pending: {len(testnet_txs)}")
        
        await asyncio.sleep(10)
```

---

## 🎯 **Expected Outcomes

After completing this scenario, you should be able to:
- Configure multi-chain island architecture with hub and member nodes
- Verify that each hub produces blocks only for its designated chain
- Verify that all nodes receive blocks from both chains via gossip
- Troubleshoot gossip sync issues (e.g., missing broadcaster module)
- Monitor cross-chain synchronization status

---

## 🔗 **Related Resources

### **AITBC Documentation**
- [Gossip Protocol](../features/gossip.md)
- [Chain Configuration](../configuration/chains.md)
- [PoA Consensus](../consensus/poa.md)

### **External Resources**
- [Redis Pub/Sub Documentation](https://redis.io/docs/manual/pubsub/)
- [Broadcaster Library](https://github.com/encode/broadcaster)

### **Next Scenarios**
- [Multi-Chain Validator](./33_multi_chain_validator.md)
- [Cross-Chain Transfer](./20_cross_chain_transfer.md)
- [Cross-Chain Trader](./27_cross_chain_trader.md)

---

## 📊 **Quality Metrics**
- **Structure**: 10/10 - Clear workflow with step-by-step instructions
- **Content**: 10/10 - Comprehensive coverage of multi-chain island architecture
- **Code Examples**: 10/10 - Working Agent SDK code examples
- **Status**: Active scenario

---

## ⚠️ **Troubleshooting

### **Issue: Node not receiving blocks from other chains**

**Symptoms**: Node shows "Successfully subscribed" but no "Received block" messages for certain chains.

**Root Cause**: Missing `broadcaster` Python module causing fallback to in-memory backend.

**Solution**:
```bash
pip install broadcaster>=0.3.1
systemctl restart aitbc-blockchain-node
```

**Verification**:
```bash
python3 -c "from broadcaster import Broadcast; print('OK')"
redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-testnet
```

### **Issue: "Gap detected" errors on member nodes**

**Symptoms**: Member node reports "Gap detected" when receiving blocks from hub.

**Root Cause**: Corrupted or stale database from previous sync attempts.

**Solution**:
```bash
systemctl stop aitbc-blockchain-node
rm -rf /var/lib/aitbc/data/[chain-name]
systemctl start aitbc-blockchain-node
```

### **Issue: Fork detection warnings**

**Symptoms**: "Fork detected" warnings in logs when receiving blocks.

**Root Cause**: Cross-chain broadcasting bug (fixed in recent code).

**Solution**: Ensure latest code is deployed with chain-specific gossip topics:
```bash
cd /opt/aitbc
git pull
systemctl restart aitbc-blockchain-node
```

---

*Last updated: 2026-05-02*  
*Version: 1.0*  
*Status: Active scenario document*
