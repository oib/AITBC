#!/usr/bin/env python3
"""
Simple script to create genesis block
"""

import sys
sys.path.insert(0, 'src')

from aitbc_chain.database import session_scope, init_db
from aitbc_chain.models import Block
from datetime import datetime
import hashlib

def compute_block_hash(height: int, parent_hash: str, timestamp: datetime) -> str:
    """Compute block hash"""
    data = f"{height}{parent_hash}{timestamp}".encode()
    return hashlib.sha256(data).hexdigest()

def create_genesis():
    """Create the genesis block"""
    print("Creating genesis block...")
    
    # Initialize database
    init_db()
    
    # Check if genesis already exists
    with session_scope() as session:
        existing = session.exec(select(Block).order_by(Block.height.desc()).limit(1)).first()
        if existing:
            print(f"Genesis block already exists: #{existing.height}")
            return
        
        # Create genesis block
        timestamp = datetime.utcnow()
        genesis_hash = compute_block_hash(0, "0x00", timestamp)
        genesis = Block(
            height=0,
            hash=genesis_hash,
            parent_hash="0x00",
            proposer="ait-devnet-proposer",
            timestamp=timestamp,
            tx_count=0,
            state_root=None,
        )
        session.add(genesis)
        session.commit()
        print(f"Genesis block created: #{genesis.height}")
        print(f"Hash: {genesis.hash}")
        print(f"Proposer: {genesis.proposer}")
        print(f"Timestamp: {genesis.timestamp}")

if __name__ == "__main__":
    from sqlmodel import select
    create_genesis()
