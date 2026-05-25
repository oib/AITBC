"""Messaging command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        messaging_parser = subparsers.add_parser("messaging", help="Messaging system and forum")
        messaging_parser.set_defaults(handler=lambda parsed, parser=messaging_parser: parser.print_help())
        messaging_subparsers = messaging_parser.add_subparsers(dest="messaging_action")
    
        messaging_deploy_parser = messaging_subparsers.add_parser("deploy", help="Deploy messaging contract")
        messaging_deploy_parser.add_argument("--chain-id", help="Chain ID")
        messaging_deploy_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_deploy_parser.set_defaults(handler=ctx.handle_messaging_deploy)
    
        messaging_state_parser = messaging_subparsers.add_parser("state", help="Get contract state")
        messaging_state_parser.add_argument("--chain-id", help="Chain ID")
        messaging_state_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_state_parser.set_defaults(handler=ctx.handle_messaging_state)
    
        messaging_topics_parser = messaging_subparsers.add_parser("topics", help="List forum topics")
        messaging_topics_parser.add_argument("--chain-id", help="Chain ID")
        messaging_topics_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_topics_parser.set_defaults(handler=ctx.handle_messaging_topics)
    
        messaging_create_topic_parser = messaging_subparsers.add_parser("create-topic", help="Create forum topic")
        messaging_create_topic_parser.add_argument("--title", required=True, help="Topic title")
        messaging_create_topic_parser.add_argument("--content", required=True, help="Topic content")
        messaging_create_topic_parser.add_argument("--wallet", help="Wallet address for authentication")
        messaging_create_topic_parser.add_argument("--password")
        messaging_create_topic_parser.add_argument("--password-file")
        messaging_create_topic_parser.add_argument("--chain-id", help="Chain ID")
        messaging_create_topic_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_create_topic_parser.set_defaults(handler=ctx.handle_messaging_create_topic)
    
        messaging_messages_parser = messaging_subparsers.add_parser("messages", help="Get topic messages")
        messaging_messages_parser.add_argument("--topic-id", required=True, help="Topic ID")
        messaging_messages_parser.add_argument("--chain-id", help="Chain ID")
        messaging_messages_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_messages_parser.set_defaults(handler=ctx.handle_messaging_messages)
    
        messaging_post_parser = messaging_subparsers.add_parser("post", help="Post message")
        messaging_post_parser.add_argument("--topic-id", required=True, help="Topic ID")
        messaging_post_parser.add_argument("--content", required=True, help="Message content")
        messaging_post_parser.add_argument("--wallet", help="Wallet address for authentication")
        messaging_post_parser.add_argument("--password")
        messaging_post_parser.add_argument("--password-file")
        messaging_post_parser.add_argument("--chain-id", help="Chain ID")
        messaging_post_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_post_parser.set_defaults(handler=ctx.handle_messaging_post)
    
        messaging_vote_parser = messaging_subparsers.add_parser("vote", help="Vote on message")
        messaging_vote_parser.add_argument("--message-id", required=True, help="Message ID")
        messaging_vote_parser.add_argument("--vote", required=True, help="Vote (up/down)")
        messaging_vote_parser.add_argument("--wallet", help="Wallet address for authentication")
        messaging_vote_parser.add_argument("--password")
        messaging_vote_parser.add_argument("--password-file")
        messaging_vote_parser.add_argument("--chain-id", help="Chain ID")
        messaging_vote_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_vote_parser.set_defaults(handler=ctx.handle_messaging_vote)
    
        messaging_search_parser = messaging_subparsers.add_parser("search", help="Search messages")
        messaging_search_parser.add_argument("--query", required=True, help="Search query")
        messaging_search_parser.add_argument("--chain-id", help="Chain ID")
        messaging_search_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_search_parser.set_defaults(handler=ctx.handle_messaging_search)
    
        messaging_reputation_parser = messaging_subparsers.add_parser("reputation", help="Get agent reputation")
        messaging_reputation_parser.add_argument("--agent-id", required=True, help="Agent ID")
        messaging_reputation_parser.add_argument("--chain-id", help="Chain ID")
        messaging_reputation_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_reputation_parser.set_defaults(handler=ctx.handle_messaging_reputation)
    
        messaging_moderate_parser = messaging_subparsers.add_parser("moderate", help="Moderate message")
        messaging_moderate_parser.add_argument("--message-id", required=True, help="Message ID")
        messaging_moderate_parser.add_argument("--action", required=True, help="Action (approve/reject)")
        messaging_moderate_parser.add_argument("--wallet", help="Wallet address for authentication")
        messaging_moderate_parser.add_argument("--password")
        messaging_moderate_parser.add_argument("--password-file")
        messaging_moderate_parser.add_argument("--chain-id", help="Chain ID")
        messaging_moderate_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
        messaging_moderate_parser.set_defaults(handler=ctx.handle_messaging_moderate)
