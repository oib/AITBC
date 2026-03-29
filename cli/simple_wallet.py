#!/usr/bin/env python3
"""
Simple wallet operations for AITBC blockchain
Compatible with existing keystore structure
"""

import json
import sys
import os
import argparse
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import requests
from typing import Optional, Dict, Any, List

# Default paths
DEFAULT_KEYSTORE_DIR = Path("/var/lib/aitbc/keystore")
DEFAULT_RPC_URL = "http://localhost:8006"


def decrypt_private_key(keystore_path: Path, password: str) -> str:
    """Decrypt private key from keystore file"""
    with open(keystore_path) as f:
        ks = json.load(f)
    
    crypto = ks['crypto']
    salt = bytes.fromhex(crypto['kdfparams']['salt'])
    kdf = PBKDF2HMAC(hashes.SHA256(), 32, salt, crypto['kdfparams']['c'])
    key = kdf.derive(password.encode())
    aesgcm = AESGCM(key)
    nonce = bytes.fromhex(crypto['cipherparams']['nonce'])
    priv = aesgcm.decrypt(nonce, bytes.fromhex(crypto['ciphertext']), None)
    return priv.hex()


def create_wallet(name: str, password: str, keystore_dir: Path = DEFAULT_KEYSTORE_DIR) -> str:
    """Create a new wallet"""
    keystore_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate new key pair
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_key_hex = private_key.private_bytes_raw().hex()
    public_key = private_key.public_key()
    public_key_hex = public_key.public_bytes_raw().hex()
    
    # Calculate address (simplified - in real implementation this would be more complex)
    address = f"ait1{public_key_hex[:40]}"
    
    # Encrypt private key
    salt = os.urandom(32)
    kdf = PBKDF2HMAC(hashes.SHA256(), 32, salt, 100000)
    key = kdf.derive(password.encode())
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, bytes.fromhex(private_key_hex), None)
    
    # Create keystore file
    keystore_data = {
        "address": address,
        "public_key": public_key_hex,
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
    
    keystore_path = keystore_dir / f"{name}.json"
    with open(keystore_path, 'w') as f:
        json.dump(keystore_data, f, indent=2)
    
    print(f"Wallet created: {name}")
    print(f"Address: {address}")
    print(f"Keystore: {keystore_path}")
    
    return address


def send_transaction(from_wallet: str, to_address: str, amount: float, fee: float, 
                   password: str, keystore_dir: Path = DEFAULT_KEYSTORE_DIR, 
                   rpc_url: str = DEFAULT_RPC_URL) -> Optional[str]:
    """Send transaction from one wallet to another"""
    
    # Get sender wallet info
    sender_keystore = keystore_dir / f"{from_wallet}.json"
    if not sender_keystore.exists():
        print(f"Error: Wallet '{from_wallet}' not found")
        return None
    
    with open(sender_keystore) as f:
        sender_data = json.load(f)
    
    sender_address = sender_data['address']
    
    # Decrypt private key
    try:
        private_key_hex = decrypt_private_key(sender_keystore, password)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    except Exception as e:
        print(f"Error decrypting wallet: {e}")
        return None
    
    # Create transaction
    transaction = {
        "sender": sender_address,
        "recipient": to_address,
        "value": int(amount),
        "fee": int(fee),
        "nonce": 0,  # In real implementation, get current nonce
        "type": "transfer",
        "payload": {}
    }
    
    # Sign transaction (simplified)
    message = json.dumps(transaction, sort_keys=True).encode()
    signature = private_key.sign(message)
    transaction["signature"] = signature.hex()
    
    # Submit transaction
    try:
        response = requests.post(f"{rpc_url}/sendTx", json=transaction)
        if response.status_code == 200:
            result = response.json()
            print(f"Transaction submitted successfully")
            print(f"From: {sender_address}")
            print(f"To: {to_address}")
            print(f"Amount: {amount} AIT")
            print(f"Fee: {fee} AIT")
            return result.get("hash")
        else:
            print(f"Error submitting transaction: {response.text}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def list_wallets(keystore_dir: Path = DEFAULT_KEYSTORE_DIR) -> list:
    """List all wallets"""
    wallets = []
    if keystore_dir.exists():
        for wallet_file in keystore_dir.glob("*.json"):
            try:
                with open(wallet_file) as f:
                    data = json.load(f)
                wallets.append({
                    "name": wallet_file.stem,
                    "address": data["address"],
                    "file": str(wallet_file)
                })
            except Exception:
                pass
    return wallets


def get_balance(wallet_name: str, keystore_dir: Path = DEFAULT_KEYSTORE_DIR, 
                rpc_url: str = DEFAULT_RPC_URL) -> Optional[Dict]:
    """Get wallet balance and transaction info"""
    try:
        keystore_path = keystore_dir / f"{wallet_name}.json"
        if not keystore_path.exists():
            print(f"Error: Wallet '{wallet_name}' not found")
            return None
        
        with open(keystore_path) as f:
            wallet_data = json.load(f)
        
        address = wallet_data['address']
        
        # Get balance from RPC
        response = requests.get(f"{rpc_url}/rpc/getBalance/{address}")
        if response.status_code == 200:
            balance_data = response.json()
            return {
                "address": address,
                "balance": balance_data.get("balance", 0),
                "nonce": balance_data.get("nonce", 0),
                "wallet_name": wallet_name
            }
        else:
            print(f"Error getting balance: {response.text}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def get_transactions(wallet_name: str, keystore_dir: Path = DEFAULT_KEYSTORE_DIR,
                    rpc_url: str = DEFAULT_RPC_URL, limit: int = 10) -> List[Dict]:
    """Get wallet transaction history"""
    try:
        keystore_path = keystore_dir / f"{wallet_name}.json"
        if not keystore_path.exists():
            print(f"Error: Wallet '{wallet_name}' not found")
            return []
        
        with open(keystore_path) as f:
            wallet_data = json.load(f)
        
        address = wallet_data['address']
        
        # Get transactions from RPC
        response = requests.get(f"{rpc_url}/rpc/transactions?address={address}&limit={limit}")
        if response.status_code == 200:
            tx_data = response.json()
            return tx_data.get("transactions", [])
        else:
            print(f"Error getting transactions: {response.text}")
            return []
    except Exception as e:
        print(f"Error: {e}")
        return []


def get_chain_info(rpc_url: str = DEFAULT_RPC_URL) -> Optional[Dict]:
    """Get blockchain information"""
    try:
        response = requests.get(f"{rpc_url}/rpc/info")
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting chain info: {response.text}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def get_network_status(rpc_url: str = DEFAULT_RPC_URL) -> Optional[Dict]:
    """Get network status and health"""
    try:
        # Get head block
        head_response = requests.get(f"{rpc_url}/rpc/head")
        if head_response.status_code == 200:
            head_data = head_response.json()
            
            # Get chain info
            chain_info = get_chain_info(rpc_url)
            
            return {
                "height": head_data.get("height", 0),
                "hash": head_data.get("hash", ""),
                "chain_id": chain_info.get("chain_id", "") if chain_info else "",
                "supported_chains": chain_info.get("supported_chains", "") if chain_info else "",
                "rpc_version": chain_info.get("rpc_version", "") if chain_info else "",
                "timestamp": head_data.get("timestamp", 0)
            }
        else:
            print(f"Error getting network status: {head_response.text}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="AITBC Wallet CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Create wallet command
    create_parser = subparsers.add_parser("create", help="Create a new wallet")
    create_parser.add_argument("--name", required=True, help="Wallet name")
    create_parser.add_argument("--password", help="Wallet password")
    create_parser.add_argument("--password-file", help="File containing wallet password")
    
    # Send transaction command
    send_parser = subparsers.add_parser("send", help="Send AIT")
    send_parser.add_argument("--from", required=True, dest="from_wallet", help="From wallet name")
    send_parser.add_argument("--to", required=True, dest="to_address", help="To address")
    send_parser.add_argument("--amount", type=float, required=True, help="Amount to send")
    send_parser.add_argument("--fee", type=float, default=10.0, help="Transaction fee")
    send_parser.add_argument("--password", help="Wallet password")
    send_parser.add_argument("--password-file", help="File containing wallet password")
    send_parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="RPC URL")
    
    # List wallets command
    list_parser = subparsers.add_parser("list", help="List wallets")
    list_parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    
    # Balance command
    balance_parser = subparsers.add_parser("balance", help="Get wallet balance")
    balance_parser.add_argument("--name", required=True, help="Wallet name")
    balance_parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="RPC URL")
    
    # Transactions command
    tx_parser = subparsers.add_parser("transactions", help="Get wallet transactions")
    tx_parser.add_argument("--name", required=True, help="Wallet name")
    tx_parser.add_argument("--limit", type=int, default=10, help="Number of transactions")
    tx_parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    tx_parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="RPC URL")
    
    # Chain info command
    chain_parser = subparsers.add_parser("chain", help="Get blockchain information")
    chain_parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="RPC URL")
    
    # Network status command
    network_parser = subparsers.add_parser("network", help="Get network status")
    network_parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="RPC URL")
    
    args = parser.parse_args()
    
    if args.command == "create":
        # Get password
        password = None
        if args.password:
            password = args.password
        elif args.password_file:
            with open(args.password_file) as f:
                password = f.read().strip()
        else:
            import getpass
            password = getpass.getpass("Enter wallet password: ")
        
        if not password:
            print("Error: Password is required")
            sys.exit(1)
        
        address = create_wallet(args.name, password)
        print(f"Wallet address: {address}")
    
    elif args.command == "send":
        # Get password
        password = None
        if args.password:
            password = args.password
        elif args.password_file:
            with open(args.password_file) as f:
                password = f.read().strip()
        else:
            import getpass
            password = getpass.getpass(f"Enter password for wallet '{args.from_wallet}': ")
        
        if not password:
            print("Error: Password is required")
            sys.exit(1)
        
        tx_hash = send_transaction(
            args.from_wallet, 
            args.to_address, 
            args.amount, 
            args.fee, 
            password,
            rpc_url=args.rpc_url
        )
        
        if tx_hash:
            print(f"Transaction hash: {tx_hash}")
        else:
            sys.exit(1)
    
    elif args.command == "list":
        wallets = list_wallets()
        
        if args.format == "json":
            print(json.dumps(wallets, indent=2))
        else:
            print("Wallets:")
            for wallet in wallets:
                print(f"  {wallet['name']}: {wallet['address']}")
    
    elif args.command == "balance":
        balance_info = get_balance(args.name, rpc_url=args.rpc_url)
        if balance_info:
            print(f"Wallet: {balance_info['wallet_name']}")
            print(f"Address: {balance_info['address']}")
            print(f"Balance: {balance_info['balance']} AIT")
            print(f"Nonce: {balance_info['nonce']}")
        else:
            sys.exit(1)
    
    elif args.command == "transactions":
        transactions = get_transactions(args.name, limit=args.limit, rpc_url=args.rpc_url)
        
        if args.format == "json":
            print(json.dumps(transactions, indent=2))
        else:
            print(f"Transactions for {args.name}:")
            for i, tx in enumerate(transactions, 1):
                print(f"  {i}. Hash: {tx.get('hash', 'N/A')}")
                print(f"     Amount: {tx.get('value', 0)} AIT")
                print(f"     Fee: {tx.get('fee', 0)} AIT")
                print(f"     Type: {tx.get('type', 'N/A')}")
                print()
    
    elif args.command == "chain":
        chain_info = get_chain_info(rpc_url=args.rpc_url)
        if chain_info:
            print("Blockchain Information:")
            print(f"  Chain ID: {chain_info.get('chain_id', 'N/A')}")
            print(f"  Supported Chains: {chain_info.get('supported_chains', 'N/A')}")
            print(f"  RPC Version: {chain_info.get('rpc_version', 'N/A')}")
            print(f"  Height: {chain_info.get('height', 'N/A')}")
        else:
            sys.exit(1)
    
    elif args.command == "network":
        network_info = get_network_status(rpc_url=args.rpc_url)
        if network_info:
            print("Network Status:")
            print(f"  Height: {network_info['height']}")
            print(f"  Latest Block: {network_info['hash'][:16]}...")
            print(f"  Chain ID: {network_info['chain_id']}")
            print(f"  RPC Version: {network_info['rpc_version']}")
            print(f"  Timestamp: {network_info['timestamp']}")
        else:
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
