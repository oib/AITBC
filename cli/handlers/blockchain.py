"""Blockchain command handlers."""

import json
import os
import sys

import requests

from aitbc import get_logger

logger = get_logger(__name__)


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
    chain_id = getattr(args, "chain_id", None) or os.getenv("CHAIN_ID", None)
    print("Querying block #%s from %s (chain: %s)...", args.number, rpc_url, chain_id or "default")
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        response = requests.get(f"{rpc_url}/rpc/blocks/{args.number}", params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print("Block #%s:", args.number)
            print("  Hash: %s", data.get("hash", "N/A"))
            print("  Timestamp: %s", data.get("timestamp", "N/A"))
            print("  Transactions: %s", data.get("tx_count", len(data.get("transactions", []))))
            print("  Miner: %s", data.get("proposer", "N/A"))
        else:
            print("Failed to get block: %s", response.status_code)
            sys.exit(1)
    except Exception as e:
        print("Error getting block: %s", e)
        sys.exit(1)


def handle_blockchain_init(args, default_rpc_url):
    """Handle blockchain init command."""
    rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
    logger.info("Checking blockchain status on %s...", rpc_url)
    try:
        # Check if blockchain is already initialized by checking for genesis block (block 0)
        response = requests.get(f"{rpc_url}/rpc/blocks/0", timeout=10)
        if response.status_code == 200:
            data = response.json()
            logger.info("Blockchain already initialized")
            logger.info("Genesis block hash: %s", data.get("hash", "N/A"))
            logger.info("Block number: %s", data.get("number", 0))
            if args.force:
                logger.info("Force flag ignored - blockchain already initialized")
        else:
            logger.info("Blockchain not initialized or endpoint unavailable: %s", response.status_code)
            sys.exit(1)
    except Exception as e:
        logger.error("Error checking blockchain status: %s", e)
        logger.info("Note: Blockchain may not be initialized or RPC endpoint unavailable")
        sys.exit(1)


def handle_blockchain_genesis(args, default_rpc_url):
    """Handle blockchain genesis command."""
    rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)

    if args.create:
        logger.info("Creating genesis block on %s...", rpc_url)
        try:
            # Check if genesis block already exists
            response = requests.get(f"{rpc_url}/rpc/blocks/0", timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.info("Genesis block already exists")
                logger.info("Block hash: %s", data.get("hash", "N/A"))
                logger.info("Block number: %s", data.get("number", 0))
                logger.info("Timestamp: %s", data.get("timestamp", "N/A"))
                logger.info("Skipping genesis block creation")
                return
            else:
                logger.info("Cannot create genesis block - endpoint not available: %s", response.status_code)
                logger.info("Note: Genesis block creation may not be supported in current RPC implementation")
                sys.exit(1)
        except Exception as e:
            logger.error("Error checking genesis block: %s", e)
            logger.info("Note: Genesis block creation may not be supported in current RPC implementation")
            sys.exit(1)
    else:
        logger.info("Inspecting genesis block on %s...", rpc_url)
        try:
            response = requests.get(f"{rpc_url}/rpc/blocks/0", timeout=10)
            if response.status_code == 200:
                data = response.json()
                logger.info("Genesis block information:")
                logger.info("  Hash: %s", data.get("hash", "N/A"))
                logger.info("  Number: %s", data.get("number", 0))
                logger.info("  Timestamp: %s", data.get("timestamp", "N/A"))
                logger.info("  Miner: %s", data.get("miner", "N/A"))
                logger.info("  Reward: %s AIT", data.get("reward", "N/A"))
            else:
                logger.error("Failed to get genesis block: %s", response.status_code)
                sys.exit(1)
        except Exception as e:
            logger.error("Error inspecting genesis block: %s", e)
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

    logger.info("Importing block to %s...", rpc_url)
    try:
        response = requests.post(f"{rpc_url}/rpc/importBlock", json=block_data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            logger.info("Block imported successfully")
            render_mapping("Import result:", result)
        else:
            logger.error("Import failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            sys.exit(1)
    except Exception as e:
        logger.error("Error importing block: %s", e)
        sys.exit(1)


def handle_blockchain_export(args, default_rpc_url):
    """Handle blockchain export command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    logger.info("Exporting chain from %s...", rpc_url)
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
                logger.info("Chain exported to %s", args.output)
            else:
                logger.info(json.dumps(chain_data, indent=2))
        else:
            logger.error("Export failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            sys.exit(1)
    except Exception as e:
        logger.error("Error exporting chain: %s", e)
        sys.exit(1)


def handle_blockchain_import_chain(args, default_rpc_url, render_mapping):
    """Handle blockchain import chain command."""
    rpc_url = args.rpc_url or default_rpc_url

    if not args.file:
        logger.error("Error: --file is required")
        sys.exit(1)

    with open(args.file) as f:
        chain_data = json.load(f)

    logger.info("Importing chain state to %s...", rpc_url)
    try:
        response = requests.post(f"{rpc_url}/rpc/import-chain", json=chain_data, timeout=120)
        if response.status_code == 200:
            result = response.json()
            logger.info("Chain state imported successfully")
            render_mapping("Import result:", result)
        else:
            logger.error("Import failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            sys.exit(1)
    except Exception as e:
        logger.error("Error importing chain state: %s", e)
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

    logger.info("Querying blocks range from %s...", rpc_url)
    try:
        response = requests.get(f"{rpc_url}/rpc/blocks-range", params=params, timeout=30)
        if response.status_code == 200:
            blocks_data = response.json()
            if output_format(args) == "json":
                logger.info(json.dumps(blocks_data, indent=2))
            else:
                logger.info("Blocks range: %s to %s", args.start or "head", args.end or "limit " + str(args.limit))
                if isinstance(blocks_data, list):
                    for block in blocks_data:
                        logger.info("  - Block #%s: %s", block.get("height", "N/A"), block.get("hash", "N/A"))
                else:
                    logger.info(json.dumps(blocks_data, indent=2))
        else:
            logger.error("Query failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            sys.exit(1)
    except Exception as e:
        logger.error("Error querying blocks range: %s", e)
        sys.exit(1)


def handle_blockchain_transactions(args, default_rpc_url):
    """Handle blockchain transactions command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    logger.info("Querying transactions from %s...", rpc_url)
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
                logger.info("Transactions: %s found", len(transactions))
                for tx in transactions[: args.limit]:
                    logger.info("  - Hash: %s", tx.get("hash", "N/A"))
                    logger.info("    From: %s", tx.get("from", "N/A"))
                    logger.info("    To: %s", tx.get("to", "N/A"))
                    logger.info("    Amount: %s AIT", tx.get("value", 0))
            else:
                logger.info(json.dumps(transactions, indent=2))
        else:
            logger.error("Query failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            sys.exit(1)
    except Exception as e:
        logger.error("Error querying transactions: %s", e)
        sys.exit(1)


def handle_blockchain_mempool(args, default_rpc_url):
    """Handle blockchain mempool command."""
    rpc_url = args.rpc_url or default_rpc_url
    chain_id = getattr(args, "chain_id", None)

    logger.info("Getting pending transactions from %s...", rpc_url)
    try:
        params = {}
        if chain_id:
            params["chain_id"] = chain_id

        response = requests.get(f"{rpc_url}/rpc/mempool", params=params, timeout=10)
        if response.status_code == 200:
            mempool = response.json()
            if isinstance(mempool, list):
                logger.info("Pending transactions: %s", len(mempool))
                for tx in mempool:
                    logger.info("  - Hash: %s", tx.get("hash", "N/A"))
                    logger.info("    From: %s", tx.get("from", "N/A"))
                    logger.info("    Amount: %s AIT", tx.get("value", 0))
            else:
                logger.info(json.dumps(mempool, indent=2))
        else:
            logger.error("Query failed: %s", response.status_code)
            logger.error("Error: %s", response.text)
            sys.exit(1)
    except Exception as e:
        logger.error("Error getting mempool: %s", e)
        sys.exit(1)
