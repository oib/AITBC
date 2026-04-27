"""Wallet command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        wallet_parser = subparsers.add_parser("wallet", help="Wallet lifecycle, balances, and transactions")
        wallet_parser.set_defaults(handler=lambda parsed, parser=wallet_parser: parser.print_help())
        wallet_subparsers = wallet_parser.add_subparsers(dest="wallet_action")
    
        wallet_create_parser = wallet_subparsers.add_parser("create", help="Create a wallet")
        wallet_create_parser.add_argument("wallet_name", nargs="?")
        wallet_create_parser.add_argument("wallet_password", nargs="?")
        wallet_create_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
        wallet_create_parser.add_argument("--password")
        wallet_create_parser.add_argument("--password-file")
        wallet_create_parser.set_defaults(handler=ctx.handle_wallet_create)
    
        wallet_list_parser = wallet_subparsers.add_parser("list", help="List wallets")
        wallet_list_parser.add_argument("--format", choices=["table", "json"], default="table")
        wallet_list_parser.set_defaults(handler=ctx.handle_wallet_list)
    
        wallet_balance_parser = wallet_subparsers.add_parser("balance", help="Show wallet balance")
        wallet_balance_parser.add_argument("wallet_name", nargs="?")
        wallet_balance_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
        wallet_balance_parser.add_argument("--all", action="store_true")
        wallet_balance_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        wallet_balance_parser.add_argument("--chain-id", help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
        wallet_balance_parser.set_defaults(handler=ctx.handle_wallet_balance)
    
        wallet_transactions_parser = wallet_subparsers.add_parser("transactions", help="Show wallet transactions")
        wallet_transactions_parser.add_argument("wallet_name", nargs="?")
        wallet_transactions_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
        wallet_transactions_parser.add_argument("--limit", type=int, default=10)
        wallet_transactions_parser.add_argument("--format", choices=["table", "json"], default="table")
        wallet_transactions_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        wallet_transactions_parser.set_defaults(handler=ctx.handle_wallet_transactions)
    
        wallet_send_parser = wallet_subparsers.add_parser("send", help="Send AIT")
        wallet_send_parser.add_argument("from_wallet_arg", nargs="?")
        wallet_send_parser.add_argument("to_address_arg", nargs="?")
        wallet_send_parser.add_argument("amount_arg", nargs="?")
        wallet_send_parser.add_argument("wallet_password", nargs="?")
        wallet_send_parser.add_argument("--from", dest="from_wallet", help=argparse.SUPPRESS)
        wallet_send_parser.add_argument("--to", dest="to_address", help=argparse.SUPPRESS)
        wallet_send_parser.add_argument("--amount", type=float)
        wallet_send_parser.add_argument("--fee", type=float, default=10.0)
        wallet_send_parser.add_argument("--password")
        wallet_send_parser.add_argument("--password-file")
        wallet_send_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        wallet_send_parser.set_defaults(handler=ctx.handle_wallet_send)
    
        wallet_import_parser = wallet_subparsers.add_parser("import", help="Import a wallet")
        wallet_import_parser.add_argument("wallet_name", nargs="?")
        wallet_import_parser.add_argument("private_key_arg", nargs="?")
        wallet_import_parser.add_argument("wallet_password", nargs="?")
        wallet_import_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
        wallet_import_parser.add_argument("--private-key", dest="private_key_opt")
        wallet_import_parser.add_argument("--password")
        wallet_import_parser.add_argument("--password-file")
        wallet_import_parser.set_defaults(handler=ctx.handle_wallet_import)
    
        wallet_export_parser = wallet_subparsers.add_parser("export", help="Export a wallet")
        wallet_export_parser.add_argument("wallet_name", nargs="?")
        wallet_export_parser.add_argument("wallet_password", nargs="?")
        wallet_export_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
        wallet_export_parser.add_argument("--password")
        wallet_export_parser.add_argument("--password-file")
        wallet_export_parser.set_defaults(handler=ctx.handle_wallet_export)
    
        wallet_delete_parser = wallet_subparsers.add_parser("delete", help="Delete a wallet")
        wallet_delete_parser.add_argument("wallet_name", nargs="?")
        wallet_delete_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
        wallet_delete_parser.add_argument("--confirm", action="store_true")
        wallet_delete_parser.set_defaults(handler=ctx.handle_wallet_delete)
    
        wallet_rename_parser = wallet_subparsers.add_parser("rename", help="Rename a wallet")
        wallet_rename_parser.add_argument("old_name_arg", nargs="?")
        wallet_rename_parser.add_argument("new_name_arg", nargs="?")
        wallet_rename_parser.add_argument("--old", dest="old_name", help=argparse.SUPPRESS)
        wallet_rename_parser.add_argument("--new", dest="new_name", help=argparse.SUPPRESS)
        wallet_rename_parser.set_defaults(handler=ctx.handle_wallet_rename)
    
        wallet_backup_parser = wallet_subparsers.add_parser("backup", help="Backup a wallet")
        wallet_backup_parser.add_argument("wallet_name", nargs="?")
        wallet_backup_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
        wallet_backup_parser.set_defaults(handler=ctx.handle_wallet_backup)
    
        wallet_sync_parser = wallet_subparsers.add_parser("sync", help="Sync wallets")
        wallet_sync_parser.add_argument("wallet_name", nargs="?")
        wallet_sync_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
        wallet_sync_parser.add_argument("--all", action="store_true")
        wallet_sync_parser.set_defaults(handler=ctx.handle_wallet_sync)
    
        wallet_batch_parser = wallet_subparsers.add_parser("batch", help="Send multiple transactions")
        wallet_batch_parser.add_argument("--file", required=True)
        wallet_batch_parser.add_argument("--password")
        wallet_batch_parser.add_argument("--password-file")
        wallet_batch_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        wallet_batch_parser.set_defaults(handler=ctx.handle_wallet_batch)
