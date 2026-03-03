#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath('apps/blockchain-node/src'))

from sqlmodel import select
from aitbc_chain.database import session_scope, init_db
from aitbc_chain.models import Block
from datetime import datetime
import hashlib

def compute_block_hash(chain_id: str, height: int, parent_hash: str, timestamp: datetime) -> str:
    data = f"{chain_id}{height}{parent_hash}{timestamp.isoformat()}".encode()
    return "0x" + hashlib.sha256(data).hexdigest()

def create_genesis(chain_id: str):
    print(f"Creating genesis block for {chain_id}...")
    
    with session_scope() as session:
        existing = session.exec(select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)).first()
        if existing:
            print(f"Genesis block already exists for {chain_id}: #{existing.height} (hash: {existing.hash})")
            return
        
        # Use a deterministic timestamp so all nodes agree on the hash
        timestamp = datetime(2025, 1, 1, 0, 0, 0)
        genesis_hash = compute_block_hash(chain_id, 0, "0x00", timestamp)
        genesis = Block(
            chain_id=chain_id,
            height=0,
            hash=genesis_hash,
            parent_hash="0x00",
            proposer="genesis",
            timestamp=timestamp,
            tx_count=0,
            state_root=None,
        )
        session.add(genesis)
        session.commit()
        print(f"Genesis block created for {chain_id}: #{genesis.height}")
        print(f"Hash: {genesis.hash}")
        print(f"Proposer: {genesis.proposer}")
        print(f"Timestamp: {genesis.timestamp.isoformat()}")

if __name__ == "__main__":
    init_db()
    for chain in ["ait-testnet", "ait-devnet", "ait-healthchain"]:
        create_genesis(chain)
