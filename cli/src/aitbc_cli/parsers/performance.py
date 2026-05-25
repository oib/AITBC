"""Performance command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        performance_parser = subparsers.add_parser("performance", help="Performance optimization and monitoring")
        performance_parser.set_defaults(handler=lambda parsed, parser=performance_parser: parser.print_help())
        performance_subparsers = performance_parser.add_subparsers(dest="performance_action")
    
        performance_benchmark_parser = performance_subparsers.add_parser("benchmark", help="Run performance benchmark")
        performance_benchmark_parser.add_argument("--target")
        performance_benchmark_parser.set_defaults(handler=ctx.handle_performance_benchmark)
    
        performance_optimize_parser = performance_subparsers.add_parser("optimize", help="Optimize performance")
        performance_optimize_parser.add_argument("--target", default="general")
        performance_optimize_parser.set_defaults(handler=ctx.handle_performance_optimize)
    
        performance_tune_parser = performance_subparsers.add_parser("tune", help="Tune system parameters")
        performance_tune_parser.add_argument("--aggressive", action="store_true")
        performance_tune_parser.add_argument("--parameters", action="store_true")
        performance_tune_parser.set_defaults(handler=ctx.handle_performance_tune)
