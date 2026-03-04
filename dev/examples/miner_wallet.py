#!/usr/bin/env python3
"""
GPU Provider wallet for managing earnings from mining
"""

import argparse
import json
import os
import sys
from datetime import datetime

# Add parent directory to path to import wallet module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import importlib.util
spec = importlib.util.spec_from_file_location("wallet", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wallet.py"))
wallet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wallet)
AITBCWallet = wallet.AITBCWallet

def main():
    parser = argparse.ArgumentParser(description="GPU Provider Wallet - Manage earnings from mining services")
    parser.add_argument("--wallet", default="miner_wallet.json", help="Wallet file name")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Balance command
    balance_parser = subparsers.add_parser("balance", help="Show balance")
    
    # Address command
    address_parser = subparsers.add_parser("address", help="Show wallet address")
    
    # History command
    history_parser = subparsers.add_parser("history", help="Show transaction history")
    
    # Earn command (receive payment for completed jobs)
    earn_parser = subparsers.add_parser("earn", help="Add earnings from completed job")
    earn_parser.add_argument("amount", type=float, help="Amount earned")
    earn_parser.add_argument("--job", required=True, help="Job ID that was completed")
    earn_parser.add_argument("--desc", default="GPU computation", help="Service description")
    
    # Withdraw command
    withdraw_parser = subparsers.add_parser("withdraw", help="Withdraw AITBC to external wallet")
    withdraw_parser.add_argument("amount", type=float, help="Amount to withdraw")
    withdraw_parser.add_argument("address", help="Destination address")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show mining statistics")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Use miner-specific wallet directory
    wallet_dir = os.path.dirname(os.path.abspath(__file__))
    wallet_path = os.path.join(wallet_dir, args.wallet)
    
    wallet = AITBCWallet(wallet_path)
    
    if args.command == "balance":
        print("⛏️  GPU PROVIDER WALLET")
        print("=" * 40)
        wallet.show_balance()
        
        # Show additional stats
        earnings = sum(t['amount'] for t in wallet.data['transactions'] if t['type'] == 'earn')
        jobs_completed = sum(1 for t in wallet.data['transactions'] if t['type'] == 'earn')
        print(f"\n📊 Mining Stats:")
        print(f"   Total Earned: {earnings} AITBC")
        print(f"   Jobs Completed: {jobs_completed}")
        print(f"   Average per Job: {earnings/jobs_completed if jobs_completed > 0 else 0} AITBC")
    
    elif args.command == "address":
        print(f"⛏️  Miner Address: {wallet.data['address']}")
        print("   Share this address to receive payments")
    
    elif args.command == "history":
        print("⛏️  MINER TRANSACTION HISTORY")
        print("=" * 40)
        wallet.show_history()
    
    elif args.command == "earn":
        print(f"💰 Adding earnings for job {args.job}")
        wallet.add_earnings(args.amount, args.job, args.desc)
    
    elif args.command == "withdraw":
        print(f"💸 Withdrawing {args.amount} AITBC to {args.address}")
        wallet.spend(args.amount, f"Withdrawal to {args.address}")
    
    elif args.command == "stats":
        print("⛏️  MINING STATISTICS")
        print("=" * 40)
        
        transactions = wallet.data['transactions']
        earnings = [t for t in transactions if t['type'] == 'earn']
        spends = [t for t in transactions if t['type'] == 'spend']
        
        total_earned = sum(t['amount'] for t in earnings)
        total_spent = sum(t['amount'] for t in spends)
        
        print(f"💰 Total Earned: {total_earned} AITBC")
        print(f"💸 Total Spent: {total_spent} AITBC")
        print(f"💳 Net Balance: {wallet.data['balance']} AITBC")
        print(f"📊 Jobs Completed: {len(earnings)}")
        
        if earnings:
            print(f"\n📈 Recent Earnings:")
            for earning in earnings[-5:]:
                print(f"   +{earning['amount']} AITBC | Job: {earning.get('job_id', 'N/A')}")

if __name__ == "__main__":
    main()
