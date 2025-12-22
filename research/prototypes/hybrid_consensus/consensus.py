"""
Hybrid Proof of Authority / Proof of Stake Consensus Implementation
Prototype for demonstrating the hybrid consensus mechanism
"""

import asyncio
import time
import hashlib
import json
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
import logging
from collections import defaultdict
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConsensusMode(Enum):
    """Consensus operation modes"""
    FAST = "fast"      # PoA dominant, 100ms finality
    BALANCED = "balanced"  # Equal PoA/PoS, 1s finality
    SECURE = "secure"  # PoS dominant, 5s finality


@dataclass
class Validator:
    """Validator information"""
    address: str
    is_authority: bool
    stake: float
    last_seen: datetime
    reputation: float
    voting_power: float
    
    def __hash__(self):
        return hash(self.address)


@dataclass
class Block:
    """Block structure"""
    number: int
    hash: str
    parent_hash: str
    proposer: str
    timestamp: datetime
    mode: ConsensusMode
    transactions: List[dict]
    authority_signatures: List[str]
    stake_signatures: List[str]
    merkle_root: str


@dataclass
class NetworkMetrics:
    """Network performance metrics"""
    tps: float
    latency: float
    active_validators: int
    stake_participation: float
    authority_availability: float
    network_load: float


class VRF:
    """Simplified Verifiable Random Function"""
    
    @staticmethod
    def evaluate(seed: str) -> float:
        """Generate pseudo-random value from seed"""
        hash_obj = hashlib.sha256(seed.encode())
        return int(hash_obj.hexdigest(), 16) / (2**256)
    
    @staticmethod
    def prove(seed: str, private_key: str) -> Tuple[str, float]:
        """Generate VRF proof and value"""
        # Simplified VRF implementation
        combined = f"{seed}{private_key}"
        proof = hashlib.sha256(combined.encode()).hexdigest()
        value = VRF.evaluate(combined)
        return proof, value


class HybridConsensus:
    """Hybrid PoA/PoS consensus implementation"""
    
    def __init__(self, config: dict):
        self.config = config
        self.mode = ConsensusMode.BALANCED
        self.authorities: Set[Validator] = set()
        self.stakers: Set[Validator] = set()
        self.current_block = 0
        self.chain: List[Block] = []
        self.vrf = VRF()
        self.metrics = NetworkMetrics(0, 0, 0, 0, 0, 0)
        self.last_block_time = datetime.utcnow()
        self.block_times = []
        
        # Initialize authorities
        self._initialize_validators()
        
    def _initialize_validators(self):
        """Initialize test validators"""
        # Create 21 authorities
        for i in range(21):
            auth = Validator(
                address=f"authority_{i:02d}",
                is_authority=True,
                stake=10000.0,
                last_seen=datetime.utcnow(),
                reputation=1.0,
                voting_power=1.0
            )
            self.authorities.add(auth)
        
        # Create 100 stakers
        for i in range(100):
            stake = random.uniform(1000, 50000)
            staker = Validator(
                address=f"staker_{i:03d}",
                is_authority=False,
                stake=stake,
                last_seen=datetime.utcnow(),
                reputation=1.0,
                voting_power=stake / 1000.0
            )
            self.stakers.add(staker)
    
    def determine_mode(self) -> ConsensusMode:
        """Determine optimal consensus mode based on network conditions"""
        load = self.metrics.network_load
        auth_availability = self.metrics.authority_availability
        stake_participation = self.metrics.stake_participation
        
        if load < 0.3 and auth_availability > 0.9:
            return ConsensusMode.FAST
        elif load > 0.7 or stake_participation > 0.8:
            return ConsensusMode.SECURE
        else:
            return ConsensusMode.BALANCED
    
    def select_proposer(self, slot: int, mode: ConsensusMode) -> Validator:
        """Select block proposer using VRF-based selection"""
        seed = f"propose-{slot}-{self.current_block}"
        
        if mode == ConsensusMode.FAST:
            return self._select_authority(seed)
        elif mode == ConsensusMode.BALANCED:
            return self._select_hybrid(seed)
        else:  # SECURE
            return self._select_staker_weighted(seed)
    
    def _select_authority(self, seed: str) -> Validator:
        """Select authority proposer"""
        authorities = list(self.authorities)
        seed_value = self.vrf.evaluate(seed)
        index = int(seed_value * len(authorities))
        return authorities[index]
    
    def _select_hybrid(self, seed: str) -> Validator:
        """Hybrid selection (70% authority, 30% staker)"""
        seed_value = self.vrf.evaluate(seed)
        
        if seed_value < 0.7:
            return self._select_authority(seed)
        else:
            return self._select_staker_weighted(seed)
    
    def _select_staker_weighted(self, seed: str) -> Validator:
        """Select staker with probability proportional to stake"""
        stakers = list(self.stakers)
        total_stake = sum(s.stake for s in stakers)
        
        # Weighted random selection
        seed_value = self.vrf.evaluate(seed) * total_stake
        cumulative = 0
        
        for staker in sorted(stakers, key=lambda x: x.stake):
            cumulative += staker.stake
            if cumulative >= seed_value:
                return staker
        
        return stakers[-1]  # Fallback
    
    async def propose_block(self, proposer: Validator, mode: ConsensusMode) -> Block:
        """Propose a new block"""
        # Create block
        block = Block(
            number=self.current_block + 1,
            parent_hash=self.chain[-1].hash if self.chain else "genesis",
            proposer=proposer.address,
            timestamp=datetime.utcnow(),
            mode=mode,
            transactions=self._generate_transactions(mode),
            authority_signatures=[],
            stake_signatures=[],
            merkle_root=""
        )
        
        # Calculate merkle root
        block.merkle_root = self._calculate_merkle_root(block.transactions)
        block.hash = self._calculate_block_hash(block)
        
        # Collect signatures
        block = await self._collect_signatures(block, mode)
        
        return block
    
    def _generate_transactions(self, mode: ConsensusMode) -> List[dict]:
        """Generate sample transactions"""
        if mode == ConsensusMode.FAST:
            tx_count = random.randint(100, 500)
        elif mode == ConsensusMode.BALANCED:
            tx_count = random.randint(50, 200)
        else:  # SECURE
            tx_count = random.randint(10, 100)
        
        transactions = []
        for i in range(tx_count):
            tx = {
                "from": f"user_{random.randint(0, 999)}",
                "to": f"user_{random.randint(0, 999)}",
                "amount": random.uniform(0.01, 1000),
                "gas": random.randint(21000, 100000),
                "nonce": i
            }
            transactions.append(tx)
        
        return transactions
    
    def _calculate_merkle_root(self, transactions: List[dict]) -> str:
        """Calculate merkle root of transactions"""
        if not transactions:
            return hashlib.sha256(b"").hexdigest()
        
        # Simple merkle tree implementation
        tx_hashes = [hashlib.sha256(json.dumps(tx, sort_keys=True).encode()).hexdigest() 
                    for tx in transactions]
        
        while len(tx_hashes) > 1:
            next_level = []
            for i in range(0, len(tx_hashes), 2):
                left = tx_hashes[i]
                right = tx_hashes[i + 1] if i + 1 < len(tx_hashes) else left
                combined = hashlib.sha256((left + right).encode()).hexdigest()
                next_level.append(combined)
            tx_hashes = next_level
        
        return tx_hashes[0]
    
    def _calculate_block_hash(self, block: Block) -> str:
        """Calculate block hash"""
        block_data = {
            "number": block.number,
            "parent_hash": block.parent_hash,
            "proposer": block.proposer,
            "timestamp": block.timestamp.isoformat(),
            "mode": block.mode.value,
            "merkle_root": block.merkle_root
        }
        return hashlib.sha256(json.dumps(block_data, sort_keys=True).encode()).hexdigest()
    
    async def _collect_signatures(self, block: Block, mode: ConsensusMode) -> Block:
        """Collect required signatures for block"""
        # Authority signatures (always required)
        auth_threshold = self._get_authority_threshold(mode)
        authorities = list(self.authorities)[:auth_threshold]
        
        for auth in authorities:
            signature = f"auth_sig_{auth.address}_{block.hash[:8]}"
            block.authority_signatures.append(signature)
        
        # Stake signatures (required in BALANCED and SECURE modes)
        if mode in [ConsensusMode.BALANCED, ConsensusMode.SECURE]:
            stake_threshold = self._get_stake_threshold(mode)
            stakers = list(self.stakers)[:stake_threshold]
            
            for staker in stakers:
                signature = f"stake_sig_{staker.address}_{block.hash[:8]}"
                block.stake_signatures.append(signature)
        
        return block
    
    def _get_authority_threshold(self, mode: ConsensusMode) -> int:
        """Get required authority signature threshold"""
        if mode == ConsensusMode.FAST:
            return 14  # 2/3 of 21
        elif mode == ConsensusMode.BALANCED:
            return 14  # 2/3 of 21
        else:  # SECURE
            return 7   # 1/3 of 21
        
    def _get_stake_threshold(self, mode: ConsensusMode) -> int:
        """Get required staker signature threshold"""
        if mode == ConsensusMode.BALANCED:
            return 33  # 1/3 of 100
        else:  # SECURE
            return 67  # 2/3 of 100
    
    def validate_block(self, block: Block) -> bool:
        """Validate block according to current mode"""
        # Check authority signatures
        auth_threshold = self._get_authority_threshold(block.mode)
        if len(block.authority_signatures) < auth_threshold:
            return False
        
        # Check stake signatures if required
        if block.mode in [ConsensusMode.BALANCED, ConsensusMode.SECURE]:
            stake_threshold = self._get_stake_threshold(block.mode)
            if len(block.stake_signatures) < stake_threshold:
                return False
        
        # Check block hash
        calculated_hash = self._calculate_block_hash(block)
        if calculated_hash != block.hash:
            return False
        
        # Check merkle root
        calculated_root = self._calculate_merkle_root(block.transactions)
        if calculated_root != block.merkle_root:
            return False
        
        return True
    
    def update_metrics(self):
        """Update network performance metrics"""
        if len(self.block_times) > 0:
            avg_block_time = sum(self.block_times[-10:]) / min(10, len(self.block_times))
            self.metrics.latency = avg_block_time
            self.metrics.tps = 1000 / avg_block_time if avg_block_time > 0 else 0
        
        self.metrics.active_validators = len(self.authorities) + len(self.stakers)
        self.metrics.stake_participation = 0.85  # Simulated
        self.metrics.authority_availability = 0.95  # Simulated
        self.metrics.network_load = random.uniform(0.2, 0.8)  # Simulated
    
    async def run_consensus(self, num_blocks: int = 100):
        """Run consensus simulation"""
        logger.info(f"Starting hybrid consensus simulation for {num_blocks} blocks")
        
        start_time = time.time()
        
        for i in range(num_blocks):
            # Update metrics and determine mode
            self.update_metrics()
            self.mode = self.determine_mode()
            
            # Select proposer
            proposer = self.select_proposer(i, self.mode)
            
            # Propose block
            block = await self.propose_block(proposer, self.mode)
            
            # Validate block
            if self.validate_block(block):
                self.chain.append(block)
                self.current_block += 1
                
                # Track block time
                now = datetime.utcnow()
                block_time = (now - self.last_block_time).total_seconds()
                self.block_times.append(block_time)
                self.last_block_time = now
                
                logger.info(
                    f"Block {block.number} proposed by {proposer.address} "
                    f"in {mode.name} mode ({block_time:.3f}s, {len(block.transactions)} txs)"
                )
            else:
                logger.error(f"Block {block.number} validation failed")
            
            # Small delay to simulate network
            await asyncio.sleep(0.01)
        
        total_time = time.time() - start_time
        
        # Print statistics
        self.print_statistics(total_time)
    
    def print_statistics(self, total_time: float):
        """Print consensus statistics"""
        logger.info("\n=== Consensus Statistics ===")
        logger.info(f"Total blocks: {len(self.chain)}")
        logger.info(f"Total time: {total_time:.2f}s")
        logger.info(f"Average TPS: {len(self.chain) / total_time:.2f}")
        logger.info(f"Average block time: {sum(self.block_times) / len(self.block_times):.3f}s")
        
        # Mode distribution
        mode_counts = defaultdict(int)
        for block in self.chain:
            mode_counts[block.mode] += 1
        
        logger.info("\nMode distribution:")
        for mode, count in mode_counts.items():
            percentage = (count / len(self.chain)) * 100
            logger.info(f"  {mode.value}: {count} blocks ({percentage:.1f}%)")
        
        # Proposer distribution
        proposer_counts = defaultdict(int)
        for block in self.chain:
            proposer_counts[block.proposer] += 1
        
        logger.info("\nTop proposers:")
        sorted_proposers = sorted(proposer_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for proposer, count in sorted_proposers:
            logger.info(f"  {proposer}: {count} blocks")


async def main():
    """Main function to run the consensus prototype"""
    config = {
        "num_authorities": 21,
        "num_stakers": 100,
        "block_time_target": 0.5,  # 500ms target
    }
    
    consensus = HybridConsensus(config)
    
    # Run simulation
    await consensus.run_consensus(num_blocks=100)
    
    logger.info("\nConsensus simulation completed!")


if __name__ == "__main__":
    asyncio.run(main())
