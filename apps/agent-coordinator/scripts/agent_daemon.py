#!/usr/bin/env python3
"""
AITBC Autonomous Agent Listener Daemon
Listens for blockchain transactions addressed to an agent wallet and autonomously replies.
"""

import sys
import time
import requests
import json
import hashlib
import argparse
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from aitbc.constants import KEYSTORE_DIR, DATA_DIR

# Default configuration
DEFAULT_KEYSTORE_DIR = KEYSTORE_DIR
DEFAULT_DB_PATH = str(DATA_DIR / "data/ait-mainnet/chain.db")
DEFAULT_RPC_URL = "http://localhost:8006"
DEFAULT_POLL_INTERVAL = 2


def decrypt_wallet(keystore_path: Path, password: str) -> bytes:
    """Decrypt private key from keystore file.
    
    Supports both keystore formats:
    - AES-256-GCM (blockchain-node standard)
    - Fernet (scripts/utils standard)
    """
    with open(keystore_path) as f:
        data = json.load(f)
    
    crypto = data.get('crypto', data)  # Handle both nested and flat crypto structures
    
    # Detect encryption method
    cipher = crypto.get('cipher', crypto.get('algorithm', ''))
    
    if cipher == 'aes-256-gcm':
        # AES-256-GCM (blockchain-node standard)
        salt = bytes.fromhex(crypto['kdfparams']['salt'])
        ciphertext = bytes.fromhex(crypto['ciphertext'])
        nonce = bytes.fromhex(crypto['cipherparams']['nonce'])
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=crypto['kdfparams']['dklen'],
            salt=salt,
            iterations=crypto['kdfparams']['c'],
            backend=default_backend()
        )
        key = kdf.derive(password.encode())
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    
    elif cipher == 'fernet' or cipher == 'PBKDF2-SHA256-Fernet':
        # Fernet (scripts/utils standard)
        from cryptography.fernet import Fernet
        import base64
        
        kdfparams = crypto.get('kdfparams', {})
        if 'salt' in kdfparams:
            salt = base64.b64decode(kdfparams['salt'])
        else:
            salt = bytes.fromhex(kdfparams.get('salt', ''))
        
        # Use PBKDF2 for secure key derivation (100,000 iterations for security)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, dklen=32)
        fernet_key = base64.urlsafe_b64encode(dk)
        
        f = Fernet(fernet_key)
        ciphertext = base64.b64decode(crypto['ciphertext'])
        priv = f.decrypt(ciphertext)
        return priv.encode()
    
    else:
        raise ValueError(f"Unsupported cipher: {cipher}")


def create_tx(private_bytes: bytes, from_addr: str, to_addr: str, amount: float, fee: float, payload: str) -> dict:
    """Create and sign a transaction"""
    priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    pub_hex = priv_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    ).hex()
    
    tx = {
        "type": "transfer",
        "from": from_addr,
        "to": to_addr,
        "amount": amount,
        "fee": fee,
        "nonce": int(time.time() * 1000),
        "payload": payload,
        "chain_id": "ait-mainnet"
    }
    
    tx_string = json.dumps(tx, sort_keys=True)
    tx["signature"] = priv_key.sign(tx_string.encode()).hex()
    tx["public_key"] = pub_hex
    return tx


def main():
    parser = argparse.ArgumentParser(description="AITBC Autonomous Agent Listener Daemon")
    parser.add_argument("--wallet", required=True, help="Wallet name (e.g., temp-agent2)")
    parser.add_argument("--address", required=True, help="Agent wallet address")
    parser.add_argument("--password", help="Wallet password")
    parser.add_argument("--password-file", help="Path to file containing wallet password")
    parser.add_argument("--keystore-dir", default=DEFAULT_KEYSTORE_DIR, help="Keystore directory")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="Path to blockchain database")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="RPC endpoint URL")
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL, help="Poll interval in seconds")
    parser.add_argument("--reply-message", default="pong", help="Message to send as reply")
    parser.add_argument("--trigger-message", default="ping", help="Message that triggers reply")
    
    args = parser.parse_args()
    
    # Get password
    if args.password_file:
        with open(args.password_file) as f:
            password = f.read().strip()
    elif args.password:
        password = args.password
    else:
        print("Error: password or password-file is required")
        sys.exit(1)
    
    # Setup paths
    keystore_path = Path(args.keystore_dir) / f"{args.wallet}.json"
    
    print(f"Agent daemon started. Listening for messages to {args.address}...")
    print(f"Trigger message: '{args.trigger_message}'")
    print(f"Reply message: '{args.reply_message}'")
    
    # Decrypt wallet
    try:
        priv_bytes = decrypt_wallet(keystore_path, password)
        print("Wallet unlocked successfully.")
    except Exception as e:
        print(f"Failed to unlock wallet: {e}")
        sys.exit(1)
    
    sys.stdout.flush()
    
    # Setup database connection
    processed_txs = set()
    sys.path.insert(0, "/opt/aitbc/apps/blockchain-node/src")
    
    try:
        from sqlmodel import create_engine, Session, select
        from aitbc_chain.models import Transaction
        
        engine = create_engine(f"sqlite:///{args.db_path}")
        print(f"Connected to database: {args.db_path}")
    except ImportError as e:
        print(f"Error importing sqlmodel: {e}")
        print("Make sure sqlmodel is installed in the virtual environment")
        sys.exit(1)
    
    sys.stdout.flush()
    
    # Main polling loop
    while True:
        try:
            with Session(engine) as session:
                txs = session.exec(
                    select(Transaction).where(Transaction.recipient == args.address)
                ).all()
                
                for tx in txs:
                    if tx.id in processed_txs:
                        continue
                    
                    processed_txs.add(tx.id)
                    
                    # Extract payload
                    data = ""
                    if hasattr(tx, "tx_metadata") and tx.tx_metadata:
                        if isinstance(tx.tx_metadata, dict):
                            data = tx.tx_metadata.get("payload", "")
                        elif isinstance(tx.tx_metadata, str):
                            try:
                                data = json.loads(tx.tx_metadata).get("payload", "")
                            except json.JSONDecodeError:
                                pass
                    elif hasattr(tx, "payload") and tx.payload:
                        if isinstance(tx.payload, dict):
                            data = tx.payload.get("payload", "")
                    
                    sender = tx.sender
                    
                    # Check if message matches trigger
                    if sender != args.address and args.trigger_message in str(data):
                        print(f"Received '{data}' from {sender}! Sending '{args.reply_message}'...")
                        reply_tx = create_tx(priv_bytes, args.address, sender, 0, 10, args.reply_message)
                        
                        try:
                            res = requests.post(f"{args.rpc_url}/rpc/transaction", json=reply_tx, timeout=10)
                            if res.status_code == 200:
                                print(f"Reply sent successfully: {res.json()}")
                            else:
                                print(f"Failed to send reply: {res.text}")
                        except requests.RequestException as e:
                            print(f"Network error sending reply: {e}")
                    
                    sys.stdout.flush()
                    
        except Exception as e:
            print(f"Error querying database: {e}")
            sys.stdout.flush()
        
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
