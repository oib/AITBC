"""Blockchain command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        blockchain_parser = subparsers.add_parser("blockchain", help="Blockchain state and block inspection")
        blockchain_parser.set_defaults(handler=ctx.handle_blockchain_info, rpc_url=ctx.default_rpc_url)
        blockchain_subparsers = blockchain_parser.add_subparsers(dest="blockchain_action")
    
        blockchain_info_parser = blockchain_subparsers.add_parser("info", help="Show chain information")
        blockchain_info_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_info_parser.set_defaults(handler=ctx.handle_blockchain_info)
    
        blockchain_height_parser = blockchain_subparsers.add_parser("height", help="Show current height")
        blockchain_height_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_height_parser.set_defaults(handler=ctx.handle_blockchain_height)
    
        blockchain_block_parser = blockchain_subparsers.add_parser("block", help="Inspect a block")
        blockchain_block_parser.add_argument("number", nargs="?", type=int)
        blockchain_block_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_block_parser.set_defaults(handler=ctx.handle_blockchain_block)
    
        blockchain_init_parser = blockchain_subparsers.add_parser("init", help="Initialize blockchain with genesis block")
        blockchain_init_parser.add_argument("--force", action="store_true", help="Force reinitialization")
        blockchain_init_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_init_parser.set_defaults(handler=ctx.handle_blockchain_init)
    
        blockchain_genesis_parser = blockchain_subparsers.add_parser("genesis", help="Create or inspect genesis block")
        blockchain_genesis_parser.add_argument("--create", action="store_true", help="Create new genesis block")
        blockchain_genesis_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_genesis_parser.set_defaults(handler=ctx.handle_blockchain_genesis)
    
        blockchain_import_parser = blockchain_subparsers.add_parser("import", help="Import a block")
        blockchain_import_parser.add_argument("--file", help="Block data file")
        blockchain_import_parser.add_argument("--json", help="Block data as JSON string")
        blockchain_import_parser.add_argument("--chain-id", help="Chain ID for the block")
        blockchain_import_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_import_parser.set_defaults(handler=ctx.handle_blockchain_import)
    
        blockchain_export_parser = blockchain_subparsers.add_parser("export", help="Export full chain")
        blockchain_export_parser.add_argument("--output", help="Output file")
        blockchain_export_parser.add_argument("--chain-id", help="Chain ID to export")
        blockchain_export_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_export_parser.set_defaults(handler=ctx.handle_blockchain_export)
    
        blockchain_import_chain_parser = blockchain_subparsers.add_parser("import-chain", help="Import chain state")
        blockchain_import_chain_parser.add_argument("--file", required=True, help="Chain state file")
        blockchain_import_chain_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_import_chain_parser.set_defaults(handler=ctx.handle_blockchain_import_chain)
    
        blockchain_blocks_range_parser = blockchain_subparsers.add_parser("blocks-range", help="Get blocks in height range")
        blockchain_blocks_range_parser.add_argument("--start", type=int, help="Start height")
        blockchain_blocks_range_parser.add_argument("--end", type=int, help="End height")
        blockchain_blocks_range_parser.add_argument("--limit", type=int, default=10, help="Limit number of blocks")
        blockchain_blocks_range_parser.add_argument("--chain-id", help="Chain ID")
        blockchain_blocks_range_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_blocks_range_parser.set_defaults(handler=ctx.handle_blockchain_blocks_range)
    
        account_parser = subparsers.add_parser("account", help="Account information")
        account_parser.set_defaults(handler=lambda parsed, parser=account_parser: parser.print_help())
        account_subparsers = account_parser.add_subparsers(dest="account_action")
    
        account_get_parser = account_subparsers.add_parser("get", help="Get account information")
        account_get_parser.add_argument("--address", required=True, help="Account address")
        account_get_parser.add_argument("--chain-id", help="Chain ID")
        account_get_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        account_get_parser.set_defaults(handler=ctx.handle_account_get)
    
        blockchain_transactions_parser = blockchain_subparsers.add_parser("transactions", help="Query transactions")
        blockchain_transactions_parser.add_argument("--address", help="Filter by address")
        blockchain_transactions_parser.add_argument("--limit", type=int, default=10)
        blockchain_transactions_parser.add_argument("--offset", type=int, default=0)
        blockchain_transactions_parser.add_argument("--chain-id", help="Chain ID")
        blockchain_transactions_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_transactions_parser.set_defaults(handler=ctx.handle_blockchain_transactions)
    
        blockchain_mempool_parser = blockchain_subparsers.add_parser("mempool", help="Get pending transactions")
        blockchain_mempool_parser.add_argument("--chain-id", help="Chain ID")
        blockchain_mempool_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        blockchain_mempool_parser.set_defaults(handler=ctx.handle_blockchain_mempool)
