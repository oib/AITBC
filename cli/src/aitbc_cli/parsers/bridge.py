"""Blockchain event bridge command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        bridge_parser = subparsers.add_parser("bridge", help="Blockchain event bridge management")
        bridge_parser.set_defaults(handler=lambda parsed, parser=bridge_parser: parser.print_help())
        bridge_subparsers = bridge_parser.add_subparsers(dest="bridge_action")
    
        bridge_health_parser = bridge_subparsers.add_parser("health", help="Health check for blockchain event bridge service")
        bridge_health_parser.add_argument("--test-mode", action="store_true")
        bridge_health_parser.set_defaults(handler=ctx.handle_bridge_health)
    
        bridge_metrics_parser = bridge_subparsers.add_parser("metrics", help="Get Prometheus metrics from blockchain event bridge service")
        bridge_metrics_parser.add_argument("--test-mode", action="store_true")
        bridge_metrics_parser.set_defaults(handler=ctx.handle_bridge_metrics)
    
        bridge_status_parser = bridge_subparsers.add_parser("status", help="Get detailed status of blockchain event bridge service")
        bridge_status_parser.add_argument("--test-mode", action="store_true")
        bridge_status_parser.set_defaults(handler=ctx.handle_bridge_status)
    
        bridge_config_parser = bridge_subparsers.add_parser("config", help="Show current configuration of blockchain event bridge service")
        bridge_config_parser.add_argument("--test-mode", action="store_true")
        bridge_config_parser.set_defaults(handler=ctx.handle_bridge_config)
    
        bridge_restart_parser = bridge_subparsers.add_parser("restart", help="Restart blockchain event bridge service (via systemd)")
        bridge_restart_parser.add_argument("--test-mode", action="store_true")
        bridge_restart_parser.set_defaults(handler=ctx.handle_bridge_restart)
