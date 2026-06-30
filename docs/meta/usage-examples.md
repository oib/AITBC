# AITBC - Usage Examples

**Last Updated**: 2026-06-30
**Version**: 1.0

## CLI Usage

```bash
# Check system status
aitbc status

# Create wallet
aitbc wallet create

# Start mining
aitbc miner start

# Check balance
aitbc wallet balance

# Trade on marketplace
aitbc marketplace trade --pair AITBC/USDT --amount 100
```

## AI Agent Development

```python
from aitbc.agent import AITBCAgent

# Create custom agent
agent = AITBCAgent(
    name="MyTradingBot",
    strategy="ml_trading",
    config="agent_config.yaml"
)

# Start agent
agent.start()
```

## Blockchain Integration

```python
from aitbc.blockchain import AITBCBlockchain

# Connect to blockchain
blockchain = AITBCBlockchain()

# Create transaction
tx = blockchain.create_transaction(
    to="0x...",
    amount=100,
    asset="AITBC"
)

# Send transaction
result = blockchain.send_transaction(tx)
```

## Related Topics

- [Project Overview](./project-overview.md) - General project information
- [Installation Guide](./installation-guide.md) - Setup instructions
- [agent Agent Usage](./agent-usage.md) - Advanced AI agent operations
