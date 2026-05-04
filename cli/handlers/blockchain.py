"""Blockchain command handlers."""

import json
import os
import sys

import requests


def handle_blockchain_info(args, get_chain_info, render_mapping):
    """Handle blockchain info command."""
    chain_info = get_chain_info(rpc_url=args.rpc_url)
    if not chain_info:
        sys.exit(1)
    render_mapping("Blockchain information:", chain_info)


def handle_blockchain_height(args, get_chain_info):
    """Handle blockchain height command."""
    chain_info = get_chain_info(rpc_url=args.rpc_url)
    print(chain_info.get("height", 0) if chain_info else 0)


def handle_blockchain_block(args, default_rpc_url):
    """Handle blockchain block command."""
    if args.number is None:
        print("Error: block number is required")
        sys.exit(1)
    
    rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
    print(f"Querying block #{args.number} from {rpc_url}...")
    
    try:
        response = requests.get(f"{rpc_url}/blocks/{args.number}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"Block #{args.number}:")
            print(f"  Hash: {data.get('hash', 'N/A')}")
            print(f"  Timestamp: {data.get('timestamp', 'N/A')}")
            print(f"  Transactions: {data.get('transaction_count', len(data.get('transactions', [])))}")
            print(f"  Miner: {data.get('miner', 'N/A')}")
        else:
            print(f"Failed to get block: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting block: {e}")
        sys.exit(1)


def handle_blockchain_init(args, default_rpc_url):
    """Handle blockchain init command."""
    rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
    print(f"Checking blockchain status on {rpc_url}...")
    
    try:
        # Check if blockchain is already initialized by checking for genesis block (block 0)
        response = requests.get(f"{rpc_url}/blocks/0", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print("Blockchain already initialized")
            print(f"Genesis block hash: {data.get('hash', 'N/A')}")
            print(f"Block number: {data.get('number', 0)}")
            if args.force:
                print("Force flag ignored - blockchain already initialized")
        else:
            print(f"Blockchain not initialized or endpoint unavailable: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking blockchain status: {e}")
        print("Note: Blockchain may not be initialized or RPC endpoint unavailable")
        sys.exit(1)


def handle_blockchain_genesis(args, default_rpc_url):
    """Handle blockchain genesis command."""
    rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
    
    if args.create:
        print(f"Creating genesis block on {rpc_url}...")
        try:
            # Check if genesis block already exists
            response = requests.get(f"{rpc_url}/blocks/0", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print("Genesis block already exists")
                print(f"Block hash: {data.get('hash', 'N/A')}")
                print(f"Block number: {data.get('number', 0)}")
                print(f"Timestamp: {data.get('timestamp', 'N/A')}")
                print("Skipping genesis block creation")
                return
            else:
                print(f"Cannot create genesis block - endpoint not available: {response.status_code}")
                print("Note: Genesis block creation may not be supported in current RPC implementation")
                sys.exit(1)
        except Exception as e:
            print(f"Error checking genesis block: {e}")
            print("Note: Genesis block creation may not be supported in current RPC implementation")
            sys.exit(1)
    else:
        print(f"Inspecting genesis block on {rpc_url}...")
        try:
            response = requests.get(f"{rpc_url}/blocks/0", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print("Genesis block information:")
                print(f"  Hash: {data.get('hash', 'N/A')}")
                print(f"  Number: {data.get('number', 0)}")
                print(f"  Timestamp: {data.get('timestamp', 'N/A')}")
                print(f"  Miner: {data.get('miner', 'N/A')}")
                print(f"  Reward: {data.get('reward', 'N/A')} AIT")
            else:
                print(f"Failed to get genesis block: {response.status_code}")
                sys.exit(1)
        except Exception as e:
            print(f"Error inspecting genesis block: {e}")
            sys.exit(1)


def handle_blockchain_import(args, default_rpc_url, render_mapping):
    """Handle blockchain import command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    # Load block data from file or stdin
    if args.file:
        with open(args.file) as f:
            block_data = json.load(f)
    elif args.json:
        block_data = json.loads(args.json)
    else:
        print("Error: --file or --json is required")
        sys.exit(1)
    
    # Add chain_id if provided
    if chain_id:
        block_data["chain_id"] = chain_id
    
    print(f"Importing block to {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/importBlock", json=block_data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print("Block imported successfully")
            render_mapping("Import result:", result)
        else:
            print(f"Import failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error importing block: {e}")
        sys.exit(1)


def handle_blockchain_export(args, default_rpc_url):
    """Handle blockchain export command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    print(f"Exporting chain from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        
        response = requests.get(f"{rpc_url}/rpc/export-chain", params=params, timeout=60)
        if response.status_code == 200:
            chain_data = response.json()
            if args.output:
                with open(args.output, "w") as f:
                    json.dump(chain_data, f, indent=2)
                print(f"Chain exported to {args.output}")
            else:
                print(json.dumps(chain_data, indent=2))
        else:
            print(f"Export failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error exporting chain: {e}")
        sys.exit(1)


def handle_blockchain_import_chain(args, default_rpc_url, render_mapping):
    """Handle blockchain import chain command."""
    rpc_url = args.rpc_url or default_rpc_url
    
    if not args.file:
        print("Error: --file is required")
        sys.exit(1)
    
    with open(args.file) as f:
        chain_data = json.load(f)
    
    print(f"Importing chain state to {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/import-chain", json=chain_data, timeout=120)
        if response.status_code == 200:
            result = response.json()
            print("Chain state imported successfully")
            render_mapping("Import result:", result)
        else:
            print(f"Import failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error importing chain state: {e}")
        sys.exit(1)


def handle_blockchain_blocks_range(args, default_rpc_url, output_format):
    """Handle blockchain blocks range command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    params = {"limit": args.limit}
    if args.start:
        params["from_height"] = args.start
    if args.end:
        params["to_height"] = args.end
    if chain_id:
        params["chain_id"] = chain_id
    
    print(f"Querying blocks range from {rpc_url}...")
    try:
        response = requests.get(f"{rpc_url}/rpc/blocks-range", params=params, timeout=30)
        if response.status_code == 200:
            blocks_data = response.json()
            if output_format(args) == "json":
                print(json.dumps(blocks_data, indent=2))
            else:
                print(f"Blocks range: {args.start or 'head'} to {args.end or 'limit ' + str(args.limit)}")
                if isinstance(blocks_data, list):
                    for block in blocks_data:
                        print(f"  - Block #{block.get('height', 'N/A')}: {block.get('hash', 'N/A')}")
                else:
                    print(json.dumps(blocks_data, indent=2))
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error querying blocks range: {e}")
        sys.exit(1)


def handle_blockchain_transactions(args, default_rpc_url):
    """Handle blockchain transactions command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    print(f"Querying transactions from {rpc_url}...")
    try:
        params = {}
        if args.address:
            params["address"] = args.address
        if chain_id:
            params["chain_id"] = chain_id
        if args.limit:
            params["limit"] = args.limit
        if args.offset:
            params["offset"] = args.offset
        
        response = requests.get(f"{rpc_url}/rpc/transactions", params=params, timeout=10)
        if response.status_code == 200:
            transactions = response.json()
            if isinstance(transactions, list):
                print(f"Transactions: {len(transactions)} found")
                for tx in transactions[:args.limit]:
                    print(f"  - Hash: {tx.get('hash', 'N/A')}")
                    print(f"    From: {tx.get('from', 'N/A')}")
                    print(f"    To: {tx.get('to', 'N/A')}")
                    print(f"    Amount: {tx.get('value', 0)} AIT")
            else:
                print(json.dumps(transactions, indent=2))
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error querying transactions: {e}")
        sys.exit(1)


def handle_blockchain_mempool(args, default_rpc_url):
    """Handle blockchain mempool command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    print(f"Getting pending transactions from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        
        response = requests.get(f"{rpc_url}/rpc/mempool", params=params, timeout=10)
        if response.status_code == 200:
            mempool = response.json()
            if isinstance(mempool, list):
                print(f"Pending transactions: {len(mempool)}")
                for tx in mempool:
                    print(f"  - Hash: {tx.get('hash', 'N/A')}")
                    print(f"    From: {tx.get('from', 'N/A')}")
                    print(f"    Amount: {tx.get('value', 0)} AIT")
            else:
                print(json.dumps(mempool, indent=2))
        else:
            print(f"Query failed: {response.status_code}")
            print(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error getting mempool: {e}")
        sys.exit(1)
