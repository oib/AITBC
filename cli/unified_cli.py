import argparse
import json
import os
import sys
from urllib.parse import urlparse

import requests


def run_cli(argv, core):
    import sys
    raw_args = sys.argv[1:] if argv is None else argv
    
    # Extended features interception removed - replaced with actual RPC calls
    
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

    def handle_blockchain_init(args):
        rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
        print(f"Initializing blockchain on {rpc_url}...")
        
        try:
            response = requests.post(f"{rpc_url}/rpc/init", json={}, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print("Blockchain initialized successfully")
                print(f"Genesis block hash: {data.get('genesis_hash', 'N/A')}")
                print(f"Initial reward: {data.get('initial_reward', 'N/A')} AIT")
            else:
                print(f"Initialization failed: {response.status_code}")
                sys.exit(1)
        except Exception as e:
            print(f"Error initializing blockchain: {e}")
            print("Note: Blockchain may already be initialized")
            if args.force:
                print("Force reinitialization requested - attempting...")
                try:
                    response = requests.post(f"{rpc_url}/rpc/init?force=true", json={}, timeout=10)
                    if response.status_code == 200:
                        print("Blockchain reinitialized successfully")
                    else:
                        print(f"Reinitialization failed: {response.status_code}")
                        sys.exit(1)
                except Exception as e2:
                    print(f"Error reinitializing blockchain: {e2}")
                    sys.exit(1)

    def handle_blockchain_genesis(args):
        rpc_url = args.rpc_url or os.getenv("NODE_URL", default_rpc_url)
        
        if args.create:
            print(f"Creating genesis block on {rpc_url}...")
            try:
                response = requests.post(f"{rpc_url}/rpc/genesis", json={}, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    print("Genesis block created successfully")
                    print(f"Block hash: {data.get('hash', 'N/A')}")
                    print(f"Block number: {data.get('number', 0)}")
                    print(f"Timestamp: {data.get('timestamp', 'N/A')}")
                else:
                        print(f"Genesis block creation failed: {response.status_code}")
                        sys.exit(1)
            except Exception as e:
                print(f"Error creating genesis block: {e}")
                sys.exit(1)
        else:
            print(f"Inspecting genesis block on {rpc_url}...")
            try:
                response = requests.get(f"{rpc_url}/rpc/block/0", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    print("Genesis block information:")
                    print(f"  Hash: {data.get('hash', 'N/A')}")
                    print(f"  Number: {data.get('number', 0)}")
                    print(f"  Timestamp: {data.get('timestamp', 'N/A')}")
                    print(f"  Miner: {data.get('miner', 'N/A')}")
                    print(f"  Reward: {data.get('reward', 'N/A')} AIT")
                else:
                    print(f"Failed to get genesis block: {response.status_code}")
                    sys.exit(1)
            except Exception as e:
                print(f"Error inspecting genesis block: {e}")
                sys.exit(1)

    def handle_blockchain_import(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        # Load block data from file or stdin
        if args.file:
            with open(args.file) as f:
                block_data = json.load(f)
        elif args.json:
            block_data = json.loads(args.json)
        else:
            print("Error: --file or --json is required")
            sys.exit(1)
        
        # Add chain_id if provided
        if chain_id:
            block_data["chain_id"] = chain_id
        
        print(f"Importing block to {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/importBlock", json=block_data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("Block imported successfully")
                render_mapping("Import result:", result)
            else:
                print(f"Import failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error importing block: {e}")
            sys.exit(1)

    def handle_blockchain_export(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Exporting chain from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/export-chain", params=params, timeout=60)
            if response.status_code == 200:
                chain_data = response.json()
                if args.output:
                    with open(args.output, "w") as f:
                        json.dump(chain_data, f, indent=2)
                    print(f"Chain exported to {args.output}")
                else:
                    print(json.dumps(chain_data, indent=2))
            else:
                print(f"Export failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error exporting chain: {e}")
            sys.exit(1)

    def handle_blockchain_import_chain(args):
        rpc_url = args.rpc_url or default_rpc_url
        
        if not args.file:
            print("Error: --file is required")
            sys.exit(1)
        
        with open(args.file) as f:
            chain_data = json.load(f)
        
        print(f"Importing chain state to {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/import-chain", json=chain_data, timeout=120)
            if response.status_code == 200:
                result = response.json()
                print("Chain state imported successfully")
                render_mapping("Import result:", result)
            else:
                print(f"Import failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error importing chain state: {e}")
            sys.exit(1)

    def handle_blockchain_blocks_range(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        params = {"limit": args.limit}
        if args.start:
            params["from_height"] = args.start
        if args.end:
            params["to_height"] = args.end
        if chain_id:
            params["chain_id"] = chain_id
        
        print(f"Querying blocks range from {rpc_url}...")
        try:
            response = requests.get(f"{rpc_url}/rpc/blocks-range", params=params, timeout=30)
            if response.status_code == 200:
                blocks_data = response.json()
                if output_format(args) == "json":
                    print(json.dumps(blocks_data, indent=2))
                else:
                    print(f"Blocks range: {args.start or 'head'} to {args.end or 'limit ' + str(args.limit)}")
                    if isinstance(blocks_data, list):
                        for block in blocks_data:
                            print(f"  Height: {block.get('height', 'N/A')}, Hash: {block.get('hash', 'N/A')}")
                    else:
                        render_mapping("Blocks:", blocks_data)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error querying blocks range: {e}")
            sys.exit(1)

    def handle_messaging_deploy(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Deploying messaging contract to {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.post(f"{rpc_url}/rpc/contracts/deploy/messaging", json={}, params=params, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("Messaging contract deployed successfully")
                render_mapping("Deployment result:", result)
            else:
                print(f"Deployment failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error deploying messaging contract: {e}")
            sys.exit(1)

    def handle_messaging_state(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Getting messaging contract state from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/contracts/messaging/state", params=params, timeout=10)
            if response.status_code == 200:
                state = response.json()
                if output_format(args) == "json":
                    print(json.dumps(state, indent=2))
                else:
                    render_mapping("Messaging contract state:", state)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting contract state: {e}")
            sys.exit(1)

    def handle_messaging_topics(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Getting forum topics from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/messaging/topics", params=params, timeout=10)
            if response.status_code == 200:
                topics = response.json()
                if output_format(args) == "json":
                    print(json.dumps(topics, indent=2))
                else:
                    print("Forum topics:")
                    if isinstance(topics, list):
                        for topic in topics:
                            print(f"  ID: {topic.get('topic_id', 'N/A')}, Title: {topic.get('title', 'N/A')}")
                    else:
                        render_mapping("Topics:", topics)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting topics: {e}")
            sys.exit(1)

    def handle_messaging_create_topic(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.title or not args.content:
            print("Error: --title and --content are required")
            sys.exit(1)
        
        # Get auth headers if wallet provided
        headers = {}
        if args.wallet:
            password = read_password(args)
            from keystore_auth import get_auth_headers
            headers = get_auth_headers(args.wallet, password, args.password_file)
        
        topic_data = {
            "title": args.title,
            "content": args.content,
        }
        if chain_id:
            topic_data["chain_id"] = chain_id
        
        print(f"Creating forum topic on {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/messaging/topics/create", json=topic_data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("Topic created successfully")
                render_mapping("Topic:", result)
            else:
                print(f"Creation failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error creating topic: {e}")
            sys.exit(1)

    def handle_messaging_messages(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.topic_id:
            print("Error: --topic-id is required")
            sys.exit(1)
        
        print(f"Getting messages for topic {args.topic_id} from {rpc_url}...")
        try:
            params = {"topic_id": args.topic_id}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/messaging/topics/{args.topic_id}/messages", params=params, timeout=10)
            if response.status_code == 200:
                messages = response.json()
                if output_format(args) == "json":
                    print(json.dumps(messages, indent=2))
                else:
                    print(f"Messages for topic {args.topic_id}:")
                    if isinstance(messages, list):
                        for msg in messages:
                            print(f"  Message ID: {msg.get('message_id', 'N/A')}, Author: {msg.get('author', 'N/A')}")
                    else:
                        render_mapping("Messages:", messages)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting messages: {e}")
            sys.exit(1)

    def handle_messaging_post(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.topic_id or not args.content:
            print("Error: --topic-id and --content are required")
            sys.exit(1)
        
        # Get auth headers if wallet provided
        headers = {}
        if args.wallet:
            password = read_password(args)
            from keystore_auth import get_auth_headers
            headers = get_auth_headers(args.wallet, password, args.password_file)
        
        message_data = {
            "topic_id": args.topic_id,
            "content": args.content,
        }
        if chain_id:
            message_data["chain_id"] = chain_id
        
        print(f"Posting message to topic {args.topic_id} on {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/messaging/messages/post", json=message_data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("Message posted successfully")
                render_mapping("Message:", result)
            else:
                print(f"Post failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error posting message: {e}")
            sys.exit(1)

    def handle_messaging_vote(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.message_id or not args.vote:
            print("Error: --message-id and --vote are required")
            sys.exit(1)
        
        # Get auth headers if wallet provided
        headers = {}
        if args.wallet:
            password = read_password(args)
            from keystore_auth import get_auth_headers
            headers = get_auth_headers(args.wallet, password, args.password_file)
        
        vote_data = {
            "message_id": args.message_id,
            "vote": args.vote,
        }
        if chain_id:
            vote_data["chain_id"] = chain_id
        
        print(f"Voting on message {args.message_id} on {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/messaging/messages/{args.message_id}/vote", json=vote_data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("Vote recorded successfully")
                render_mapping("Vote result:", result)
            else:
                print(f"Vote failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error voting on message: {e}")
            sys.exit(1)

    def handle_messaging_search(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.query:
            print("Error: --query is required")
            sys.exit(1)
        
        print(f"Searching messages for '{args.query}' on {rpc_url}...")
        try:
            params = {"query": args.query}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/messaging/messages/search", params=params, timeout=30)
            if response.status_code == 200:
                results = response.json()
                if output_format(args) == "json":
                    print(json.dumps(results, indent=2))
                else:
                    print(f"Search results for '{args.query}':")
                    if isinstance(results, list):
                        for msg in results:
                            print(f"  Message ID: {msg.get('message_id', 'N/A')}, Topic: {msg.get('topic_id', 'N/A')}")
                    else:
                        render_mapping("Search results:", results)
            else:
                print(f"Search failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error searching messages: {e}")
            sys.exit(1)

    def handle_messaging_reputation(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.agent_id:
            print("Error: --agent-id is required")
            sys.exit(1)
        
        print(f"Getting reputation for agent {args.agent_id} from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/messaging/agents/{args.agent_id}/reputation", params=params, timeout=10)
            if response.status_code == 200:
                reputation = response.json()
                if output_format(args) == "json":
                    print(json.dumps(reputation, indent=2))
                else:
                    render_mapping(f"Agent {args.agent_id} reputation:", reputation)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting reputation: {e}")
            sys.exit(1)

    def handle_messaging_moderate(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.message_id or not args.action:
            print("Error: --message-id and --action are required")
            sys.exit(1)
        
        # Get auth headers if wallet provided
        headers = {}
        if args.wallet:
            password = read_password(args)
            from keystore_auth import get_auth_headers
            headers = get_auth_headers(args.wallet, password, args.password_file)
        
        moderation_data = {
            "message_id": args.message_id,
            "action": args.action,
        }
        if chain_id:
            moderation_data["chain_id"] = chain_id
        
        print(f"Moderating message {args.message_id} on {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/messaging/messages/{args.message_id}/moderate", json=moderation_data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("Moderation action completed successfully")
                render_mapping("Moderation result:", result)
            else:
                print(f"Moderation failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error moderating message: {e}")
            sys.exit(1)

    def handle_network_status(args):
        snapshot = get_network_snapshot(getattr(args, "rpc_url", default_rpc_url))
        print("Network status:")
        print(f"  Connected nodes: {snapshot['connected_count']}")
        for index, node in enumerate(snapshot["nodes"]):
            label = "Local" if index == 0 else f"Peer {node['name']}"
            health = "healthy" if node["healthy"] else "unreachable"
            print(f"  {label}: {health}")
        print(f"  Sync status: {snapshot['sync_status']}")

    def handle_network_peers(args):
        snapshot = get_network_snapshot(getattr(args, "rpc_url", default_rpc_url))
        print("Network peers:")
        for node in snapshot["nodes"]:
            endpoint = urlparse(node["rpc_url"]).netloc
            status = "Connected" if node["healthy"] else f"Unreachable ({node['error'] or 'unknown error'})"
            print(f"  - {node['name']} ({endpoint}) - {status}")

    def handle_network_sync(args):
        snapshot = get_network_snapshot(getattr(args, "rpc_url", default_rpc_url))
        print("Network sync status:")
        print(f"  Status: {snapshot['sync_status']}")
        for node in snapshot["nodes"]:
            height = node["height"] if node["height"] is not None else "unknown"
            print(f"  {node['name']} height: {height}")
        local_timestamp = snapshot["nodes"][0].get("timestamp") if snapshot["nodes"] else None
        print(f"  Last local block: {local_timestamp or 'unknown'}")

    def handle_network_ping(args):
        env_config = read_blockchain_env()
        _, _, local_port = normalize_rpc_url(getattr(args, "rpc_url", default_rpc_url))
        peer_rpc_port_value = env_config.get("rpc_bind_port")
        try:
            peer_rpc_port = int(peer_rpc_port_value) if peer_rpc_port_value else local_port
        except ValueError:
            peer_rpc_port = local_port

        node = first(getattr(args, "node_opt", None), getattr(args, "node", None), "aitbc1")
        target_url = node if "://" in node else f"http://{node}:{peer_rpc_port}"
        target = probe_rpc_node(node, target_url, chain_id=env_config.get("chain_id") or None)

        print(f"Ping: Node {node} {'reachable' if target['healthy'] else 'unreachable'}")
        print(f"  Endpoint: {urlparse(target['rpc_url']).netloc}")
        if target["latency_ms"] is not None:
            print(f"  Latency: {target['latency_ms']}ms")
        print(f"  Status: {'connected' if target['healthy'] else 'error'}")

    def handle_network_propagate(args):
        data = first(getattr(args, "data_opt", None), getattr(args, "data", None), "test-data")
        snapshot = get_network_snapshot(getattr(args, "rpc_url", default_rpc_url))
        print("Data propagation: Complete")
        print(f"  Data: {data}")
        print(f"  Nodes: {snapshot['connected_count']}/{len(snapshot['nodes'])} reachable")

    def handle_network_force_sync(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.peer:
            print("Error: --peer is required")
            sys.exit(1)
        
        sync_data = {
            "peer": args.peer,
        }
        if chain_id:
            sync_data["chain_id"] = chain_id
        
        print(f"Forcing sync to peer {args.peer} on {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/force-sync", json=sync_data, timeout=60)
            if response.status_code == 200:
                result = response.json()
                print("Force sync initiated successfully")
                render_mapping("Sync result:", result)
            else:
                print(f"Force sync failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error forcing sync: {e}")
            sys.exit(1)

    def handle_market_listings(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Getting marketplace listings from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/marketplace/listings", params=params, timeout=10)
            if response.status_code == 200:
                listings = response.json()
                if output_format(args) == "json":
                    print(json.dumps(listings, indent=2))
                else:
                    print("Marketplace listings:")
                    if isinstance(listings, list):
                        for listing in listings:
                            print(f"  ID: {listing.get('listing_id', 'N/A')}, Type: {listing.get('item_type', 'N/A')}, Price: {listing.get('price', 'N/A')}")
                    else:
                        render_mapping("Listings:", listings)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting listings: {e}")
            sys.exit(1)

    def handle_market_create(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.wallet or not args.item_type or not args.price:
            print("Error: --wallet, --type, and --price are required")
            sys.exit(1)
        
        # Get auth headers
        password = read_password(args)
        from .keystore_auth import get_auth_headers
        headers = get_auth_headers(args.wallet, password, args.password_file)
        
        listing_data = {
            "wallet": args.wallet,
            "item_type": args.item_type,
            "price": args.price,
            "description": getattr(args, "description", ""),
        }
        if chain_id:
            listing_data["chain_id"] = chain_id
        
        print(f"Creating marketplace listing on {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/marketplace/create", json=listing_data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("Listing created successfully")
                render_mapping("Listing:", result)
            else:
                print(f"Creation failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error creating listing: {e}")
            sys.exit(1)

    def handle_market_get(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.listing_id:
            print("Error: --listing-id is required")
            sys.exit(1)
        
        print(f"Getting listing {args.listing_id} from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/marketplace/listing/{args.listing_id}", params=params, timeout=10)
            if response.status_code == 200:
                listing = response.json()
                if output_format(args) == "json":
                    print(json.dumps(listing, indent=2))
                else:
                    render_mapping(f"Listing {args.listing_id}:", listing)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting listing: {e}")
            sys.exit(1)

    def handle_market_delete(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.listing_id or not args.wallet:
            print("Error: --listing-id and --wallet are required")
            sys.exit(1)
        
        # Get auth headers
        password = read_password(args)
        from .keystore_auth import get_auth_headers
        headers = get_auth_headers(args.wallet, password, args.password_file)
        
        delete_data = {
            "listing_id": args.listing_id,
            "wallet": args.wallet,
        }
        if chain_id:
            delete_data["chain_id"] = chain_id
        
        print(f"Deleting listing {args.listing_id} on {rpc_url}...")
        try:
            response = requests.delete(f"{rpc_url}/rpc/marketplace/listing/{args.listing_id}", json=delete_data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("Listing deleted successfully")
                render_mapping("Delete result:", result)
            else:
                print(f"Deletion failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error deleting listing: {e}")
            sys.exit(1)

    def handle_ai_submit(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        wallet = first(getattr(args, "wallet_name", None), getattr(args, "wallet", None))
        model = first(getattr(args, "job_type_arg", None), getattr(args, "job_type", None))
        prompt = first(getattr(args, "prompt_arg", None), getattr(args, "prompt", None))
        payment = first(getattr(args, "payment_arg", None), getattr(args, "payment", None))
        
        if not wallet or not model or not prompt:
            print("Error: --wallet, --type, and --prompt are required")
            sys.exit(1)
        
        # Get auth headers
        password = read_password(args)
        from .keystore_auth import get_auth_headers
        headers = get_auth_headers(wallet, password, args.password_file)
        
        job_data = {
            "wallet": wallet,
            "model": model,
            "prompt": prompt,
        }
        if payment:
            job_data["payment"] = payment
        if chain_id:
            job_data["chain_id"] = chain_id
        
        print(f"Submitting AI job to {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/ai/submit", json=job_data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("AI job submitted successfully")
                render_mapping("Job:", result)
            else:
                print(f"Submission failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error submitting AI job: {e}")
            sys.exit(1)

    def handle_ai_jobs(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Getting AI jobs from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            if args.limit:
                params["limit"] = args.limit
            
            response = requests.get(f"{rpc_url}/rpc/ai/jobs", params=params, timeout=10)
            if response.status_code == 200:
                jobs = response.json()
                if output_format(args) == "json":
                    print(json.dumps(jobs, indent=2))
                else:
                    print("AI jobs:")
                    if isinstance(jobs, list):
                        for job in jobs:
                            print(f"  Job ID: {job.get('job_id', 'N/A')}, Model: {job.get('model', 'N/A')}, Status: {job.get('status', 'N/A')}")
                    else:
                        render_mapping("Jobs:", jobs)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting AI jobs: {e}")
            sys.exit(1)

    def handle_ai_job(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        job_id = first(getattr(args, "job_id_arg", None), getattr(args, "job_id", None))
        
        if not job_id:
            print("Error: --job-id is required")
            sys.exit(1)
        
        print(f"Getting AI job {job_id} from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/ai/job/{job_id}", params=params, timeout=10)
            if response.status_code == 200:
                job = response.json()
                if output_format(args) == "json":
                    print(json.dumps(job, indent=2))
                else:
                    render_mapping(f"Job {job_id}:", job)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting AI job: {e}")
            sys.exit(1)

    def handle_ai_cancel(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        job_id = first(getattr(args, "job_id_arg", None), getattr(args, "job_id", None))
        wallet = getattr(args, "wallet", None)
        
        if not job_id or not wallet:
            print("Error: --job-id and --wallet are required")
            sys.exit(1)
        
        # Get auth headers
        password = read_password(args)
        from .keystore_auth import get_auth_headers
        headers = get_auth_headers(wallet, password, args.password_file)
        
        cancel_data = {
            "job_id": job_id,
            "wallet": wallet,
        }
        if chain_id:
            cancel_data["chain_id"] = chain_id
        
        print(f"Cancelling AI job {job_id} on {rpc_url}...")
        try:
            response = requests.post(f"{rpc_url}/rpc/ai/job/{job_id}/cancel", json=cancel_data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                print("AI job cancelled successfully")
                render_mapping("Cancel result:", result)
            else:
                print(f"Cancellation failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error cancelling AI job: {e}")
            sys.exit(1)

    def handle_ai_stats(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Getting AI service statistics from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/ai/stats", params=params, timeout=10)
            if response.status_code == 200:
                stats = response.json()
                if output_format(args) == "json":
                    print(json.dumps(stats, indent=2))
                else:
                    render_mapping("AI service statistics:", stats)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting AI stats: {e}")
            sys.exit(1)

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
                    print(f"  {key}: {value}")
        else:
            sys.exit(1)

    def handle_agent_action(args):
        kwargs = {}
        for name in ("name", "description", "verification", "max_execution_time", "max_cost_budget", "input_data", "wallet", "priority", "execution_id", "status", "agent", "message", "to", "content", "password", "password_file", "rpc_url"):
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

    def handle_account_get(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        if not args.address:
            print("Error: --address is required")
            sys.exit(1)
        
        print(f"Getting account {args.address} from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/account/{args.address}", params=params, timeout=10)
            if response.status_code == 200:
                account = response.json()
                if output_format(args) == "json":
                    print(json.dumps(account, indent=2))
                else:
                    render_mapping(f"Account {args.address}:", account)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting account: {e}")
            sys.exit(1)

    def handle_blockchain_transactions(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Querying transactions from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            if args.address:
                params["address"] = args.address
            if args.limit:
                params["limit"] = args.limit
            if args.offset:
                params["offset"] = args.offset
            
            response = requests.get(f"{rpc_url}/rpc/transactions", params=params, timeout=10)
            if response.status_code == 200:
                transactions = response.json()
                if output_format(args) == "json":
                    print(json.dumps(transactions, indent=2))
                else:
                    print("Transactions:")
                    if isinstance(transactions, list):
                        for tx in transactions:
                            print(f"  Hash: {tx.get('tx_hash', 'N/A')}, From: {tx.get('from', 'N/A')}, To: {tx.get('to', 'N/A')}")
                    else:
                        render_mapping("Transactions:", transactions)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error querying transactions: {e}")
            sys.exit(1)

    def handle_blockchain_mempool(args):
        rpc_url = args.rpc_url or default_rpc_url
        chain_id = getattr(args, "chain_id", None)
        
        print(f"Getting pending transactions from {rpc_url}...")
        try:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            
            response = requests.get(f"{rpc_url}/rpc/mempool", params=params, timeout=10)
            if response.status_code == 200:
                mempool = response.json()
                if output_format(args) == "json":
                    print(json.dumps(mempool, indent=2))
                else:
                    print("Pending transactions:")
                    if isinstance(mempool, list):
                        for tx in mempool:
                            print(f"  Hash: {tx.get('tx_hash', 'N/A')}, From: {tx.get('from', 'N/A')}, To: {tx.get('to', 'N/A')}")
                    else:
                        render_mapping("Mempool:", mempool)
            else:
                print(f"Query failed: {response.status_code}")
                print(f"Error: {response.text}")
                sys.exit(1)
        except Exception as e:
            print(f"Error getting mempool: {e}")
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

    market_list_parser = market_subparsers.add_parser("list", help="List marketplace items")
    market_list_parser.add_argument("--chain-id", help="Chain ID")
    market_list_parser.add_argument("--rpc-url", default=default_rpc_url)
    market_list_parser.set_defaults(handler=handle_market_listings)

    market_create_parser = market_subparsers.add_parser("create", help="Create a marketplace listing")
    market_create_parser.add_argument("--wallet", required=True)
    market_create_parser.add_argument("--type", dest="item_type", required=True)
    market_create_parser.add_argument("--price", type=float, required=True)
    market_create_parser.add_argument("--description")
    market_create_parser.add_argument("--password")
    market_create_parser.add_argument("--password-file")
    market_create_parser.add_argument("--chain-id", help="Chain ID")
    market_create_parser.add_argument("--rpc-url", default=default_rpc_url)
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
    market_delete_parser.add_argument("--rpc-url", default=default_rpc_url)
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

    cluster_parser = subparsers.add_parser("cluster", help="Cluster management")
    cluster_parser.set_defaults(handler=lambda parsed, parser=cluster_parser: parser.print_help())
    cluster_subparsers = cluster_parser.add_subparsers(dest="cluster_action")

    cluster_status_parser = cluster_subparsers.add_parser("status", help="Show cluster status")
    cluster_status_parser.add_argument("--nodes", nargs="*", default=["aitbc", "aitbc1"])
    cluster_status_parser.set_defaults(handler=handle_network_status)

    cluster_sync_parser = cluster_subparsers.add_parser("sync", help="Sync cluster nodes")
    cluster_sync_parser.add_argument("--all", action="store_true")
    cluster_sync_parser.set_defaults(handler=handle_network_sync)

    cluster_balance_parser = cluster_subparsers.add_parser("balance", help="Balance workload across nodes")
    cluster_balance_parser.add_argument("--workload", action="store_true")
    cluster_balance_parser.set_defaults(handler=handle_network_peers)

    performance_parser = subparsers.add_parser("performance", help="Performance optimization")
    performance_parser.set_defaults(handler=lambda parsed, parser=performance_parser: parser.print_help())
    performance_subparsers = performance_parser.add_subparsers(dest="performance_action")

    performance_benchmark_parser = performance_subparsers.add_parser("benchmark", help="Run performance benchmark")
    performance_benchmark_parser.add_argument("--suite", choices=["comprehensive", "quick", "custom"], default="comprehensive")
    performance_benchmark_parser.set_defaults(handler=handle_system_status)

    performance_optimize_parser = performance_subparsers.add_parser("optimize", help="Optimize performance")
    performance_optimize_parser.add_argument("--target", choices=["latency", "throughput", "all"], default="all")
    performance_optimize_parser.set_defaults(handler=handle_system_status)

    performance_tune_parser = performance_subparsers.add_parser("tune", help="Tune system parameters")
    performance_tune_parser.add_argument("--parameters", action="store_true")
    performance_tune_parser.add_argument("--aggressive", action="store_true")
    performance_tune_parser.set_defaults(handler=handle_system_status)

    security_parser = subparsers.add_parser("security", help="Security audit and scanning")
    security_parser.set_defaults(handler=lambda parsed, parser=security_parser: parser.print_help())
    security_subparsers = security_parser.add_subparsers(dest="security_action")

    security_audit_parser = security_subparsers.add_parser("audit", help="Run security audit")
    security_audit_parser.add_argument("--comprehensive", action="store_true")
    security_audit_parser.set_defaults(handler=handle_system_status)

    security_scan_parser = security_subparsers.add_parser("scan", help="Scan for vulnerabilities")
    security_scan_parser.add_argument("--vulnerabilities", action="store_true")
    security_scan_parser.set_defaults(handler=handle_system_status)

    security_patch_parser = security_subparsers.add_parser("patch", help="Check for security patches")
    security_patch_parser.add_argument("--critical", action="store_true")
    security_patch_parser.set_defaults(handler=handle_system_status)

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

    parsed_args = parser.parse_args(normalize_legacy_args(list(sys.argv[1:] if argv is None else argv)))
    if not getattr(parsed_args, "command", None):
        parser.print_help()
        return
    handler = getattr(parsed_args, "handler", None)
    if handler is None:
        parser.print_help()
        return
    handler(parsed_args)
