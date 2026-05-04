"""OpenClaw Agent Training command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        openclaw_training_parser = subparsers.add_parser("openclaw-training", help="OpenClaw agent training operations")
        openclaw_training_parser.set_defaults(handler=lambda parsed, parser=openclaw_training_parser: parser.print_help())
        openclaw_training_subparsers = openclaw_training_parser.add_subparsers(dest="openclaw_training_action")
    
        openclaw_deploy_parser = openclaw_training_subparsers.add_parser("deploy", help="Deploy an OpenClaw agent")
        openclaw_deploy_parser.add_argument("--agent-file", required=True)
        openclaw_deploy_parser.add_argument("--wallet", required=True)
        openclaw_deploy_parser.add_argument("--environment", choices=["dev", "staging", "prod"], default="dev")
        openclaw_deploy_parser.set_defaults(handler=ctx.handle_openclaw_training_action)
    
        openclaw_monitor_parser = openclaw_training_subparsers.add_parser("monitor", help="Monitor OpenClaw performance")
        openclaw_monitor_parser.add_argument("--agent-id")
        openclaw_monitor_parser.add_argument("--metrics", choices=["performance", "cost", "errors", "all"], default="all")
        openclaw_monitor_parser.set_defaults(handler=ctx.handle_openclaw_training_action)
    
        openclaw_market_parser = openclaw_training_subparsers.add_parser("market", help="Manage OpenClaw marketplace activity")
        openclaw_market_parser.add_argument("market_action", nargs="?", choices=["list", "publish", "purchase", "evaluate"])
        openclaw_market_parser.add_argument("--action", dest="market_action_opt", choices=["list", "publish", "purchase", "evaluate"], help=argparse.SUPPRESS)
        openclaw_market_parser.add_argument("--agent-id")
        openclaw_market_parser.add_argument("--price", type=float)
        openclaw_market_parser.set_defaults(handler=ctx.handle_openclaw_training_action, openclaw_training_action="market")
    
        openclaw_train_parser = openclaw_training_subparsers.add_parser("train", help="Agent training operations")
        openclaw_train_subparsers = openclaw_train_parser.add_subparsers(dest="train_action")
        
        openclaw_train_agent_parser = openclaw_train_subparsers.add_parser("agent", help="Train OpenClaw agent on AITBC operations")
        openclaw_train_agent_parser.add_argument("--agent-id", required=True, help="Agent ID to train")
        openclaw_train_agent_parser.add_argument("--stage", required=True, help="Training stage (stage1_foundation, stage2_operations_mastery, etc.)")
        openclaw_train_agent_parser.add_argument("--training-data", required=True, help="Path to training data JSON file")
        openclaw_train_agent_parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"], help="Logging level")
        openclaw_train_agent_parser.set_defaults(handler=ctx.handle_openclaw_training_action, openclaw_training_action="train")
        
        openclaw_train_validate_parser = openclaw_train_subparsers.add_parser("validate", help="Validate agent training progress")
        openclaw_train_validate_parser.add_argument("--agent-id", required=True, help="Agent ID to validate")
        openclaw_train_validate_parser.add_argument("--stage", required=True, help="Training stage to validate")
        openclaw_train_validate_parser.set_defaults(handler=ctx.handle_openclaw_training_action, openclaw_training_action="train")
        
        openclaw_train_certify_parser = openclaw_train_subparsers.add_parser("certify", help="Certify agent mastery")
        openclaw_train_certify_parser.add_argument("--agent-id", required=True, help="Agent ID to certify")
        openclaw_train_certify_parser.set_defaults(handler=ctx.handle_openclaw_training_action, openclaw_training_action="train")
