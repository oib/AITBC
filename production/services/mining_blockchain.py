#!/usr/bin/env python3
"""
Real Blockchain with Mining and Multi-Chain Support
"""

import os
import sys
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import threading

# Production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/var/log/aitbc/production/blockchain/mining.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProofOfWork:
    """Real Proof of Work mining algorithm"""
    
    def __init__(self, difficulty: int = 4):
        self.difficulty = difficulty
        self.target = "0" * difficulty
    
    def mine(self, block_data: dict) -> tuple:
        """Mine a block with real proof of work"""
        nonce = 0
        start_time = time.time()
        
        while True:
            # Create block hash with nonce
            content = f"{json.dumps(block_data, sort_keys=True)}{nonce}"
            block_hash = hashlib.sha256(content.encode()).hexdigest()
            
            # Check if hash meets difficulty
            if block_hash.startswith(self.target):
                mining_time = time.time() - start_time
                logger.info(f"Block mined! Nonce: {nonce}, Hash: {block_hash[:16]}..., Time: {mining_time:.2f}s")
                return block_hash, nonce, mining_time
            
            nonce += 1
            
            # Prevent infinite loop
            if nonce > 10000000:
                raise Exception("Mining failed - nonce too high")

class MultiChainManager:
    """Multi-chain blockchain manager"""
    
    def __init__(self):
        self.chains = {}
        self.miners = {}
        self.node_id = os.getenv('NODE_ID', 'aitbc')
        self.data_dir = Path(f'/var/lib/aitbc/data/blockchain/{self.node_id}')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize multiple chains
        self._initialize_chains()
        
        logger.info(f"Multi-chain manager initialized for node: {self.node_id}")
    
    def _initialize_chains(self):
        """Initialize multiple blockchain chains"""
        chains_config = [
            {
                'name': 'aitbc-main',
                'difficulty': 4,
                'block_reward': 50.0,
                'description': 'Main AITBC blockchain'
            },
            {
                'name': 'aitbc-gpu',
                'difficulty': 3,
                'block_reward': 25.0,
                'description': 'GPU computing blockchain'
            }
        ]
        
        for chain_config in chains_config:
            chain_name = chain_config['name']
            self.chains[chain_name] = {
                'name': chain_name,
                'blocks': [],
                'difficulty': chain_config['difficulty'],
                'block_reward': chain_config['block_reward'],
                'description': chain_config['description'],
                'pending_transactions': [],
                'balances': {},
                'mining_stats': {
                    'blocks_mined': 0,
                    'total_mining_time': 0,
                    'average_mining_time': 0
                }
            }
            
            # Create miner for this chain
            self.miners[chain_name] = ProofOfWork(chain_config['difficulty'])
            
            # Load existing chain data
            self._load_chain(chain_name)
            
            # Create genesis block if empty
            if not self.chains[chain_name]['blocks']:
                self._create_genesis_block(chain_name)
            
            logger.info(f"Chain {chain_name} initialized with {len(self.chains[chain_name]['blocks'])} blocks")
    
    def _load_chain(self, chain_name: str):
        """Load existing chain data"""
        chain_file = self.data_dir / f'{chain_name}.json'
        
        try:
            if chain_file.exists():
                with open(chain_file, 'r') as f:
                    data = json.load(f)
                
                self.chains[chain_name] = data
                logger.info(f"Loaded chain {chain_name} with {len(data.get('blocks', []))} blocks")
            
        except Exception as e:
            logger.error(f"Failed to load chain {chain_name}: {e}")
    
    def _save_chain(self, chain_name: str):
        """Save chain data"""
        try:
            chain_file = self.data_dir / f'{chain_name}.json'
            
            with open(chain_file, 'w') as f:
                json.dump(self.chains[chain_name], f, indent=2)
            
            logger.debug(f"Chain {chain_name} saved")
            
        except Exception as e:
            logger.error(f"Failed to save chain {chain_name}: {e}")
    
    def _create_genesis_block(self, chain_name: str):
        """Create genesis block for chain"""
        chain = self.chains[chain_name]
        
        genesis_data = {
            'index': 0,
            'timestamp': time.time(),
            'data': {
                'type': 'genesis',
                'chain': chain_name,
                'node_id': self.node_id,
                'description': chain['description'],
                'block_reward': chain['block_reward']
            },
            'previous_hash': '0',
            'nonce': 0
        }
        
        # Mine genesis block
        block_hash, nonce, mining_time = self.miners[chain_name].mine(genesis_data)
        
        genesis_block = {
            'index': 0,
            'timestamp': genesis_data['timestamp'],
            'data': genesis_data['data'],
            'previous_hash': '0',
            'hash': block_hash,
            'nonce': nonce,
            'mining_time': mining_time,
            'miner': self.node_id
        }
        
        chain['blocks'].append(genesis_block)
        chain['mining_stats']['blocks_mined'] = 1
        chain['mining_stats']['total_mining_time'] = mining_time
        chain['mining_stats']['average_mining_time'] = mining_time
        
        # Initialize miner balance with block reward
        chain['balances'][f'miner_{self.node_id}'] = chain['block_reward']
        
        self._save_chain(chain_name)
        
        logger.info(f"Genesis block created for {chain_name} - Reward: {chain['block_reward']} AITBC")
    
    def mine_block(self, chain_name: str, transactions: List[dict] = None) -> dict:
        """Mine a new block on specified chain"""
        if chain_name not in self.chains:
            raise Exception(f"Chain {chain_name} not found")
        
        chain = self.chains[chain_name]
        
        # Prepare block data
        block_data = {
            'index': len(chain['blocks']),
            'timestamp': time.time(),
            'data': {
                'transactions': transactions or [],
                'chain': chain_name,
                'node_id': self.node_id
            },
            'previous_hash': chain['blocks'][-1]['hash'] if chain['blocks'] else '0'
        }
        
        # Mine the block
        block_hash, nonce, mining_time = self.miners[chain_name].mine(block_data)
        
        # Create block
        new_block = {
            'index': block_data['index'],
            'timestamp': block_data['timestamp'],
            'data': block_data['data'],
            'previous_hash': block_data['previous_hash'],
            'hash': block_hash,
            'nonce': nonce,
            'mining_time': mining_time,
            'miner': self.node_id,
            'transactions_count': len(transactions or [])
        }
        
        # Add to chain
        chain['blocks'].append(new_block)
        
        # Update mining stats
        chain['mining_stats']['blocks_mined'] += 1
        chain['mining_stats']['total_mining_time'] += mining_time
        chain['mining_stats']['average_mining_time'] = (
            chain['mining_stats']['total_mining_time'] / chain['mining_stats']['blocks_mined']
        )
        
        # Reward miner
        miner_address = f'miner_{self.node_id}'
        if miner_address not in chain['balances']:
            chain['balances'][miner_address] = 0
        chain['balances'][miner_address] += chain['block_reward']
        
        # Process transactions
        for tx in transactions or []:
            self._process_transaction(chain, tx)
        
        self._save_chain(chain_name)
        
        logger.info(f"Block mined on {chain_name} - Reward: {chain['block_reward']} AITBC")
        
        return new_block
    
    def _process_transaction(self, chain: dict, transaction: dict):
        """Process a transaction"""
        from_addr = transaction.get('from_address')
        to_addr = transaction.get('to_address')
        amount = transaction.get('amount', 0)
        
        # Initialize balances
        if from_addr not in chain['balances']:
            chain['balances'][from_addr] = 1000.0  # Initial balance
        if to_addr not in chain['balances']:
            chain['balances'][to_addr] = 0.0
        
        # Process transaction
        if chain['balances'][from_addr] >= amount:
            chain['balances'][from_addr] -= amount
            chain['balances'][to_addr] += amount
            logger.info(f"Transaction processed: {amount} AITBC from {from_addr} to {to_addr}")
    
    def get_chain_info(self, chain_name: str) -> dict:
        """Get chain information"""
        if chain_name not in self.chains:
            return {'error': f'Chain {chain_name} not found'}
        
        chain = self.chains[chain_name]
        
        return {
            'chain_name': chain_name,
            'blocks': len(chain['blocks']),
            'difficulty': chain['difficulty'],
            'block_reward': chain['block_reward'],
            'description': chain['description'],
            'mining_stats': chain['mining_stats'],
            'total_addresses': len(chain['balances']),
            'total_balance': sum(chain['balances'].values()),
            'latest_block': chain['blocks'][-1] if chain['blocks'] else None
        }
    
    def get_all_chains_info(self) -> dict:
        """Get information about all chains"""
        return {
            'node_id': self.node_id,
            'total_chains': len(self.chains),
            'chains': {name: self.get_chain_info(name) for name in self.chains.keys()}
        }

if __name__ == '__main__':
    # Initialize multi-chain manager
    manager = MultiChainManager()
    
    # Mine blocks on all chains
    for chain_name in manager.chains.keys():
        try:
            # Create sample transactions
            transactions = [
                {
                    'from_address': f'user_{manager.node_id}',
                    'to_address': f'user_other',
                    'amount': 10.0,
                    'data': {'type': 'payment'}
                }
            ]
            
            # Mine block
            block = manager.mine_block(chain_name, transactions)
            print(f"Mined block on {chain_name}: {block['hash'][:16]}...")
            
        except Exception as e:
            logger.error(f"Failed to mine block on {chain_name}: {e}")
    
    # Print chain information
    info = manager.get_all_chains_info()
    print(f"Multi-chain info: {json.dumps(info, indent=2)}")
