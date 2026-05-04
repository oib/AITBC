"""AI command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        ai_parser = subparsers.add_parser("ai", help="AI job submission and inspection")
        ai_parser.set_defaults(handler=lambda parsed, parser=ai_parser: parser.print_help())
        ai_subparsers = ai_parser.add_subparsers(dest="ai_action")
    
        ai_submit_parser = ai_subparsers.add_parser("submit", help="Submit an AI job")
        ai_submit_parser.add_argument("wallet_name", nargs="?")
        ai_submit_parser.add_argument("job_type_arg", nargs="?")
        ai_submit_parser.add_argument("prompt_arg", nargs="?")
        ai_submit_parser.add_argument("payment_arg", nargs="?")
        ai_submit_parser.add_argument("--wallet")
        ai_submit_parser.add_argument("--type", dest="job_type")
        ai_submit_parser.add_argument("--prompt")
        ai_submit_parser.add_argument("--payment", type=float)
        ai_submit_parser.add_argument("--password")
        ai_submit_parser.add_argument("--password-file")
        ai_submit_parser.add_argument("--chain-id", help="Chain ID")
        ai_submit_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        ai_submit_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)
        ai_submit_parser.set_defaults(handler=ctx.handle_ai_submit)
    
        ai_jobs_parser = ai_subparsers.add_parser("jobs", help="List AI jobs")
        ai_jobs_parser.add_argument("--limit", type=int, default=10)
        ai_jobs_parser.add_argument("--chain-id", help="Chain ID")
        ai_jobs_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        ai_jobs_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)
        ai_jobs_parser.set_defaults(handler=ctx.handle_ai_jobs)
    
        ai_status_parser = ai_subparsers.add_parser("status", help="Show AI job status")
        ai_status_parser.add_argument("job_id_arg", nargs="?")
        ai_status_parser.add_argument("--job-id", dest="job_id")
        ai_status_parser.add_argument("--wallet")
        ai_status_parser.add_argument("--chain-id", help="Chain ID")
        ai_status_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        ai_status_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)
        ai_status_parser.set_defaults(handler=ctx.handle_ai_status)
    
        ai_service_parser = ai_subparsers.add_parser("service", help="AI service management")
        ai_service_subparsers = ai_service_parser.add_subparsers(dest="ai_service_action")
    
        ai_service_list_parser = ai_service_subparsers.add_parser("list", help="List available AI services")
        ai_service_list_parser.set_defaults(handler=ctx.handle_ai_service_list)
    
        ai_service_status_parser = ai_service_subparsers.add_parser("status", help="Check AI service status")
        ai_service_status_parser.add_argument("--name", help="Service name to check")
        ai_service_status_parser.set_defaults(handler=ctx.handle_ai_service_status)
    
        ai_service_test_parser = ai_service_subparsers.add_parser("test", help="Test AI service endpoint")
        ai_service_test_parser.add_argument("--name", help="Service name to test")
        ai_service_test_parser.set_defaults(handler=ctx.handle_ai_service_test)
    
        ai_results_parser = ai_subparsers.add_parser("results", help="Show AI job results")
        ai_results_parser.add_argument("job_id_arg", nargs="?")
        ai_results_parser.add_argument("--job-id", dest="job_id")
        ai_results_parser.add_argument("--wallet")
        ai_results_parser.add_argument("--chain-id", help="Chain ID")
        ai_results_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        ai_results_parser.set_defaults(handler=ctx.handle_ai_job)  # Reuse job handler
    
        ai_cancel_parser = ai_subparsers.add_parser("cancel", help="Cancel AI job")
        ai_cancel_parser.add_argument("job_id_arg", nargs="?")
        ai_cancel_parser.add_argument("--job-id", dest="job_id")
        ai_cancel_parser.add_argument("--wallet", required=True)
        ai_cancel_parser.add_argument("--password")
        ai_cancel_parser.add_argument("--password-file")
        ai_cancel_parser.add_argument("--chain-id", help="Chain ID")
        ai_cancel_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        ai_cancel_parser.set_defaults(handler=ctx.handle_ai_cancel)
    
        ai_stats_parser = ai_subparsers.add_parser("stats", help="AI service statistics")
        ai_stats_parser.add_argument("--chain-id", help="Chain ID")
        ai_stats_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        ai_stats_parser.set_defaults(handler=ctx.handle_ai_stats)
