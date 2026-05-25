"""Pool hub command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        pool_hub_parser = subparsers.add_parser("pool-hub", help="Pool hub management for SLA monitoring and billing")
        pool_hub_parser.set_defaults(handler=lambda parsed, parser=pool_hub_parser: parser.print_help())
        pool_hub_subparsers = pool_hub_parser.add_subparsers(dest="pool_hub_action")
    
        pool_hub_sla_metrics_parser = pool_hub_subparsers.add_parser("sla-metrics", help="Get SLA metrics for miner or all miners")
        pool_hub_sla_metrics_parser.add_argument("miner_id", nargs="?")
        pool_hub_sla_metrics_parser.add_argument("--test-mode", action="store_true")
        pool_hub_sla_metrics_parser.set_defaults(handler=ctx.handle_pool_hub_sla_metrics)
    
        pool_hub_sla_violations_parser = pool_hub_subparsers.add_parser("sla-violations", help="Get SLA violations")
        pool_hub_sla_violations_parser.add_argument("--test-mode", action="store_true")
        pool_hub_sla_violations_parser.set_defaults(handler=ctx.handle_pool_hub_sla_violations)
    
        pool_hub_capacity_snapshots_parser = pool_hub_subparsers.add_parser("capacity-snapshots", help="Get capacity planning snapshots")
        pool_hub_capacity_snapshots_parser.add_argument("--test-mode", action="store_true")
        pool_hub_capacity_snapshots_parser.set_defaults(handler=ctx.handle_pool_hub_capacity_snapshots)
    
        pool_hub_capacity_forecast_parser = pool_hub_subparsers.add_parser("capacity-forecast", help="Get capacity forecast")
        pool_hub_capacity_forecast_parser.add_argument("--test-mode", action="store_true")
        pool_hub_capacity_forecast_parser.set_defaults(handler=ctx.handle_pool_hub_capacity_forecast)
    
        pool_hub_capacity_recommendations_parser = pool_hub_subparsers.add_parser("capacity-recommendations", help="Get scaling recommendations")
        pool_hub_capacity_recommendations_parser.add_argument("--test-mode", action="store_true")
        pool_hub_capacity_recommendations_parser.set_defaults(handler=ctx.handle_pool_hub_capacity_recommendations)
    
        pool_hub_billing_usage_parser = pool_hub_subparsers.add_parser("billing-usage", help="Get billing usage data")
        pool_hub_billing_usage_parser.add_argument("--test-mode", action="store_true")
        pool_hub_billing_usage_parser.set_defaults(handler=ctx.handle_pool_hub_billing_usage)
    
        pool_hub_billing_sync_parser = pool_hub_subparsers.add_parser("billing-sync", help="Trigger billing sync with coordinator-api")
        pool_hub_billing_sync_parser.add_argument("--test-mode", action="store_true")
        pool_hub_billing_sync_parser.set_defaults(handler=ctx.handle_pool_hub_billing_sync)
    
        pool_hub_collect_metrics_parser = pool_hub_subparsers.add_parser("collect-metrics", help="Trigger SLA metrics collection")
        pool_hub_collect_metrics_parser.add_argument("--test-mode", action="store_true")
        pool_hub_collect_metrics_parser.set_defaults(handler=ctx.handle_pool_hub_collect_metrics)
