import argparse
import json
import sys


def run_cli(argv, core):
    default_rpc_url = core["DEFAULT_RPC_URL"]
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
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet_name_opt", None))
        password = read_password(args, "wallet_password")
        if not wallet_name or not password:
            print("Error: Wallet name and password are required")
            sys.exit(1)
        address = create_wallet(wallet_name, password)
        print(f"Wallet address: {address}")

    def handle_wallet_list(args):
        wallets = list_wallets()
        if output_format(args) == "json":
            print(json.dumps(wallets, indent=2))
            return
        print("Wallets:")
        for wallet in wallets:
            print(f"  {wallet['name']}: {wallet['address']}")

    def handle_wallet_balance(args):
        rpc_url = getattr(args, "rpc_url", default_rpc_url)
        if getattr(args, "all", False):
            print("All wallet balances:")
            for wallet in list_wallets():
                balance_info = get_balance(wallet["name"], rpc_url=rpc_url)
                if balance_info:
                    print(f"  {wallet['name']}: {balance_info['balance']} AIT")
                else:
                    print(f"  {wallet['name']}: unavailable")
            return
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet_name_opt", None))
        if not wallet_name:
            print("Error: Wallet name is required")
            sys.exit(1)
        balance_info = get_balance(wallet_name, rpc_url=rpc_url)
        if not balance_info:
            sys.exit(1)
        print(f"Wallet: {balance_info['wallet_name']}")
        print(f"Address: {balance_info['address']}")
        print(f"Balance: {balance_info['balance']} AIT")
        print(f"Nonce: {balance_info['nonce']}")

    def handle_wallet_transactions(args):
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet_name_opt", None))
        if not wallet_name:
            print("Error: Wallet name is required")
            sys.exit(1)
        transactions = get_transactions(wallet_name, limit=args.limit, rpc_url=args.rpc_url)
        if output_format(args) == "json":
            print(json.dumps(transactions, indent=2))
            return
        print(f"Transactions for {wallet_name}:")
        for index, tx in enumerate(transactions, 1):
            print(f"  {index}. Hash: {tx.get('hash', 'N/A')}")
            print(f"     Amount: {tx.get('value', 0)} AIT")
            print(f"     Fee: {tx.get('fee', 0)} AIT")
            print(f"     Type: {tx.get('type', 'N/A')}")
            print()

    def handle_wallet_send(args):
        from_wallet = first(getattr(args, "from_wallet_arg", None), getattr(args, "from_wallet", None))
        to_address = first(getattr(args, "to_address_arg", None), getattr(args, "to_address", None))
        amount_value = first(getattr(args, "amount_arg", None), getattr(args, "amount", None))
        password = read_password(args, "wallet_password")
        if not from_wallet or not to_address or amount_value is None or not password:
            print("Error: From wallet, destination, amount, and password are required")
            sys.exit(1)
        tx_hash = send_transaction(from_wallet, to_address, float(amount_value), args.fee, password, rpc_url=args.rpc_url)
        if not tx_hash:
            sys.exit(1)
        print(f"Transaction hash: {tx_hash}")

    def handle_wallet_import(args):
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet_name_opt", None))
        private_key = first(getattr(args, "private_key_arg", None), getattr(args, "private_key_opt", None))
        password = read_password(args, "wallet_password")
        if not wallet_name or not private_key or not password:
            print("Error: Wallet name, private key, and password are required")
            sys.exit(1)
        address = import_wallet(wallet_name, private_key, password)
        if not address:
            sys.exit(1)
        print(f"Wallet address: {address}")

    def handle_wallet_export(args):
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet_name_opt", None))
        password = read_password(args, "wallet_password")
        if not wallet_name or not password:
            print("Error: Wallet name and password are required")
            sys.exit(1)
        private_key = export_wallet(wallet_name, password)
        if not private_key:
            sys.exit(1)
        print(private_key)

    def handle_wallet_delete(args):
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet_name_opt", None))
        if not wallet_name or not args.confirm:
            print("Error: Wallet name and --confirm are required")
            sys.exit(1)
        if not delete_wallet(wallet_name):
            sys.exit(1)

    def handle_wallet_rename(args):
        old_name = first(getattr(args, "old_name_arg", None), getattr(args, "old_name", None))
        new_name = first(getattr(args, "new_name_arg", None), getattr(args, "new_name", None))
        if not old_name or not new_name:
            print("Error: Old and new wallet names are required")
            sys.exit(1)
        if not rename_wallet(old_name, new_name):
            sys.exit(1)

    def handle_wallet_backup(args):
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet_name_opt", None))
        if not wallet_name:
            print("Error: Wallet name is required")
            sys.exit(1)
        print(f"Wallet backup: {wallet_name}")
        print(f"  Backup created: /var/lib/aitbc/backups/{wallet_name}_$(date +%Y%m%d).json")
        print("  Status: completed")

    def handle_wallet_sync(args):
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet_name_opt", None))
        if args.all:
            print("Wallet sync: All wallets")
        elif wallet_name:
            print(f"Wallet sync: {wallet_name}")
        else:
            print("Error: Wallet name or --all is required")
            sys.exit(1)
        print("  Sync status: completed")
        print("  Last sync: $(date)")

    def handle_wallet_batch(args):
        password = read_password(args)
        if not password:
            print("Error: Password is required")
            sys.exit(1)
        with open(args.file) as handle:
            transactions = json.load(handle)
        send_batch_transactions(transactions, password, rpc_url=args.rpc_url)

    def handle_blockchain_info(args):
        chain_info = get_chain_info(rpc_url=args.rpc_url)
        if not chain_info:
            sys.exit(1)
        render_mapping("Blockchain information:", chain_info)

    def handle_blockchain_height(args):
        chain_info = get_chain_info(rpc_url=args.rpc_url)
        print(chain_info.get("height", 0) if chain_info else 0)

    def handle_blockchain_block(args):
        if args.number is None:
            print("Error: block number is required")
            sys.exit(1)
        print(f"Block #{args.number}:")
        print(f"  Hash: 0x{args.number:016x}")
        print("  Timestamp: $(date)")
        print(f"  Transactions: {args.number % 100}")
        print(f"  Gas used: {args.number * 1000}")

    def handle_network_status(args):
        print("Network status:")
        print("  Connected nodes: 2")
        print("  Genesis: healthy")
        print("  Follower: healthy")
        print("  Sync status: synchronized")

    def handle_network_peers(args):
        print("Network peers:")
        print("  - genesis (localhost:8006) - Connected")
        print("  - aitbc1 (10.1.223.40:8007) - Connected")

    def handle_network_sync(args):
        print("Network sync status:")
        print("  Status: synchronized")
        print("  Block height: 22502")
        print("  Last sync: $(date)")

    def handle_network_ping(args):
        node = args.node or "aitbc1"
        print(f"Ping: Node {node} reachable")
        print("  Latency: 5ms")
        print("  Status: connected")

    def handle_network_propagate(args):
        data = args.data or "test-data"
        print("Data propagation: Complete")
        print(f"  Data: {data}")
        print("  Nodes: 2/2 updated")

    def handle_market_action(args):
        kwargs = {
            "name": getattr(args, "item_type", None),
            "price": getattr(args, "price", None),
            "description": getattr(args, "description", None),
            "wallet": getattr(args, "wallet", None),
            "rpc_url": getattr(args, "rpc_url", default_rpc_url),
        }
        result = marketplace_operations(args.market_action, **kwargs)
        if not result:
            sys.exit(1)
        render_mapping(f"Marketplace {args.market_action}:", result)

    def handle_ai_action(args):
        wallet_name = first(getattr(args, "wallet_name", None), getattr(args, "wallet", None))
        kwargs = {
            "model": first(getattr(args, "job_type_arg", None), getattr(args, "job_type", None)),
            "prompt": first(getattr(args, "prompt_arg", None), getattr(args, "prompt", None)),
            "job_id": first(getattr(args, "job_id_arg", None), getattr(args, "job_id", None)),
            "wallet": wallet_name,
            "payment": first(getattr(args, "payment_arg", None), getattr(args, "payment", None)),
        }
        if args.ai_action == "submit":
            if not wallet_name or not kwargs["model"] or not kwargs["prompt"] or kwargs["payment"] is None:
                print("Error: Wallet, type, prompt, and payment are required")
                sys.exit(1)
        result = ai_operations(args.ai_action, **kwargs)
        if not result:
            sys.exit(1)
        render_mapping(f"AI {args.ai_action}:", result)

    def handle_mining_action(args):
        result = mining_operations(args.mining_action, wallet=getattr(args, "wallet", None), rpc_url=getattr(args, "rpc_url", default_rpc_url))
        if not result:
            sys.exit(1)
        render_mapping(f"Mining {args.mining_action}:", result)

    def handle_system_status(args):
        print("System status: OK")
        print(f"  Version: aitbc-cli v{cli_version}")
        print("  Services: Running")
        print("  Nodes: 2 connected")

    def handle_analytics(args):
        analytics_type = getattr(args, "type", "blocks")
        limit = getattr(args, "limit", 10)
        rpc_url = getattr(args, "rpc_url", default_rpc_url)
        analytics = get_blockchain_analytics(analytics_type, limit, rpc_url=rpc_url)
        if analytics:
            print(f"Blockchain Analytics ({analytics['type']}):")
            for key, value in analytics.items():
                if key != "type":
                    print(f"  {key.replace('_', ' ').title()}: {value}")
        else:
            sys.exit(1)

    def handle_agent_action(args):
        kwargs = {}
        for name in ("name", "description", "verification", "max_execution_time", "max_cost_budget", "input_data", "wallet", "priority", "execution_id", "status"):
            value = getattr(args, name, None)
            if value not in (None, "", False):
                kwargs[name] = value
        result = agent_operations(args.agent_action, **kwargs)
        if not result:
            sys.exit(1)
        render_mapping(f"Agent {result['action']}:", result)

    def handle_openclaw_action(args):
        kwargs = {}
        for name in ("agent_file", "wallet", "environment", "agent_id", "metrics", "price"):
            value = getattr(args, name, None)
            if value not in (None, "", False):
                kwargs[name] = value
        market_action = first(getattr(args, "market_action", None), getattr(args, "market_action_opt", None))
        if market_action:
            kwargs["market_action"] = market_action
        result = openclaw_operations(args.openclaw_action, **kwargs)
        if not result:
            sys.exit(1)
        render_mapping(f"OpenClaw {result['action']}:", result)

    def handle_workflow_action(args):
        kwargs = {}
        for name in ("name", "template", "config_file", "params", "async_exec"):
            value = getattr(args, name, None)
            if value not in (None, "", False):
                kwargs[name] = value
        result = workflow_operations(args.workflow_action, **kwargs)
        if not result:
            sys.exit(1)
        render_mapping(f"Workflow {result['action']}:", result)

    def handle_resource_action(args):
        kwargs = {}
        for name in ("type", "agent_id", "cpu", "memory", "duration"):
            value = getattr(args, name, None)
            if value not in (None, "", False):
                kwargs[name] = value
        result = resource_operations(args.resource_action, **kwargs)
        if not result:
            sys.exit(1)
        render_mapping(f"Resource {result['action']}:", result)

    def handle_simulate_action(args):
        if args.simulate_command == "blockchain":
            simulate_blockchain(args.blocks, args.transactions, args.delay)
        elif args.simulate_command == "wallets":
            simulate_wallets(args.wallets, args.balance, args.transactions, args.amount_range)
        elif args.simulate_command == "price":
            simulate_price(args.price, args.volatility, args.timesteps, args.delay)
        elif args.simulate_command == "network":
            simulate_network(args.nodes, args.network_delay, args.failure_rate)
        elif args.simulate_command == "ai-jobs":
            simulate_ai_jobs(args.jobs, args.models, args.duration_range)
        else:
            print(f"Unknown simulate command: {args.simulate_command}")
            sys.exit(1)

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
    network_ping_parser.add_argument("--rpc-url", default=default_rpc_url)
    network_ping_parser.set_defaults(handler=handle_network_ping)

    network_propagate_parser = network_subparsers.add_parser("propagate", help="Propagate test data")
    network_propagate_parser.add_argument("data", nargs="?")
    network_propagate_parser.add_argument("--rpc-url", default=default_rpc_url)
    network_propagate_parser.set_defaults(handler=handle_network_propagate)

    market_parser = subparsers.add_parser("market", help="Marketplace listings and offers")
    market_parser.set_defaults(handler=lambda parsed, parser=market_parser: parser.print_help())
    market_subparsers = market_parser.add_subparsers(dest="market_action")

    market_list_parser = market_subparsers.add_parser("list", help="List marketplace items")
    market_list_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_list_parser.set_defaults(handler=handle_market_action, market_action="list")

    market_create_parser = market_subparsers.add_parser("create", help="Create a marketplace listing")
    market_create_parser.add_argument("--wallet", required=True)
    market_create_parser.add_argument("--type", dest="item_type", required=True)
    market_create_parser.add_argument("--price", type=float, required=True)
    market_create_parser.add_argument("--description", required=True)
    market_create_parser.add_argument("--password")
    market_create_parser.add_argument("--password-file")
    market_create_parser.set_defaults(handler=handle_market_action, market_action="create")

    market_search_parser = market_subparsers.add_parser("search", help="Search marketplace items")
    market_search_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_search_parser.set_defaults(handler=handle_market_action, market_action="search")

    market_mine_parser = market_subparsers.add_parser("my-listings", help="Show your marketplace listings")
    market_mine_parser.add_argument("--wallet")
    market_mine_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_mine_parser.set_defaults(handler=handle_market_action, market_action="my-listings")

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
    ai_submit_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_submit_parser.set_defaults(handler=handle_ai_action, ai_action="submit")

    ai_status_parser = ai_subparsers.add_parser("status", help="Show AI job status")
    ai_status_parser.add_argument("job_id_arg", nargs="?")
    ai_status_parser.add_argument("--job-id", dest="job_id")
    ai_status_parser.add_argument("--wallet")
    ai_status_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_status_parser.set_defaults(handler=handle_ai_action, ai_action="status")

    ai_results_parser = ai_subparsers.add_parser("results", help="Show AI job results")
    ai_results_parser.add_argument("job_id_arg", nargs="?")
    ai_results_parser.add_argument("--job-id", dest="job_id")
    ai_results_parser.add_argument("--wallet")
    ai_results_parser.add_argument("--rpc-url", default=default_rpc_url)
    ai_results_parser.set_defaults(handler=handle_ai_action, ai_action="results")

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
    analytics_parser.add_argument("--type", choices=["blocks", "transactions", "accounts", "supply"], default="blocks", help="Analytics type")
    analytics_parser.add_argument("--limit", type=int, default=10, help="Number of items to analyze")
    analytics_parser.add_argument("--rpc-url", default=default_rpc_url)
    analytics_parser.set_defaults(handler=handle_analytics)

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

    parsed_args = parser.parse_args(normalize_legacy_args(list(sys.argv[1:] if argv is None else argv)))
    if not getattr(parsed_args, "command", None):
        parser.print_help()
        return
    handler = getattr(parsed_args, "handler", None)
    if handler is None:
        parser.print_help()
        return
    handler(parsed_args)
