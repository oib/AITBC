"""hermes Agent Training command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        hermes_training_parser = subparsers.add_parser("hermes-training", help="hermes agent training operations")
        hermes_training_parser.set_defaults(handler=lambda parsed, parser=hermes_training_parser: parser.print_help())
        hermes_training_subparsers = hermes_training_parser.add_subparsers(dest="hermes_training_action")
    
        hermes_deploy_parser = hermes_training_subparsers.add_parser("deploy", help="Deploy an hermes agent")
        hermes_deploy_parser.add_argument("--agent-file", required=True)
        hermes_deploy_parser.add_argument("--wallet", required=True)
        hermes_deploy_parser.add_argument("--environment", choices=["dev", "staging", "prod"], default="dev")
        hermes_deploy_parser.set_defaults(handler=ctx.handle_hermes_training_action)
    
        hermes_monitor_parser = hermes_training_subparsers.add_parser("monitor", help="Monitor hermes performance")
        hermes_monitor_parser.add_argument("--agent-id")
        hermes_monitor_parser.add_argument("--metrics", choices=["performance", "cost", "errors", "all"], default="all")
        hermes_monitor_parser.set_defaults(handler=ctx.handle_hermes_training_action)
    
        hermes_market_parser = hermes_training_subparsers.add_parser("market", help="Manage hermes marketplace activity")
        hermes_market_parser.add_argument("market_action", nargs="?", choices=["list", "publish", "purchase", "evaluate"])
        hermes_market_parser.add_argument("--action", dest="market_action_opt", choices=["list", "publish", "purchase", "evaluate"], help=argparse.SUPPRESS)
        hermes_market_parser.add_argument("--agent-id")
        hermes_market_parser.add_argument("--price", type=float)
        hermes_market_parser.set_defaults(handler=ctx.handle_hermes_training_action, hermes_training_action="market")
    
        hermes_train_parser = hermes_training_subparsers.add_parser("train", help="Agent training operations")
        hermes_train_subparsers = hermes_train_parser.add_subparsers(dest="train_action")
        
        hermes_train_agent_parser = hermes_train_subparsers.add_parser("agent", help="Train hermes agent on AITBC operations")
        hermes_train_agent_parser.add_argument("--agent-id", required=True, help="Agent ID to train")
        hermes_train_agent_parser.add_argument("--stage", required=True, help="Training stage (stage1_foundation, stage2_operations_mastery, etc.)")
        hermes_train_agent_parser.add_argument("--training-data", required=True, help="Path to training data JSON file")
        hermes_train_agent_parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"], help="Logging level")
        hermes_train_agent_parser.set_defaults(handler=ctx.handle_hermes_training_action, hermes_training_action="train")
        
        hermes_train_validate_parser = hermes_train_subparsers.add_parser("validate", help="Validate agent training progress")
        hermes_train_validate_parser.add_argument("--agent-id", required=True, help="Agent ID to validate")
        hermes_train_validate_parser.add_argument("--stage", required=True, help="Training stage to validate")
        hermes_train_validate_parser.set_defaults(handler=ctx.handle_hermes_training_action, hermes_training_action="train")
        
        hermes_train_certify_parser = hermes_train_subparsers.add_parser("certify", help="Certify agent mastery")
        hermes_train_certify_parser.add_argument("--agent-id", required=True, help="Agent ID to certify")
        hermes_train_certify_parser.set_defaults(handler=ctx.handle_hermes_training_action, hermes_training_action="train")
