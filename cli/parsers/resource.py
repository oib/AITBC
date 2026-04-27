"""Resource command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        resource_parser = subparsers.add_parser("resource", help="Resource utilization and allocation")
        resource_parser.set_defaults(handler=lambda parsed, parser=resource_parser: parser.print_help())
        resource_subparsers = resource_parser.add_subparsers(dest="resource_action")
    
        resource_status_parser = resource_subparsers.add_parser("status", help="Show resource status")
        resource_status_parser.add_argument("--type", choices=["cpu", "memory", "storage", "network", "all"], default="all")
        resource_status_parser.set_defaults(handler=ctx.handle_resource_action)
    
        resource_allocate_parser = resource_subparsers.add_parser("allocate", help="Allocate resources")
        resource_allocate_parser.add_argument("--agent-id", required=True)
        resource_allocate_parser.add_argument("--cpu", type=float)
        resource_allocate_parser.add_argument("--memory", type=int)
        resource_allocate_parser.add_argument("--duration", type=int)
        resource_allocate_parser.set_defaults(handler=ctx.handle_resource_action)
    
        resource_optimize_parser = resource_subparsers.add_parser("optimize", help="Optimize resource usage")
        resource_optimize_parser.add_argument("--agent-id")
        resource_optimize_parser.add_argument("--target", choices=["cpu", "memory", "all"], default="all")
        resource_optimize_parser.set_defaults(handler=ctx.handle_resource_action, resource_action="optimize")
    
        resource_benchmark_parser = resource_subparsers.add_parser("benchmark", help="Run resource benchmark")
        resource_benchmark_parser.add_argument("--type", choices=["cpu", "memory", "io", "all"], default="all")
        resource_benchmark_parser.set_defaults(handler=ctx.handle_resource_action, resource_action="benchmark")
    
        resource_monitor_parser = resource_subparsers.add_parser("monitor", help="Monitor resource utilization")
        resource_monitor_parser.add_argument("--interval", type=int, default=5, help="Monitoring interval in seconds")
        resource_monitor_parser.add_argument("--duration", type=int, default=60, help="Monitoring duration in seconds")
        resource_monitor_parser.set_defaults(handler=ctx.handle_resource_action, resource_action="monitor")
