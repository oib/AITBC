"""OpenClaw command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        openclaw_parser = subparsers.add_parser("openclaw", help="OpenClaw ecosystem operations")
        openclaw_parser.set_defaults(handler=lambda parsed, parser=openclaw_parser: parser.print_help())
        openclaw_subparsers = openclaw_parser.add_subparsers(dest="openclaw_action")
    
        openclaw_deploy_parser = openclaw_subparsers.add_parser("deploy", help="Deploy an OpenClaw agent")
        openclaw_deploy_parser.add_argument("--agent-file", required=True)
        openclaw_deploy_parser.add_argument("--wallet", required=True)
        openclaw_deploy_parser.add_argument("--environment", choices=["dev", "staging", "prod"], default="dev")
        openclaw_deploy_parser.set_defaults(handler=ctx.handle_openclaw_action)
    
        openclaw_monitor_parser = openclaw_subparsers.add_parser("monitor", help="Monitor OpenClaw performance")
        openclaw_monitor_parser.add_argument("--agent-id")
        openclaw_monitor_parser.add_argument("--metrics", choices=["performance", "cost", "errors", "all"], default="all")
        openclaw_monitor_parser.set_defaults(handler=ctx.handle_openclaw_action)
    
        openclaw_market_parser = openclaw_subparsers.add_parser("market", help="Manage OpenClaw marketplace activity")
        openclaw_market_parser.add_argument("market_action", nargs="?", choices=["list", "publish", "purchase", "evaluate"])
        openclaw_market_parser.add_argument("--action", dest="market_action_opt", choices=["list", "publish", "purchase", "evaluate"], help=argparse.SUPPRESS)
        openclaw_market_parser.add_argument("--agent-id")
        openclaw_market_parser.add_argument("--price", type=float)
        openclaw_market_parser.set_defaults(handler=ctx.handle_openclaw_action, openclaw_action="market")
