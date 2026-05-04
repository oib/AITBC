#!/usr/bin/env python3
"""
AITBC Advanced CLI - Long-term implementation with full features
"""

import json
import sys
import os
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests

# Default paths
DEFAULT_KEYSTORE_DIR = Path("/var/lib/aitbc/keystore")
DEFAULT_RPC_URL = "http://localhost:8005"

# Note: Legacy simple_wallet.py module has been replaced by unified CLI
# This file should use the new nested CLI structure via subprocess calls

def batch_transactions(transactions_file: str, password: str, rpc_url: str = DEFAULT_RPC_URL):
    """Process batch transactions from JSON file"""
    try:
        with open(transactions_file) as f:
            transactions = json.load(f)
        
        results = []
        for i, tx in enumerate(transactions, 1):
            print(f"Processing transaction {i}/{len(transactions)}...")
            
            result = send_transaction(
                tx['from_wallet'],
                tx['to_address'],
                tx['amount'],
                tx.get('fee', 10.0),
                password,
                rpc_url
            )
            
            results.append({
                'transaction': tx,
                'hash': result,
                'success': result is not None
            })
            
            if result:
                print(f"✅ Success: {result}")
            else:
                print(f"❌ Failed")
        
        # Summary
        successful = sum(1 for r in results if r['success'])
        print(f"\nBatch Summary: {successful}/{len(transactions)} successful")
        
        return results
    except Exception as e:
        print(f"Error processing batch: {e}")
        return []

def mining_operations(operation: str, wallet_name: str = None, threads: int = 1, rpc_url: str = DEFAULT_RPC_URL):
    """Handle mining operations"""
    if operation == "start":
        if not wallet_name:
            print("Error: Wallet name required for mining start")
            return False
        
        # Get wallet address
        wallet_info = get_balance(wallet_name)
        if not wallet_info:
            return False
        
        mining_config = {
            "miner_address": wallet_info['address'],
            "threads": threads,
            "enabled": True
        }
        
        try:
            response = requests.post(f"{rpc_url}/rpc/mining/start", json=mining_config)
            if response.status_code == 200:
                print(f"Mining started with wallet '{wallet_name}'")
                print(f"Address: {wallet_info['address']}")
                print(f"Threads: {threads}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    elif operation == "stop":
        try:
            response = requests.post(f"{rpc_url}/rpc/mining/stop")
            if response.status_code == 200:
                print("Mining stopped")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    elif operation == "status":
        try:
            response = requests.get(f"{rpc_url}/rpc/mining/status")
            if response.status_code == 200:
                status = response.json()
                print("Mining Status:")
                print(f"  Active: {status.get('active', False)}")
                print(f"  Threads: {status.get('threads', 0)}")
                print(f"  Hash Rate: {status.get('hash_rate', 0)} H/s")
                print(f"  Blocks Mined: {status.get('blocks_mined', 0)}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False

def marketplace_operations(operation: str, wallet_name: str = None, item_type: str = None,
                         price: float = None, description: str = None, password: str = None,
                         rpc_url: str = DEFAULT_RPC_URL):
    """Handle marketplace operations"""
    if operation == "list":
        try:
            response = requests.get(f"{rpc_url}/rpc/marketplace/listings")
            if response.status_code == 200:
                listings = response.json().get("listings", [])
                print(f"Marketplace Listings ({len(listings)} items):")
                for i, item in enumerate(listings, 1):
                    print(f"  {i}. {item.get('item_type', 'Unknown')} - {item.get('price', 0)} AIT")
                    print(f"     {item.get('description', 'No description')}")
                    print(f"     Seller: {item.get('seller_address', 'Unknown')}")
                    print()
                return listings
            else:
                print(f"Error: {response.text}")
                return []
        except Exception as e:
            print(f"Error: {e}")
            return []
    
    elif operation == "create":
        if not all([wallet_name, item_type, price is not None, description, password]):
            print("Error: All parameters required for marketplace creation")
            return None
        
        # Get wallet address
        wallet_info = get_balance(wallet_name)
        if not wallet_info:
            return None
        
        listing_data = {
            "seller_address": wallet_info['address'],
            "item_type": item_type,
            "price": price,
            "description": description
        }
        
        try:
            response = requests.post(f"{rpc_url}/rpc/marketplace/create", json=listing_data)
            if response.status_code == 200:
                result = response.json()
                listing_id = result.get("listing_id")
                print(f"Marketplace listing created")
                print(f"Listing ID: {listing_id}")
                print(f"Item: {item_type}")
                print(f"Price: {price} AIT")
                return listing_id
            else:
                print(f"Error: {response.text}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None

def ai_operations(operation: str, wallet_name: str = None, job_type: str = None,
                 prompt: str = None, payment: float = None, password: str = None,
                 rpc_url: str = DEFAULT_RPC_URL):
    """Handle AI operations"""
    if operation == "submit":
        if not all([wallet_name, job_type, prompt, payment is not None, password]):
            print("Error: All parameters required for AI job submission")
            return None
        
        # Get wallet address
        wallet_info = get_balance(wallet_name)
        if not wallet_info:
            return None
        
        job_data = {
            "client_address": wallet_info['address'],
            "job_type": job_type,
            "prompt": prompt,
            "payment": payment
        }
        
        try:
            response = requests.post(f"{rpc_url}/rpc/ai/submit", json=job_data)
            if response.status_code == 200:
                result = response.json()
                job_id = result.get("job_id")
                print(f"AI job submitted")
                print(f"Job ID: {job_id}")
                print(f"Type: {job_type}")
                print(f"Payment: {payment} AIT")
                return job_id
            else:
                print(f"Error: {response.text}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description="AITBC Advanced CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Batch operations
    batch_parser = subparsers.add_parser("batch", help="Process batch transactions")
    batch_parser.add_argument("--file", required=True, help="JSON file with transactions")
    batch_parser.add_argument("--password", required=True, help="Wallet password")
    batch_parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="RPC URL")
    
    # Mining operations
    mine_parser = subparsers.add_parser("mine", help="Mining operations")
    mine_subparsers = mine_parser.add_subparsers(dest="mine_action", help="Mining actions")
    
    mine_start_parser = mine_subparsers.add_parser("start", help="Start mining")
    mine_start_parser.add_argument("--wallet", required=True, help="Mining wallet name")
    mine_start_parser.add_argument("--threads", type=int, default=1, help="Number of threads")
    
    mine_stop_parser = mine_subparsers.add_parser("stop", help="Stop mining")
    mine_status_parser = mine_subparsers.add_parser("status", help="Get mining status")
    
    # Marketplace operations
    market_parser = subparsers.add_parser("market", help="Marketplace operations")
    market_subparsers = market_parser.add_subparsers(dest="market_action", help="Marketplace actions")
    
    market_list_parser = market_subparsers.add_parser("list", help="List marketplace items")
    market_create_parser = market_subparsers.add_parser("create", help="Create marketplace listing")
    market_create_parser.add_argument("--wallet", required=True, help="Seller wallet name")
    market_create_parser.add_argument("--type", required=True, help="Item type")
    market_create_parser.add_argument("--price", type=float, required=True, help="Price in AIT")
    market_create_parser.add_argument("--description", required=True, help="Item description")
    market_create_parser.add_argument("--password", required=True, help="Wallet password")
    
    # AI operations
    ai_parser = subparsers.add_parser("ai", help="AI operations")
    ai_subparsers = ai_parser.add_subparsers(dest="ai_action", help="AI actions")
    
    ai_submit_parser = ai_subparsers.add_parser("submit", help="Submit AI job")
    ai_submit_parser.add_argument("--wallet", required=True, help="Client wallet name")
    ai_submit_parser.add_argument("--type", required=True, help="Job type")
    ai_submit_parser.add_argument("--prompt", required=True, help="AI prompt")
    ai_submit_parser.add_argument("--payment", type=float, required=True, help="Payment in AIT")
    ai_submit_parser.add_argument("--password", required=True, help="Wallet password")
    
    args = parser.parse_args()
    
    if args.command == "batch":
        batch_transactions(args.file, args.password, args.rpc_url)
    
    elif args.command == "mine":
        if args.mine_action == "start":
            mining_operations("start", args.wallet, args.threads)
        elif args.mine_action == "stop":
            mining_operations("stop")
        elif args.mine_action == "status":
            mining_operations("status")
        else:
            mine_parser.print_help()
    
    elif args.command == "market":
        if args.market_action == "list":
            marketplace_operations("list")
        elif args.market_action == "create":
            marketplace_operations("create", args.wallet, args.type, args.price, args.description, args.password)
        else:
            market_parser.print_help()
    
    elif args.command == "ai":
        if args.ai_action == "submit":
            ai_operations("submit", args.wallet, args.type, args.prompt, args.payment, args.password)
        else:
            ai_parser.print_help()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
