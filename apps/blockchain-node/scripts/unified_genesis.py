#!/usr/bin/env python3
"""
Unified Genesis Block and Wallet Generation

This script combines genesis block creation with genesis wallet generation,
connected to the wallet service for proper key management and storage.

Usage:
    python3 unified_genesis.py --chain-id ait-mainnet --create-wallet
    python3 unified_genesis.py --chain-id ait-mainnet --force
"""

import json
import hashlib
import argparse
import secrets
import base64
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Add project paths
sys.path.insert(0, '/opt/aitbc')
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')

try:
    from aitbc_chain.config import BlockchainConfig
    from aitbc_chain.models import Block, Account
    from sqlmodel import Session, create_engine, select
except ImportError:
    print("Warning: Could not import blockchain modules, running in wallet-only mode")


def derive_address_from_public_key(pub_key_bytes: bytes) -> str:
    """Derive AITBC address from public key"""
    digest = hashlib.sha256(pub_key_bytes).digest()
    address_hash = digest[:20].hex()
    return f"aitbc1{address_hash}"


def compute_block_hash(height: int, parent_hash: str, timestamp: datetime, chain_id: str = "ait-mainnet") -> str:
    """Compute block hash"""
    hash_input = f"{height}{parent_hash}{timestamp.isoformat()}{chain_id}".encode()
    return hashlib.sha256(hash_input).hexdigest()


def create_genesis_wallet(password: str = None, chain_id: str = "ait-mainnet") -> Dict[str, str]:
    """Create genesis wallet with secure random private key"""
    # Generate cryptographically secure random private key
    private_key_bytes = secrets.token_bytes(32)
    
    # Generate Ed25519 key pair
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    public_key = private_key.public_key()
    
    # Get public key bytes
    pub_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    # Derive address
    address = derive_address_from_public_key(pub_key_bytes)
    ait_address = address.replace("aitbc1", "ait1")
    
    # Generate password if not provided
    if not password:
        password = secrets.token_urlsafe(32)
    
    # Encrypt private key with password
    salt = secrets.token_bytes(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = kdf.derive(password.encode())
    
    # Encrypt using AES-GCM
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, private_key_bytes, None)
    
    # Create wallet data
    wallet_data = {
        "address": ait_address,
        "public_key": pub_key_bytes.hex(),
        "crypto": {
            "kdf": "pbkdf2",
            "kdfparams": {
                "salt": salt.hex(),
                "c": 100000,
                "dklen": 32,
                "prf": "hmac-sha256"
            },
            "cipher": "aes-256-gcm",
            "cipherparams": {
                "nonce": nonce.hex()
            },
            "ciphertext": ciphertext.hex()
        },
        "version": 1
    }
    
    return {
        "wallet": wallet_data,
        "address": ait_address,
        "public_key": pub_key_bytes.hex(),
        "private_key": private_key_bytes.hex(),
        "password": password
    }


def create_genesis_block(chain_id: str, proposer: str, timestamp: datetime = None) -> Dict[str, Any]:
    """Create genesis block"""
    if not timestamp:
        timestamp = datetime.fromisoformat("2025-01-01 00:00:00")
    
    parent_hash = "0x00"
    genesis_hash = compute_block_hash(0, parent_hash, timestamp, chain_id)
    
    genesis_block = {
        "height": 0,
        "hash": genesis_hash,
        "parent_hash": parent_hash,
        "proposer": proposer,
        "timestamp": timestamp.isoformat(),
        "tx_count": 0,
        "chain_id": chain_id,
        "state_root": "0x00",
        "metadata": {
            "chain_type": "mainnet",
            "purpose": "production",
            "consensus_algorithm": "poa"
        }
    }
    
    return genesis_block


def create_genesis_allocations(genesis_address: str, additional_allocations: List[Dict] = None) -> List[Dict]:
    """Create genesis allocations including genesis wallet"""
    allocations = [
        {
            "address": genesis_address,
            "balance": 1000000000,  # 1 billion AIT for genesis
            "nonce": 0
        }
    ]
    
    if additional_allocations:
        allocations.extend(additional_allocations)
    
    return allocations


def save_genesis_wallet(wallet_data: Dict, keystore_path: Path, password: str):
    """Save genesis wallet to keystore"""
    keystore_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(keystore_path, 'w') as f:
        json.dump(wallet_data, f, indent=2)
    
    # Save password securely
    password_path = keystore_path.parent / ".genesis_password"
    with open(password_path, 'w') as f:
        f.write(password)
    os.chmod(password_path, 0o600)


def save_genesis_json(genesis_block: Dict, allocations: List[Dict], genesis_path: Path):
    """Save genesis configuration to JSON file"""
    genesis_path.parent.mkdir(parents=True, exist_ok=True)
    
    genesis_config = {
        "chain_id": genesis_block["chain_id"],
        "block": genesis_block,
        "allocations": allocations
    }
    
    with open(genesis_path, 'w') as f:
        json.dump(genesis_config, f, indent=2)


def initialize_genesis_database(genesis_block: Dict, allocations: List[Dict], db_path: Path):
    """Initialize blockchain database with genesis data"""
    import sqlite3
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if genesis block already exists
        cursor.execute("SELECT * FROM block WHERE height=0 AND chain_id=?", (genesis_block["chain_id"],))
        existing = cursor.fetchone()
        
        if existing:
            print(f"⚠️  Genesis block already exists in database")
            return False
        
        # Create genesis block
        cursor.execute(
            """INSERT INTO block (height, hash, parent_hash, proposer, timestamp, tx_count, chain_id, state_root) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                genesis_block["height"],
                genesis_block["hash"],
                genesis_block["parent_hash"],
                genesis_block["proposer"],
                genesis_block["timestamp"],
                genesis_block["tx_count"],
                genesis_block["chain_id"],
                genesis_block.get("state_root", "0x00")
            )
        )
        
        # Create genesis accounts
        for alloc in allocations:
            cursor.execute(
                """INSERT INTO account (chain_id, address, balance, nonce, updated_at) 
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    genesis_block["chain_id"],
                    alloc["address"],
                    alloc["balance"],
                    alloc["nonce"],
                    datetime.utcnow().isoformat()
                )
            )
        
        conn.commit()
        print(f"✅ Genesis initialized in database: {db_path}")
        return True
            
    except sqlite3.Error as e:
        print(f"❌ Error initializing genesis in database: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()


def register_wallet_with_service(wallet_address: str, wallet_data: Dict, service_url: str = "http://localhost:8003"):
    """Register genesis wallet with wallet daemon service"""
    try:
        import httpx
        
        response = httpx.post(
            f"{service_url}/api/wallet",
            json={
                "address": wallet_address,
                "public_key": wallet_data["public_key"],
                "wallet_type": "genesis"
            },
            timeout=5
        )
        
        if response.status_code in (200, 201):
            print(f"✅ Genesis wallet registered with wallet service")
            return True
        else:
            print(f"⚠️  Failed to register with wallet service: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"⚠️  Could not connect to wallet service: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Unified Genesis Block and Wallet Generation")
    parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID")
    parser.add_argument("--proposer", help="Proposer address (defaults to genesis wallet)")
    parser.add_argument("--create-wallet", action="store_true", help="Create genesis wallet")
    parser.add_argument("--password", help="Wallet password (auto-generated if not provided)")
    parser.add_argument("--db-path", default="/var/lib/aitbc/data/chain.db", help="Database path")
    parser.add_argument("--keystore-path", default="/var/lib/aitbc/keystore/genesis.json", help="Keystore path")
    parser.add_argument("--genesis-path", default="/var/lib/aitbc/data/ait-mainnet/genesis.json", help="Genesis config path")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing genesis")
    parser.add_argument("--register-service", action="store_true", help="Register with wallet service")
    parser.add_argument("--service-url", default="http://localhost:8003", help="Wallet service URL")
    
    args = parser.parse_args()
    
    print(f"🌟 Unified Genesis Generation for {args.chain_id}")
    print("=" * 60)
    
    # Create genesis wallet
    if args.create_wallet:
        print(f"\n📝 Creating Genesis Wallet...")
        wallet_result = create_genesis_wallet(args.password, args.chain_id)
        
        print(f"Address: {wallet_result['address']}")
        print(f"Public key: {wallet_result['public_key']}")
        print(f"Private key: {wallet_result['private_key']}")
        print(f"Password: {wallet_result['password']}")
        
        save_genesis_wallet(wallet_result['wallet'], Path(args.keystore_path), wallet_result['password'])
        print(f"Wallet saved to: {args.keystore_path}")
        
        proposer = args.proposer or wallet_result['address']
    else:
        proposer = args.proposer or "genesis"
        wallet_result = None
    
    # Create genesis block
    print(f"\n📦 Creating Genesis Block...")
    genesis_block = create_genesis_block(args.chain_id, proposer)
    print(f"Height: {genesis_block['height']}")
    print(f"Hash: {genesis_block['hash']}")
    print(f"Proposer: {genesis_block['proposer']}")
    
    # Create allocations
    print(f"\n💰 Creating Genesis Allocations...")
    if wallet_result:
        allocations = create_genesis_allocations(wallet_result['address'])
    else:
        allocations = create_genesis_allocations(proposer)
    
    print(f"Total allocations: {len(allocations)}")
    for alloc in allocations[:3]:  # Show first 3
        print(f"  - {alloc['address']}: {alloc['balance']} AIT")
    
    # Save genesis configuration
    print(f"\n💾 Saving Genesis Configuration...")
    save_genesis_json(genesis_block, allocations, Path(args.genesis_path))
    print(f"Genesis config saved to: {args.genesis_path}")
    
    # Initialize database
    print(f"\n🗄️  Initializing Database...")
    if initialize_genesis_database(genesis_block, allocations, Path(args.db_path)):
        print(f"Database initialized: {args.db_path}")
    
    # Register with wallet service
    if args.register_service and wallet_result:
        print(f"\n🔗 Registering with Wallet Service...")
        register_wallet_with_service(wallet_result['address'], wallet_result['wallet'], args.service_url)
    
    print(f"\n✅ Unified Genesis Generation Complete!")
    print(f"\n📋 Summary:")
    print(f"  Chain ID: {args.chain_id}")
    print(f"  Genesis Block: {genesis_block['hash']}")
    if wallet_result:
        print(f"  Genesis Wallet: {wallet_result['address']}")
        print(f"  Wallet Password: {wallet_result['password']}")
        print(f"  ⚠️  IMPORTANT: Store the password securely!")
    print(f"  Database: {args.db_path}")
    print(f"  Config: {args.genesis_path}")


if __name__ == "__main__":
    main()
