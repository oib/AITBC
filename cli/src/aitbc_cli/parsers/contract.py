"""Contract command registration for the unified CLI."""

import argparse

from parser_context import ParserContext


def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
    contract_parser = subparsers.add_parser("contract", help="Smart contract operations")
    contract_parser.set_defaults(handler=lambda parsed, parser=contract_parser: parser.print_help())
    contract_subparsers = contract_parser.add_subparsers(dest="contract_action")

    contract_list_parser = contract_subparsers.add_parser("list", help="List deployed contracts")
    contract_list_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
    contract_list_parser.set_defaults(handler=ctx.handle_contract_list)

    contract_deploy_parser = contract_subparsers.add_parser("deploy", help="Deploy a smart contract")
    contract_deploy_parser.add_argument("--name", required=True, help="Contract name")
    contract_deploy_parser.add_argument("--type", default="zk-verifier", help="Contract type (default: zk-verifier)")
    contract_deploy_parser.add_argument("--password", help="Wallet password")
    contract_deploy_parser.add_argument("--password-file", help="Wallet password file")
    contract_deploy_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
    contract_deploy_parser.set_defaults(handler=ctx.handle_contract_deploy)

    contract_call_parser = contract_subparsers.add_parser("call", help="Call a contract method")
    contract_call_parser.add_argument("--address", required=True, help="Contract address")
    contract_call_parser.add_argument("--method", required=True, help="Method name")
    contract_call_parser.add_argument("--params", help="Method parameters (JSON)")
    contract_call_parser.add_argument("--password", help="Wallet password")
    contract_call_parser.add_argument("--password-file", help="Wallet password file")
    contract_call_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
    contract_call_parser.set_defaults(handler=ctx.handle_contract_call)

    contract_verify_parser = contract_subparsers.add_parser("verify", help="Verify a ZK proof against a contract")
    contract_verify_parser.add_argument("--address", required=True, help="Contract address")
    contract_verify_parser.add_argument("--proof-file", help="Proof data file (JSON)")
    contract_verify_parser.add_argument("--password", help="Wallet password")
    contract_verify_parser.add_argument("--password-file", help="Wallet password file")
    contract_verify_parser.add_argument("--rpc-url", default=ctx.default_rpc_url)
    contract_verify_parser.set_defaults(handler=ctx.handle_contract_verify)
