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
    
        # Agent SDK commands for lifecycle management
        agent_sdk_parser = agent_subparsers.add_parser("sdk", help="Agent SDK lifecycle management")
        agent_sdk_subparsers = agent_sdk_parser.add_subparsers(dest="agent_sdk_action")
    
        # agent sdk create
        agent_sdk_create_parser = agent_sdk_subparsers.add_parser("create", help="Create a new agent using Agent SDK")
        agent_sdk_create_parser.add_argument("--name", required=True, help="Agent name")
        agent_sdk_create_parser.add_argument("--type", choices=["provider", "consumer", "general"], default="provider", help="Agent type")
        agent_sdk_create_parser.add_argument("--compute-type", default="inference", help="Compute type")
        agent_sdk_create_parser.add_argument("--gpu-memory", type=int, help="GPU memory in GB")
        agent_sdk_create_parser.add_argument("--models", help="Comma-separated supported models")
        agent_sdk_create_parser.add_argument("--performance", type=float, default=0.8, help="Performance score")
        agent_sdk_create_parser.add_argument("--max-jobs", type=int, default=1, help="Max concurrent jobs")
        agent_sdk_create_parser.add_argument("--specialization", help="Agent specialization")
        agent_sdk_create_parser.add_argument("--coordinator-url", help="Coordinator URL")
        agent_sdk_create_parser.add_argument("--auto-detect", action="store_true", help="Auto-detect capabilities")
        agent_sdk_create_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="create")
    
        # agent sdk register
        agent_sdk_register_parser = agent_sdk_subparsers.add_parser("register", help="Register agent with coordinator")
        agent_sdk_register_parser.add_argument("--agent-id", required=True, help="Agent ID")
        agent_sdk_register_parser.add_argument("--coordinator-url", default="http://localhost:8001", help="Coordinator URL")
        agent_sdk_register_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="register")
    
        # agent sdk list
        agent_sdk_list_parser = agent_sdk_subparsers.add_parser("list", help="List local agents")
        agent_sdk_list_parser.add_argument("--agent-dir", help="Agent directory path")
        agent_sdk_list_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="list")
    
        # agent sdk status
        agent_sdk_status_parser = agent_sdk_subparsers.add_parser("status", help="Get agent status")
        agent_sdk_status_parser.add_argument("--agent-id", required=True, help="Agent ID")
        agent_sdk_status_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="status")
    
        # agent sdk capabilities
        agent_sdk_caps_parser = agent_sdk_subparsers.add_parser("capabilities", help="Show system capabilities")
        agent_sdk_caps_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="capabilities")
    
        # agent sdk config-set
        agent_sdk_config_set_parser = agent_sdk_subparsers.add_parser("config-set", help="Set agent configuration value")
        agent_sdk_config_set_parser.add_argument("--name", required=True, help="Agent name")
        agent_sdk_config_set_parser.add_argument("--key", required=True, help="Configuration key")
        agent_sdk_config_set_parser.add_argument("--value", required=True, help="Configuration value")
        agent_sdk_config_set_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="config_set")
    
        # agent sdk config-get
        agent_sdk_config_get_parser = agent_sdk_subparsers.add_parser("config-get", help="Get agent configuration")
        agent_sdk_config_get_parser.add_argument("--name", required=True, help="Agent name")
        agent_sdk_config_get_parser.add_argument("--key", help="Specific configuration key")
        agent_sdk_config_get_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="config_get")
    
        # agent sdk config-validate
        agent_sdk_config_validate_parser = agent_sdk_subparsers.add_parser("config-validate", help="Validate agent configuration")
        agent_sdk_config_validate_parser.add_argument("--name", required=True, help="Agent name")
        agent_sdk_config_validate_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="config_validate")
    
        # agent sdk config-import
        agent_sdk_config_import_parser = agent_sdk_subparsers.add_parser("config-import", help="Import agent configuration from file")
        agent_sdk_config_import_parser.add_argument("--file", required=True, help="Configuration file path")
        agent_sdk_config_import_parser.add_argument("--name", help="Override agent name")
        agent_sdk_config_import_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="config_import")
    
        # agent sdk config-export
        agent_sdk_config_export_parser = agent_sdk_subparsers.add_parser("config-export", help="Export agent configuration to file")
        agent_sdk_config_export_parser.add_argument("--name", required=True, help="Agent name")
        agent_sdk_config_export_parser.add_argument("--output", required=True, help="Output file path")
        agent_sdk_config_export_parser.set_defaults(handler=ctx.handle_agent_sdk_action, agent_sdk_action="config_export")
