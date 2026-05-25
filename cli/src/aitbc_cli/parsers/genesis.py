"""Genesis command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        genesis_parser = subparsers.add_parser("genesis", help="Genesis block and wallet generation")
        genesis_parser.set_defaults(handler=lambda parsed, parser=genesis_parser: parser.print_help())
        genesis_subparsers = genesis_parser.add_subparsers(dest="genesis_action")
    
        genesis_init_parser = genesis_subparsers.add_parser("init", help="Initialize genesis block and wallet")
        genesis_init_parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID for genesis")
        genesis_init_parser.add_argument("--create-wallet", action="store_true", help="Create genesis wallet with secure random key")
        genesis_init_parser.add_argument("--password", help="Wallet password (auto-generated if not provided)")
        genesis_init_parser.add_argument("--proposer", help="Proposer address (defaults to genesis wallet)")
        genesis_init_parser.add_argument("--force", action="store_true", help="Force overwrite existing genesis")
        genesis_init_parser.add_argument("--register-service", action="store_true", help="Register genesis wallet with wallet service")
        genesis_init_parser.add_argument("--service-url", default="http://localhost:8003", help="Wallet service URL")
        genesis_init_parser.set_defaults(handler=ctx.handle_genesis_init)
    
        genesis_verify_parser = genesis_subparsers.add_parser("verify", help="Verify genesis block and wallet configuration")
        genesis_verify_parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID to verify")
        genesis_verify_parser.set_defaults(handler=ctx.handle_genesis_verify)
    
        genesis_info_parser = genesis_subparsers.add_parser("info", help="Show genesis block information")
        genesis_info_parser.add_argument("--chain-id", default="ait-mainnet", help="Chain ID to show info for")
        genesis_info_parser.set_defaults(handler=ctx.handle_genesis_info)
