"""
General operations commands for AITBC CLI (marketplace, AI, agents)
"""

import json
from pathlib import Path

import click
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

from ..config import get_config
from ..utils import error, output, success
from ..utils.wallet import decrypt_private_key

logger = get_logger(__name__)

DEFAULT_RPC_URL = "http://localhost:8202"
DEFAULT_WALLET_DIR = Path.home() / ".aitbc" / "wallets"


def _load_wallet(wallet_path: Path, wallet_name: str) -> dict:
    """Load wallet and decrypt private key if needed"""
    with open(wallet_path) as f:
        wallet_data = json.load(f)

    # Decrypt private key if encrypted
    if wallet_data.get("encrypted") and "private_key" in wallet_data:
        from ..utils.wallet import decrypt_value
        password = _get_wallet_password(wallet_name)
        try:
            wallet_data["private_key"] = decrypt_value(
                wallet_data["private_key"], password
            )
        except Exception:
            error("Invalid password for wallet")
            raise click.Abort()

    return wallet_data


def _get_wallet_password(wallet_name: str) -> str:
    """Get wallet password from user input"""
    import getpass
    return getpass.getpass(f"Enter password for wallet '{wallet_name}': ")


@click.group()
def operations():
    """General operations commands"""
    pass


# Marketplace operations
@operations.group()
def marketplace():
    """Marketplace operations"""
    pass


@marketplace.command()
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
def list_listings(format: str):
    """List marketplace listings"""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=30)
        data = http_client.get("/rpc/marketplace/listings")
        listings = data.get("listings", [])
        success(f"Marketplace listings: {len(listings)}")
        if format == 'json':
            click.echo(json.dumps(listings, indent=2))
        else:
            for listing in listings:
                click.echo(f"  - {listing.get('name', 'unknown')}: {listing.get('price', 0)} AIT")
    except NetworkError as e:
        error(f"Error getting marketplace listings: {e}")
    except Exception as e:
        error(f"Error: {e}")


@marketplace.command()
@click.argument('listing_id')
@click.option('--quantity', type=int, default=1, help='Quantity to purchase')
@click.option('--wallet', help='Wallet name for payment')
def purchase(listing_id: str, quantity: int, wallet: str | None):
    """Purchase from marketplace listing"""
    try:
        import httpx
        
        if not wallet:
            error("Wallet name required for payment")
            raise click.Abort()
        
        # Get wallet configuration
        config = get_config()
        keystore_path = DEFAULT_KEYSTORE_DIR / f"{wallet}.json"
        if not keystore_path.exists():
            error(f"Wallet '{wallet}' not found")
            raise click.Abort()
        
        # Load wallet
        with open(keystore_path) as f:
            wallet_data = json.load(f)
        
        wallet_address = wallet_data.get("address")
        if not wallet_address:
            error("Invalid wallet data")
            raise click.Abort()
        
        # Get wallet password
        password = os.environ.get("AITBC_WALLET_PASSWORD") or click.prompt("Wallet password", hide_input=True)
        
        # Get listing details from marketplace
        marketplace_url = config.get("marketplace_url", "http://localhost:8101")
        listing_response = httpx.get(f"{marketplace_url}/v1/marketplace/listings/{listing_id}")
        
        if listing_response.status_code != 200:
            error(f"Failed to get listing: {listing_response.text}")
            raise click.Abort()
        
        listing = listing_response.json()
        price = listing.get("price", 0) * quantity
        
        success(f"Purchase {quantity} of listing {listing_id} for {price} AIT")
        
        if not click.confirm("Confirm purchase?"):
            info("Cancelled")
            return
        
        # Unlock wallet via wallet daemon
        wallet_daemon_url = config.get("wallet_daemon_url", "http://localhost:8105")
        unlock_response = httpx.post(
            f"{wallet_daemon_url}/v1/chains/ait-hub/wallets/{wallet}/unlock",
            json={"password": password}
        )
        
        if unlock_response.status_code != 200:
            error("Failed to unlock wallet")
            raise click.Abort()
        
        # Sign transaction
        tx_payload = {
            "from": wallet_address,
            "to": listing.get("seller_address"),
            "value": str(int(price * 1000)),  # Convert to milli-AIT
            "data": json.dumps({"listing_id": listing_id, "quantity": quantity}),
            "type": "PURCHASE"
        }
        
        sign_response = httpx.post(
            f"{wallet_daemon_url}/v1/chains/ait-hub/wallets/{wallet}/sign",
            json=tx_payload
        )
        
        if sign_response.status_code != 200:
            error(f"Failed to sign transaction: {sign_response.text}")
            raise click.Abort()
        
        signed_tx = sign_response.json()
        tx_hash = signed_tx.get("transaction_hash")
        
        # Submit transaction to blockchain
        blockchain_rpc_url = config.get("blockchain_rpc_url", "http://localhost:8202")
        submit_response = httpx.post(
            f"{blockchain_rpc_url}/rpc/transactions/marketplace",
            json=signed_tx
        )
        
        if submit_response.status_code != 200:
            error(f"Failed to submit transaction: {submit_response.text}")
            raise click.Abort()
        
        success(f"Purchase successful (tx: {tx_hash[:16]}...)")
        
    except Exception as e:
        error(f"Error purchasing: {e}")
        raise click.Abort()


@marketplace.command()
@click.option('--wallet-name', required=True, help='Seller wallet name')
@click.option('--item-type', required=True, help='Type of item')
@click.option('--price', type=float, required=True, help='Listing price')
@click.option('--description', help='Item description')
def create_listing(wallet_name: str, item_type: str, price: float, description: str | None):
    """Create a marketplace listing"""
    try:
        # Get wallet address
        keystore_path = DEFAULT_KEYSTORE_DIR / f"{wallet_name}.json"
        if not keystore_path.exists():
            error(f"Wallet '{wallet_name}' not found")
            return None

        with open(keystore_path) as f:
            wallet_data = json.load(f)
        address = wallet_data['address']

        # Create listing via RPC
        listing_config = {
            "seller_address": address,
            "item_type": item_type,
            "price": price,
            "description": description or ""
        }

        try:
            http_client = AITBCHTTPClient(base_url="http://localhost:8102", timeout=30)
            result = http_client.post("/rpc/marketplace/create", json=listing_config)
            success("Listing created successfully")
            click.echo(f"Item: {item_type}")
            click.echo(f"Price: {price} AIT")
            click.echo(f"Listing ID: {result.get('listing_id', 'unknown')}")
            return result
        except NetworkError as e:
            error(f"Error creating listing: {e}")
            return None
        except Exception as e:
            error(f"Error: {e}")
            return None
    except Exception as e:
        error(f"Error: {e}")


# AI operations
@operations.group()
def ai():
    """AI operations"""
    pass


@ai.command()
@click.option('--wallet-name', required=True, help='Client wallet name')
@click.option('--job-type', required=True, help='Type of AI job')
@click.option('--prompt', required=True, help='AI prompt')
@click.option('--payment', type=float, required=True, help='Payment amount')
@click.option('--model', help='AI model to use')
def submit_job(wallet_name: str, job_type: str, prompt: str, payment: float, model: str | None):
    """Submit an AI job"""
    try:
        # Get wallet address
        keystore_path = DEFAULT_KEYSTORE_DIR / f"{wallet_name}.json"
        if not keystore_path.exists():
            error(f"Wallet '{wallet_name}' not found")
            return None

        with open(keystore_path) as f:
            wallet_data = json.load(f)
        address = wallet_data['address']

        # Submit job via coordinator API
        job_config = {
            "client_address": address,
            "job_type": job_type,
            "prompt": prompt,
            "payment": payment,
            "model": model or "default"
        }

        try:
            http_client = AITBCHTTPClient(base_url="http://localhost:8107", timeout=30)
            result = http_client.post("/v1/jobs", json=job_config)
            success("AI job submitted successfully")
            click.echo(f"Job ID: {result.get('job_id', 'unknown')}")
            click.echo(f"Type: {job_type}")
            click.echo(f"Payment: {payment} AIT")
            return result
        except NetworkError as e:
            error(f"Error submitting AI job: {e}")
            return None
        except Exception as e:
            error(f"Error: {e}")
            return None
    except Exception as e:
        error(f"Error: {e}")


@ai.command()
@click.option('--job-id', help='Specific job ID')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
def status(job_id: str | None, format: str):
    """Get AI job status"""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:9001", timeout=30)
        if job_id:
            result = http_client.get(f"/v1/jobs/{job_id}")
            success(f"Job status for {job_id}")
        else:
            result = http_client.get("/v1/jobs")
            success("All jobs status")

        if format == 'json':
            click.echo(json.dumps(result, indent=2))
        else:
            if job_id:
                click.echo(f"Status: {result.get('state', 'unknown')}")
                click.echo(f"Progress: {result.get('progress', '0%')}")
            else:
                for job in result.get('jobs', []):
                    click.echo(f"  - {job.get('job_id', 'unknown')}: {job.get('state', 'unknown')}")
    except NetworkError as e:
        error(f"Error getting AI job status: {e}")
    except Exception as e:
        error(f"Error: {e}")


@ai.command()
@click.option('--job-id', help='Specific job ID')
def cancel(job_id: str | None):
    """Cancel an AI job"""
    if not job_id:
        error("Job ID is required")
        return

    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:9001", timeout=30)
        result = http_client.post(f"/v1/jobs/{job_id}/cancel")
        success(f"AI job {job_id} cancelled")
    except NetworkError as e:
        error(f"Error cancelling AI job: {e}")
    except Exception as e:
        error(f"Error: {e}")


# Agent operations
@operations.group()
def agent():
    """Agent operations"""
    pass


@agent.command()
@click.option('--agent-id', required=True, help='Agent ID')
@click.option('--status', type=click.Choice(['active', 'inactive', 'busy', 'offline']), default='active', help='Agent status')
def register(agent_id: str, status: str):
    """Register an agent"""
    try:
        agent_config = {
            "agent_id": agent_id,
            "status": status
        }

        http_client = AITBCHTTPClient(base_url="http://localhost:9001", timeout=30)
        result = http_client.post("/v1/agents/register", json=agent_config)
        success(f"Agent {agent_id} registered with status {status}")
    except NetworkError as e:
        error(f"Error registering agent: {e}")
    except Exception as e:
        error(f"Error: {e}")


@agent.command()
@click.option('--status', help='Filter by status')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
def list(status: str | None, format: str):
    """List registered agents"""
    try:
        import requests
        coordinator_url = "http://localhost:8107"

        query = {}
        if status:
            query["status"] = status

        response = requests.post(f"{coordinator_url}/v1/agents/discover", json=query, timeout=10)

        if response.status_code == 200:
            data = response.json()
            agents = data.get("agents", [])
            success(f"Agents: {len(agents)}")
            if format == 'json':
                click.echo(json.dumps(agents, indent=2))
            else:
                for agent in agents:
                    click.echo(f"  - {agent.get('agent_id', 'unknown')}: {agent.get('status', 'unknown')} - {agent.get('agent_type', 'unknown')}")
        else:
            error(f"Error listing agents: {response.status_code}")
    except Exception as e:
        error(f"Error: {e}")


@agent.command()
@click.argument('agent_id')
def deregister(agent_id: str):
    """Deregister an agent"""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:9001", timeout=30)
        result = http_client.post(f"/v1/agents/{agent_id}/deregister")
        success(f"Agent {agent_id} deregistered")
    except NetworkError as e:
        error(f"Error deregistering agent: {e}")
    except Exception as e:
        error(f"Error: {e}")


@agent.command()
@click.option('--agent', required=True, help='Recipient agent address')
@click.option('--message', required=True, help='Message content')
@click.option('--wallet', required=True, help='Wallet name for signing')
@click.option('--password', help='Wallet password')
@click.option('--password-file', help='File containing wallet password')
@click.option('--rpc-url', help='Blockchain RPC URL')
def message(agent: str, message: str, wallet: str, password: str | None, password_file: str | None, rpc_url: str | None):
    """Send message to agent via blockchain transaction"""
    if not rpc_url:
        rpc_url = DEFAULT_RPC_URL

    # Get password
    if password_file:
        with open(password_file) as f:
            password = f.read().strip()
    elif not password:
        import getpass
        password = getpass.getpass("Enter wallet password: ")

    try:
        # Decrypt wallet
        keystore_path = DEFAULT_KEYSTORE_DIR / f"{wallet}.json"
        private_key_hex = decrypt_private_key(keystore_path, password)
        private_key_bytes = bytes.fromhex(private_key_hex)

        # Get sender address
        with open(keystore_path) as f:
            keystore_data = json.load(f)
        sender_address = keystore_data['address']

        # Create transaction with message as payload
        priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        pub_hex = priv_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        ).hex()

        # Get chain_id
        from ..utils.chain_id import get_chain_id
        chain_id = get_chain_id(rpc_url)

        # Get actual nonce
        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
            account_data = http_client.get(f"/rpc/account/{sender_address}")
            actual_nonce = account_data.get("nonce", 0)
        except Exception:
            actual_nonce = 0

        tx = {
            "type": "TRANSFER",
            "chain_id": chain_id,
            "from": sender_address,
            "nonce": actual_nonce,
            "fee": 10,
            "payload": {
                "recipient": agent,
                "amount": 0,
                "message": message
            }
        }

        # Sign transaction
        tx_string = json.dumps(tx, sort_keys=True)
        tx["signature"] = priv_key.sign(tx_string.encode()).hex()
        tx["public_key"] = pub_hex

        # Submit transaction
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=tx)
        success("Message sent successfully")
        click.echo(f"From: {sender_address}")
        click.echo(f"To: {agent}")
        click.echo(f"Content: {message}")
        click.echo(f"TX Hash: {result.get('transaction_hash', 'unknown')}")
    except Exception as e:
        error(f"Error sending message: {e}")


# Governance operations
@operations.group()
def governance():
    """Governance operations"""
    pass


@governance.command()
@click.argument('proposal_id')
@click.option('--vote', type=click.Choice(['for', 'against', 'abstain']), required=True, help='Vote option')
@click.option('--wallet', required=True, help='Wallet name for signing')
@click.option('--voting-power', type=int, default=0, help='Voting power to use')
@click.option('--reason', help='Vote reason')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def vote(ctx, proposal_id: str, vote: str, wallet: str, voting_power: int, reason: str | None, format: str):
    """Vote on a governance proposal on blockchain"""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id
            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Get wallet address from correct wallet directory
        wallet_path = DEFAULT_WALLET_DIR / f"{wallet}.json"
        if not wallet_path.exists():
            error(f"Wallet '{wallet}' not found at {wallet_path}")
            return

        wallet_data = _load_wallet(wallet_path, wallet)
        voter_address = wallet_data['address']

        # Convert bech32 address to hex for RPC compatibility
        from ..utils.crypto_utils import bech32_to_hex
        hex_address = bech32_to_hex(voter_address)

        # Submit vote to blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        vote_data = {
            "proposal_id": proposal_id,
            "voter_address": hex_address,
            "vote_type": vote,
            "voting_power": voting_power,
            "reason": reason,
            "chain_id": chain_id
        }
        result = http_client.post("/rpc/governance/vote", json=vote_data)

        success(f"Vote '{vote}' cast for proposal {proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error casting vote: {e}")


@governance.command()
@click.option('--proposal-id', required=True, help='Proposal ID')
@click.option('--title', required=True, help='Proposal title')
@click.option('--description', required=True, help='Proposal description')
@click.option('--category', default='general', help='Proposal category')
@click.option('--wallet', required=True, help='Wallet name for signing')
@click.option('--voting-days', type=int, default=7, help='Voting period in days')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def proposal(ctx, proposal_id: str, title: str, description: str, category: str, wallet: str, voting_days: int, format: str):
    """Create a governance proposal on blockchain"""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id
            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Get wallet address from correct wallet directory
        wallet_path = DEFAULT_WALLET_DIR / f"{wallet}.json"
        if not wallet_path.exists():
            error(f"Wallet '{wallet}' not found at {wallet_path}")
            return

        wallet_data = _load_wallet(wallet_path, wallet)
        proposer_address = wallet_data['address']

        # Convert bech32 address to hex for RPC compatibility
        from ..utils.crypto_utils import bech32_to_hex
        hex_address = bech32_to_hex(proposer_address)

        # Calculate voting times
        from datetime import datetime, timedelta, UTC
        voting_starts = datetime.now(UTC).isoformat()
        voting_ends = (datetime.now(UTC) + timedelta(days=voting_days)).isoformat()

        # Submit proposal to blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        proposal_data = {
            "proposal_id": proposal_id,
            "proposer_address": hex_address,
            "title": title,
            "description": description,
            "category": category,
            "voting_starts": voting_starts,
            "voting_ends": voting_ends,
            "chain_id": chain_id
        }
        result = http_client.post("/rpc/governance/proposal", json=proposal_data)

        success(f"Proposal created: {proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error creating proposal: {e}")


@governance.command()
@click.argument('proposal_id')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def get_proposal(ctx, proposal_id: str, format: str):
    """Get a governance proposal from blockchain"""
    config = get_config()

    try:
        # Get RPC URL from config (use hub for cross-node operations)
        rpc_url = getattr(config, 'blockchain_rpc_url', 'http://localhost:8006')
        rpc_url = rpc_url.replace('localhost', config.hub_discovery_url or 'hub.aitbc.bubuit.net')

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id
            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os
            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Query proposal from blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get(f"/rpc/governance/proposal/{proposal_id}")

        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting proposal: {e}")


# v0.4.12 New CLI Commands
@governance.command()
@click.option('--address', required=True, help='Staker address')
@click.option('--amount', type=int, required=True, help='Amount of tokens to stake')
@click.option('--lock-days', type=int, default=30, help='Lock period in days (min 30)')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def stake(ctx, address: str, amount: int, lock_days: int, format: str):
    """Stake tokens for enhanced voting power"""
    config = get_config()

    try:
        if lock_days < 30:
            error("Lock period must be at least 30 days")
            return

        # Get governance service URL
        governance_url = getattr(config, 'governance_service_url', 'http://localhost:8105')

        # Submit staking request
        http_client = AITBCHTTPClient(base_url=governance_url, timeout=30)
        stake_data = {
            "staker_address": address,
            "amount": amount,
            "lock_period_days": lock_days
        }
        result = http_client.post("/v1/governance/stake", json=stake_data)

        success(f"Staked {amount} tokens for {lock_days} days")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error staking tokens: {e}")


@governance.command()
@click.option('--delegator', required=True, help='Delegator address')
@click.option('--delegate', required=True, help='Delegate address')
@click.option('--amount', type=int, required=True, help='Amount of voting power to delegate')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def delegate(ctx, delegator: str, delegate: str, amount: int, format: str):
    """Delegate voting power to another address"""
    config = get_config()

    try:
        # Get governance service URL
        governance_url = getattr(config, 'governance_service_url', 'http://localhost:8105')

        # Submit delegation request
        http_client = AITBCHTTPClient(base_url=governance_url, timeout=30)
        delegation_data = {
            "delegator_address": delegator,
            "delegate_address": delegate,
            "amount": amount
        }
        result = http_client.post("/v1/governance/delegate", json=delegation_data)

        success(f"Delegated {amount} voting power from {delegator} to {delegate}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error delegating voting power: {e}")


@governance.command()
@click.argument('proposal_id')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def execute(ctx, proposal_id: str, format: str):
    """Execute a passed proposal"""
    config = get_config()

    try:
        # Get governance service URL
        governance_url = getattr(config, 'governance_service_url', 'http://localhost:8105')

        # Submit execution request
        http_client = AITBCHTTPClient(base_url=governance_url, timeout=30)
        result = http_client.post(f"/v1/governance/proposals/{proposal_id}/execute")

        success(f"Executed proposal {proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error executing proposal: {e}")


@governance.command()
@click.argument('address')
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.pass_context
def voting_power(ctx, address: str, format: str):
    """Get voting power for an address"""
    config = get_config()

    try:
        # Get governance service URL
        governance_url = getattr(config, 'governance_service_url', 'http://localhost:8105')

        # Query voting power
        http_client = AITBCHTTPClient(base_url=governance_url, timeout=30)
        result = http_client.get(f"/v1/governance/voting-power/{address}")

        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting voting power: {e}")


