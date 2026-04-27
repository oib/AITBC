"""Marketplace command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        market_parser = subparsers.add_parser("market", help="Marketplace listings and offers")
        market_parser.set_defaults(handler=lambda parsed, parser=market_parser: parser.print_help())
        market_subparsers = market_parser.add_subparsers(dest="market_action")
    
        # GPU marketplace subcommands
        market_gpu_parser = market_subparsers.add_parser("gpu", help="GPU marketplace operations")
        market_gpu_parser.set_defaults(handler=lambda parsed, parser=market_gpu_parser: parser.print_help())
        market_gpu_subparsers = market_gpu_parser.add_subparsers(dest="gpu_action")
    
        market_gpu_register_parser = market_gpu_subparsers.add_parser("register", help="Register GPU on marketplace")
        market_gpu_register_parser.add_argument("--name", help="GPU name/model")
        market_gpu_register_parser.add_argument("--memory", type=int, help="GPU memory in GB")
        market_gpu_register_parser.add_argument("--cuda-cores", type=int, help="Number of CUDA cores")
        market_gpu_register_parser.add_argument("--compute-capability", help="Compute capability (e.g., 8.9)")
        market_gpu_register_parser.add_argument("--price-per-hour", type=float, required=True, help="Price per hour in AIT")
        market_gpu_register_parser.add_argument("--description", help="GPU description")
        market_gpu_register_parser.add_argument("--miner-id", help="Miner ID")
        market_gpu_register_parser.add_argument("--force", action="store_true", help="Force registration without hardware validation")
        market_gpu_register_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)
        market_gpu_register_parser.set_defaults(handler=ctx.handle_market_gpu_register)
    
        market_gpu_list_parser = market_gpu_subparsers.add_parser("list", help="List available GPUs")
        market_gpu_list_parser.add_argument("--available", action="store_true", help="Show only available GPUs")
        market_gpu_list_parser.add_argument("--price-max", type=float, help="Maximum price per hour")
        market_gpu_list_parser.add_argument("--region", help="Filter by region")
        market_gpu_list_parser.add_argument("--model", help="Filter by GPU model")
        market_gpu_list_parser.add_argument("--limit", type=int, default=100, help="Maximum number of results")
        market_gpu_list_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)
        market_gpu_list_parser.set_defaults(handler=ctx.handle_market_gpu_list)
    
        market_list_parser = market_subparsers.add_parser("list", help="List marketplace items")
        market_list_parser.add_argument("--chain-id", help="Chain ID")
        market_list_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)
        market_list_parser.set_defaults(handler=ctx.handle_market_listings)
    
        market_create_parser = market_subparsers.add_parser("create", help="Create a marketplace listing")
        market_create_parser.add_argument("--wallet", required=True)
        market_create_parser.add_argument("--type", dest="item_type", required=True)
        market_create_parser.add_argument("--price", type=float, required=True)
        market_create_parser.add_argument("--description")
        market_create_parser.add_argument("--password")
        market_create_parser.add_argument("--password-file")
        market_create_parser.add_argument("--chain-id", help="Chain ID")
        market_create_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)
        market_create_parser.set_defaults(handler=ctx.handle_market_create)
    
        market_search_parser = market_subparsers.add_parser("search", help="Search marketplace items")
        market_search_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        market_search_parser.set_defaults(handler=ctx.handle_market_listings)  # Reuse listings for now
    
        market_mine_parser = market_subparsers.add_parser("my-listings", help="Show your marketplace listings")
        market_mine_parser.add_argument("--wallet")
        market_mine_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        market_mine_parser.set_defaults(handler=ctx.handle_market_listings)  # Reuse listings for now
    
        market_get_parser = market_subparsers.add_parser("get", help="Get listing by ID")
        market_get_parser.add_argument("--listing-id", required=True)
        market_get_parser.add_argument("--chain-id", help="Chain ID")
        market_get_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        market_get_parser.set_defaults(handler=ctx.handle_market_get)
    
        market_delete_parser = market_subparsers.add_parser("delete", help="Delete listing")
        market_delete_parser.add_argument("--listing-id", required=True)
        market_delete_parser.add_argument("--wallet", required=True)
        market_delete_parser.add_argument("--password")
        market_delete_parser.add_argument("--password-file")
        market_delete_parser.add_argument("--chain-id", help="Chain ID")
        market_delete_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)
        market_delete_parser.set_defaults(handler=ctx.handle_market_delete)
    
        market_buy_parser = market_subparsers.add_parser("buy", help="Buy from marketplace")
        market_buy_parser.add_argument("--item", required=True)
        market_buy_parser.add_argument("--wallet", required=True)
        market_buy_parser.add_argument("--password")
        market_buy_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        market_buy_parser.set_defaults(handler=ctx.handle_market_listings)  # Placeholder
    
        market_sell_parser = market_subparsers.add_parser("sell", help="Sell on marketplace")
        market_sell_parser.add_argument("--item", required=True)
        market_sell_parser.add_argument("--price", type=float, required=True)
        market_sell_parser.add_argument("--wallet", required=True)
        market_sell_parser.add_argument("--password")
        market_sell_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        market_sell_parser.set_defaults(handler=ctx.handle_market_create)  # Reuse create
    
        market_orders_parser = market_subparsers.add_parser("orders", help="Show marketplace orders")
        market_orders_parser.add_argument("--wallet")
        market_orders_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        market_orders_parser.set_defaults(handler=ctx.handle_market_listings)  # Reuse listings for now
