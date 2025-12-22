"""
Beacon Chain for Sharding Architecture
Coordinates shard chains and manages cross-shard transactions
"""

import asyncio
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from enum import Enum
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ShardStatus(Enum):
    """Shard chain status"""
    ACTIVE = "active"
    SYNCING = "syncing"
    OFFLINE = "offline"


@dataclass
class ShardInfo:
    """Information about a shard"""
    shard_id: int
    status: ShardStatus
    validator_count: int
    last_checkpoint: int
    gas_price: int
    transaction_count: int
    cross_shard_txs: int


@dataclass
class CrossShardTransaction:
    """Cross-shard transaction"""
    tx_hash: str
    from_shard: int
    to_shard: int
    sender: str
    receiver: str
    amount: int
    data: str
    nonce: int
    timestamp: datetime
    status: str = "pending"


@dataclass
class Checkpoint:
    """Beacon chain checkpoint"""
    epoch: int
    shard_roots: Dict[int, str]
    cross_shard_roots: List[str]
    validator_set: List[str]
    timestamp: datetime


class BeaconChain:
    """Beacon chain for coordinating shards"""
    
    def __init__(self, num_shards: int = 64):
        self.num_shards = num_shards
        self.shards: Dict[int, ShardInfo] = {}
        self.current_epoch = 0
        self.checkpoints: List[Checkpoint] = []
        self.cross_shard_pool: List[CrossShardTransaction] = []
        self.validators: Set[str] = set()
        self.randao = None
        
        # Initialize shards
        self._initialize_shards()
        
    def _initialize_shards(self):
        """Initialize all shards"""
        for i in range(self.num_shards):
            self.shards[i] = ShardInfo(
                shard_id=i,
                status=ShardStatus.ACTIVE,
                validator_count=100,
                last_checkpoint=0,
                gas_price=20 * 10**9,  # 20 gwei
                transaction_count=0,
                cross_shard_txs=0
            )
    
    def add_validator(self, validator_address: str):
        """Add a validator to the beacon chain"""
        self.validators.add(validator_address)
        logger.info(f"Added validator: {validator_address}")
    
    def remove_validator(self, validator_address: str):
        """Remove a validator from the beacon chain"""
        self.validators.discard(validator_address)
        logger.info(f"Removed validator: {validator_address}")
    
    def get_shard_for_address(self, address: str) -> int:
        """Determine which shard an address belongs to"""
        hash_bytes = hashlib.sha256(address.encode()).digest()
        shard_id = int.from_bytes(hash_bytes[:4], byteorder='big') % self.num_shards
        return shard_id
    
    def submit_cross_shard_transaction(
        self,
        from_shard: int,
        to_shard: int,
        sender: str,
        receiver: str,
        amount: int,
        data: str = ""
    ) -> str:
        """Submit a cross-shard transaction"""
        
        # Generate transaction hash
        tx_data = {
            "from_shard": from_shard,
            "to_shard": to_shard,
            "sender": sender,
            "receiver": receiver,
            "amount": amount,
            "data": data,
            "nonce": len(self.cross_shard_pool),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        tx_hash = hashlib.sha256(json.dumps(tx_data, sort_keys=True).encode()).hexdigest()
        
        # Create cross-shard transaction
        cross_tx = CrossShardTransaction(
            tx_hash=tx_hash,
            from_shard=from_shard,
            to_shard=to_shard,
            sender=sender,
            receiver=receiver,
            amount=amount,
            data=data,
            nonce=len(self.cross_shard_pool),
            timestamp=datetime.utcnow()
        )
        
        # Add to pool
        self.cross_shard_pool.append(cross_tx)
        
        # Update shard metrics
        if from_shard in self.shards:
            self.shards[from_shard].cross_shard_txs += 1
        if to_shard in self.shards:
            self.shards[to_shard].cross_shard_txs += 1
        
        logger.info(f"Submitted cross-shard tx {tx_hash[:8]} from shard {from_shard} to {to_shard}")
        
        return tx_hash
    
    async def process_cross_shard_transactions(self) -> List[str]:
        """Process pending cross-shard transactions"""
        processed = []
        
        # Group transactions by destination shard
        shard_groups = {}
        for tx in self.cross_shard_pool:
            if tx.status == "pending":
                if tx.to_shard not in shard_groups:
                    shard_groups[tx.to_shard] = []
                shard_groups[tx.to_shard].append(tx)
        
        # Process each group
        for shard_id, transactions in shard_groups.items():
            if len(transactions) > 0:
                # Create batch for shard
                batch_hash = self._create_batch_hash(transactions)
                
                # Submit to shard (simulated)
                success = await self._submit_to_shard(shard_id, batch_hash, transactions)
                
                if success:
                    for tx in transactions:
                        tx.status = "processed"
                        processed.append(tx.tx_hash)
        
        logger.info(f"Processed {len(processed)} cross-shard transactions")
        
        return processed
    
    def _create_batch_hash(self, transactions: List[CrossShardTransaction]) -> str:
        """Create hash for transaction batch"""
        tx_hashes = [tx.tx_hash for tx in transactions]
        combined = "".join(sorted(tx_hashes))
        return hashlib.sha256(combined.encode()).hexdigest()
    
    async def _submit_to_shard(
        self,
        shard_id: int,
        batch_hash: str,
        transactions: List[CrossShardTransaction]
    ) -> bool:
        """Submit batch to shard (simulated)"""
        # Simulate network delay
        await asyncio.sleep(0.01)
        
        # Simulate success rate
        return random.random() > 0.05  # 95% success rate
    
    def create_checkpoint(self) -> Checkpoint:
        """Create a new checkpoint"""
        self.current_epoch += 1
        
        # Collect shard roots (simulated)
        shard_roots = {}
        for shard_id in range(self.num_shards):
            shard_roots[shard_id] = f"root_{shard_id}_{self.current_epoch}"
        
        # Collect cross-shard transaction roots
        cross_shard_txs = [tx for tx in self.cross_shard_pool if tx.status == "processed"]
        cross_shard_roots = [tx.tx_hash for tx in cross_shard_txs[-100:]]  # Last 100
        
        # Create checkpoint
        checkpoint = Checkpoint(
            epoch=self.current_epoch,
            shard_roots=shard_roots,
            cross_shard_roots=cross_shard_roots,
            validator_set=list(self.validators),
            timestamp=datetime.utcnow()
        )
        
        self.checkpoints.append(checkpoint)
        
        # Update shard checkpoint info
        for shard_id in range(self.num_shards):
            if shard_id in self.shards:
                self.shards[shard_id].last_checkpoint = self.current_epoch
        
        logger.info(f"Created checkpoint {self.current_epoch} with {len(cross_shard_roots)} cross-shard txs")
        
        return checkpoint
    
    def get_shard_info(self, shard_id: int) -> Optional[ShardInfo]:
        """Get information about a specific shard"""
        return self.shards.get(shard_id)
    
    def get_all_shards(self) -> Dict[int, ShardInfo]:
        """Get information about all shards"""
        return self.shards.copy()
    
    def get_cross_shard_pool_size(self) -> int:
        """Get number of pending cross-shard transactions"""
        return len([tx for tx in self.cross_shard_pool if tx.status == "pending"])
    
    def get_network_stats(self) -> Dict:
        """Get network-wide statistics"""
        total_txs = sum(shard.transaction_count for shard in self.shards.values())
        total_cross_txs = sum(shard.cross_shard_txs for shard in self.shards.values())
        avg_gas_price = sum(shard.gas_price for shard in self.shards.values()) / len(self.shards)
        
        return {
            "epoch": self.current_epoch,
            "total_shards": self.num_shards,
            "active_shards": sum(1 for s in self.shards.values() if s.status == ShardStatus.ACTIVE),
            "total_transactions": total_txs,
            "cross_shard_transactions": total_cross_txs,
            "pending_cross_shard": self.get_cross_shard_pool_size(),
            "average_gas_price": avg_gas_price,
            "validator_count": len(self.validators),
            "checkpoints": len(self.checkpoints)
        }
    
    async def run_epoch(self):
        """Run a single epoch"""
        logger.info(f"Starting epoch {self.current_epoch + 1}")
        
        # Process cross-shard transactions
        await self.process_cross_shard_transactions()
        
        # Create checkpoint
        self.create_checkpoint()
        
        # Randomly update shard metrics
        for shard in self.shards.values():
            shard.transaction_count += random.randint(100, 1000)
            shard.gas_price = max(10 * 10**9, shard.gas_price + random.randint(-5, 5) * 10**9)
    
    def simulate_load(self, duration_seconds: int = 60):
        """Simulate network load"""
        logger.info(f"Simulating load for {duration_seconds} seconds")
        
        start_time = time.time()
        tx_count = 0
        
        while time.time() - start_time < duration_seconds:
            # Generate random cross-shard transactions
            for _ in range(random.randint(5, 20)):
                from_shard = random.randint(0, self.num_shards - 1)
                to_shard = random.randint(0, self.num_shards - 1)
                
                if from_shard != to_shard:
                    self.submit_cross_shard_transaction(
                        from_shard=from_shard,
                        to_shard=to_shard,
                        sender=f"user_{random.randint(0, 9999)}",
                        receiver=f"user_{random.randint(0, 9999)}",
                        amount=random.randint(1, 1000) * 10**18,
                        data=f"transfer_{tx_count}"
                    )
                    tx_count += 1
            
            # Small delay
            time.sleep(0.1)
        
        logger.info(f"Generated {tx_count} cross-shard transactions")
        
        return tx_count


async def main():
    """Main function to run beacon chain simulation"""
    logger.info("Starting Beacon Chain Sharding Simulation")
    
    # Create beacon chain
    beacon = BeaconChain(num_shards=64)
    
    # Add validators
    for i in range(100):
        beacon.add_validator(f"validator_{i:03d}")
    
    # Simulate initial load
    beacon.simulate_load(duration_seconds=5)
    
    # Run epochs
    for epoch in range(5):
        await beacon.run_epoch()
        
        # Print stats
        stats = beacon.get_network_stats()
        logger.info(f"Epoch {epoch} Stats:")
        logger.info(f"  Total Transactions: {stats['total_transactions']}")
        logger.info(f"  Cross-Shard TXs: {stats['cross_shard_transactions']}")
        logger.info(f"  Pending Cross-Shard: {stats['pending_cross_shard']}")
        logger.info(f"  Active Shards: {stats['active_shards']}/{stats['total_shards']}")
        
        # Simulate more load
        beacon.simulate_load(duration_seconds=2)
    
    # Print final stats
    final_stats = beacon.get_network_stats()
    logger.info("\n=== Final Network Statistics ===")
    for key, value in final_stats.items():
        logger.info(f"{key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
