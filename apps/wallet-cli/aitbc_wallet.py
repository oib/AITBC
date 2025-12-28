#!/usr/bin/env python3
"""
AITBC Wallet CLI - Command Line Interface for AITBC Blockchain Wallet
"""

import argparse
import sys
import json
import os
from pathlib import Path
from typing import Optional
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "wallet-daemon" / "src"))

from app.keystore.service import KeystoreService
from app.ledger_mock import SQLiteLedgerAdapter
from app.settings import Settings


class AITBCWallet:
    """AITBC Blockchain Wallet CLI"""
    
    def __init__(self, wallet_dir: str = None):
        self.wallet_dir = Path(wallet_dir or os.path.expanduser("~/.aitbc/wallets"))
        self.wallet_dir.mkdir(parents=True, exist_ok=True)
        self.keystore = KeystoreService()
        self.blockchain_rpc = "http://127.0.0.1:9080"  # Default blockchain node RPC
        
    def _get_wallet_path(self, wallet_id: str) -> Path:
        """Get the path to a wallet file"""
        return self.wallet_dir / f"{wallet_id}.wallet"
    
    def create_wallet(self, wallet_id: str, password: str) -> dict:
        """Create a new wallet"""
        wallet_path = self._get_wallet_path(wallet_id)
        
        if wallet_path.exists():
            return {"error": "Wallet already exists"}
        
        # Generate keypair
        keypair = self.keystore.generate_keypair()
        
        # Store encrypted wallet
        wallet_data = {
            "wallet_id": wallet_id,
            "public_key": keypair["public_key"],
            "encrypted_private_key": keypair["encrypted_private_key"],
            "salt": keypair["salt"]
        }
        
        # Encrypt and save
        self.keystore.save_wallet(wallet_path, wallet_data, password)
        
        return {
            "wallet_id": wallet_id,
            "public_key": keypair["public_key"],
            "status": "created"
        }
    
    def list_wallets(self) -> list:
        """List all wallet addresses"""
        wallets = []
        for wallet_file in self.wallet_dir.glob("*.wallet"):
            try:
                wallet_id = wallet_file.stem
                # Try to read public key without decrypting
                with open(wallet_file, 'rb') as f:
                    # This is simplified - in real implementation, we'd read metadata
                    wallets.append({
                        "wallet_id": wallet_id,
                        "address": f"0x{wallet_id[:8]}...",  # Simplified address format
                        "path": str(wallet_file)
                    })
            except Exception:
                continue
        return wallets
    
    def get_balance(self, wallet_id: str, password: str) -> dict:
        """Get wallet balance from blockchain"""
        # First unlock wallet to get public key
        wallet_path = self._get_wallet_path(wallet_id)
        
        if not wallet_path.exists():
            return {"error": "Wallet not found"}
        
        try:
            wallet_data = self.keystore.load_wallet(wallet_path, password)
            public_key = wallet_data["public_key"]
            
            # Query blockchain for balance
            try:
                with httpx.Client() as client:
                    response = client.get(
                        f"{self.blockchain_rpc}/v1/balances/{public_key}",
                        timeout=5.0
                    )
                    if response.status_code == 200:
                        return response.json()
                    else:
                        return {"error": "Failed to query blockchain", "status": response.status_code}
            except Exception as e:
                return {"error": f"Cannot connect to blockchain: {str(e)}"}
                
        except Exception as e:
            return {"error": f"Failed to unlock wallet: {str(e)}"}
    
    def check_connection(self) -> dict:
        """Check if connected to blockchain"""
        try:
            with httpx.Client() as client:
                # Try to get the latest block
                response = client.get(f"{self.blockchain_rpc}/v1/blocks/head", timeout=5.0)
                if response.status_code == 200:
                    block = response.json()
                    return {
                        "connected": True,
                        "blockchain_url": self.blockchain_rpc,
                        "latest_block": block.get("height", "unknown"),
                        "status": "connected"
                    }
                else:
                    return {
                        "connected": False,
                        "error": f"HTTP {response.status_code}",
                        "status": "disconnected"
                    }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "status": "disconnected"
            }
    
    def send_transaction(self, wallet_id: str, password: str, to_address: str, amount: float) -> dict:
        """Send transaction"""
        wallet_path = self._get_wallet_path(wallet_id)
        
        if not wallet_path.exists():
            return {"error": "Wallet not found"}
        
        try:
            # Unlock wallet
            wallet_data = self.keystore.load_wallet(wallet_path, password)
            private_key = wallet_data["private_key"]
            
            # Create transaction
            transaction = {
                "from": wallet_data["public_key"],
                "to": to_address,
                "amount": amount,
                "nonce": 0  # Would get from blockchain
            }
            
            # Sign transaction
            signature = self.keystore.sign_transaction(private_key, transaction)
            transaction["signature"] = signature
            
            # Send to blockchain
            with httpx.Client() as client:
                response = client.post(
                    f"{self.blockchain_rpc}/v1/transactions",
                    json=transaction,
                    timeout=5.0
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"Failed to send transaction: {response.text}"}
                    
        except Exception as e:
            return {"error": str(e)}


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="AITBC Blockchain Wallet CLI")
    parser.add_argument("--wallet-dir", default=None, help="Wallet directory path")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Create wallet
    create_parser = subparsers.add_parser("create", help="Create a new wallet")
    create_parser.add_argument("wallet_id", help="Wallet identifier")
    create_parser.add_argument("password", help="Wallet password")
    
    # List wallets
    subparsers.add_parser("list", help="List all wallets")
    
    # Get balance
    balance_parser = subparsers.add_parser("balance", help="Get wallet balance")
    balance_parser.add_argument("wallet_id", help="Wallet identifier")
    balance_parser.add_argument("password", help="Wallet password")
    
    # Check connection
    subparsers.add_parser("status", help="Check blockchain connection status")
    
    # Send transaction
    send_parser = subparsers.add_parser("send", help="Send transaction")
    send_parser.add_argument("wallet_id", help="Wallet identifier")
    send_parser.add_argument("password", help="Wallet password")
    send_parser.add_argument("to_address", help="Recipient address")
    send_parser.add_argument("amount", type=float, help="Amount to send")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    wallet = AITBCWallet(args.wallet_dir)
    
    if args.command == "create":
        result = wallet.create_wallet(args.wallet_id, args.password)
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
        else:
            print(f"Wallet created successfully!")
            print(f"Wallet ID: {result['wallet_id']}")
            print(f"Public Key: {result['public_key']}")
    
    elif args.command == "list":
        wallets = wallet.list_wallets()
        if wallets:
            print("Available wallets:")
            for w in wallets:
                print(f"  - {w['wallet_id']}: {w['address']}")
        else:
            print("No wallets found")
    
    elif args.command == "balance":
        result = wallet.get_balance(args.wallet_id, args.password)
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
        else:
            print(f"Balance: {result.get('balance', 'unknown')}")
    
    elif args.command == "status":
        result = wallet.check_connection()
        if result["connected"]:
            print(f"✓ Connected to blockchain at {result['blockchain_url']}")
            print(f"  Latest block: {result['latest_block']}")
        else:
            print(f"✗ Not connected: {result['error']}")
    
    elif args.command == "send":
        result = wallet.send_transaction(args.wallet_id, args.password, args.to_address, args.amount)
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
        else:
            print(f"Transaction sent: {result.get('tx_hash', 'unknown')}")


if __name__ == "__main__":
    main()
