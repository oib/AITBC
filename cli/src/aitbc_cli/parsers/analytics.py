"""Analytics command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        analytics_parser = subparsers.add_parser("analytics", help="Blockchain analytics and statistics")
        analytics_parser.set_defaults(handler=lambda parsed, parser=analytics_parser: parser.print_help())
        analytics_subparsers = analytics_parser.add_subparsers(dest="analytics_action")
    
        analytics_blocks_parser = analytics_subparsers.add_parser("blocks", help="Block analytics")
        analytics_blocks_parser.add_argument("--limit", type=int, default=10)
        analytics_blocks_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        analytics_blocks_parser.set_defaults(handler=ctx.handle_analytics_metrics)
    
        analytics_metrics_parser = analytics_subparsers.add_parser("metrics", help="Show performance metrics")
        analytics_metrics_parser.add_argument("--limit", type=int, default=10)
        analytics_metrics_parser.add_argument("--period", default="24h")
        analytics_metrics_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        analytics_metrics_parser.set_defaults(handler=ctx.handle_analytics_metrics)
    
        analytics_report_parser = analytics_subparsers.add_parser("report", help="Generate analytics report")
        analytics_report_parser.add_argument("--type", dest="report_type", choices=["performance", "transactions", "all"], default="all")
        analytics_report_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        analytics_report_parser.set_defaults(handler=ctx.handle_analytics_report)
    
        analytics_export_parser = analytics_subparsers.add_parser("export", help="Export analytics data")
        analytics_export_parser.add_argument("--format", choices=["json", "csv"], default="json")
        analytics_export_parser.add_argument("--output")
        analytics_export_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        analytics_export_parser.set_defaults(handler=ctx.handle_analytics_export)
    
        analytics_predict_parser = analytics_subparsers.add_parser("predict", help="Run predictive analytics")
        analytics_predict_parser.add_argument("--model", default="lstm")
        analytics_predict_parser.add_argument("--target", default="job-completion")
        analytics_predict_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        analytics_predict_parser.set_defaults(handler=ctx.handle_analytics_predict)
    
        analytics_optimize_parser = analytics_subparsers.add_parser("optimize", help="Optimize system parameters")
        analytics_optimize_parser.add_argument("--parameters", action="store_true")
        analytics_optimize_parser.add_argument("--target", default="efficiency")
        analytics_optimize_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        analytics_optimize_parser.set_defaults(handler=ctx.handle_analytics_optimize)
