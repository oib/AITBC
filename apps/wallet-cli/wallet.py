#!/usr/bin/env python3
"""
Simple AITBC Wallet CLI
"""

import argparse
import json
import sys
import os
from pathlib import Path
import httpx
import getpass

def check_blockchain_connection():
    """Check if connected to blockchain"""
    try:
        response = httpx.get("http://127.0.0.1:9080/rpc/head", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            return True, data.get("height", "unknown")
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)

def get_balance(address):
    """Get balance for an address"""
    try:
        response = httpx.get(f"http://127.0.0.1:9080/rpc/getBalance/{address}", timeout=5.0)
        if response.status_code == 200:
            return response.json()
        return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def list_wallets():
    """List local wallets"""
    wallet_dir = Path.home() / ".aitbc" / "wallets"
    wallet_dir.mkdir(parents=True, exist_ok=True)
    
    wallets = []
    for wallet_file in wallet_dir.glob("*.json"):
        try:
            with open(wallet_file, 'r') as f:
                data = json.load(f)
                wallets.append({
                    "id": wallet_file.stem,
                    "address": data.get("address", "unknown"),
                    "public_key": data.get("public_key", "unknown")[:20] + "..."
                })
        except:
            continue
    return wallets

def main():
    parser = argparse.ArgumentParser(description="AITBC Wallet CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Status command
    subparsers.add_parser("status", help="Check blockchain connection")
    
    # List command
    subparsers.add_parser("list", help="List wallets")
    
    # Balance command
    balance_parser = subparsers.add_parser("balance", help="Get balance")
    balance_parser.add_argument("address", help="Wallet address")
    
    args = parser.parse_args()
    
    if args.command == "status":
        connected, info = check_blockchain_connection()
        if connected:
            print(f"✓ Connected to AITBC Blockchain")
            print(f"  Latest block: {info}")
            print(f"  Node: http://127.0.0.1:9080")
        else:
            print(f"✗ Not connected: {info}")
    
    elif args.command == "list":
        wallets = list_wallets()
        if wallets:
            print("Local wallets:")
            for w in wallets:
                print(f"  {w['id']}: {w['address']}")
        else:
            print("No wallets found")
            print(f"Wallet directory: {Path.home() / '.aitbc' / 'wallets'}")
    
    elif args.command == "balance":
        result = get_balance(args.address)
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            balance = result.get("balance", 0)
            print(f"Balance: {balance} AITBC")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
