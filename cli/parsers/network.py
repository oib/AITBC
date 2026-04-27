"""Network command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        network_parser = subparsers.add_parser("network", help="Peer connectivity and sync")
        network_parser.set_defaults(handler=ctx.handle_network_status)
        network_subparsers = network_parser.add_subparsers(dest="network_action")
    
        network_status_parser = network_subparsers.add_parser("status", help="Show network status")
        network_status_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        network_status_parser.set_defaults(handler=ctx.handle_network_status)
    
        network_peers_parser = network_subparsers.add_parser("peers", help="List peers")
        network_peers_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        network_peers_parser.set_defaults(handler=ctx.handle_network_peers)
    
        network_sync_parser = network_subparsers.add_parser("sync", help="Show sync status")
        network_sync_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        network_sync_parser.set_defaults(handler=ctx.handle_network_sync)
    
        network_ping_parser = network_subparsers.add_parser("ping", help="Ping a node")
        network_ping_parser.add_argument("node", nargs="?")
        network_ping_parser.add_argument("--node", dest="node_opt", help=argparse.SUPPRESS)
        network_ping_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        network_ping_parser.set_defaults(handler=ctx.handle_network_ping)
    
        network_propagate_parser = network_subparsers.add_parser("propagate", help="Propagate test data")
        network_propagate_parser.add_argument("data", nargs="?")
        network_propagate_parser.add_argument("--data", dest="data_opt", help=argparse.SUPPRESS)
        network_propagate_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        network_propagate_parser.set_defaults(handler=ctx.handle_network_propagate)
    
        network_force_sync_parser = network_subparsers.add_parser("force-sync", help="Force reorg to specified peer")
        network_force_sync_parser.add_argument("--peer", required=True, help="Peer to sync from")
        network_force_sync_parser.add_argument("--chain-id", help="Chain ID")
        network_force_sync_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        network_force_sync_parser.set_defaults(handler=ctx.handle_network_force_sync)
