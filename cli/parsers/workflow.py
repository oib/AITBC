"""Workflow command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
        workflow_parser = subparsers.add_parser("workflow", help="Workflow templates and execution")
        workflow_parser.set_defaults(handler=lambda parsed, parser=workflow_parser: parser.print_help())
        workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_action")
    
        workflow_create_parser = workflow_subparsers.add_parser("create", help="Create a workflow")
        workflow_create_parser.add_argument("--name", required=True)
        workflow_create_parser.add_argument("--template")
        workflow_create_parser.add_argument("--config-file")
        workflow_create_parser.add_argument("--steps", type=int, default=5)
        workflow_create_parser.set_defaults(handler=ctx.handle_workflow_create)
    
        workflow_run_parser = workflow_subparsers.add_parser("run", help="Run a workflow")
        workflow_run_parser.add_argument("--name", required=True)
        workflow_run_parser.add_argument("--params")
        workflow_run_parser.add_argument("--async-exec", action="store_true")
        workflow_run_parser.set_defaults(handler=ctx.handle_workflow_action)
    
        workflow_schedule_parser = workflow_subparsers.add_parser("schedule", help="Schedule a workflow")
        workflow_schedule_parser.add_argument("--name")
        workflow_schedule_parser.add_argument("--cron", required=True)
        workflow_schedule_parser.add_argument("--command")
        workflow_schedule_parser.add_argument("--params")
        workflow_schedule_parser.set_defaults(handler=ctx.handle_workflow_schedule)
    
        workflow_monitor_parser = workflow_subparsers.add_parser("monitor", help="Monitor workflow execution")
        workflow_monitor_parser.add_argument("--name")
        workflow_monitor_parser.add_argument("--execution-id")
        workflow_monitor_parser.set_defaults(handler=ctx.handle_workflow_monitor)
