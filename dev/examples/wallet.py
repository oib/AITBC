#!/usr/bin/env python3
"""
AITBC Wallet CLI Tool - Track earnings and manage wallet
"""

import argparse
import json
import os
from datetime import datetime
from typing import Dict, List

class AITBCWallet:
    def __init__(self, wallet_file: str = None):
        if wallet_file is None:
            wallet_file = os.path.expanduser("~/.aitbc_wallet.json")
        
        self.wallet_file = wallet_file
        self.data = self._load_wallet()
    
    def _load_wallet(self) -> dict:
        """Load wallet data from file"""
        if os.path.exists(self.wallet_file):
            try:
                with open(self.wallet_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Create new wallet
        return {
            "address": "aitbc1" + os.urandom(10).hex(),
            "balance": 0.0,
            "transactions": [],
            "created_at": datetime.now().isoformat()
        }
    
    def save(self):
        """Save wallet to file"""
        with open(self.wallet_file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def add_earnings(self, amount: float, job_id: str, description: str = ""):
        """Add earnings from completed job"""
        transaction = {
            "type": "earn",
            "amount": amount,
            "job_id": job_id,
            "description": description or f"Job {job_id}",
            "timestamp": datetime.now().isoformat()
        }
        
        self.data["transactions"].append(transaction)
        self.data["balance"] += amount
        self.save()
        
        print(f"💰 Added {amount} AITBC to wallet")
        print(f"   New balance: {self.data['balance']} AITBC")
    
    def spend(self, amount: float, description: str):
        """Spend AITBC"""
        if self.data["balance"] < amount:
            print(f"❌ Insufficient balance!")
            print(f"   Balance: {self.data['balance']} AITBC")
            print(f"   Needed: {amount} AITBC")
            return False
        
        transaction = {
            "type": "spend",
            "amount": -amount,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
        
        self.data["transactions"].append(transaction)
        self.data["balance"] -= amount
        self.save()
        
        print(f"💸 Spent {amount} AITBC")
        print(f"   Remaining: {self.data['balance']} AITBC")
        return True
    
    def show_balance(self):
        """Show wallet balance"""
        print(f"💳 Wallet Address: {self.data['address']}")
        print(f"💰 Balance: {self.data['balance']} AITBC")
        print(f"📊 Total Transactions: {len(self.data['transactions'])}")
    
    def show_history(self, limit: int = 10):
        """Show transaction history"""
        transactions = self.data["transactions"][-limit:]
        
        if not transactions:
            print("📭 No transactions yet")
            return
        
        print(f"📜 Recent Transactions (last {limit}):")
        print("-" * 60)
        
        for tx in reversed(transactions):
            symbol = "💰" if tx["type"] == "earn" else "💸"
            print(f"{symbol} {tx['amount']:+8.2f} AITBC | {tx.get('description', 'N/A')}")
            print(f"    📅 {tx['timestamp']}")
            if "job_id" in tx:
                print(f"    🆔 Job: {tx['job_id']}")
            print()

def main():
    parser = argparse.ArgumentParser(description="AITBC Wallet CLI")
    parser.add_argument("--wallet", help="Wallet file path")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Balance command
    balance_parser = subparsers.add_parser("balance", help="Show balance")
    
    # History command
    history_parser = subparsers.add_parser("history", help="Show transaction history")
    history_parser.add_argument("--limit", type=int, default=10, help="Number of transactions")
    
    # Earn command
    earn_parser = subparsers.add_parser("earn", help="Add earnings")
    earn_parser.add_argument("amount", type=float, help="Amount earned")
    earn_parser.add_argument("--job", help="Job ID")
    earn_parser.add_argument("--desc", help="Description")
    
    # Spend command
    spend_parser = subparsers.add_parser("spend", help="Spend AITBC")
    spend_parser.add_argument("amount", type=float, help="Amount to spend")
    spend_parser.add_argument("description", help="What you're spending on")
    
    # Address command
    address_parser = subparsers.add_parser("address", help="Show wallet address")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    wallet = AITBCWallet(args.wallet)
    
    if args.command == "balance":
        wallet.show_balance()
    
    elif args.command == "history":
        wallet.show_history(args.limit)
    
    elif args.command == "earn":
        wallet.add_earnings(args.amount, args.job or "unknown", args.desc or "")
    
    elif args.command == "spend":
        wallet.spend(args.amount, args.description)
    
    elif args.command == "address":
        print(f"💳 Wallet Address: {wallet.data['address']}")

if __name__ == "__main__":
    main()
