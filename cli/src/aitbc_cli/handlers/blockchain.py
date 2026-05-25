"""Blockchain command handlers."""

import json
import os
import sys

import requests
import logging
logger = logging.getLogger(__name__)



def handle_blockchain_info(args, get_chain_info, render_mapping):
    """Handle blockchain info command."""
    chain_info = get_chain_info(rpc_url=args.rpc_url)
    if not chain_info:
        sys.exit(1)
    render_mapping("Blockchain information:", chain_info)


def handle_blockchain_height(args, get_chain_info):
    """Handle blockchain height command."""
    chain_info = get_chain_info(rpc_url=args.rpc_url)
    logger.info(chain_info.get("height", 0) if chain_info else 0)
def handle_blockchain_block(args, default_rpc_url):
    """Handle blockchain block command."""
    if args.number is None:
        logger.error("Error: block number is required")
        sys.exit(1)
    
    rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
    chain_id = getattr(args, 'chain_id', None) or os.getenv('CHAIN_ID', 'ait-mainnet')
    logger.info(f"Querying block #{args.number} from {rpc_url} (chain: {chain_id})...")
    try:
        params = {}
        if chain_id:
            params['chain_id'] = chain_id
        response = requests.get(f"{rpc_url}/rpc/blocks/{args.number}", params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Block #{args.number}:")
            logger.info(f"  Hash: {data.get('hash', 'N/A')}")
            logger.info(f"  Timestamp: {data.get('timestamp', 'N/A')}")
            logger.info(f"  Transactions: {data.get('tx_count', len(data.get('transactions', [])))}")
            logger.info(f"  Miner: {data.get('proposer', 'N/A')}")
        else:
            logger.error(f"Failed to get block: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error getting block: {e}")
        sys.exit(1)


def handle_blockchain_init(args, default_rpc_url):
    """Handle blockchain init command."""
    rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
    logger.info(f"Checking blockchain status on {rpc_url}...")
    try:
        # Check if blockchain is already initialized by checking for genesis block (block 0)
        response = requests.get(f"{rpc_url}/rpc/blocks/0", timeout=10)
        if response.status_code == 200:
            data = response.json()
            logger.info("Blockchain already initialized")
            logger.info(f"Genesis block hash: {data.get('hash', 'N/A')}")
            logger.info(f"Block number: {data.get('number', 0)}")
            if args.force:
                logger.info("Force flag ignored - blockchain already initialized")
        else:
            logger.info(f"Blockchain not initialized or endpoint unavailable: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error checking blockchain status: {e}")
        logger.info("Note: Blockchain may not be initialized or RPC endpoint unavailable")
        sys.exit(1)


def handle_blockchain_genesis(args, default_rpc_url):
    """Handle blockchain genesis command."""
    rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
    
    if args.create:
        logger.info(f"Creating genesis block on {rpc_url}...")
        try:
            # Check if genesis block already exists
            response = requests.get(f"{rpc_url}/rpc/blocks/0", timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.info("Genesis block already exists")
                logger.info(f"Block hash: {data.get('hash', 'N/A')}")
                logger.info(f"Block number: {data.get('number', 0)}")
                logger.info(f"Timestamp: {data.get('timestamp', 'N/A')}")
                logger.info("Skipping genesis block creation")
                return
            else:
                logger.info(f"Cannot create genesis block - endpoint not available: {response.status_code}")
                logger.info("Note: Genesis block creation may not be supported in current RPC implementation")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Error checking genesis block: {e}")
            logger.info("Note: Genesis block creation may not be supported in current RPC implementation")
            sys.exit(1)
    else:
        logger.info(f"Inspecting genesis block on {rpc_url}...")
        try:
            response = requests.get(f"{rpc_url}/rpc/blocks/0", timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.info("Genesis block information:")
                logger.info(f"  Hash: {data.get('hash', 'N/A')}")
                logger.info(f"  Number: {data.get('number', 0)}")
                logger.info(f"  Timestamp: {data.get('timestamp', 'N/A')}")
                logger.info(f"  Miner: {data.get('miner', 'N/A')}")
                logger.info(f"  Reward: {data.get('reward', 'N/A')} AIT")
            else:
                logger.error(f"Failed to get genesis block: {response.status_code}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Error inspecting genesis block: {e}")
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
        logger.error("Error: --file or --json is required")
        sys.exit(1)
    
    # Add chain_id if provided
    if chain_id:
        block_data["chain_id"] = chain_id
    
    logger.info(f"Importing block to {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/importBlock", json=block_data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            logger.info("Block imported successfully")
            render_mapping("Import result:", result)
        else:
            logger.error(f"Import failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error importing block: {e}")
        sys.exit(1)


def handle_blockchain_export(args, default_rpc_url):
    """Handle blockchain export command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    logger.info(f"Exporting chain from {rpc_url}...")
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
                logger.info(f"Chain exported to {args.output}")
            else:
                logger.info(json.dumps(chain_data, indent=2))
        else:
            logger.error(f"Export failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error exporting chain: {e}")
        sys.exit(1)


def handle_blockchain_import_chain(args, default_rpc_url, render_mapping):
    """Handle blockchain import chain command."""
    rpc_url = args.rpc_url or default_rpc_url
    
    if not args.file:
        logger.error("Error: --file is required")
        sys.exit(1)
    
    with open(args.file) as f:
        chain_data = json.load(f)
    
    logger.info(f"Importing chain state to {rpc_url}...")
    try:
        response = requests.post(f"{rpc_url}/rpc/import-chain", json=chain_data, timeout=120)
        if response.status_code == 200:
            result = response.json()
            logger.info("Chain state imported successfully")
            render_mapping("Import result:", result)
        else:
            logger.error(f"Import failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error importing chain state: {e}")
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
    
    logger.info(f"Querying blocks range from {rpc_url}...")
    try:
        response = requests.get(f"{rpc_url}/rpc/blocks-range", params=params, timeout=30)
        if response.status_code == 200:
            blocks_data = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(blocks_data, indent=2))
            else:
                logger.info(f"Blocks range: {args.start or 'head'} to {args.end or 'limit ' + str(args.limit)}")
                if isinstance(blocks_data, list):
                    for block in blocks_data:
                        logger.info(f"  - Block #{block.get('height', 'N/A')}: {block.get('hash', 'N/A')}")
                else:
                    logger.info(json.dumps(blocks_data, indent=2))
        else:
            logger.error(f"Query failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error querying blocks range: {e}")
        sys.exit(1)


def handle_blockchain_transactions(args, default_rpc_url):
    """Handle blockchain transactions command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    logger.info(f"Querying transactions from {rpc_url}...")
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
                logger.info(f"Transactions: {len(transactions)} found")
                for tx in transactions[:args.limit]:
                    logger.info(f"  - Hash: {tx.get('hash', 'N/A')}")
                    logger.info(f"    From: {tx.get('from', 'N/A')}")
                    logger.info(f"    To: {tx.get('to', 'N/A')}")
                    logger.info(f"    Amount: {tx.get('value', 0)} AIT")
            else:
                logger.info(json.dumps(transactions, indent=2))
        else:
            logger.error(f"Query failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error querying transactions: {e}")
        sys.exit(1)


def handle_blockchain_mempool(args, default_rpc_url):
    """Handle blockchain mempool command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)
    
    logger.info(f"Getting pending transactions from {rpc_url}...")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        
        response = requests.get(f"{rpc_url}/rpc/mempool", params=params, timeout=10)
        if response.status_code == 200:
            mempool = response.json()
            if isinstance(mempool, list):
                logger.info(f"Pending transactions: {len(mempool)}")
                for tx in mempool:
                    logger.info(f"  - Hash: {tx.get('hash', 'N/A')}")
                    logger.info(f"    From: {tx.get('from', 'N/A')}")
                    logger.info(f"    Amount: {tx.get('value', 0)} AIT")
            else:
                logger.info(json.dumps(mempool, indent=2))
        else:
            logger.error(f"Query failed: {response.status_code}")
            logger.error(f"Error: {response.text}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error getting mempool: {e}")
        sys.exit(1)
