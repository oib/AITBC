"""Contract commands for AITBC CLI"""

import click

from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group(
    epilog="""Examples:

  aitbc contract deploy --contract-name MyContract

  aitbc contract call --contract-address 0x... --method getBalance"""
)
def contract():
    """Deploy smart contracts and call methods on deployed contract addresses."""
    pass


@contract.command(
    epilog="""Examples:

  aitbc contract deploy --contract-name MyContract

  aitbc contract deploy --contract-name MyContract --rpc-url http://node2.example.net:8202"""
)
@click.option("--contract-name", required=True, help="Contract name")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def deploy(ctx, contract_name, rpc_url):
    """Deploy a named smart contract to the blockchain."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/contracts/deploy", json={"contract_name": contract_name})
        output(result, ctx.obj.get("output_format", "table"), title="Contract Deployed")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error deploying contract: {e}", from_exception=e)


@contract.command(
    epilog="""Examples:

  aitbc contract call --contract-address 0x... --method getBalance

  aitbc contract call --contract-address 0x... --method setValue --args '["hello"]'"""
)
@click.option("--contract-address", required=True, help="Contract address")
@click.option("--method", required=True, help="Method to call")
@click.option("--args", help="Method arguments (JSON array)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def call(ctx, contract_address, method, args, rpc_url):
    """Call a method on a deployed smart contract with optional arguments."""
    try:
        import json

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        payload = {"contract_address": contract_address, "method": method}
        if args:
            payload["args"] = json.loads(args)
        result = http_client.post("/rpc/contracts/call", json=payload)
        output(result, ctx.obj.get("output_format", "table"), title="Contract Call")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error calling contract: {e}", from_exception=e)


def _get(ctx, path: str, rpc_url: str, title: str, params: dict | None = None):
    """GET ``path`` against the blockchain RPC and render the result."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.get(path, params={k: v for k, v in (params or {}).items() if v is not None})
        output(result, ctx.obj.get("output_format", "table"), title=title)
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error calling {path}: {e}", from_exception=e)


@contract.command(
    name="list",
    epilog="""Examples:

  aitbc contract list

  aitbc contract list --rpc-url http://node2.example.net:8202""",
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def list_contracts(ctx, rpc_url):
    """List contracts deployed on the node."""
    _get(ctx, "/rpc/contracts", rpc_url, "Deployed Contracts")


@contract.command(
    epilog="""Examples:

  aitbc contract verify --contract-address 0x... --proof '{"pi_a": ...}'

  aitbc contract verify --contract-address 0x... --proof @proof.json"""
)
@click.option("--contract-address", required=True, help="Deployed contract address")
@click.option("--proof", required=True, help="ZK proof data (JSON string, or @path to a JSON file)")
@click.option("--chain-id", "chain_id", default=None, help="Chain ID the contract is deployed on")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def verify(ctx, contract_address, proof, chain_id, rpc_url):
    """Verify a ZK proof against a deployed contract."""
    import json
    from pathlib import Path

    raw = proof
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text()
    try:
        proof_data = json.loads(raw)
    except ValueError:
        proof_data = raw  # opaque proof strings are passed through verbatim
    payload = {"address": contract_address, "proof": proof_data}
    if chain_id:
        payload["chain_id"] = chain_id
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/contracts/verify", json=payload)
        output(result, ctx.obj.get("output_format", "table"), title="Contract Verify")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error verifying contract: {e}", from_exception=e)


@contract.command(
    name="messaging-state",
    epilog="""Example:

  aitbc contract messaging-state""",
)
@click.option("--chain-id", "chain_id", default=None, help="Chain ID to query")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def messaging_state(ctx, chain_id, rpc_url):
    """Show forum totals derived from sealed MESSAGE transactions."""
    params = f"?chain_id={chain_id}" if chain_id else ""
    _get(ctx, f"/rpc/contracts/messaging/state{params}", rpc_url, "Messaging Contract State")


@contract.command(
    name="messaging-topics",
    epilog="""Example:

  aitbc contract messaging-topics --limit 20 --sort-by last_activity""",
)
@click.option("--limit", default=50, type=int, help="Max topics to return")
@click.option("--offset", default=0, type=int, help="Offset for pagination")
@click.option("--sort-by", "sort_by", default="last_activity", help="Sort field (default: last_activity)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def messaging_topics(ctx, limit, offset, sort_by, rpc_url):
    """List forum topics from the chain-derived index."""
    _get(
        ctx,
        "/rpc/contracts/messaging/topics",
        rpc_url,
        "Forum Topics",
        params={"limit": limit, "offset": offset, "sort_by": sort_by},
    )


@contract.command(
    name="messaging-messages",
    epilog="""Example:

  aitbc contract messaging-messages --topic-id general --limit 20""",
)
@click.option("--topic-id", "topic_id", required=True, help="Topic slug")
@click.option("--limit", default=50, type=int, help="Max messages to return")
@click.option("--offset", default=0, type=int, help="Offset for pagination")
@click.option("--sort-by", "sort_by", default="timestamp", help="Sort field (default: timestamp)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def messaging_messages(ctx, topic_id, limit, offset, sort_by, rpc_url):
    """List messages in a forum topic."""
    _get(
        ctx,
        f"/rpc/contracts/messaging/topics/{topic_id}/messages",
        rpc_url,
        f"Messages in {topic_id}",
        params={"limit": limit, "offset": offset, "sort_by": sort_by},
    )


@contract.command(
    name="messaging-search",
    epilog="""Example:

  aitbc contract messaging-search --query 'agent staking' --limit 10""",
)
@click.option("--query", required=True, help="Search query over message bodies")
@click.option("--limit", default=50, type=int, help="Max matches to return")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def messaging_search(ctx, query, limit, rpc_url):
    """Search forum message bodies."""
    _get(ctx, "/rpc/contracts/messaging/messages/search", rpc_url, "Message Search", params={"query": query, "limit": limit})


@contract.command(
    name="messaging-reputation",
    epilog="""Example:

  aitbc contract messaging-reputation --address 0xAbc...""",
)
@click.option("--address", "address", required=True, help="Sender address to look up reputation for")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def messaging_reputation(ctx, address, rpc_url):
    """Show an address's messaging reputation (derived from sealed votes)."""
    _get(ctx, f"/rpc/contracts/messaging/agents/{address}/reputation", rpc_url, f"Reputation {address}")
