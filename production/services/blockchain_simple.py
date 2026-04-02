#!/usr/bin/env python3
"""
Production Blockchain Service - Simplified
Working blockchain implementation with persistence
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
import hashlib

# Production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/opt/aitbc/production/logs/blockchain/blockchain.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Block:
    """Simple block implementation"""
    
    def __init__(self, index: int, data: dict, previous_hash: str):
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """Calculate block hash"""
        content = f"{self.index}{self.timestamp}{json.dumps(self.data, sort_keys=True)}{self.previous_hash}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def to_dict(self) -> dict:
        """Convert block to dictionary"""
        return {
            'index': self.index,
            'timestamp': self.timestamp,
            'data': self.data,
            'previous_hash': self.previous_hash,
            'hash': self.hash
        }

class Transaction:
    """Simple transaction implementation"""
    
    def __init__(self, from_address: str, to_address: str, amount: float, data: dict = None):
        self.from_address = from_address
        self.to_address = to_address
        self.amount = amount
        self.data = data or {}
        self.timestamp = time.time()
        self.tx_hash = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """Calculate transaction hash"""
        content = f"{self.from_address}{self.to_address}{self.amount}{json.dumps(self.data, sort_keys=True)}{self.timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def to_dict(self) -> dict:
        """Convert transaction to dictionary"""
        return {
            'from_address': self.from_address,
            'to_address': self.to_address,
            'amount': self.amount,
            'data': self.data,
            'timestamp': self.timestamp,
            'tx_hash': self.tx_hash
        }

class ProductionBlockchain:
    """Production-grade blockchain implementation"""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.data_dir = Path(f'/opt/aitbc/production/data/blockchain/{node_id}')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize blockchain
        self.chain = []
        self.pending_transactions = []
        self.balances = {}
        
        # Load existing data if available
        self._load_blockchain()
        
        # Create genesis block if empty
        if not self.chain:
            self._create_genesis_block()
        
        logger.info(f"Production blockchain initialized for node: {node_id}")
    
    def _create_genesis_block(self):
        """Create genesis block"""
        genesis_data = {
            'type': 'genesis',
            'node_id': self.node_id,
            'message': 'AITBC Production Blockchain Genesis Block',
            'timestamp': time.time()
        }
        
        genesis_block = Block(0, genesis_data, '0')
        self.chain.append(genesis_block)
        self._save_blockchain()
        
        logger.info("Genesis block created")
    
    def _load_blockchain(self):
        """Load existing blockchain data"""
        chain_file = self.data_dir / 'blockchain.json'
        balances_file = self.data_dir / 'balances.json'
        
        try:
            if chain_file.exists():
                with open(chain_file, 'r') as f:
                    data = json.load(f)
                
                # Load blocks
                self.chain = []
                for block_data in data.get('blocks', []):
                    block = Block(
                        block_data['index'],
                        block_data['data'],
                        block_data['previous_hash']
                    )
                    block.hash = block_data['hash']
                    block.timestamp = block_data['timestamp']
                    self.chain.append(block)
                
                logger.info(f"Loaded {len(self.chain)} blocks")
            
            if balances_file.exists():
                with open(balances_file, 'r') as f:
                    self.balances = json.load(f)
                logger.info(f"Loaded balances for {len(self.balances)} addresses")
            
        except Exception as e:
            logger.error(f"Failed to load blockchain: {e}")
    
    def _save_blockchain(self):
        """Save blockchain state"""
        try:
            chain_file = self.data_dir / 'blockchain.json'
            balances_file = self.data_dir / 'balances.json'
            
            # Save blocks
            data = {
                'blocks': [block.to_dict() for block in self.chain],
                'last_updated': time.time(),
                'node_id': self.node_id
            }
            
            with open(chain_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Save balances
            with open(balances_file, 'w') as f:
                json.dump(self.balances, f, indent=2)
            
            logger.debug(f"Blockchain saved to {chain_file}")
            
        except Exception as e:
            logger.error(f"Failed to save blockchain: {e}")
    
    def create_transaction(self, from_address: str, to_address: str, amount: float, data: dict = None):
        """Create and process a transaction"""
        try:
            transaction = Transaction(from_address, to_address, amount, data)
            
            # Add to pending transactions
            self.pending_transactions.append(transaction)
            
            # Process transaction (simplified - no validation for demo)
            self._process_transaction(transaction)
            
            # Create new block if we have enough transactions
            if len(self.pending_transactions) >= 1:  # Create block for each transaction in production
                self._create_block()
            
            logger.info(f"Transaction processed: {transaction.tx_hash}")
            return transaction.tx_hash
            
        except Exception as e:
            logger.error(f"Failed to create transaction: {e}")
            raise
    
    def _process_transaction(self, transaction: Transaction):
        """Process a transaction"""
        # Initialize balances if needed
        if transaction.from_address not in self.balances:
            self.balances[transaction.from_address] = 10000.0  # Initial balance
        if transaction.to_address not in self.balances:
            self.balances[transaction.to_address] = 0.0
        
        # Check balance (simplified)
        if self.balances[transaction.from_address] >= transaction.amount:
            self.balances[transaction.from_address] -= transaction.amount
            self.balances[transaction.to_address] += transaction.amount
            logger.info(f"Transferred {transaction.amount} from {transaction.from_address} to {transaction.to_address}")
        else:
            logger.warning(f"Insufficient balance for {transaction.from_address}")
    
    def _create_block(self):
        """Create a new block"""
        if not self.pending_transactions:
            return
        
        previous_hash = self.chain[-1].hash if self.chain else '0'
        
        block_data = {
            'transactions': [tx.to_dict() for tx in self.pending_transactions],
            'node_id': self.node_id,
            'block_reward': 10.0
        }
        
        new_block = Block(len(self.chain), block_data, previous_hash)
        self.chain.append(new_block)
        
        # Clear pending transactions
        self.pending_transactions.clear()
        
        # Save blockchain
        self._save_blockchain()
        
        logger.info(f"Block {new_block.index} created")
    
    def get_balance(self, address: str) -> float:
        """Get balance for address"""
        return self.balances.get(address, 0.0)
    
    def get_blockchain_info(self) -> dict:
        """Get blockchain information"""
        return {
            'node_id': self.node_id,
            'blocks': len(self.chain),
            'pending_transactions': len(self.pending_transactions),
            'total_addresses': len(self.balances),
            'last_block': self.chain[-1].to_dict() if self.chain else None,
            'total_balance': sum(self.balances.values())
        }

if __name__ == '__main__':
    node_id = os.getenv('NODE_ID', 'aitbc')
    blockchain = ProductionBlockchain(node_id)
    
    # Example transaction
    try:
        tx_hash = blockchain.create_transaction(
            from_address='0xuser1',
            to_address='0xuser2',
            amount=100.0,
            data={'type': 'payment', 'description': 'Production test transaction'}
        )
        print(f"Transaction created: {tx_hash}")
        
        # Print blockchain info
        info = blockchain.get_blockchain_info()
        print(f"Blockchain info: {info}")
        
    except Exception as e:
        logger.error(f"Production blockchain error: {e}")
        sys.exit(1)
