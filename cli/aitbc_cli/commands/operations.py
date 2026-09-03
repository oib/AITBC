"""
Legacy on-chain operations commands for AITBC CLI.

Prefer the top-level groups: `aitbc ai`, `aitbc agent`, `aitbc governance`,
and `aitbc market` for the coordinator-backed or service-backed paths.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS
from aitbc.utils.validation import validate_address

from ..config import get_config
from ..utils import DECIMAL, error, output, success
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.wallet import decrypt_private_key
from ..utils.wallet_paths import find_wallet_file

logger = get_logger(__name__)

DEFAULT_RPC_URL = "http://localhost:8202"


def _load_wallet(wallet_path: Path, wallet_name: str) -> dict[str, Any]:
    """Load wallet and decrypt private key if needed"""
    with open(wallet_path) as f:
        wallet_data: dict[str, Any] = json.load(f)

    # Decrypt private key if encrypted
    if wallet_data.get("encrypted") and "private_key" in wallet_data:
        from ..utils import decode_value

        password = _get_wallet_password(wallet_name)
        try:
            wallet_data["private_key"] = decode_value(wallet_data["private_key"], password)
        except Exception:
            abort(None, "Invalid password for wallet")
    return wallet_data


def _get_wallet_password(wallet_name: str) -> str:
    """Get wallet password from user input"""
    import getpass

    return getpass.getpass(f"Enter password for wallet '{wallet_name}': ")


@click.group(
    hidden=True,
    deprecated=True,
    epilog="""Examples:

  aitbc operations marketplace list-listings

  aitbc operations governance vote --proposal-id prop-123 --vote for""",
)
def operations():
    """Deprecated legacy on-chain operations commands for marketplace, AI, agent, and governance."""
    pass


# AI operations
@operations.group(
    epilog="""Examples:

  aitbc operations ai status

  aitbc operations ai submit-job --wallet-name wallet-1 --job-type infer --prompt 'hello' --payment 10"""
)
def ai():
    """Deprecated AI operations subgroup for submitting and monitoring jobs."""
    pass


@ai.command(
    epilog="""Examples:

  aitbc operations ai submit-job --wallet-name wallet-1 --job-type infer --prompt 'hello' --payment 10

  aitbc operations ai submit-job --wallet-name wallet-1 --job-type infer --prompt 'hello' --payment 10 --model llama3"""
)
@click.option("--wallet-name", required=True, help="Client wallet name")
@click.option("--job-type", required=True, help="Type of AI job")
@click.option("--prompt", required=True, help="AI prompt")
@click.option("--payment", type=DECIMAL, required=True, help="Payment amount")
@click.option("--model", help="AI model to use")
def submit_job(wallet_name: str, job_type: str, prompt: str, payment: Decimal, model: str | None):
    """Submit an AI job with wallet, type, prompt, and payment."""
    try:
        # Get wallet address
        wallet_path = find_wallet_file(wallet_name)
        if wallet_path is None:
            error(f"Wallet '{wallet_name}' not found")
            return None

        with open(wallet_path) as f:
            wallet_data = json.load(f)
        address = wallet_data["address"]

        # Submit job via coordinator API
        job_config = {
            "client_address": address,
            "job_type": job_type,
            "prompt": prompt,
            "payment": str(payment),
            "model": model or "default",
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


@ai.command(
    epilog="""Examples:

  aitbc operations ai status

  aitbc operations ai status --job-id job-123"""
)
@click.option("--job-id", help="Specific job ID")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
def status(job_id: str | None, format: str):
    """Get the status of one or all AI jobs."""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8107", timeout=30)
        if job_id:
            result = http_client.get(f"/v1/jobs/{job_id}")
            success(f"Job status for {job_id}")
        else:
            result = http_client.get("/v1/jobs")
            success("All jobs status")

        if format == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            if job_id:
                click.echo(f"Status: {result.get('state', 'unknown')}")
                click.echo(f"Progress: {result.get('progress', '0%')}")
            else:
                for job in result.get("jobs", []):
                    click.echo(f"  - {job.get('job_id', 'unknown')}: {job.get('state', 'unknown')}")
    except NetworkError as e:
        error(f"Error getting AI job status: {e}")
    except Exception as e:
        error(f"Error: {e}")


@ai.command(
    epilog="""Examples:

  aitbc operations ai cancel --job-id job-123"""
)
@click.option("--job-id", help="Specific job ID")
def cancel(job_id: str | None):
    """Cancel an AI job by its ID."""
    if not job_id:
        error("Job ID is required")
        return

    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8107", timeout=30)
        _ = http_client.post(f"/v1/jobs/{job_id}/cancel")
        success(f"AI job {job_id} cancelled")
    except NetworkError as e:
        error(f"Error cancelling AI job: {e}")
    except Exception as e:
        error(f"Error: {e}")


# Agent operations
@operations.group(
    epilog="""Examples:

  aitbc operations agent list

  aitbc operations agent deregister --agent-id agent-1"""
)
def agent():
    """Deprecated agent operations subgroup for registering and messaging agents."""
    pass


@agent.command(
    epilog="""Examples:

  aitbc operations agent register --agent-id agent-1

  aitbc operations agent register --agent-id agent-1 --status active"""
)
@click.option("--agent-id", required=True, help="Agent ID")
@click.option("--status", type=click.Choice(["active", "inactive", "busy", "offline"]), default="active", help="Agent status")
def register(agent_id: str, status: str):
    """Register an agent with a status."""
    try:
        agent_config = {"agent_id": agent_id, "status": status}

        http_client = AITBCHTTPClient(base_url="http://localhost:8107", timeout=30)
        _ = http_client.post("/v1/agents/register", json=agent_config)
        success(f"Agent {agent_id} registered with status {status}")
    except NetworkError as e:
        error(f"Error registering agent: {e}")
    except Exception as e:
        error(f"Error: {e}")


@agent.command(
    epilog="""Examples:

  aitbc operations agent list

  aitbc operations agent list --status active"""
)
@click.option("--status", help="Filter by status")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
def list(status: str | None, format: str):
    """List registered agents, optionally filtered by status."""
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
            if format == "json":
                click.echo(json.dumps(agents, indent=2))
            else:
                for agent in agents:
                    click.echo(
                        f"  - {agent.get('agent_id', 'unknown')}: {agent.get('status', 'unknown')} - {agent.get('agent_type', 'unknown')}"
                    )
        else:
            error(f"Error listing agents: {response.status_code}")
    except Exception as e:
        error(f"Error: {e}")


@agent.command(
    epilog="""Examples:

  aitbc operations agent deregister --agent-id agent-1"""
)
@click.option("--agent-id", "agent_id", required=True, help="The Agent id.")
def deregister(agent_id: str):
    """Deregister an agent by its ID."""
    try:
        http_client = AITBCHTTPClient(base_url="http://localhost:8107", timeout=30)
        _ = http_client.post(f"/v1/agents/{agent_id}/deregister")
        success(f"Agent {agent_id} deregistered")
    except NetworkError as e:
        error(f"Error deregistering agent: {e}")
    except Exception as e:
        error(f"Error: {e}")


@agent.command(
    epilog="""Examples:

  aitbc operations agent message --agent 0x... --message 'hello' --wallet wallet-1

  aitbc operations agent message --agent 0x... --message 'hello' --wallet wallet-1 --password-file /tmp/pass"""
)
@click.option("--agent", required=True, help="Recipient agent address")
@click.option("--message", required=True, help="Message content")
@click.option("--wallet", required=True, help="Wallet name for signing")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL")
def message(agent: str, message: str, wallet: str, password: str | None, password_file: str | None, rpc_url: str | None):
    """Send a message to an agent via a blockchain transaction."""
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
        keystore_path = wallet_dir() / f"{wallet}.json"
        private_key_hex = decrypt_private_key(keystore_path, password)
        private_key_bytes = bytes.fromhex(private_key_hex)

        # Get sender address
        with open(keystore_path) as f:
            keystore_data = json.load(f)
        sender_address = keystore_data["address"]

        # Create transaction with message as payload
        priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        pub_hex = (
            priv_key.public_key()
            .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
            .hex()
        )

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
            "fee": DEFAULT_TX_FEE_UNITS,
            "payload": {"recipient": agent, "amount": 0, "message": message},
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
@operations.group(
    deprecated=True,
    epilog="""Examples:

  aitbc operations governance proposal --proposal-id prop-1 --title 'Change fee' --description 'Lower fee' --wallet wallet-1

  aitbc operations governance vote --proposal-id prop-1 --vote for""",
)
def governance():
    """Deprecated on-chain governance operations subgroup."""
    pass


@governance.command(
    epilog="""Examples:

  aitbc operations governance vote --proposal-id prop-1 --vote for --wallet wallet-1

  aitbc operations governance vote --proposal-id prop-1 --vote for --wallet wallet-1 --voting-power 100"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--vote", type=click.Choice(["for", "against", "abstain"]), required=True, help="Vote option")
@click.option("--wallet", required=True, help="Wallet name for signing")
@click.option("--voting-power", type=int, default=0, help="Voting power to use")
@click.option("--reason", help="Vote reason")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def vote(ctx, proposal_id: str, vote: str, wallet: str, voting_power: int, reason: str | None, format: str):
    """Cast a vote on a governance proposal using a wallet."""
    config = get_config()

    try:
        # Get RPC URL from config (default local blockchain RPC)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id

            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os

            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Get wallet address from correct wallet directory
        wallet_path = find_wallet_file(wallet)
        if wallet_path is None:
            error(f"Wallet '{wallet}' not found")
            return

        wallet_data = _load_wallet(wallet_path, wallet)
        voter_address = wallet_data["address"]

        hex_address = canonical_address(voter_address)
        if not validate_address(hex_address):
            error(f"Invalid voter address: {voter_address}")
            return

        # Submit vote to blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        vote_data = {
            "proposal_id": proposal_id,
            "voter_address": hex_address,
            "vote_type": vote,
            "voting_power": voting_power,
            "reason": reason,
            "chain_id": chain_id,
        }
        result = http_client.post("/rpc/governance/vote", json=vote_data)

        success(f"Vote '{vote}' cast for proposal {proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error casting vote: {e}")


@governance.command(
    epilog="""Examples:

  aitbc operations governance proposal --proposal-id prop-1 --title 'Change fee' --description 'Lower fee' --wallet wallet-1

  aitbc operations governance proposal --proposal-id prop-1 --title 'Change fee' --description 'Lower fee' --wallet wallet-1 --voting-days 14"""
)
@click.option("--proposal-id", required=True, help="Proposal ID")
@click.option("--title", required=True, help="Proposal title")
@click.option("--description", required=True, help="Proposal description")
@click.option("--category", default="general", help="Proposal category")
@click.option(
    "--params",
    default=None,
    help='JSON execution payload, e.g. {"action":"parameter_change","parameter":"block_time_seconds","value":"10"}',
)
@click.option("--wallet", required=True, help="Wallet name for signing")
@click.option("--voting-days", type=int, default=7, help="Voting period in days")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def proposal(
    ctx,
    proposal_id: str,
    title: str,
    description: str,
    category: str,
    params: str | None,
    wallet: str,
    voting_days: int,
    format: str,
):
    """Create a governance proposal on the blockchain."""
    config = get_config()

    try:
        # Get RPC URL from config (default local blockchain RPC)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id

            chain_id = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os

            chain_id = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Get wallet address from correct wallet directory
        wallet_path = find_wallet_file(wallet)
        if wallet_path is None:
            error(f"Wallet '{wallet}' not found")
            return

        wallet_data = _load_wallet(wallet_path, wallet)
        proposer_address = wallet_data["address"]

        hex_address = canonical_address(proposer_address)
        if not validate_address(hex_address):
            error(f"Invalid proposer address: {proposer_address}")
            return

        # Calculate voting times
        from datetime import UTC, datetime, timedelta

        voting_starts = datetime.now(UTC).isoformat()
        voting_ends = (datetime.now(UTC) + timedelta(days=voting_days)).isoformat()

        # Build execution payload from --params if provided
        execution_payload = {}
        if params:
            try:
                execution_payload = json.loads(params)
            except json.JSONDecodeError:
                error("Invalid JSON in --params")
                return

        # Submit proposal to blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        proposal_data = {
            "proposal_id": proposal_id,
            "proposer_address": hex_address,
            "title": title,
            "description": description,
            "category": category,
            "execution_payload": execution_payload,
            "voting_starts": voting_starts,
            "voting_ends": voting_ends,
            "chain_id": chain_id,
        }
        result = http_client.post("/rpc/governance/proposal", json=proposal_data)

        success(f"Proposal created: {proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error creating proposal: {e}")


@governance.command(
    epilog="""Examples:

  aitbc operations governance get-proposal --proposal-id prop-1

  aitbc operations governance get-proposal --proposal-id prop-1 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get_proposal(ctx, proposal_id: str, format: str):
    """Get a governance proposal from the blockchain."""
    config = get_config()

    try:
        # Get RPC URL from config (default local blockchain RPC)
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")

        # Get chain_id
        try:
            from ..utils.chain_id import get_chain_id

            _ = get_chain_id(rpc_url, override=None, timeout=5)
        except Exception:
            import os

            _ = os.getenv("CHAIN_ID", "ait-hub.aitbc.bubuit.net")

        # Query proposal from blockchain RPC
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.get(f"/rpc/governance/proposal/{proposal_id}")

        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting proposal: {e}")


# v0.4.12 New CLI Commands
@governance.command(
    epilog="""Examples:

  aitbc operations governance stake --address 0x... --amount 1000

  aitbc operations governance stake --address 0x... --amount 1000 --lock-days 60"""
)
@click.option("--address", required=True, help="Staker address")
@click.option("--amount", type=int, required=True, help="Amount of tokens to stake")
@click.option("--lock-days", type=int, default=30, help="Lock period in days (min 30)")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def stake(ctx, address: str, amount: int, lock_days: int, format: str):
    """Stake tokens for enhanced voting power."""
    config = get_config()

    try:
        if lock_days < 30:
            error("Lock period must be at least 30 days")
            return

        # Get governance service URL
        governance_url = getattr(config, "governance_service_url", "http://localhost:8105")

        # Submit staking request
        http_client = AITBCHTTPClient(base_url=governance_url, timeout=30)
        stake_data = {"staker_address": address, "amount": amount, "lock_period_days": lock_days}
        result = http_client.post("/v1/governance/stake", json=stake_data)

        success(f"Staked {amount} tokens for {lock_days} days")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error staking tokens: {e}")


@governance.command(
    epilog="""Examples:

  aitbc operations governance delegate --delegator 0x... --delegate 0x... --amount 1000"""
)
@click.option("--delegator", required=True, help="Delegator address")
@click.option("--delegate", required=True, help="Delegate address")
@click.option("--amount", type=int, required=True, help="Amount of voting power to delegate")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def delegate(ctx, delegator: str, delegate: str, amount: int, format: str):
    """Delegate voting power from one address to another."""
    config = get_config()

    try:
        # Get governance service URL
        governance_url = getattr(config, "governance_service_url", "http://localhost:8105")

        # Submit delegation request
        http_client = AITBCHTTPClient(base_url=governance_url, timeout=30)
        delegation_data = {"delegator_address": delegator, "delegate_address": delegate, "amount": amount}
        result = http_client.post("/v1/governance/delegate", json=delegation_data)

        success(f"Delegated {amount} voting power from {delegator} to {delegate}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error delegating voting power: {e}")


@governance.command(
    epilog="""Examples:

  aitbc operations governance execute --proposal-id prop-1

  aitbc operations governance execute --proposal-id prop-1 --output json"""
)
@click.option("--proposal-id", "proposal_id", required=True, help="The Proposal id.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def execute(ctx, proposal_id: str, format: str):
    """Execute a passed governance proposal on the blockchain."""
    config = get_config()

    try:
        # Use the local blockchain RPC for on-chain governance execution
        rpc_url = getattr(config, "blockchain_rpc_url", "http://localhost:8202")

        # Submit execution request
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post(f"/rpc/governance/proposal/{proposal_id}/execute")

        success(f"Executed proposal {proposal_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error executing proposal: {e}")


@governance.command(
    epilog="""Examples:

  aitbc operations governance voting-power --address 0x...

  aitbc operations governance voting-power --address 0x... --output json"""
)
@click.option("--address", "address", required=True, help="Blockchain address to fund.")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def voting_power(ctx, address: str, format: str):
    """Get voting power for a blockchain address."""
    config = get_config()

    try:
        # Get governance service URL
        governance_url = getattr(config, "governance_service_url", "http://localhost:8105")

        # Query voting power
        http_client = AITBCHTTPClient(base_url=governance_url, timeout=30)
        result = http_client.get(f"/v1/governance/voting-power/{address}")

        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting voting power: {e}")
