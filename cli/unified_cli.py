import argparse
import json
import os
import sys
from urllib.parse import urlparse

import requests

# Import command handlers
from handlers import market as market_handlers
from handlers import wallet as wallet_handlers
from handlers import blockchain as blockchain_handlers
from handlers import messaging as messaging_handlers
from handlers import network as network_handlers
from handlers import ai as ai_handlers
from handlers import system as system_handlers
from handlers import pool_hub as pool_hub_handlers
from handlers import bridge as bridge_handlers
from handlers import account as account_handlers


def run_cli(argv, core):
    import sys
    raw_args = sys.argv[1:] if argv is None else argv
    
    # Extended features interception removed - replaced with actual RPC calls
    
    default_rpc_url = core["DEFAULT_RPC_URL"]
    default_coordinator_url = core.get("DEFAULT_COORDINATOR_URL", "http://localhost:8000")
    cli_version = core.get("CLI_VERSION", "0.0.0")
    create_wallet = core["create_wallet"]
    list_wallets = core["list_wallets"]
    get_balance = core["get_balance"]
    get_transactions = core["get_transactions"]
    send_transaction = core["send_transaction"]
    import_wallet = core["import_wallet"]
    export_wallet = core["export_wallet"]
    delete_wallet = core["delete_wallet"]
    rename_wallet = core["rename_wallet"]
    send_batch_transactions = core["send_batch_transactions"]
    get_chain_info = core["get_chain_info"]
    get_blockchain_analytics = core["get_blockchain_analytics"]
    marketplace_operations = core["marketplace_operations"]
    ai_operations = core["ai_operations"]
    mining_operations = core["mining_operations"]
    agent_operations = core["agent_operations"]
    openclaw_operations = core["openclaw_operations"]
    workflow_operations = core["workflow_operations"]
    resource_operations = core["resource_operations"]
    simulate_blockchain = core["simulate_blockchain"]
    simulate_wallets = core["simulate_wallets"]
    simulate_price = core["simulate_price"]
    simulate_network = core["simulate_network"]
    simulate_ai_jobs = core["simulate_ai_jobs"]

    def first(*values):
        for value in values:
            if value not in (None, "", False):
                return value
        return None

    def extract_option(parts, option):
        if option not in parts:
            return None
        index = parts.index(option)
        if index + 1 < len(parts):
            value = parts[index + 1]
            del parts[index:index + 2]
            return value
        del parts[index:index + 1]
        return None

    def read_password(args, positional_name=None):
        positional_value = getattr(args, positional_name, None) if positional_name else None
        if positional_value:
            return positional_value
        if getattr(args, "password", None):
            return args.password
        if getattr(args, "password_file", None):
            with open(args.password_file) as handle:
                return handle.read().strip()
        return None

    def output_format(args, default="table"):
        explicit_output = getattr(args, "output", None)
        if explicit_output not in (None, "", default):
            return explicit_output
        return first(getattr(args, "format", None), explicit_output, default)

    def render_mapping(title, mapping):
        print(title)
        for key, value in mapping.items():
            if key == "action":
                continue
            if isinstance(value, list):
                print(f"  {key.replace('_', ' ').title()}:")
                for item in value:
                    print(f"    - {item}")
            else:
                print(f"  {key.replace('_', ' ').title()}: {value}")

    def read_blockchain_env(path="/etc/aitbc/blockchain.env"):
        config = {}
        try:
            with open(path) as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
        except OSError:
            return {}
        return config

    def normalize_rpc_url(rpc_url):
        parsed = urlparse(rpc_url if "://" in rpc_url else f"http://{rpc_url}")
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if scheme == "https" else 80)
        return f"{scheme}://{host}:{port}", host, port

    def probe_rpc_node(name, rpc_url, chain_id=None):
        base_url, _, _ = normalize_rpc_url(rpc_url)
        health = None
        head = None
        error = None
        latency_ms = None

        try:
            health_response = requests.get(f"{base_url}/health", timeout=5)
            latency_ms = round(health_response.elapsed.total_seconds() * 1000, 1)
            if health_response.status_code == 200:
                health = health_response.json()
                if chain_id is None:
                    supported_chains = health.get("supported_chains", [])
                    if isinstance(supported_chains, str):
                        supported_chains = [chain.strip() for chain in supported_chains.split(",") if chain.strip()]
                    if supported_chains:
                        chain_id = supported_chains[0]
            else:
                error = f"health returned {health_response.status_code}"
        except Exception as exc:
            error = str(exc)

        head_url = f"{base_url}/rpc/head"
        if chain_id:
            head_url = f"{head_url}?chain_id={chain_id}"

        try:
            head_response = requests.get(head_url, timeout=5)
            if head_response.status_code == 200:
                head = head_response.json()
            elif head_response.status_code != 404 and error is None:
                error = f"head returned {head_response.status_code}"
        except Exception as exc:
            if error is None:
                error = str(exc)

        return {
            "name": name,
            "rpc_url": base_url,
            "healthy": health is not None,
            "height": head.get("height") if head else None,
            "timestamp": head.get("timestamp") if head else None,
            "chain_id": chain_id,
            "error": error,
            "latency_ms": latency_ms,
        }

    def get_network_snapshot(rpc_url):
        env_config = read_blockchain_env()
        local_url, local_host, local_port = normalize_rpc_url(rpc_url)
        local_name = env_config.get("p2p_node_id") or local_host or "local"
        local_chain_id = env_config.get("chain_id") or None
        nodes = [probe_rpc_node(local_name, local_url, chain_id=local_chain_id)]

        peer_rpc_port_value = env_config.get("rpc_bind_port")
        try:
            peer_rpc_port = int(peer_rpc_port_value) if peer_rpc_port_value else local_port
        except ValueError:
            peer_rpc_port = local_port

        seen_urls = {nodes[0]["rpc_url"]}
        peers_raw = env_config.get("p2p_peers", "")
        for peer in [item.strip() for item in peers_raw.split(",") if item.strip()]:
            peer_host = peer.rsplit(":", 1)[0]
            peer_url = f"http://{peer_host}:{peer_rpc_port}"
            normalized_peer_url, _, _ = normalize_rpc_url(peer_url)
            if normalized_peer_url in seen_urls:
                continue
            seen_urls.add(normalized_peer_url)
            nodes.append(probe_rpc_node(peer_host, normalized_peer_url, chain_id=local_chain_id))

        reachable_nodes = [node for node in nodes if node["healthy"]]
        heights = [node["height"] for node in reachable_nodes if node["height"] is not None]
        if len(nodes) <= 1:
            sync_status = "standalone"
        elif len(reachable_nodes) != len(nodes):
            sync_status = "degraded"
        elif len(heights) == len(nodes) and len(set(heights)) == 1:
            sync_status = "synchronized"
        else:
            sync_status = "syncing"

        return {
            "nodes": nodes,
            "connected_count": len(reachable_nodes),
            "sync_status": sync_status,
        }

    def normalize_legacy_args(raw_args):
        if not raw_args:
            return raw_args

        normalized = list(raw_args)
        command = normalized[0]
        rest = normalized[1:]

        direct_map = {
            "create": ["wallet", "create"],
            "list": ["wallet", "list"],
            "balance": ["wallet", "balance"],
            "transactions": ["wallet", "transactions"],
            "send": ["wallet", "send"],
            "import": ["wallet", "import"],
            "export": ["wallet", "export"],
            "delete": ["wallet", "delete"],
            "rename": ["wallet", "rename"],
            "batch": ["wallet", "batch"],
            "all-balances": ["wallet", "balance", "--all"],
            "chain": ["blockchain", "info"],
            "market-list": ["market", "list"],
            "market-create": ["market", "create"],
            "ai-submit": ["ai", "submit"],
            "wallet-backup": ["wallet", "backup"],
            "wallet-export": ["wallet", "export"],
            "wallet-sync": ["wallet", "sync"],
            "mine-start": ["mining", "start"],
            "mine-stop": ["mining", "stop"],
            "mine-status": ["mining", "status"],
        }

        if command in direct_map:
            return [*direct_map[command], *rest]

        if command == "marketplace":
            action = extract_option(rest, "--action")
            return ["market", *([action] if action else []), *rest]

        if command == "ai-ops":
            action = extract_option(rest, "--action")
            return ["ai", *([action] if action else []), *rest]

        if command == "mining":
            action = extract_option(rest, "--action")
            if action:
                return ["mining", action, *rest]
            for flag, mapped_action in (("--start", "start"), ("--stop", "stop"), ("--status", "status")):
                if flag in rest:
                    rest.remove(flag)
                    return ["mining", mapped_action, *rest]
            return normalized

        if command == "system" and "--status" in rest:
            rest.remove("--status")
            return ["system", "status", *rest]

        return normalized

    def handle_wallet_create(args):
        wallet_handlers.handle_wallet_create(args, create_wallet, read_password, first)

    def handle_wallet_list(args):
        wallet_handlers.handle_wallet_list(args, list_wallets, output_format)

    def handle_wallet_balance(args):
        wallet_handlers.handle_wallet_balance(args, default_rpc_url, list_wallets, get_balance, first)

    def handle_wallet_transactions(args):
        wallet_handlers.handle_wallet_transactions(args, get_transactions, output_format, first)

    def handle_wallet_send(args):
        wallet_handlers.handle_wallet_send(args, send_transaction, read_password, first)

    def handle_wallet_import(args):
        wallet_handlers.handle_wallet_import(args, import_wallet, read_password, first)

    def handle_wallet_export(args):
        wallet_handlers.handle_wallet_export(args, export_wallet, read_password, first)

    def handle_wallet_delete(args):
        wallet_handlers.handle_wallet_delete(args, delete_wallet, first)

    def handle_wallet_rename(args):
        wallet_handlers.handle_wallet_rename(args, rename_wallet, first)

    def handle_wallet_backup(args):
        wallet_handlers.handle_wallet_backup(args, first)

    def handle_wallet_sync(args):
        wallet_handlers.handle_wallet_sync(args, first)

    def handle_wallet_batch(args):
        wallet_handlers.handle_wallet_batch(args, send_batch_transactions, read_password)

    def handle_blockchain_info(args):
        blockchain_handlers.handle_blockchain_info(args, get_chain_info, render_mapping)

    def handle_blockchain_height(args):
        blockchain_handlers.handle_blockchain_height(args, get_chain_info)

    def handle_blockchain_block(args):
        blockchain_handlers.handle_blockchain_block(args)

    def handle_blockchain_init(args):
        blockchain_handlers.handle_blockchain_init(args, default_rpc_url)

    def handle_blockchain_genesis(args):
        blockchain_handlers.handle_blockchain_genesis(args, default_rpc_url)

    def handle_blockchain_import(args):
        blockchain_handlers.handle_blockchain_import(args, default_rpc_url, render_mapping)

    def handle_blockchain_export(args):
        blockchain_handlers.handle_blockchain_export(args, default_rpc_url)

    def handle_blockchain_import_chain(args):
        blockchain_handlers.handle_blockchain_import_chain(args, default_rpc_url, render_mapping)

    def handle_blockchain_blocks_range(args):
        blockchain_handlers.handle_blockchain_blocks_range(args, default_rpc_url, output_format)

    def handle_blockchain_transactions(args):
        blockchain_handlers.handle_blockchain_transactions(args, default_rpc_url)

    def handle_blockchain_mempool(args):
        blockchain_handlers.handle_blockchain_mempool(args, default_rpc_url)

    def handle_messaging_deploy(args):
        messaging_handlers.handle_messaging_deploy(args, default_rpc_url, render_mapping)

    def handle_messaging_state(args):
        messaging_handlers.handle_messaging_state(args, default_rpc_url, output_format, render_mapping)

    def handle_messaging_topics(args):
        messaging_handlers.handle_messaging_topics(args, default_rpc_url, output_format, render_mapping)

    def handle_messaging_create_topic(args):
        messaging_handlers.handle_messaging_create_topic(args, default_rpc_url, read_password, render_mapping)

    def handle_messaging_messages(args):
        messaging_handlers.handle_messaging_messages(args, default_rpc_url, output_format, render_mapping)

    def handle_messaging_post(args):
        messaging_handlers.handle_messaging_post(args, default_rpc_url, read_password, render_mapping)

    def handle_messaging_vote(args):
        messaging_handlers.handle_messaging_vote(args, default_rpc_url, read_password, render_mapping)

    def handle_messaging_search(args):
        messaging_handlers.handle_messaging_search(args, default_rpc_url, output_format, render_mapping)

    def handle_messaging_reputation(args):
        messaging_handlers.handle_messaging_reputation(args, default_rpc_url, output_format, render_mapping)

    def handle_messaging_moderate(args):
        messaging_handlers.handle_messaging_moderate(args, default_rpc_url, read_password, render_mapping)

    def handle_network_status(args):
        network_handlers.handle_network_status(args, default_rpc_url, get_network_snapshot)

    def handle_network_peers(args):
        network_handlers.handle_network_peers(args, default_rpc_url, get_network_snapshot)

    def handle_network_sync(args):
        network_handlers.handle_network_sync(args, default_rpc_url, get_network_snapshot)

    def handle_network_ping(args):
        network_handlers.handle_network_ping(args, default_rpc_url, read_blockchain_env, normalize_rpc_url, first, probe_rpc_node)

    def handle_network_propagate(args):
        network_handlers.handle_network_propagate(args, default_rpc_url, get_network_snapshot, first)

    def handle_network_force_sync(args):
        network_handlers.handle_network_force_sync(args, default_rpc_url, render_mapping)

    def handle_market_listings(args):
        market_handlers.handle_market_listings(args, default_coordinator_url, output_format, render_mapping)

    def handle_market_create(args):
        market_handlers.handle_market_create(args, default_coordinator_url, read_password, render_mapping)

    def handle_market_get(args):
        market_handlers.handle_market_get(args, default_rpc_url)

    def handle_market_delete(args):
        market_handlers.handle_market_delete(args, default_coordinator_url, read_password, render_mapping)

    def handle_market_gpu_register(args):
        market_handlers.handle_market_gpu_register(args, default_coordinator_url)

    def handle_market_gpu_list(args):
        market_handlers.handle_market_gpu_list(args, default_coordinator_url, output_format)

    def handle_ai_submit(args):
        ai_handlers.handle_ai_submit(args, default_rpc_url, first, read_password, render_mapping)

    def handle_ai_jobs(args):
        ai_handlers.handle_ai_jobs(args, default_rpc_url, output_format, render_mapping)

    def handle_ai_job(args):
        ai_handlers.handle_ai_job(args, default_rpc_url, output_format, render_mapping, first)

    def handle_ai_cancel(args):
        ai_handlers.handle_ai_cancel(args, default_rpc_url, read_password, render_mapping, first)

    def handle_ai_stats(args):
        ai_handlers.handle_ai_stats(args, default_rpc_url, output_format, render_mapping)

    def handle_ai_service_list(args):
        ai_handlers.handle_ai_service_list(args, ai_operations, render_mapping)

    def handle_ai_service_status(args):
        ai_handlers.handle_ai_service_status(args, ai_operations, render_mapping)

    def handle_ai_service_test(args):
        ai_handlers.handle_ai_service_test(args, ai_operations, render_mapping)

    def handle_economics_action(args):
        system_handlers.handle_economics_action(args, render_mapping)

    def handle_cluster_action(args):
        system_handlers.handle_cluster_action(args, render_mapping)

    def handle_performance_action(args):
        system_handlers.handle_performance_action(args, render_mapping)

    def handle_security_action(args):
        system_handlers.handle_security_action(args, render_mapping)

    def handle_mining_action(args):
        system_handlers.handle_mining_action(args, default_rpc_url, mining_operations)

    def handle_system_status(args):
        system_handlers.handle_system_status(args, cli_version)

    def handle_analytics(args):
        system_handlers.handle_analytics(args, default_rpc_url, get_blockchain_analytics)

    def handle_agent_action(args):
        system_handlers.handle_agent_action(args, agent_operations, render_mapping)

    def handle_openclaw_action(args):
        system_handlers.handle_openclaw_action(args, openclaw_operations, first, render_mapping)

    def handle_workflow_action(args):
        system_handlers.handle_workflow_action(args, workflow_operations, render_mapping)

    def handle_resource_action(args):
        system_handlers.handle_resource_action(args, resource_operations, render_mapping)

    def handle_simulate_action(args):
        system_handlers.handle_simulate_action(args, simulate_blockchain, simulate_wallets, simulate_price, simulate_network, simulate_ai_jobs)

    def handle_account_get(args):
        account_handlers.handle_account_get(args, default_rpc_url, output_format)

    def handle_pool_hub_sla_metrics(args):
        pool_hub_handlers.handle_pool_hub_sla_metrics(args)

    def handle_pool_hub_sla_violations(args):
        pool_hub_handlers.handle_pool_hub_sla_violations(args)

    def handle_pool_hub_capacity_snapshots(args):
        pool_hub_handlers.handle_pool_hub_capacity_snapshots(args)

    def handle_pool_hub_capacity_forecast(args):
        pool_hub_handlers.handle_pool_hub_capacity_forecast(args)

    def handle_pool_hub_capacity_recommendations(args):
        pool_hub_handlers.handle_pool_hub_capacity_recommendations(args)

    def handle_pool_hub_billing_usage(args):
        pool_hub_handlers.handle_pool_hub_billing_usage(args)

    def handle_pool_hub_billing_sync(args):
        pool_hub_handlers.handle_pool_hub_billing_sync(args)

    def handle_pool_hub_collect_metrics(args):
        pool_hub_handlers.handle_pool_hub_collect_metrics(args)

    def handle_bridge_health(args):
        bridge_handlers.handle_bridge_health(args)

    def handle_bridge_metrics(args):
        bridge_handlers.handle_bridge_metrics(args)

    def handle_bridge_status(args):
        bridge_handlers.handle_bridge_status(args)

    def handle_bridge_config(args):
        bridge_handlers.handle_bridge_config(args)

    def handle_bridge_restart(args):
        bridge_handlers.handle_bridge_restart(args)

    parser = argparse.ArgumentParser(
        description="AITBC CLI - Comprehensive Blockchain Management Tool",
        epilog="Examples: aitbc wallet create demo secret | aitbc wallet balance demo | aitbc ai submit --wallet demo --type text-generation --prompt 'hello' --payment 1",
    )
    parser.add_argument("--version", action="version", version=f"aitbc-cli {cli_version}")
    parser.add_argument("--output", choices=["table", "json", "yaml"], default="table")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    wallet_parser = subparsers.add_parser("wallet", help="Wallet lifecycle, balances, and transactions")
    wallet_parser.set_defaults(handler=lambda parsed, parser=wallet_parser: parser.print_help())
    wallet_subparsers = wallet_parser.add_subparsers(dest="wallet_action")

    wallet_create_parser = wallet_subparsers.add_parser("create", help="Create a wallet")
    wallet_create_parser.add_argument("wallet_name", nargs="?")
    wallet_create_parser.add_argument("wallet_password", nargs="?")
    wallet_create_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
    wallet_create_parser.add_argument("--password")
    wallet_create_parser.add_argument("--password-file")
    wallet_create_parser.set_defaults(handler=handle_wallet_create)

    wallet_list_parser = wallet_subparsers.add_parser("list", help="List wallets")
    wallet_list_parser.add_argument("--format", choices=["table", "json"], default="table")
    wallet_list_parser.set_defaults(handler=handle_wallet_list)

    wallet_balance_parser = wallet_subparsers.add_parser("balance", help="Show wallet balance")
    wallet_balance_parser.add_argument("wallet_name", nargs="?")
    wallet_balance_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
    wallet_balance_parser.add_argument("--all", action="store_true")
    wallet_balance_parser.add_argument("--rpc-url", default=default_rpc_url)
    wallet_balance_parser.add_argument("--chain-id", help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
    wallet_balance_parser.set_defaults(handler=handle_wallet_balance)

    wallet_transactions_parser = wallet_subparsers.add_parser("transactions", help="Show wallet transactions")
    wallet_transactions_parser.add_argument("wallet_name", nargs="?")
    wallet_transactions_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
    wallet_transactions_parser.add_argument("--limit", type=int, default=10)
    wallet_transactions_parser.add_argument("--format", choices=["table", "json"], default="table")
    wallet_transactions_parser.add_argument("--rpc-url", default=default_rpc_url)
    wallet_transactions_parser.set_defaults(handler=handle_wallet_transactions)

    wallet_send_parser = wallet_subparsers.add_parser("send", help="Send AIT")
    wallet_send_parser.add_argument("from_wallet_arg", nargs="?")
    wallet_send_parser.add_argument("to_address_arg", nargs="?")
    wallet_send_parser.add_argument("amount_arg", nargs="?")
    wallet_send_parser.add_argument("wallet_password", nargs="?")
    wallet_send_parser.add_argument("--from", dest="from_wallet", help=argparse.SUPPRESS)
    wallet_send_parser.add_argument("--to", dest="to_address", help=argparse.SUPPRESS)
    wallet_send_parser.add_argument("--amount", type=float)
    wallet_send_parser.add_argument("--fee", type=float, default=10.0)
    wallet_send_parser.add_argument("--password")
    wallet_send_parser.add_argument("--password-file")
    wallet_send_parser.add_argument("--rpc-url", default=default_rpc_url)
    wallet_send_parser.set_defaults(handler=handle_wallet_send)

    wallet_import_parser = wallet_subparsers.add_parser("import", help="Import a wallet")
    wallet_import_parser.add_argument("wallet_name", nargs="?")
    wallet_import_parser.add_argument("private_key_arg", nargs="?")
    wallet_import_parser.add_argument("wallet_password", nargs="?")
    wallet_import_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
    wallet_import_parser.add_argument("--private-key", dest="private_key_opt")
    wallet_import_parser.add_argument("--password")
    wallet_import_parser.add_argument("--password-file")
    wallet_import_parser.set_defaults(handler=handle_wallet_import)

    wallet_export_parser = wallet_subparsers.add_parser("export", help="Export a wallet")
    wallet_export_parser.add_argument("wallet_name", nargs="?")
    wallet_export_parser.add_argument("wallet_password", nargs="?")
    wallet_export_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
    wallet_export_parser.add_argument("--password")
    wallet_export_parser.add_argument("--password-file")
    wallet_export_parser.set_defaults(handler=handle_wallet_export)

    wallet_delete_parser = wallet_subparsers.add_parser("delete", help="Delete a wallet")
    wallet_delete_parser.add_argument("wallet_name", nargs="?")
    wallet_delete_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
    wallet_delete_parser.add_argument("--confirm", action="store_true")
    wallet_delete_parser.set_defaults(handler=handle_wallet_delete)

    wallet_rename_parser = wallet_subparsers.add_parser("rename", help="Rename a wallet")
    wallet_rename_parser.add_argument("old_name_arg", nargs="?")
    wallet_rename_parser.add_argument("new_name_arg", nargs="?")
    wallet_rename_parser.add_argument("--old", dest="old_name", help=argparse.SUPPRESS)
    wallet_rename_parser.add_argument("--new", dest="new_name", help=argparse.SUPPRESS)
    wallet_rename_parser.set_defaults(handler=handle_wallet_rename)

    wallet_backup_parser = wallet_subparsers.add_parser("backup", help="Backup a wallet")
    wallet_backup_parser.add_argument("wallet_name", nargs="?")
    wallet_backup_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
    wallet_backup_parser.set_defaults(handler=handle_wallet_backup)

    wallet_sync_parser = wallet_subparsers.add_parser("sync", help="Sync wallets")
    wallet_sync_parser.add_argument("wallet_name", nargs="?")
    wallet_sync_parser.add_argument("--name", dest="wallet_name_opt", help=argparse.SUPPRESS)
    wallet_sync_parser.add_argument("--all", action="store_true")
    wallet_sync_parser.set_defaults(handler=handle_wallet_sync)

    wallet_batch_parser = wallet_subparsers.add_parser("batch", help="Send multiple transactions")
    wallet_batch_parser.add_argument("--file", required=True)
    wallet_batch_parser.add_argument("--password")
    wallet_batch_parser.add_argument("--password-file")
    wallet_batch_parser.add_argument("--rpc-url", default=default_rpc_url)
    wallet_batch_parser.set_defaults(handler=handle_wallet_batch)

    blockchain_parser = subparsers.add_parser("blockchain", help="Blockchain state and block inspection")
    blockchain_parser.set_defaults(handler=handle_blockchain_info, rpc_url=default_rpc_url)
    blockchain_subparsers = blockchain_parser.add_subparsers(dest="blockchain_action")

    blockchain_info_parser = blockchain_subparsers.add_parser("info", help="Show chain information")
    blockchain_info_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_info_parser.set_defaults(handler=handle_blockchain_info)

    blockchain_height_parser = blockchain_subparsers.add_parser("height", help="Show current height")
    blockchain_height_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_height_parser.set_defaults(handler=handle_blockchain_height)

    blockchain_block_parser = blockchain_subparsers.add_parser("block", help="Inspect a block")
    blockchain_block_parser.add_argument("number", nargs="?", type=int)
    blockchain_block_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_block_parser.set_defaults(handler=handle_blockchain_block)

    blockchain_init_parser = blockchain_subparsers.add_parser("init", help="Initialize blockchain with genesis block")
    blockchain_init_parser.add_argument("--force", action="store_true", help="Force reinitialization")
    blockchain_init_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_init_parser.set_defaults(handler=handle_blockchain_init)

    blockchain_genesis_parser = blockchain_subparsers.add_parser("genesis", help="Create or inspect genesis block")
    blockchain_genesis_parser.add_argument("--create", action="store_true", help="Create new genesis block")
    blockchain_genesis_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_genesis_parser.set_defaults(handler=handle_blockchain_genesis)

    blockchain_import_parser = blockchain_subparsers.add_parser("import", help="Import a block")
    blockchain_import_parser.add_argument("--file", help="Block data file")
    blockchain_import_parser.add_argument("--json", help="Block data as JSON string")
    blockchain_import_parser.add_argument("--chain-id", help="Chain ID for the block")
    blockchain_import_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_import_parser.set_defaults(handler=handle_blockchain_import)

    blockchain_export_parser = blockchain_subparsers.add_parser("export", help="Export full chain")
    blockchain_export_parser.add_argument("--output", help="Output file")
    blockchain_export_parser.add_argument("--chain-id", help="Chain ID to export")
    blockchain_export_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_export_parser.set_defaults(handler=handle_blockchain_export)

    blockchain_import_chain_parser = blockchain_subparsers.add_parser("import-chain", help="Import chain state")
    blockchain_import_chain_parser.add_argument("--file", required=True, help="Chain state file")
    blockchain_import_chain_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_import_chain_parser.set_defaults(handler=handle_blockchain_import_chain)

    blockchain_blocks_range_parser = blockchain_subparsers.add_parser("blocks-range", help="Get blocks in height range")
    blockchain_blocks_range_parser.add_argument("--start", type=int, help="Start height")
    blockchain_blocks_range_parser.add_argument("--end", type=int, help="End height")
    blockchain_blocks_range_parser.add_argument("--limit", type=int, default=10, help="Limit number of blocks")
    blockchain_blocks_range_parser.add_argument("--chain-id", help="Chain ID")
    blockchain_blocks_range_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_blocks_range_parser.set_defaults(handler=handle_blockchain_blocks_range)

    account_parser = subparsers.add_parser("account", help="Account information")
    account_parser.set_defaults(handler=lambda parsed, parser=account_parser: parser.print_help())
    account_subparsers = account_parser.add_subparsers(dest="account_action")

    account_get_parser = account_subparsers.add_parser("get", help="Get account information")
    account_get_parser.add_argument("--address", required=True, help="Account address")
    account_get_parser.add_argument("--chain-id", help="Chain ID")
    account_get_parser.add_argument("--rpc-url", default=default_rpc_url)
    account_get_parser.set_defaults(handler=handle_account_get)

    blockchain_transactions_parser = blockchain_subparsers.add_parser("transactions", help="Query transactions")
    blockchain_transactions_parser.add_argument("--address", help="Filter by address")
    blockchain_transactions_parser.add_argument("--limit", type=int, default=10)
    blockchain_transactions_parser.add_argument("--offset", type=int, default=0)
    blockchain_transactions_parser.add_argument("--chain-id", help="Chain ID")
    blockchain_transactions_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_transactions_parser.set_defaults(handler=handle_blockchain_transactions)

    blockchain_mempool_parser = blockchain_subparsers.add_parser("mempool", help="Get pending transactions")
    blockchain_mempool_parser.add_argument("--chain-id", help="Chain ID")
    blockchain_mempool_parser.add_argument("--rpc-url", default=default_rpc_url)
    blockchain_mempool_parser.set_defaults(handler=handle_blockchain_mempool)

    messaging_parser = subparsers.add_parser("messaging", help="Messaging system and forum")
    messaging_parser.set_defaults(handler=lambda parsed, parser=messaging_parser: parser.print_help())
    messaging_subparsers = messaging_parser.add_subparsers(dest="messaging_action")

    messaging_deploy_parser = messaging_subparsers.add_parser("deploy", help="Deploy messaging contract")
    messaging_deploy_parser.add_argument("--chain-id", help="Chain ID")
    messaging_deploy_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_deploy_parser.set_defaults(handler=handle_messaging_deploy)

    messaging_state_parser = messaging_subparsers.add_parser("state", help="Get contract state")
    messaging_state_parser.add_argument("--chain-id", help="Chain ID")
    messaging_state_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_state_parser.set_defaults(handler=handle_messaging_state)

    messaging_topics_parser = messaging_subparsers.add_parser("topics", help="List forum topics")
    messaging_topics_parser.add_argument("--chain-id", help="Chain ID")
    messaging_topics_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_topics_parser.set_defaults(handler=handle_messaging_topics)

    messaging_create_topic_parser = messaging_subparsers.add_parser("create-topic", help="Create forum topic")
    messaging_create_topic_parser.add_argument("--title", required=True, help="Topic title")
    messaging_create_topic_parser.add_argument("--content", required=True, help="Topic content")
    messaging_create_topic_parser.add_argument("--wallet", help="Wallet address for authentication")
    messaging_create_topic_parser.add_argument("--password")
    messaging_create_topic_parser.add_argument("--password-file")
    messaging_create_topic_parser.add_argument("--chain-id", help="Chain ID")
    messaging_create_topic_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_create_topic_parser.set_defaults(handler=handle_messaging_create_topic)

    messaging_messages_parser = messaging_subparsers.add_parser("messages", help="Get topic messages")
    messaging_messages_parser.add_argument("--topic-id", required=True, help="Topic ID")
    messaging_messages_parser.add_argument("--chain-id", help="Chain ID")
    messaging_messages_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_messages_parser.set_defaults(handler=handle_messaging_messages)

    messaging_post_parser = messaging_subparsers.add_parser("post", help="Post message")
    messaging_post_parser.add_argument("--topic-id", required=True, help="Topic ID")
    messaging_post_parser.add_argument("--content", required=True, help="Message content")
    messaging_post_parser.add_argument("--wallet", help="Wallet address for authentication")
    messaging_post_parser.add_argument("--password")
    messaging_post_parser.add_argument("--password-file")
    messaging_post_parser.add_argument("--chain-id", help="Chain ID")
    messaging_post_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_post_parser.set_defaults(handler=handle_messaging_post)

    messaging_vote_parser = messaging_subparsers.add_parser("vote", help="Vote on message")
    messaging_vote_parser.add_argument("--message-id", required=True, help="Message ID")
    messaging_vote_parser.add_argument("--vote", required=True, help="Vote (up/down)")
    messaging_vote_parser.add_argument("--wallet", help="Wallet address for authentication")
    messaging_vote_parser.add_argument("--password")
    messaging_vote_parser.add_argument("--password-file")
    messaging_vote_parser.add_argument("--chain-id", help="Chain ID")
    messaging_vote_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_vote_parser.set_defaults(handler=handle_messaging_vote)

    messaging_search_parser = messaging_subparsers.add_parser("search", help="Search messages")
    messaging_search_parser.add_argument("--query", required=True, help="Search query")
    messaging_search_parser.add_argument("--chain-id", help="Chain ID")
    messaging_search_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_search_parser.set_defaults(handler=handle_messaging_search)

    messaging_reputation_parser = messaging_subparsers.add_parser("reputation", help="Get agent reputation")
    messaging_reputation_parser.add_argument("--agent-id", required=True, help="Agent ID")
    messaging_reputation_parser.add_argument("--chain-id", help="Chain ID")
    messaging_reputation_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_reputation_parser.set_defaults(handler=handle_messaging_reputation)

    messaging_moderate_parser = messaging_subparsers.add_parser("moderate", help="Moderate message")
    messaging_moderate_parser.add_argument("--message-id", required=True, help="Message ID")
    messaging_moderate_parser.add_argument("--action", required=True, help="Action (approve/reject)")
    messaging_moderate_parser.add_argument("--wallet", help="Wallet address for authentication")
    messaging_moderate_parser.add_argument("--password")
    messaging_moderate_parser.add_argument("--password-file")
    messaging_moderate_parser.add_argument("--chain-id", help="Chain ID")
    messaging_moderate_parser.add_argument("--rpc-url", default=default_rpc_url)
    messaging_moderate_parser.set_defaults(handler=handle_messaging_moderate)

    network_parser = subparsers.add_parser("network", help="Peer connectivity and sync")
    network_parser.set_defaults(handler=handle_network_status)
    network_subparsers = network_parser.add_subparsers(dest="network_action")

    network_status_parser = network_subparsers.add_parser("status", help="Show network status")
    network_status_parser.add_argument("--rpc-url", default=default_rpc_url)
    network_status_parser.set_defaults(handler=handle_network_status)

    network_peers_parser = network_subparsers.add_parser("peers", help="List peers")
    network_peers_parser.add_argument("--rpc-url", default=default_rpc_url)
    network_peers_parser.set_defaults(handler=handle_network_peers)

    network_sync_parser = network_subparsers.add_parser("sync", help="Show sync status")
    network_sync_parser.add_argument("--rpc-url", default=default_rpc_url)
    network_sync_parser.set_defaults(handler=handle_network_sync)

    network_ping_parser = network_subparsers.add_parser("ping", help="Ping a node")
    network_ping_parser.add_argument("node", nargs="?")
    network_ping_parser.add_argument("--node", dest="node_opt", help=argparse.SUPPRESS)
    network_ping_parser.add_argument("--rpc-url", default=default_rpc_url)
    network_ping_parser.set_defaults(handler=handle_network_ping)

    network_propagate_parser = network_subparsers.add_parser("propagate", help="Propagate test data")
    network_propagate_parser.add_argument("data", nargs="?")
    network_propagate_parser.add_argument("--data", dest="data_opt", help=argparse.SUPPRESS)
    network_propagate_parser.add_argument("--rpc-url", default=default_rpc_url)
    network_propagate_parser.set_defaults(handler=handle_network_propagate)

    network_force_sync_parser = network_subparsers.add_parser("force-sync", help="Force reorg to specified peer")
    network_force_sync_parser.add_argument("--peer", required=True, help="Peer to sync from")
    network_force_sync_parser.add_argument("--chain-id", help="Chain ID")
    network_force_sync_parser.add_argument("--rpc-url", default=default_rpc_url)
    network_force_sync_parser.set_defaults(handler=handle_network_force_sync)

    market_parser = subparsers.add_parser("market", help="Marketplace listings and offers")
    market_parser.set_defaults(handler=lambda parsed, parser=market_parser: parser.print_help())
    market_subparsers = market_parser.add_subparsers(dest="market_action")

    # GPU marketplace subcommands
    market_gpu_parser = market_subparsers.add_parser("gpu", help="GPU marketplace operations")
    market_gpu_parser.set_defaults(handler=lambda parsed, parser=market_gpu_parser: parser.print_help())
    market_gpu_subparsers = market_gpu_parser.add_subparsers(dest="gpu_action")

    market_gpu_register_parser = market_gpu_subparsers.add_parser("register", help="Register GPU on marketplace")
    market_gpu_register_parser.add_argument("--name", help="GPU name/model")
    market_gpu_register_parser.add_argument("--memory", type=int, help="GPU memory in GB")
    market_gpu_register_parser.add_argument("--cuda-cores", type=int, help="Number of CUDA cores")
    market_gpu_register_parser.add_argument("--compute-capability", help="Compute capability (e.g., 8.9)")
    market_gpu_register_parser.add_argument("--price-per-hour", type=float, required=True, help="Price per hour in AIT")
    market_gpu_register_parser.add_argument("--description", help="GPU description")
    market_gpu_register_parser.add_argument("--miner-id", help="Miner ID")
    market_gpu_register_parser.add_argument("--force", action="store_true", help="Force registration without hardware validation")
    market_gpu_register_parser.add_argument("--coordinator-url", default=default_coordinator_url)
    market_gpu_register_parser.set_defaults(handler=handle_market_gpu_register)

    market_gpu_list_parser = market_gpu_subparsers.add_parser("list", help="List available GPUs")
    market_gpu_list_parser.add_argument("--available", action="store_true", help="Show only available GPUs")
    market_gpu_list_parser.add_argument("--price-max", type=float, help="Maximum price per hour")
    market_gpu_list_parser.add_argument("--region", help="Filter by region")
    market_gpu_list_parser.add_argument("--model", help="Filter by GPU model")
    market_gpu_list_parser.add_argument("--limit", type=int, default=100, help="Maximum number of results")
    market_gpu_list_parser.add_argument("--coordinator-url", default=default_coordinator_url)
    market_gpu_list_parser.set_defaults(handler=handle_market_gpu_list)

    market_list_parser = market_subparsers.add_parser("list", help="List marketplace items")
    market_list_parser.add_argument("--chain-id", help="Chain ID")
    market_list_parser.add_argument("--coordinator-url", default=default_coordinator_url)
    market_list_parser.set_defaults(handler=handle_market_listings)

    market_create_parser = market_subparsers.add_parser("create", help="Create a marketplace listing")
    market_create_parser.add_argument("--wallet", required=True)
    market_create_parser.add_argument("--type", dest="item_type", required=True)
    market_create_parser.add_argument("--price", type=float, required=True)
    market_create_parser.add_argument("--description")
    market_create_parser.add_argument("--password")
    market_create_parser.add_argument("--password-file")
    market_create_parser.add_argument("--chain-id", help="Chain ID")
    market_create_parser.add_argument("--coordinator-url", default=default_coordinator_url)
    market_create_parser.set_defaults(handler=handle_market_create)

    market_search_parser = market_subparsers.add_parser("search", help="Search marketplace items")
    market_search_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_search_parser.set_defaults(handler=handle_market_listings)  # Reuse listings for now

    market_mine_parser = market_subparsers.add_parser("my-listings", help="Show your marketplace listings")
    market_mine_parser.add_argument("--wallet")
    market_mine_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_mine_parser.set_defaults(handler=handle_market_listings)  # Reuse listings for now

    market_get_parser = market_subparsers.add_parser("get", help="Get listing by ID")
    market_get_parser.add_argument("--listing-id", required=True)
    market_get_parser.add_argument("--chain-id", help="Chain ID")
    market_get_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_get_parser.set_defaults(handler=handle_market_get)

    market_delete_parser = market_subparsers.add_parser("delete", help="Delete listing")
    market_delete_parser.add_argument("--listing-id", required=True)
    market_delete_parser.add_argument("--wallet", required=True)
    market_delete_parser.add_argument("--password")
    market_delete_parser.add_argument("--password-file")
    market_delete_parser.add_argument("--chain-id", help="Chain ID")
    market_delete_parser.add_argument("--coordinator-url", default=default_coordinator_url)
    market_delete_parser.set_defaults(handler=handle_market_delete)

    market_buy_parser = market_subparsers.add_parser("buy", help="Buy from marketplace")
    market_buy_parser.add_argument("--item", required=True)
    market_buy_parser.add_argument("--wallet", required=True)
    market_buy_parser.add_argument("--password")
    market_buy_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_buy_parser.set_defaults(handler=handle_market_listings)  # Placeholder

    market_sell_parser = market_subparsers.add_parser("sell", help="Sell on marketplace")
    market_sell_parser.add_argument("--item", required=True)
    market_sell_parser.add_argument("--price", type=float, required=True)
    market_sell_parser.add_argument("--wallet", required=True)
    market_sell_parser.add_argument("--password")
    market_sell_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_sell_parser.set_defaults(handler=handle_market_create)  # Reuse create

    market_orders_parser = market_subparsers.add_parser("orders", help="Show marketplace orders")
    market_orders_parser.add_argument("--wallet")
    market_orders_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_orders_parser.set_defaults(handler=handle_market_listings)  # Reuse listings for now

    ai_parser = subparsers.add_parser("ai", help="AI job submission and inspection")
    ai_parser.set_defaults(handler=lambda parsed, parser=ai_parser: parser.print_help())
    ai_subparsers = ai_parser.add_subparsers(dest="ai_action")

    ai_submit_parser = ai_subparsers.add_parser("submit", help="Submit an AI job")
    ai_submit_parser.add_argument("wallet_name", nargs="?")
    ai_submit_parser.add_argument("job_type_arg", nargs="?")
    ai_submit_parser.add_argument("prompt_arg", nargs="?")
    ai_submit_parser.add_argument("payment_arg", nargs="?")
    ai_submit_parser.add_argument("--wallet")
    ai_submit_parser.add_argument("--type", dest="job_type")
    ai_submit_parser.add_argument("--prompt")
    ai_submit_parser.add_argument("--payment", type=float)
    ai_submit_parser.add_argument("--password")
    ai_submit_parser.add_argument("--password-file")
    ai_submit_parser.add_argument("--chain-id", help="Chain ID")
    ai_submit_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_submit_parser.set_defaults(handler=handle_ai_submit)

    ai_jobs_parser = ai_subparsers.add_parser("jobs", help="List AI jobs")
    ai_jobs_parser.add_argument("--limit", type=int, default=10)
    ai_jobs_parser.add_argument("--chain-id", help="Chain ID")
    ai_jobs_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_jobs_parser.set_defaults(handler=handle_ai_jobs)

    ai_status_parser = ai_subparsers.add_parser("status", help="Show AI job status")
    ai_status_parser.add_argument("job_id_arg", nargs="?")
    ai_status_parser.add_argument("--job-id", dest="job_id")
    ai_status_parser.add_argument("--wallet")
    ai_status_parser.add_argument("--chain-id", help="Chain ID")
    ai_status_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_status_parser.set_defaults(handler=handle_ai_job)

    ai_service_parser = ai_subparsers.add_parser("service", help="AI service management")
    ai_service_subparsers = ai_service_parser.add_subparsers(dest="ai_service_action")

    ai_service_list_parser = ai_service_subparsers.add_parser("list", help="List available AI services")
    ai_service_list_parser.set_defaults(handler=handle_ai_service_list)

    ai_service_status_parser = ai_service_subparsers.add_parser("status", help="Check AI service status")
    ai_service_status_parser.add_argument("--name", help="Service name to check")
    ai_service_status_parser.set_defaults(handler=handle_ai_service_status)

    ai_service_test_parser = ai_service_subparsers.add_parser("test", help="Test AI service endpoint")
    ai_service_test_parser.add_argument("--name", help="Service name to test")
    ai_service_test_parser.set_defaults(handler=handle_ai_service_test)

    ai_results_parser = ai_subparsers.add_parser("results", help="Show AI job results")
    ai_results_parser.add_argument("job_id_arg", nargs="?")
    ai_results_parser.add_argument("--job-id", dest="job_id")
    ai_results_parser.add_argument("--wallet")
    ai_results_parser.add_argument("--chain-id", help="Chain ID")
    ai_results_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_results_parser.set_defaults(handler=handle_ai_job)  # Reuse job handler

    ai_cancel_parser = ai_subparsers.add_parser("cancel", help="Cancel AI job")
    ai_cancel_parser.add_argument("job_id_arg", nargs="?")
    ai_cancel_parser.add_argument("--job-id", dest="job_id")
    ai_cancel_parser.add_argument("--wallet", required=True)
    ai_cancel_parser.add_argument("--password")
    ai_cancel_parser.add_argument("--password-file")
    ai_cancel_parser.add_argument("--chain-id", help="Chain ID")
    ai_cancel_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_cancel_parser.set_defaults(handler=handle_ai_cancel)

    ai_stats_parser = ai_subparsers.add_parser("stats", help="AI service statistics")
    ai_stats_parser.add_argument("--chain-id", help="Chain ID")
    ai_stats_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_stats_parser.set_defaults(handler=handle_ai_stats)

    mining_parser = subparsers.add_parser("mining", help="Mining lifecycle and rewards")
    mining_parser.set_defaults(handler=handle_mining_action, mining_action="status")
    mining_subparsers = mining_parser.add_subparsers(dest="mining_action")

    mining_status_parser = mining_subparsers.add_parser("status", help="Show mining status")
    mining_status_parser.add_argument("--wallet")
    mining_status_parser.add_argument("--rpc-url", default=default_rpc_url)
    mining_status_parser.set_defaults(handler=handle_mining_action, mining_action="status")

    mining_start_parser = mining_subparsers.add_parser("start", help="Start mining")
    mining_start_parser.add_argument("--wallet")
    mining_start_parser.add_argument("--rpc-url", default=default_rpc_url)
    mining_start_parser.set_defaults(handler=handle_mining_action, mining_action="start")

    mining_stop_parser = mining_subparsers.add_parser("stop", help="Stop mining")
    mining_stop_parser.add_argument("--rpc-url", default=default_rpc_url)
    mining_stop_parser.set_defaults(handler=handle_mining_action, mining_action="stop")

    mining_rewards_parser = mining_subparsers.add_parser("rewards", help="Show mining rewards")
    mining_rewards_parser.add_argument("--wallet")
    mining_rewards_parser.add_argument("--rpc-url", default=default_rpc_url)
    mining_rewards_parser.set_defaults(handler=handle_mining_action, mining_action="rewards")

    analytics_parser = subparsers.add_parser("analytics", help="Blockchain analytics and statistics")
    analytics_parser.set_defaults(handler=lambda parsed, parser=analytics_parser: parser.print_help())
    analytics_subparsers = analytics_parser.add_subparsers(dest="analytics_action")

    analytics_blocks_parser = analytics_subparsers.add_parser("blocks", help="Block analytics")
    analytics_blocks_parser.add_argument("--limit", type=int, default=10)
    analytics_blocks_parser.add_argument("--rpc-url", default=default_rpc_url)
    analytics_blocks_parser.set_defaults(handler=handle_analytics, type="blocks")

    analytics_report_parser = analytics_subparsers.add_parser("report", help="Generate analytics report")
    analytics_report_parser.add_argument("--type", choices=["performance", "transactions", "all"], default="all")
    analytics_report_parser.add_argument("--rpc-url", default=default_rpc_url)
    analytics_report_parser.set_defaults(handler=handle_analytics, type="report")

    analytics_metrics_parser = analytics_subparsers.add_parser("metrics", help="Show performance metrics")
    analytics_metrics_parser.add_argument("--limit", type=int, default=10)
    analytics_metrics_parser.add_argument("--rpc-url", default=default_rpc_url)
    analytics_metrics_parser.set_defaults(handler=handle_analytics, type="metrics")

    analytics_export_parser = analytics_subparsers.add_parser("export", help="Export analytics data")
    analytics_export_parser.add_argument("--format", choices=["json", "csv"], default="json")
    analytics_export_parser.add_argument("--output")
    analytics_export_parser.add_argument("--rpc-url", default=default_rpc_url)
    analytics_export_parser.set_defaults(handler=handle_analytics, type="export")

    system_parser = subparsers.add_parser("system", help="System health and overview")
    system_parser.set_defaults(handler=handle_system_status)
    system_subparsers = system_parser.add_subparsers(dest="system_action")

    system_status_parser = system_subparsers.add_parser("status", help="Show system status")
    system_status_parser.set_defaults(handler=handle_system_status)

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
    agent_create_parser.set_defaults(handler=handle_agent_action)

    agent_execute_parser = agent_subparsers.add_parser("execute", help="Execute an agent workflow")
    agent_execute_parser.add_argument("--name", required=True)
    agent_execute_parser.add_argument("--input-data")
    agent_execute_parser.add_argument("--wallet")
    agent_execute_parser.add_argument("--priority", choices=["low", "medium", "high"], default="medium")
    agent_execute_parser.set_defaults(handler=handle_agent_action)

    agent_status_parser = agent_subparsers.add_parser("status", help="Show agent status")
    agent_status_parser.add_argument("--name")
    agent_status_parser.add_argument("--execution-id")
    agent_status_parser.set_defaults(handler=handle_agent_action)

    agent_list_parser = agent_subparsers.add_parser("list", help="List agents")
    agent_list_parser.add_argument("--status", choices=["active", "completed", "failed"])
    agent_list_parser.set_defaults(handler=handle_agent_action)

    agent_message_parser = agent_subparsers.add_parser("message", help="Send message to agent")
    agent_message_parser.add_argument("--agent", required=True)
    agent_message_parser.add_argument("--message", required=True)
    agent_message_parser.add_argument("--wallet", required=True)
    agent_message_parser.add_argument("--password")
    agent_message_parser.add_argument("--password-file")
    agent_message_parser.add_argument("--rpc-url", default=default_rpc_url)
    agent_message_parser.set_defaults(handler=handle_agent_action, agent_action="message")

    agent_messages_parser = agent_subparsers.add_parser("messages", help="List agent messages")
    agent_messages_parser.add_argument("--agent", required=True)
    agent_messages_parser.add_argument("--wallet")
    agent_messages_parser.add_argument("--rpc-url", default=default_rpc_url)
    agent_messages_parser.set_defaults(handler=handle_agent_action, agent_action="messages")

    openclaw_parser = subparsers.add_parser("openclaw", help="OpenClaw ecosystem operations")
    openclaw_parser.set_defaults(handler=lambda parsed, parser=openclaw_parser: parser.print_help())
    openclaw_subparsers = openclaw_parser.add_subparsers(dest="openclaw_action")

    openclaw_deploy_parser = openclaw_subparsers.add_parser("deploy", help="Deploy an OpenClaw agent")
    openclaw_deploy_parser.add_argument("--agent-file", required=True)
    openclaw_deploy_parser.add_argument("--wallet", required=True)
    openclaw_deploy_parser.add_argument("--environment", choices=["dev", "staging", "prod"], default="dev")
    openclaw_deploy_parser.set_defaults(handler=handle_openclaw_action)

    openclaw_monitor_parser = openclaw_subparsers.add_parser("monitor", help="Monitor OpenClaw performance")
    openclaw_monitor_parser.add_argument("--agent-id")
    openclaw_monitor_parser.add_argument("--metrics", choices=["performance", "cost", "errors", "all"], default="all")
    openclaw_monitor_parser.set_defaults(handler=handle_openclaw_action)

    openclaw_market_parser = openclaw_subparsers.add_parser("market", help="Manage OpenClaw marketplace activity")
    openclaw_market_parser.add_argument("market_action", nargs="?", choices=["list", "publish", "purchase", "evaluate"])
    openclaw_market_parser.add_argument("--action", dest="market_action_opt", choices=["list", "publish", "purchase", "evaluate"], help=argparse.SUPPRESS)
    openclaw_market_parser.add_argument("--agent-id")
    openclaw_market_parser.add_argument("--price", type=float)
    openclaw_market_parser.set_defaults(handler=handle_openclaw_action, openclaw_action="market")

    workflow_parser = subparsers.add_parser("workflow", help="Workflow templates and execution")
    workflow_parser.set_defaults(handler=lambda parsed, parser=workflow_parser: parser.print_help())
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_action")

    workflow_create_parser = workflow_subparsers.add_parser("create", help="Create a workflow")
    workflow_create_parser.add_argument("--name", required=True)
    workflow_create_parser.add_argument("--template")
    workflow_create_parser.add_argument("--config-file")
    workflow_create_parser.set_defaults(handler=handle_workflow_action)

    workflow_run_parser = workflow_subparsers.add_parser("run", help="Run a workflow")
    workflow_run_parser.add_argument("--name", required=True)
    workflow_run_parser.add_argument("--params")
    workflow_run_parser.add_argument("--async-exec", action="store_true")
    workflow_run_parser.set_defaults(handler=handle_workflow_action)

    workflow_schedule_parser = workflow_subparsers.add_parser("schedule", help="Schedule a workflow")
    workflow_schedule_parser.add_argument("--name", required=True)
    workflow_schedule_parser.add_argument("--cron", required=True)
    workflow_schedule_parser.add_argument("--params")
    workflow_schedule_parser.set_defaults(handler=handle_workflow_action, workflow_action="schedule")

    workflow_monitor_parser = workflow_subparsers.add_parser("monitor", help="Monitor workflow execution")
    workflow_monitor_parser.add_argument("--name")
    workflow_monitor_parser.add_argument("--execution-id")
    workflow_monitor_parser.set_defaults(handler=handle_workflow_action, workflow_action="monitor")

    resource_parser = subparsers.add_parser("resource", help="Resource utilization and allocation")
    resource_parser.set_defaults(handler=lambda parsed, parser=resource_parser: parser.print_help())
    resource_subparsers = resource_parser.add_subparsers(dest="resource_action")

    resource_status_parser = resource_subparsers.add_parser("status", help="Show resource status")
    resource_status_parser.add_argument("--type", choices=["cpu", "memory", "storage", "network", "all"], default="all")
    resource_status_parser.set_defaults(handler=handle_resource_action)

    resource_allocate_parser = resource_subparsers.add_parser("allocate", help="Allocate resources")
    resource_allocate_parser.add_argument("--agent-id", required=True)
    resource_allocate_parser.add_argument("--cpu", type=float)
    resource_allocate_parser.add_argument("--memory", type=int)
    resource_allocate_parser.add_argument("--duration", type=int)
    resource_allocate_parser.set_defaults(handler=handle_resource_action)

    resource_optimize_parser = resource_subparsers.add_parser("optimize", help="Optimize resource usage")
    resource_optimize_parser.add_argument("--agent-id")
    resource_optimize_parser.add_argument("--target", choices=["cpu", "memory", "all"], default="all")
    resource_optimize_parser.set_defaults(handler=handle_resource_action, resource_action="optimize")

    resource_benchmark_parser = resource_subparsers.add_parser("benchmark", help="Run resource benchmark")
    resource_benchmark_parser.add_argument("--type", choices=["cpu", "memory", "io", "all"], default="all")
    resource_benchmark_parser.set_defaults(handler=handle_resource_action, resource_action="benchmark")

    resource_monitor_parser = resource_subparsers.add_parser("monitor", help="Monitor resource utilization")
    resource_monitor_parser.add_argument("--interval", type=int, default=5, help="Monitoring interval in seconds")
    resource_monitor_parser.add_argument("--duration", type=int, default=60, help="Monitoring duration in seconds")
    resource_monitor_parser.set_defaults(handler=handle_resource_action, resource_action="monitor")

    economics_parser = subparsers.add_parser("economics", help="Economic intelligence and modeling")
    economics_parser.set_defaults(handler=lambda parsed, parser=economics_parser: parser.print_help())
    economics_subparsers = economics_parser.add_subparsers(dest="economics_action")

    economics_distributed_parser = economics_subparsers.add_parser("distributed", help="Distributed cost optimization")
    economics_distributed_parser.add_argument("--cost-optimize", action="store_true")
    economics_distributed_parser.set_defaults(handler=handle_economics_action)

    economics_market_parser = economics_subparsers.add_parser("market", help="Market analysis")
    economics_market_parser.add_argument("--analyze", action="store_true")
    economics_market_parser.set_defaults(handler=handle_economics_action)

    economics_trends_parser = economics_subparsers.add_parser("trends", help="Economic trends analysis")
    economics_trends_parser.add_argument("--period")
    economics_trends_parser.set_defaults(handler=handle_economics_action)

    economics_optimize_parser = economics_subparsers.add_parser("optimize", help="Optimize economic strategy")
    economics_optimize_parser.add_argument("--target", choices=["revenue", "cost", "all"], default="all")
    economics_optimize_parser.set_defaults(handler=handle_economics_action)

    cluster_parser = subparsers.add_parser("cluster", help="Cluster management")
    cluster_parser.set_defaults(handler=lambda parsed, parser=cluster_parser: parser.print_help())
    cluster_subparsers = cluster_parser.add_subparsers(dest="cluster_action")

    cluster_status_parser = cluster_subparsers.add_parser("status", help="Show cluster status")
    cluster_status_parser.add_argument("--nodes", nargs="*", default=["aitbc", "aitbc1"])
    cluster_status_parser.set_defaults(handler=handle_network_status)

    cluster_sync_parser = cluster_subparsers.add_parser("sync", help="Sync cluster nodes")
    cluster_sync_parser.add_argument("--all", action="store_true")
    cluster_sync_parser.set_defaults(handler=handle_cluster_action)

    cluster_balance_parser = cluster_subparsers.add_parser("balance", help="Balance workload across nodes")
    cluster_balance_parser.add_argument("--workload", action="store_true")
    cluster_balance_parser.set_defaults(handler=handle_cluster_action)

    performance_parser = subparsers.add_parser("performance", help="Performance optimization")
    performance_parser.set_defaults(handler=lambda parsed, parser=performance_parser: parser.print_help())
    performance_subparsers = performance_parser.add_subparsers(dest="performance_action")

    performance_benchmark_parser = performance_subparsers.add_parser("benchmark", help="Run performance benchmark")
    performance_benchmark_parser.add_argument("--suite", choices=["comprehensive", "quick", "custom"], default="comprehensive")
    performance_benchmark_parser.set_defaults(handler=handle_performance_action)

    performance_optimize_parser = performance_subparsers.add_parser("optimize", help="Optimize performance")
    performance_optimize_parser.add_argument("--target", choices=["latency", "throughput", "all"], default="all")
    performance_optimize_parser.set_defaults(handler=handle_performance_action)

    performance_tune_parser = performance_subparsers.add_parser("tune", help="Tune system parameters")
    performance_tune_parser.add_argument("--parameters", action="store_true")
    performance_tune_parser.add_argument("--aggressive", action="store_true")
    performance_tune_parser.set_defaults(handler=handle_performance_action)

    security_parser = subparsers.add_parser("security", help="Security audit and scanning")
    security_parser.set_defaults(handler=lambda parsed, parser=security_parser: parser.print_help())
    security_subparsers = security_parser.add_subparsers(dest="security_action")

    security_audit_parser = security_subparsers.add_parser("audit", help="Run security audit")
    security_audit_parser.add_argument("--comprehensive", action="store_true")
    security_audit_parser.set_defaults(handler=handle_security_action)

    security_scan_parser = security_subparsers.add_parser("scan", help="Scan for vulnerabilities")
    security_scan_parser.add_argument("--vulnerabilities", action="store_true")
    security_scan_parser.set_defaults(handler=handle_security_action)

    security_patch_parser = security_subparsers.add_parser("patch", help="Check for security patches")
    security_patch_parser.add_argument("--critical", action="store_true")
    security_patch_parser.set_defaults(handler=handle_security_action)

    compliance_parser = subparsers.add_parser("compliance", help="Compliance checking and reporting")
    compliance_parser.set_defaults(handler=lambda parsed, parser=compliance_parser: parser.print_help())
    compliance_subparsers = compliance_parser.add_subparsers(dest="compliance_action")

    compliance_check_parser = compliance_subparsers.add_parser("check", help="Check compliance status")
    compliance_check_parser.add_argument("--standard", choices=["gdpr", "hipaa", "soc2", "all"], default="gdpr")
    compliance_check_parser.set_defaults(handler=handle_system_status)

    compliance_report_parser = compliance_subparsers.add_parser("report", help="Generate compliance report")
    compliance_report_parser.add_argument("--format", choices=["detailed", "summary", "json"], default="detailed")
    compliance_report_parser.set_defaults(handler=handle_system_status)

    simulate_parser = subparsers.add_parser("simulate", help="Simulation utilities")
    simulate_parser.set_defaults(handler=lambda parsed, parser=simulate_parser: parser.print_help())
    simulate_subparsers = simulate_parser.add_subparsers(dest="simulate_command")

    simulate_blockchain_parser = simulate_subparsers.add_parser("blockchain", help="Simulate blockchain activity")
    simulate_blockchain_parser.add_argument("--blocks", type=int, default=10)
    simulate_blockchain_parser.add_argument("--transactions", type=int, default=50)
    simulate_blockchain_parser.add_argument("--delay", type=float, default=1.0)
    simulate_blockchain_parser.set_defaults(handler=handle_simulate_action)

    simulate_wallets_parser = simulate_subparsers.add_parser("wallets", help="Simulate wallet activity")
    simulate_wallets_parser.add_argument("--wallets", type=int, default=5)
    simulate_wallets_parser.add_argument("--balance", type=float, default=1000.0)
    simulate_wallets_parser.add_argument("--transactions", type=int, default=20)
    simulate_wallets_parser.add_argument("--amount-range", default="1.0-100.0")
    simulate_wallets_parser.set_defaults(handler=handle_simulate_action)

    simulate_price_parser = simulate_subparsers.add_parser("price", help="Simulate price movement")
    simulate_price_parser.add_argument("--price", type=float, default=100.0)
    simulate_price_parser.add_argument("--volatility", type=float, default=0.05)
    simulate_price_parser.add_argument("--timesteps", type=int, default=100)
    simulate_price_parser.add_argument("--delay", type=float, default=0.1)
    simulate_price_parser.set_defaults(handler=handle_simulate_action)

    simulate_network_parser = simulate_subparsers.add_parser("network", help="Simulate network topology")
    simulate_network_parser.add_argument("--nodes", type=int, default=3)
    simulate_network_parser.add_argument("--network-delay", type=float, default=0.1)
    simulate_network_parser.add_argument("--failure-rate", type=float, default=0.05)
    simulate_network_parser.set_defaults(handler=handle_simulate_action)

    simulate_ai_jobs_parser = simulate_subparsers.add_parser("ai-jobs", help="Simulate AI job traffic")
    simulate_ai_jobs_parser.add_argument("--jobs", type=int, default=10)
    simulate_ai_jobs_parser.add_argument("--models", default="text-generation")
    simulate_ai_jobs_parser.add_argument("--duration-range", default="30-300")
    simulate_ai_jobs_parser.set_defaults(handler=handle_simulate_action)

    pool_hub_parser = subparsers.add_parser("pool-hub", help="Pool hub management for SLA monitoring and billing")
    pool_hub_parser.set_defaults(handler=lambda parsed, parser=pool_hub_parser: parser.print_help())
    pool_hub_subparsers = pool_hub_parser.add_subparsers(dest="pool_hub_action")

    pool_hub_sla_metrics_parser = pool_hub_subparsers.add_parser("sla-metrics", help="Get SLA metrics for miner or all miners")
    pool_hub_sla_metrics_parser.add_argument("miner_id", nargs="?")
    pool_hub_sla_metrics_parser.add_argument("--test-mode", action="store_true")
    pool_hub_sla_metrics_parser.set_defaults(handler=handle_pool_hub_sla_metrics)

    pool_hub_sla_violations_parser = pool_hub_subparsers.add_parser("sla-violations", help="Get SLA violations")
    pool_hub_sla_violations_parser.add_argument("--test-mode", action="store_true")
    pool_hub_sla_violations_parser.set_defaults(handler=handle_pool_hub_sla_violations)

    pool_hub_capacity_snapshots_parser = pool_hub_subparsers.add_parser("capacity-snapshots", help="Get capacity planning snapshots")
    pool_hub_capacity_snapshots_parser.add_argument("--test-mode", action="store_true")
    pool_hub_capacity_snapshots_parser.set_defaults(handler=handle_pool_hub_capacity_snapshots)

    pool_hub_capacity_forecast_parser = pool_hub_subparsers.add_parser("capacity-forecast", help="Get capacity forecast")
    pool_hub_capacity_forecast_parser.add_argument("--test-mode", action="store_true")
    pool_hub_capacity_forecast_parser.set_defaults(handler=handle_pool_hub_capacity_forecast)

    pool_hub_capacity_recommendations_parser = pool_hub_subparsers.add_parser("capacity-recommendations", help="Get scaling recommendations")
    pool_hub_capacity_recommendations_parser.add_argument("--test-mode", action="store_true")
    pool_hub_capacity_recommendations_parser.set_defaults(handler=handle_pool_hub_capacity_recommendations)

    pool_hub_billing_usage_parser = pool_hub_subparsers.add_parser("billing-usage", help="Get billing usage data")
    pool_hub_billing_usage_parser.add_argument("--test-mode", action="store_true")
    pool_hub_billing_usage_parser.set_defaults(handler=handle_pool_hub_billing_usage)

    pool_hub_billing_sync_parser = pool_hub_subparsers.add_parser("billing-sync", help="Trigger billing sync with coordinator-api")
    pool_hub_billing_sync_parser.add_argument("--test-mode", action="store_true")
    pool_hub_billing_sync_parser.set_defaults(handler=handle_pool_hub_billing_sync)

    pool_hub_collect_metrics_parser = pool_hub_subparsers.add_parser("collect-metrics", help="Trigger SLA metrics collection")
    pool_hub_collect_metrics_parser.add_argument("--test-mode", action="store_true")
    pool_hub_collect_metrics_parser.set_defaults(handler=handle_pool_hub_collect_metrics)

    bridge_parser = subparsers.add_parser("bridge", help="Blockchain event bridge management")
    bridge_parser.set_defaults(handler=lambda parsed, parser=bridge_parser: parser.print_help())
    bridge_subparsers = bridge_parser.add_subparsers(dest="bridge_action")

    bridge_health_parser = bridge_subparsers.add_parser("health", help="Health check for blockchain event bridge service")
    bridge_health_parser.add_argument("--test-mode", action="store_true")
    bridge_health_parser.set_defaults(handler=handle_bridge_health)

    bridge_metrics_parser = bridge_subparsers.add_parser("metrics", help="Get Prometheus metrics from blockchain event bridge service")
    bridge_metrics_parser.add_argument("--test-mode", action="store_true")
    bridge_metrics_parser.set_defaults(handler=handle_bridge_metrics)

    bridge_status_parser = bridge_subparsers.add_parser("status", help="Get detailed status of blockchain event bridge service")
    bridge_status_parser.add_argument("--test-mode", action="store_true")
    bridge_status_parser.set_defaults(handler=handle_bridge_status)

    bridge_config_parser = bridge_subparsers.add_parser("config", help="Show current configuration of blockchain event bridge service")
    bridge_config_parser.add_argument("--test-mode", action="store_true")
    bridge_config_parser.set_defaults(handler=handle_bridge_config)

    bridge_restart_parser = bridge_subparsers.add_parser("restart", help="Restart blockchain event bridge service (via systemd)")
    bridge_restart_parser.add_argument("--test-mode", action="store_true")
    bridge_restart_parser.set_defaults(handler=handle_bridge_restart)

    parsed_args = parser.parse_args(normalize_legacy_args(list(sys.argv[1:] if argv is None else argv)))
    if not getattr(parsed_args, "command", None):
        parser.print_help()
        return
    handler = getattr(parsed_args, "handler", None)
    if handler is None:
        parser.print_help()
        return
    handler(parsed_args)
