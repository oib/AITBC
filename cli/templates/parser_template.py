"""{{COMMAND_NAME}} command registration for the unified CLI."""

import argparse
from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
    """Register {{COMMAND_NAME}} command with the CLI."""
    {{COMMAND_NAME}}_parser = subparsers.add_parser("{{COMMAND_NAME}}", help="{{COMMAND_DESCRIPTION}}")
    {{COMMAND_NAME}}_parser.set_defaults(handler=lambda parsed, parser={{COMMAND_NAME}}_parser: parser.print_help())
    {{COMMAND_NAME}}_subparsers = {{COMMAND_NAME}}_parser.add_subparsers(dest="{{COMMAND_NAME}}_action")
    
    # Add subcommands
    {{COMMAND_NAME}}_action_parser = {{COMMAND_NAME}}_subparsers.add_parser("action", help="Action description")
    {{COMMAND_NAME}}_action_parser.add_argument("--option", help="Option description")
    {{COMMAND_NAME}}_action_parser.set_defaults(handler=ctx.handle_{{COMMAND_NAME}}_action)
