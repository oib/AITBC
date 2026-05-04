import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import command handlers
from handlers import market as market_handlers
from handlers import wallet as wallet_handlers
from handlers import blockchain as blockchain_handlers
from handlers import messaging as messaging_handlers
from handlers import network as network_handlers
from handlers import ai as ai_handlers
from handlers import analytics as analytics_handlers
from handlers import system as system_handlers
from handlers import pool_hub as pool_hub_handlers
from handlers import bridge as bridge_handlers
from handlers import account as account_handlers
from handlers import contract as contract_handlers
from handlers import workflow as workflow_handlers
from handlers import performance as performance_handlers
from handlers import resource as resource_handlers
from parser_context import ParserContext
from parsers import register_all


def run_cli(argv, core):
    import sys
    raw_args = sys.argv[1:] if argv is None else argv
    
    # Extended features interception removed - replaced with actual RPC calls
    
    default_rpc_url = core["DEFAULT_RPC_URL"]
    default_coordinator_url = core.get("DEFAULT_COORDINATOR_URL", "http://localhost:9001")
    # New microservice URLs
    default_gpu_url = core.get("DEFAULT_GPU_URL", "http://localhost:8101")
    default_marketplace_url = core.get("DEFAULT_MARKETPLACE_URL", "http://localhost:8001")
    default_trading_url = core.get("DEFAULT_TRADING_URL", "http://localhost:8104")
    default_governance_url = core.get("DEFAULT_GOVERNANCE_URL", "http://localhost:8105")
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
            if "--list" in rest:
                rest.remove("--list")
                return ["market", "list", *rest]
            action = extract_option(rest, "--action")
            return ["market", *([action] if action else []), *rest]

        if command == "analytics":
            if rest and not rest[0].startswith("-"):
                return normalized
            for flag, mapped_action in (
                ("--report", "report"),
                ("--metrics", "metrics"),
                ("--export", "export"),
                ("--predict", "predict"),
                ("--optimize", "optimize"),
            ):
                if flag in rest:
                    rest.remove(flag)
                    return ["analytics", mapped_action, *rest]

        if command == "economics":
            if rest and not rest[0].startswith("-"):
                return normalized
            for flag, mapped_action in (
                ("--model", "model"),
                ("--market", "market"),
                ("--distributed", "distributed"),
                ("--strategy", "strategy"),
            ):
                if flag in rest:
                    rest.remove(flag)
                    return ["economics", mapped_action, *rest]

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
        blockchain_handlers.handle_blockchain_block(args, default_rpc_url)

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
        market_handlers.handle_market_listings(args, default_marketplace_url, output_format, render_mapping)

    def handle_market_create(args):
        market_handlers.handle_market_create(args, default_marketplace_url, read_password, render_mapping)

    def handle_market_get(args):
        market_handlers.handle_market_get(args, default_marketplace_url)

    def handle_market_delete(args):
        market_handlers.handle_market_delete(args, default_marketplace_url, read_password, render_mapping)

    def handle_market_gpu_register(args):
        market_handlers.handle_market_gpu_register(args, default_gpu_url)

    def handle_market_gpu_list(args):
        market_handlers.handle_market_gpu_list(args, default_gpu_url, output_format)

    def handle_market_buy(args):
        market_handlers.handle_market_buy(args, default_marketplace_url, read_password, render_mapping)

    def handle_market_sell(args):
        market_handlers.handle_market_sell(args, default_marketplace_url, read_password, render_mapping)

    def handle_market_orders(args):
        market_handlers.handle_market_orders(args, default_marketplace_url, output_format, render_mapping)

    def handle_workflow_create(args):
        workflow_handlers.handle_workflow_create(args, render_mapping)

    def handle_workflow_schedule(args):
        workflow_handlers.handle_workflow_schedule(args, render_mapping)

    def handle_workflow_monitor(args):
        workflow_handlers.handle_workflow_monitor(args, output_format, render_mapping)

    def handle_performance_benchmark(args):
        performance_handlers.handle_performance_benchmark(args, output_format, render_mapping)

    def handle_performance_optimize(args):
        performance_handlers.handle_performance_optimize(args, render_mapping)

    def handle_performance_tune(args):
        performance_handlers.handle_performance_tune(args, render_mapping)

    def handle_resource_status(args):
        resource_handlers.handle_resource_status(args, output_format, render_mapping)

    def handle_resource_allocate(args):
        resource_handlers.handle_resource_allocate(args, render_mapping)

    def handle_resource_monitor(args):
        resource_handlers.handle_resource_monitor(args, render_mapping)

    def handle_resource_optimize(args):
        resource_handlers.handle_resource_optimize(args, render_mapping)

    def handle_resource_benchmark(args):
        resource_handlers.handle_resource_benchmark(args, render_mapping)

    def handle_analytics_metrics(args):
        analytics_handlers.handle_analytics_metrics(args, default_rpc_url, output_format, render_mapping)

    def handle_analytics_report(args):
        analytics_handlers.handle_analytics_report(args, default_rpc_url, output_format, render_mapping)

    def handle_analytics_export(args):
        analytics_handlers.handle_analytics_export(args, default_rpc_url, render_mapping)

    def handle_analytics_predict(args):
        analytics_handlers.handle_analytics_predict(args, default_rpc_url, render_mapping)

    def handle_analytics_optimize(args):
        analytics_handlers.handle_analytics_optimize(args, default_rpc_url, render_mapping)

    def handle_compliance_check(args):
        system_handlers.handle_compliance_check(args, render_mapping)

    def handle_compliance_report(args):
        system_handlers.handle_compliance_report(args, render_mapping)

    def handle_cluster_status(args):
        system_handlers.handle_cluster_status(args, render_mapping)

    def handle_cluster_sync(args):
        system_handlers.handle_cluster_sync(args, render_mapping)

    def handle_cluster_balance(args):
        system_handlers.handle_cluster_balance(args, render_mapping)

    def handle_script_run(args):
        system_handlers.handle_script_run(args, render_mapping)

    def handle_ai_submit(args):
        ai_handlers.handle_ai_submit(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping)

    def handle_ai_jobs(args):
        ai_handlers.handle_ai_jobs(args, default_rpc_url, default_coordinator_url, output_format, render_mapping)

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

    def handle_ai_status(args):
        ai_handlers.handle_ai_status(args, default_coordinator_url, default_rpc_url, output_format, render_mapping)

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

    def handle_agent_sdk_action(args):
        system_handlers.handle_agent_sdk_action(args, render_mapping)

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

    def handle_bridge_restart(args):
        """Restart blockchain event bridge service (via systemd)"""
        import subprocess
        try:
            result = subprocess.run(["systemctl", "restart", "aitbc-blockchain-bridge.service"], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Blockchain event bridge service restarted successfully")
            else:
                print(f"❌ Failed to restart blockchain event bridge service: {result.stderr}")
        except Exception as e:
            print(f"❌ Error restarting blockchain event bridge service: {e}")

    def handle_contract_list(args):
        contract_handlers.handle_contract_list(args, default_rpc_url)

    def handle_contract_deploy(args):
        contract_handlers.handle_contract_deploy(args, default_rpc_url, read_password, render_mapping)

    def handle_contract_call(args):
        contract_handlers.handle_contract_call(args, default_rpc_url, read_password)

    def handle_contract_verify(args):
        contract_handlers.handle_contract_verify(args, default_rpc_url, read_password)

    handlers = {
        "handle_wallet_create": handle_wallet_create,
        "handle_wallet_list": handle_wallet_list,
        "handle_wallet_balance": handle_wallet_balance,
        "handle_wallet_transactions": handle_wallet_transactions,
        "handle_wallet_send": handle_wallet_send,
        "handle_wallet_import": handle_wallet_import,
        "handle_wallet_export": handle_wallet_export,
        "handle_wallet_delete": handle_wallet_delete,
        "handle_wallet_rename": handle_wallet_rename,
        "handle_wallet_backup": handle_wallet_backup,
        "handle_wallet_sync": handle_wallet_sync,
        "handle_wallet_batch": handle_wallet_batch,
        "handle_blockchain_info": handle_blockchain_info,
        "handle_blockchain_height": handle_blockchain_height,
        "handle_blockchain_block": handle_blockchain_block,
        "handle_blockchain_init": handle_blockchain_init,
        "handle_blockchain_genesis": handle_blockchain_genesis,
        "handle_blockchain_import": handle_blockchain_import,
        "handle_blockchain_export": handle_blockchain_export,
        "handle_blockchain_import_chain": handle_blockchain_import_chain,
        "handle_blockchain_blocks_range": handle_blockchain_blocks_range,
        "handle_blockchain_transactions": handle_blockchain_transactions,
        "handle_blockchain_mempool": handle_blockchain_mempool,
        "handle_account_get": handle_account_get,
        "handle_messaging_deploy": handle_messaging_deploy,
        "handle_messaging_state": handle_messaging_state,
        "handle_messaging_topics": handle_messaging_topics,
        "handle_messaging_create_topic": handle_messaging_create_topic,
        "handle_messaging_messages": handle_messaging_messages,
        "handle_messaging_post": handle_messaging_post,
        "handle_messaging_vote": handle_messaging_vote,
        "handle_messaging_search": handle_messaging_search,
        "handle_messaging_reputation": handle_messaging_reputation,
        "handle_messaging_moderate": handle_messaging_moderate,
        "handle_network_status": handle_network_status,
        "handle_network_peers": handle_network_peers,
        "handle_network_sync": handle_network_sync,
        "handle_network_ping": handle_network_ping,
        "handle_network_propagate": handle_network_propagate,
        "handle_network_force_sync": handle_network_force_sync,
        "handle_market_listings": handle_market_listings,
        "handle_market_create": handle_market_create,
        "handle_market_get": handle_market_get,
        "handle_market_delete": handle_market_delete,
        "handle_market_gpu_register": handle_market_gpu_register,
        "handle_market_gpu_list": handle_market_gpu_list,
        "handle_market_buy": handle_market_buy,
        "handle_market_sell": handle_market_sell,
        "handle_market_orders": handle_market_orders,
        "handle_workflow_create": handle_workflow_create,
        "handle_workflow_schedule": handle_workflow_schedule,
        "handle_workflow_monitor": handle_workflow_monitor,
        "handle_performance_benchmark": handle_performance_benchmark,
        "handle_performance_optimize": handle_performance_optimize,
        "handle_performance_tune": handle_performance_tune,
        "handle_resource_status": handle_resource_status,
        "handle_resource_allocate": handle_resource_allocate,
        "handle_resource_monitor": handle_resource_monitor,
        "handle_resource_optimize": handle_resource_optimize,
        "handle_resource_benchmark": handle_resource_benchmark,
        "handle_analytics_metrics": handle_analytics_metrics,
        "handle_analytics_report": handle_analytics_report,
        "handle_analytics_export": handle_analytics_export,
        "handle_analytics_predict": handle_analytics_predict,
        "handle_analytics_optimize": handle_analytics_optimize,
        "handle_compliance_check": handle_compliance_check,
        "handle_compliance_report": handle_compliance_report,
        "handle_cluster_status": handle_cluster_status,
        "handle_cluster_sync": handle_cluster_sync,
        "handle_cluster_balance": handle_cluster_balance,
        "handle_script_run": handle_script_run,
        "handle_ai_submit": handle_ai_submit,
        "handle_ai_jobs": handle_ai_jobs,
        "handle_ai_job": handle_ai_job,
        "handle_ai_cancel": handle_ai_cancel,
        "handle_ai_stats": handle_ai_stats,
        "handle_ai_service_list": handle_ai_service_list,
        "handle_ai_service_status": handle_ai_service_status,
        "handle_ai_service_test": handle_ai_service_test,
        "handle_ai_status": handle_ai_status,
        "handle_economics_action": handle_economics_action,
        "handle_cluster_action": handle_cluster_action,
        "handle_performance_action": handle_performance_action,
        "handle_security_action": handle_security_action,
        "handle_mining_action": handle_mining_action,
        "handle_system_status": handle_system_status,
        "handle_analytics": handle_analytics,
        "handle_agent_action": handle_agent_action,
        "handle_agent_sdk_action": handle_agent_sdk_action,
        "handle_openclaw_action": handle_openclaw_action,
        "handle_workflow_action": handle_workflow_action,
        "handle_resource_action": handle_resource_action,
        "handle_simulate_action": handle_simulate_action,
        "handle_pool_hub_sla_metrics": handle_pool_hub_sla_metrics,
        "handle_pool_hub_sla_violations": handle_pool_hub_sla_violations,
        "handle_pool_hub_capacity_snapshots": handle_pool_hub_capacity_snapshots,
        "handle_pool_hub_capacity_forecast": handle_pool_hub_capacity_forecast,
        "handle_pool_hub_capacity_recommendations": handle_pool_hub_capacity_recommendations,
        "handle_pool_hub_billing_usage": handle_pool_hub_billing_usage,
        "handle_pool_hub_billing_sync": handle_pool_hub_billing_sync,
        "handle_pool_hub_collect_metrics": handle_pool_hub_collect_metrics,
        "handle_bridge_health": handle_bridge_health,
        "handle_bridge_metrics": handle_bridge_metrics,
        "handle_bridge_status": handle_bridge_status,
        "handle_bridge_config": globals()["handle_bridge_config"],
        "handle_bridge_restart": globals()["handle_bridge_restart"],
        "handle_genesis_init": globals()["handle_genesis_init"],
        "handle_contract_list": handle_contract_list,
        "handle_contract_deploy": handle_contract_deploy,
        "handle_contract_call": handle_contract_call,
        "handle_contract_verify": handle_contract_verify,
        "handle_genesis_verify": globals()["handle_genesis_verify"],
        "handle_genesis_info": globals()["handle_genesis_info"],
    }

    ctx = ParserContext(
        default_rpc_url=default_rpc_url,
        default_coordinator_url=default_coordinator_url,
        cli_version=cli_version,
        first=first,
        read_password=read_password,
        output_format=output_format,
        render_mapping=render_mapping,
        read_blockchain_env=read_blockchain_env,
        normalize_rpc_url=normalize_rpc_url,
        probe_rpc_node=probe_rpc_node,
        get_network_snapshot=get_network_snapshot,
        handlers=handlers,
    )

    parser = argparse.ArgumentParser(
        description="AITBC CLI - Comprehensive Blockchain Management Tool",
        epilog="Examples: aitbc wallet create demo secret | aitbc wallet balance demo | aitbc ai submit --wallet demo --type text-generation --prompt 'hello' --payment 1",
    )
    parser.add_argument("--version", action="version", version=f"aitbc-cli {cli_version}")
    parser.add_argument("--output", choices=["table", "json", "yaml"], default="table")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    register_all(subparsers, ctx)

    parsed_args = parser.parse_args(normalize_legacy_args(list(raw_args)))
    if not getattr(parsed_args, "command", None):
        parser.print_help()
        return 0
    handler = getattr(parsed_args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    handler(parsed_args)
    return 0

def handle_genesis_init(args):
    """Initialize genesis block and wallet"""
    import subprocess
    import sys
    from pathlib import Path
    
    # Use new genesis-init.py script for basic genesis initialization
    new_script_path = Path("/opt/aitbc/scripts/utils/genesis-init.py")
    old_script_path = Path("/opt/aitbc/apps/blockchain-node/scripts/unified_genesis.py")
    
    # Prefer new script if it exists and we're not doing wallet creation
    if new_script_path.exists() and not args.create_wallet:
        script_path = new_script_path
        use_new_script = True
    elif old_script_path.exists():
        script_path = old_script_path
        use_new_script = False
    else:
        print(f"Error: Genesis generation script not found")
        return
    
    if use_new_script:
        # Use new simpler script
        cmd = [sys.executable, str(script_path), "--chain-id", args.chain_id]
        if args.proposer:
            cmd.extend(["--proposer", args.proposer])
        else:
            print("Error: --proposer is required for genesis initialization")
            return
    else:
        # Use old comprehensive script for wallet creation
        cmd = [sys.executable, str(script_path), "--chain-id", args.chain_id]
        if args.create_wallet:
            cmd.append("--create-wallet")
        if args.password:
            cmd.extend(["--password", args.password])
        if args.proposer:
            cmd.extend(["--proposer", args.proposer])
        if args.force:
            cmd.append("--force")
        if args.register_service:
            cmd.append("--register-service")
            cmd.extend(["--service-url", args.service_url])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error: Genesis generation failed: {e.stderr}")

def handle_genesis_verify(args):
    """Verify genesis block and wallet configuration"""
    import json
    import sqlite3
    from pathlib import Path
    
    chain_id = args.chain_id
    
    # Check genesis config file
    genesis_path = Path(f"/var/lib/aitbc/data/{chain_id}/genesis.json")
    if not genesis_path.exists():
        print(f"Error: Genesis config not found: {genesis_path}")
        return
    
    try:
        with open(genesis_path) as f:
            genesis_data = json.load(f)
        
        print(f"✓ Genesis config found: {genesis_path}")
        print(f"  Chain ID: {genesis_data.get('chain_id')}")
        print(f"  Genesis Hash: {genesis_data.get('block', {}).get('hash')}")
        print(f"  Proposer: {genesis_data.get('block', {}).get('proposer')}")
        print(f"  Allocations: {len(genesis_data.get('allocations', []))}")
    except Exception as e:
        print(f"Error: Failed to read genesis config: {e}")
        return
    
    # Check database
    db_path = Path("/var/lib/aitbc/data/chain.db")
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}")
        return
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM block WHERE height=0 AND chain_id=?", (chain_id,))
        genesis_block = cursor.fetchone()
        
        if genesis_block:
            print(f"✓ Genesis block found in database")
            print(f"  Height: {genesis_block[1]}")
            print(f"  Hash: {genesis_block[2]}")
            print(f"  Proposer: {genesis_block[4]}")
        else:
            print(f"Error: Genesis block not found in database for chain {chain_id}")
        
        cursor.execute("SELECT COUNT(*) FROM account WHERE chain_id=?", (chain_id,))
        account_count = cursor.fetchone()[0]
        
        if account_count > 0:
            print(f"✓ Found {account_count} accounts in database")
        else:
            print(f"Error: No accounts found in database for chain {chain_id}")
        
        conn.close()
    except Exception as e:
        print(f"Error: Failed to verify database: {e}")
        return
    
    # Check genesis wallet
    wallet_path = Path("/var/lib/aitbc/keystore/genesis.json")
    if wallet_path.exists():
        print(f"✓ Genesis wallet found: {wallet_path}")
        try:
            with open(wallet_path) as f:
                wallet_data = json.load(f)
            print(f"  Address: {wallet_data.get('address')}")
            print(f"  Public Key: {wallet_data.get('public_key')[:16]}..." if wallet_data.get('public_key') else "N/A")
        except Exception as e:
            print(f"Error: Failed to read genesis wallet: {e}")
    else:
        print(f"Error: Genesis wallet not found: {wallet_path}")

def handle_genesis_info(args):
    """Show genesis block information"""
    import json
    from pathlib import Path
    
    chain_id = args.chain_id
    genesis_path = Path(f"/var/lib/aitbc/data/{chain_id}/genesis.json")
    
    if not genesis_path.exists():
        print(f"Error: Genesis config not found: {genesis_path}")
        return
    
    try:
        with open(genesis_path) as f:
            genesis_data = json.load(f)
        
        block = genesis_data.get("block", {})
        allocations = genesis_data.get("allocations", [])
        
        print(f"Genesis Information for {chain_id}:")
        print(f"  Chain ID: {genesis_data.get('chain_id')}")
        print(f"  Block Height: {block.get('height')}")
        print(f"  Block Hash: {block.get('hash')}")
        print(f"  Parent Hash: {block.get('parent_hash')}")
        print(f"  Proposer: {block.get('proposer')}")
        print(f"  Timestamp: {block.get('timestamp')}")
        print(f"  Transaction Count: {block.get('tx_count')}")
        print(f"  Total Allocations: {len(allocations)}")
        print(f"\n  Top Allocations:")
        for i, alloc in enumerate(allocations[:5], 1):
            print(f"    {i}. {alloc.get('address')}: {alloc.get('balance')} AIT")
        
    except Exception as e:
        print(f"Error: Failed to read genesis info: {e}")

def handle_bridge_config(args):
    bridge_handlers.handle_bridge_config(args)

def handle_bridge_restart(args):
    bridge_handlers.handle_bridge_restart(args)

def main(argv=None):
    import importlib.util
    from pathlib import Path

    cli_path = Path(__file__).with_name("aitbc_cli.py")
    spec = importlib.util.spec_from_file_location("aitbc_cli_script_entry", cli_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load CLI entrypoint from {cli_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
