#!/usr/bin/env python3
"""
AITBC Enterprise CLI - Long-term implementation with full features
Standalone version with all advanced operations
"""

import argparse
import getpass
import json

import click
import requests

from aitbc.utils.paths import get_keystore_path

# Default paths
DEFAULT_KEYSTORE_DIR = get_keystore_path()
DEFAULT_RPC_URL = "http://localhost:8006"

def get_password(password_arg: str = None, password_file: str = None) -> str:
    """Get password from various sources"""
    if password_arg:
        return password_arg
    elif password_file:
        with open(password_file) as f:
            return f.read().strip()
    else:
        return getpass.getpass("Enter password: ")

def batch_transactions(transactions_file: str, password: str, rpc_url: str = DEFAULT_RPC_URL):
    """Process batch transactions from JSON file"""
    try:
        with open(transactions_file) as f:
            transactions = json.load(f)

        click.echo(f"Processing {len(transactions)} transactions...")
        results = []

        for i, tx in enumerate(transactions, 1):
            click.echo(f"Transaction {i}/{len(transactions)}: {tx['from_wallet']} → {tx['to_address']} ({tx['amount']} AIT)")
            # Create transaction
            transaction = {
                "sender": tx['from_wallet'],
                "recipient": tx['to_address'],
                "value": int(tx['amount']),
                "fee": int(tx.get('fee', 10.0)),
                "nonce": tx.get('nonce', 0),
                "type": "transfer",
                "payload": {}
            }

            try:
                response = requests.post(f"{rpc_url}/rpc/sendTx", json=transaction)
                if response.status_code == 200:
                    result = response.json()
                    tx_hash = result.get("hash")
                    results.append({
                        'transaction': tx,
                        'hash': tx_hash,
                        'success': tx_hash is not None
                    })
                    click.echo(f"  ✅ Success: {tx_hash}")
                else:
                    click.echo(f"  ❌ Failed: {response.text}")
                    results.append({
                        'transaction': tx,
                        'hash': None,
                        'success': False
                    })
            except Exception as e:
                click.echo(f"  ❌ Error: {e}")
                results.append({
                    'transaction': tx,
                    'hash': None,
                    'success': False,
                    'error': str(e)
                })

        # Summary
        successful = sum(1 for r in results if r['success'])
        click.echo(f"\n📊 Batch Summary: {successful}/{len(transactions)} successful")
        # Save results
        results_file = transactions_file.replace('.json', '_results.json')
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        click.echo(f"Results saved to: {results_file}")
        return results
    except Exception as e:
        click.echo(f"Error processing batch: {e}")
        return []

def mining_operations(operation: str, wallet_name: str = None, threads: int = 1, rpc_url: str = DEFAULT_RPC_URL):
    """Handle mining operations"""
    if operation == "start":
        if not wallet_name:
            click.echo("Error: Wallet name required for mining start")
            return False

        click.echo(f"Starting mining with wallet '{wallet_name}' using {threads} threads...")
        mining_config = {
            "proposer_address": wallet_name,  # Fixed field name for PoA
            "threads": threads
        }

        try:
            response = requests.post(f"{rpc_url}/rpc/mining/start", json=mining_config)
            if response.status_code == 200:
                result = response.json()
                click.echo("✅ Mining started successfully")
                click.echo(f"   Wallet: {wallet_name}")
                click.echo(f"   Threads: {threads}")
                click.echo(f"   Status: {result.get('status', 'started')}")
                return True
            else:
                click.echo(f"❌ Error starting mining: {response.text}")
                return False
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            return False

    elif operation == "stop":
        click.echo("Stopping mining...")
        try:
            response = requests.post(f"{rpc_url}/rpc/mining/stop", timeout=30)
            if response.status_code == 200:
                result = response.json()
                click.echo("✅ Mining stopped")
                click.echo(f"   Status: {result.get('status', 'stopped')}")
                return True
            else:
                click.echo(f"❌ Error stopping mining: {response.text}")
                return False
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            return False

    elif operation == "status":
        click.echo("Getting mining status...")
        try:
            response = requests.get(f"{rpc_url}/rpc/mining/status", timeout=30)
            if response.status_code == 200:
                status = response.json()
                click.echo("⛏️  Mining Status:")
                click.echo(f"   Active: {'✅ Yes' if status.get('active', False) else '❌ No'}")
                click.echo(f"   Threads: {status.get('threads', 0)}")
                click.echo(f"   Hash Rate: {status.get('hash_rate', 0):.2f} H/s")
                click.echo(f"   Blocks Mined: {status.get('blocks_mined', 0)}")
                click.echo(f"   Mining Address: {status.get('miner_address', 'N/A')}")
                return True
            else:
                click.echo(f"❌ Error getting status: {response.text}")
                return False
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            return False

def marketplace_operations(operation: str, wallet_name: str = None, item_type: str = None,
                         price: float = None, description: str = None, password: str = None,
                         rpc_url: str = DEFAULT_RPC_URL):
    """Handle marketplace operations"""
    if operation == "list":
        click.echo("Getting marketplace listings...")
        try:
            response = requests.get(f"{rpc_url}/rpc/marketplace/listings", timeout=30)
            if response.status_code == 200:
                listings = response.json().get("listings", [])
                click.echo(f"🏪 Marketplace Listings ({len(listings)} items):")
                if not listings:
                    click.echo("   No listings found")
                else:
                    for i, item in enumerate(listings, 1):
                        click.echo(f"   {i}. {item.get('item_type', 'Unknown')} - {item.get('price', 0)} AIT")
                        click.echo(f"      {item.get('description', 'No description')[:50]}...")
                        click.echo(f"      Seller: {item.get('seller_address', 'Unknown')[:16]}...")
                        click.echo("")
                return listings
            else:
                click.echo(f"❌ Error: {response.text}")
                return []
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            return []

    elif operation == "create":
        if not all([wallet_name, item_type, price is not None, description]):
            click.echo("❌ Error: All parameters required for marketplace creation")
            return None

        click.echo("Creating marketplace listing...")
        click.echo(f"   Item: {item_type}")
        click.echo(f"   Price: {price} AIT")
        click.echo(f"   Description: {description[:50]}...")
        listing_data = {
            "seller_address": wallet_name,  # Simplified for demo
            "item_type": item_type,
            "price": price,
            "description": description
        }

        try:
            response = requests.post(f"{rpc_url}/rpc/marketplace/create", json=listing_data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                listing_id = result.get("listing_id")
                click.echo("✅ Marketplace listing created")
                click.echo(f"   Listing ID: {listing_id}")
                click.echo(f"   Item: {item_type}")
                click.echo(f"   Price: {price} AIT")
                return listing_id
            else:
                click.echo(f"❌ Error creating listing: {response.text}")
                return None
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            return None

def ai_operations(operation: str, wallet_name: str = None, job_type: str = None,
                 prompt: str = None, payment: float = None, password: str = None,
                 rpc_url: str = DEFAULT_RPC_URL):
    """Handle AI operations"""
    if operation == "submit":
        if not all([wallet_name, job_type, prompt, payment is not None]):
            click.echo("❌ Error: All parameters required for AI job submission")
            return None

        click.echo("Submitting AI job...")
        click.echo(f"   Type: {job_type}")
        click.echo(f"   Payment: {payment} AIT")
        click.echo(f"   Prompt: {prompt[:50]}...")
        job_data = {
            "wallet_address": wallet_name,  # Fixed field name
            "job_type": job_type,
            "prompt": prompt,
            "payment": payment
        }

        try:
            response = requests.post(f"{rpc_url}/rpc/ai/submit", json=job_data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                job_id = result.get("job_id")
                click.echo("✅ AI job submitted")
                click.echo(f"   Job ID: {job_id}")
                click.echo(f"   Type: {job_type}")
                click.echo(f"   Payment: {payment} AIT")
                click.echo(f"   Status: {result.get('status', 'queued')}")
                return job_id
            else:
                click.echo(f"❌ Error submitting job: {response.text}")
                return None
        except Exception as e:
            click.echo(f"❌ Error: {e}")
            return None

def create_sample_batch_file():
    """Create a sample batch transaction file"""
    sample_transactions = [
        {
            "from_wallet": "aitbc1genesis",
            "to_address": "ait1abc123def456...",
            "amount": 100,
            "fee": 10,
            "nonce": 0
        },
        {
            "from_wallet": "aitbc1genesis",
            "to_address": "ait1def456abc789...",
            "amount": 200,
            "fee": 10,
            "nonce": 1
        }
    ]

    with open("sample_batch.json", "w") as f:
        json.dump(sample_transactions, f, indent=2)

    click.echo("📝 Sample batch file created: sample_batch.json")
    click.echo("Edit this file with your actual transactions and run:")
    click.echo("python /opt/aitbc/cli/advanced_wallet.py batch --file sample_batch.json --password <password>")
def main():
    parser = argparse.ArgumentParser(description="AITBC Enterprise CLI - Advanced Operations")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Batch operations
    batch_parser = subparsers.add_parser("batch", help="Process batch transactions")
    batch_parser.add_argument("--file", required=True, help="JSON file with transactions")
    batch_parser.add_argument("--password", help="Wallet password")
    batch_parser.add_argument("--password-file", help="File containing wallet password")
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
    market_create_parser.add_argument("--password", help="Wallet password")
    market_create_parser.add_argument("--password-file", help="File containing wallet password")

    # AI operations
    ai_parser = subparsers.add_parser("ai", help="AI operations")
    ai_subparsers = ai_parser.add_subparsers(dest="ai_action", help="AI actions")

    ai_submit_parser = ai_subparsers.add_parser("submit", help="Submit AI job")
    ai_submit_parser.add_argument("--wallet", required=True, help="Client wallet name")
    ai_submit_parser.add_argument("--type", required=True, help="Job type")
    ai_submit_parser.add_argument("--prompt", required=True, help="AI prompt")
    ai_submit_parser.add_argument("--payment", type=float, required=True, help="Payment in AIT")
    ai_submit_parser.add_argument("--password", help="Wallet password")
    ai_submit_parser.add_argument("--password-file", help="File containing wallet password")

    # Utility commands
    sample_parser = subparsers.add_parser("sample", help="Create sample batch file")

    args = parser.parse_args()

    if args.command == "batch":
        password = get_password(args.password, args.password_file)
        batch_transactions(args.file, password, args.rpc_url)

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
            password = get_password(args.password, args.password_file)
            marketplace_operations("create", args.wallet, args.type, args.price, args.description, password)
        else:
            market_parser.print_help()

    elif args.command == "ai":
        if args.ai_action == "submit":
            password = get_password(args.password, args.password_file)
            ai_operations("submit", args.wallet, args.type, args.prompt, args.payment, password)
        else:
            ai_parser.print_help()

    elif args.command == "sample":
        create_sample_batch_file()

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
