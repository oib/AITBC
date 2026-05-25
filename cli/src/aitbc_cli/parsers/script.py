"""Script command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        script_parser = subparsers.add_parser("script", help="Script execution and automation")
        script_parser.add_argument("--run", action="store_true", help="Run a script file")
        script_parser.add_argument("--file", help="Script file to execute")
        script_parser.add_argument("--args", help="Arguments to pass to script")
        script_parser.set_defaults(handler=ctx.handle_script_run)
