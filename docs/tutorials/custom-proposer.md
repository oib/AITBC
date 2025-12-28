# Building Custom Proposers in AITBC

This tutorial guides you through creating custom proposers for the AITBC blockchain network. Custom proposers allow you to implement specialized block proposal logic tailored to your specific use case.

## Overview

In AITBC, proposers are responsible for creating new blocks in the Proof of Authority (PoA) consensus. While the default proposer works for most cases, you might need custom logic for:
- Priority-based transaction ordering
- Specialized transaction selection
- Custom block validation rules
- Integration with external systems

## Prerequisites

- Python 3.8+
- AITBC blockchain node running
- Understanding of PoA consensus
- Development environment set up

## Step 1: Create a Custom Proposer Class

Start by creating a new file for your custom proposer:

```python
# custom_proposer.py
from typing import List, Optional
from datetime import datetime
from aitbc_chain.models import Block, Transaction
from aitbc_chain.consensus.base import BaseProposer
from aitbc_chain.config import ProposerConfig

class PriorityProposer(BaseProposer):
    """
    A custom proposer that prioritizes transactions by fee and priority score.
    """
    
    def __init__(self, config: ProposerConfig):
        super().__init__(config)
        self.min_priority_score = config.get("min_priority_score", 0)
        self.max_block_size = config.get("max_block_size", 1000)
    
    async def select_transactions(
        self, 
        pending_txs: List[Transaction],
        current_block: Optional[Block] = None
    ) -> List[Transaction]:
        """
        Select and order transactions based on priority.
        """
        # Filter transactions by minimum priority
        filtered_txs = [
            tx for tx in pending_txs
            if self._calculate_priority(tx) >= self.min_priority_score
        ]
        
        # Sort by priority (highest first)
        sorted_txs = sorted(
            filtered_txs,
            key=self._calculate_priority,
            reverse=True
        )
        
        # Limit block size
        return sorted_txs[:self.max_block_size]
    
    def _calculate_priority(self, tx: Transaction) -> int:
        """
        Calculate transaction priority score.
        """
        # Base priority from fee
        fee_priority = tx.fee or 0
        
        # Bonus for specific transaction types
        type_bonus = {
            "computation": 10,
            "settlement": 5,
            "transfer": 1
        }.get(tx.type, 0)
        
        # Time-based priority (older transactions get higher priority)
        age_bonus = max(0, (datetime.utcnow() - tx.timestamp).seconds // 60)
        
        return fee_priority + type_bonus + age_bonus
```

## Step 2: Implement Custom Block Validation

Add custom validation logic for your blocks:

```python
# custom_proposer.py (continued)
from aitbc_chain.consensus.exceptions import InvalidBlockException

class PriorityProposer(BaseProposer):
    # ... previous code ...
    
    async def validate_block(
        self, 
        block: Block,
        parent_block: Optional[Block] = None
    ) -> bool:
        """
        Validate block with custom rules.
        """
        # Run standard validation first
        if not await super().validate_block(block, parent_block):
            return False
        
        # Custom validation: check minimum priority threshold
        if block.transactions:
            min_priority = min(
                self._calculate_priority(tx) 
                for tx in block.transactions
            )
            
            if min_priority < self.min_priority_score:
                raise InvalidBlockException(
                    f"Block contains transactions below priority threshold"
                )
        
        # Custom validation: ensure proposer diversity
        if parent_block and block.proposer == parent_block.proposer:
            # Allow consecutive blocks only if underutilized
            utilization = len(block.transactions) / self.max_block_size
            if utilization > 0.5:
                raise InvalidBlockException(
                    "Consecutive blocks from same proposer not allowed"
                )
        
        return True
```

## Step 3: Register Your Custom Proposer

Register your proposer with the blockchain node:

```python
# node_config.py
from custom_proposer import PriorityProposer
from aitbc_chain.config import ProposerConfig

def create_custom_proposer():
    """Create and configure the custom proposer."""
    config = ProposerConfig({
        "min_priority_score": 5,
        "max_block_size": 500,
        "proposer_address": "0xYOUR_PROPOSER_ADDRESS",
        "signing_key": "YOUR_PRIVATE_KEY"
    })
    
    return PriorityProposer(config)

# In your node initialization
proposer = create_custom_proposer()
node.set_proposer(proposer)
```

## Step 4: Add Monitoring and Metrics

Track your proposer's performance:

```python
# custom_proposer.py (continued)
from prometheus_client import Counter, Histogram, Gauge

class PriorityProposer(BaseProposer):
    # ... previous code ...
    
    def __init__(self, config: ProposerConfig):
        super().__init__(config)
        
        # Metrics
        self.blocks_proposed = Counter(
            'blocks_proposed_total',
            'Total number of blocks proposed',
            ['proposer_type']
        )
        self.tx_selected = Histogram(
            'transactions_selected_per_block',
            'Number of transactions selected per block'
        )
        self.avg_priority = Gauge(
            'average_transaction_priority',
            'Average priority of selected transactions'
        )
    
    async def propose_block(
        self, 
        pending_txs: List[Transaction]
    ) -> Optional[Block]:
        """
        Propose a new block with metrics tracking.
        """
        selected_txs = await self.select_transactions(pending_txs)
        
        if not selected_txs:
            return None
        
        # Create block
        block = await self._create_block(selected_txs)
        
        # Update metrics
        self.blocks_proposed.labels(proposer_type='priority').inc()
        self.tx_selected.observe(len(selected_txs))
        
        if selected_txs:
            avg_prio = sum(
                self._calculate_priority(tx) 
                for tx in selected_txs
            ) / len(selected_txs)
            self.avg_priority.set(avg_prio)
        
        return block
```

## Step 5: Test Your Custom Proposer

Create tests for your proposer:

```python
# test_custom_proposer.py
import pytest
from custom_proposer import PriorityProposer
from aitbc_chain.models import Transaction
from datetime import datetime, timedelta

@pytest.fixture
def proposer():
    config = ProposerConfig({
        "min_priority_score": 5,
        "max_block_size": 10
    })
    return PriorityProposer(config)

@pytest.fixture
def sample_transactions():
    txs = []
    for i in range(20):
        tx = Transaction(
            id=f"tx_{i}",
            fee=i * 2,
            type="computation" if i % 3 == 0 else "transfer",
            timestamp=datetime.utcnow() - timedelta(minutes=i)
        )
        txs.append(tx)
    return txs

async def test_transaction_selection(proposer, sample_transactions):
    """Test that high-priority transactions are selected."""
    selected = await proposer.select_transactions(sample_transactions)
    
    # Should select max_block_size transactions
    assert len(selected) == 10
    
    # Should be sorted by priority (highest first)
    priorities = [proposer._calculate_priority(tx) for tx in selected]
    assert priorities == sorted(priorities, reverse=True)
    
    # All should meet minimum priority
    assert all(p >= 5 for p in priorities)

async def test_priority_calculation(proposer):
    """Test priority calculation logic."""
    high_fee_tx = Transaction(id="1", fee=100, type="computation")
    low_fee_tx = Transaction(id="2", fee=1, type="transfer")
    
    high_priority = proposer._calculate_priority(high_fee_tx)
    low_priority = proposer._calculate_priority(low_fee_tx)
    
    assert high_priority > low_priority
```

## Advanced Features

### 1. Dynamic Priority Adjustment

```python
class AdaptiveProposer(PriorityProposer):
    """Proposer that adjusts priority based on network conditions."""
    
    async def adjust_priority_threshold(self):
        """Dynamically adjust minimum priority based on pending transactions."""
        pending_count = await self.get_pending_transaction_count()
        
        if pending_count > 1000:
            self.min_priority_score = 10  # Increase threshold
        elif pending_count < 100:
            self.min_priority_score = 1   # Lower threshold
```

### 2. MEV Protection

```python
class MEVProtectedProposer(PriorityProposer):
    """Proposer with MEV (Maximum Extractable Value) protection."""
    
    async def select_transactions(self, pending_txs):
        """Select transactions while preventing MEV extraction."""
        # Group related transactions
        tx_groups = self._group_related_transactions(pending_txs)
        
        # Process groups atomically
        selected = []
        for group in tx_groups:
            if self._validate_mev_safety(group):
                selected.extend(group)
        
        return selected[:self.max_block_size]
```

### 3. Cross-Shard Coordination

```python
class ShardAwareProposer(BaseProposer):
    """Proposer that coordinates across multiple shards."""
    
    async def coordinate_with_shards(self, block):
        """Coordinate block proposal with other shards."""
        # Get cross-shard dependencies
        dependencies = await self.get_cross_shard_deps(block.transactions)
        
        # Wait for confirmations from other shards
        await self.wait_for_shard_confirmations(dependencies)
        
        return block
```

## Deployment

1. **Package your proposer**:
```bash
pip install -e .
```

2. **Update node configuration**:
```yaml
# config.yaml
proposer:
  type: custom
  module: my_proposers.PriorityProposer
  config:
    min_priority_score: 5
    max_block_size: 500
```

3. **Restart the node**:
```bash
sudo systemctl restart aitbc-node
```

## Monitoring

Monitor your proposer's performance with Grafana dashboards:
- Block proposal rate
- Transaction selection efficiency
- Average priority scores
- MEV protection metrics

## Best Practices

1. **Keep proposers simple** - Complex logic can cause delays
2. **Test thoroughly** - Use testnet before mainnet deployment
3. **Monitor performance** - Track metrics and optimize
4. **Handle edge cases** - Empty blocks, network partitions
5. **Document behavior** - Clear documentation for custom logic

## Troubleshooting

### Common Issues

1. **Blocks not being proposed**
   - Check proposer registration
   - Verify signing key
   - Review logs for errors

2. **Low transaction throughput**
   - Adjust priority thresholds
   - Check block size limits
   - Optimize selection logic

3. **Invalid blocks**
   - Review validation rules
   - Check transaction ordering
   - Verify signatures

## Conclusion

Custom proposers give you fine-grained control over block production in AITBC. This tutorial covered the basics of creating, testing, and deploying custom proposers. You can now extend these examples to build sophisticated consensus mechanisms tailored to your specific needs.

For more advanced examples and community contributions, visit the AITBC GitHub repository.
