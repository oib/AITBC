#!/usr/bin/env python3
"""
Client wallet for managing AITBC tokens
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
    parser = argparse.ArgumentParser(description="Client Wallet - Manage AITBC for paying for GPU services")
    parser.add_argument("--wallet", default="client_wallet.json", help="Wallet file name")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Balance command
    balance_parser = subparsers.add_parser("balance", help="Show balance")
    
    # Address command
    address_parser = subparsers.add_parser("address", help="Show wallet address")
    
    # History command
    history_parser = subparsers.add_parser("history", help="Show transaction history")
    
    # Send command (pay for services)
    send_parser = subparsers.add_parser("send", help="Send AITBC to GPU provider")
    send_parser.add_argument("amount", type=float, help="Amount to send")
    send_parser.add_argument("to", help="Recipient address")
    send_parser.add_argument("description", help="Payment description")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Use client-specific wallet directory
    wallet_dir = os.path.dirname(os.path.abspath(__file__))
    wallet_path = os.path.join(wallet_dir, args.wallet)
    
    wallet = AITBCWallet(wallet_path)
    
    if args.command == "balance":
        print("💼 CLIENT WALLET")
        print("=" * 40)
        wallet.show_balance()
        print("\n💡 Use 'send' to pay for GPU services")
    
    elif args.command == "address":
        print(f"💼 Client Address: {wallet.data['address']}")
        print("   Share this address to receive AITBC")
    
    elif args.command == "history":
        print("💼 CLIENT TRANSACTION HISTORY")
        print("=" * 40)
        wallet.show_history()
    
    elif args.command == "send":
        print(f"💸 Sending {args.amount} AITBC to {args.to}")
        print(f"   For: {args.description}")
        wallet.spend(args.amount, args.description)

if __name__ == "__main__":
    main()
