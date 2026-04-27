"""Agent command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        agent_parser = subparsers.add_parser("agent", help="AI agent workflow orchestration")
        agent_parser.set_defaults(handler=lambda parsed, parser=agent_parser: parser.print_help())
        agent_subparsers = agent_parser.add_subparsers(dest="agent_action")
    
        agent_create_parser = agent_subparsers.add_parser("create", help="Create an agent workflow")
        agent_create_parser.add_argument("--name", required=True)
        agent_create_parser.add_argument("--description")
        agent_create_parser.add_argument("--workflow-file")
        agent_create_parser.add_argument("--verification", choices=["basic", "full", "zero-knowledge"], default="basic")
        agent_create_parser.add_argument("--max-execution-time", type=int, default=3600)
        agent_create_parser.add_argument("--max-cost-budget", type=float, default=0.0)
        agent_create_parser.set_defaults(handler=ctx.handle_agent_action)
    
        agent_execute_parser = agent_subparsers.add_parser("execute", help="Execute an agent workflow")
        agent_execute_parser.add_argument("--name", required=True)
        agent_execute_parser.add_argument("--input-data")
        agent_execute_parser.add_argument("--wallet")
        agent_execute_parser.add_argument("--priority", choices=["low", "medium", "high"], default="medium")
        agent_execute_parser.set_defaults(handler=ctx.handle_agent_action)
    
        agent_status_parser = agent_subparsers.add_parser("status", help="Show agent status")
        agent_status_parser.add_argument("--name")
        agent_status_parser.add_argument("--execution-id")
        agent_status_parser.set_defaults(handler=ctx.handle_agent_action)
    
        agent_list_parser = agent_subparsers.add_parser("list", help="List agents")
        agent_list_parser.add_argument("--status", choices=["active", "completed", "failed"])
        agent_list_parser.set_defaults(handler=ctx.handle_agent_action)
    
        agent_message_parser = agent_subparsers.add_parser("message", help="Send message to agent")
        agent_message_parser.add_argument("--agent", required=True)
        agent_message_parser.add_argument("--message", required=True)
        agent_message_parser.add_argument("--wallet", required=True)
        agent_message_parser.add_argument("--password")
        agent_message_parser.add_argument("--password-file")
        agent_message_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        agent_message_parser.set_defaults(handler=ctx.handle_agent_action, agent_action="message")
    
        agent_messages_parser = agent_subparsers.add_parser("messages", help="List agent messages")
        agent_messages_parser.add_argument("--agent", required=True)
        agent_messages_parser.add_argument("--wallet")
        agent_messages_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        agent_messages_parser.set_defaults(handler=ctx.handle_agent_action, agent_action="messages")
