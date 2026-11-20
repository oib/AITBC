"""Contract commands for AITBC CLI"""

import click
import httpx

from aitbc.exceptions import AITBCError
from ..utils import output
from ..utils.error_handling import CLIError, abort
from ..utils.http_client import AITBCHTTPClient, NetworkError

# Expected failure surface for the command handlers below: filesystem/JSON,
# data-shape, runtime, optional-dependency imports, HTTP-client errors and
# both error hierarchies (CLIError, aitbc_errors.AITBCError). RuntimeError
# covers generic runtime failures; abort() raises CLIError (already listed),
# preserving the previous re-abort behaviour. BaseExceptions still propagate
# (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    CLIError,
    AITBCError,
    httpx.HTTPError,
)


@click.group(
    epilog="""Examples:

  aitbc contract deploy --contract-name MyContract

  aitbc contract call --contract-address 0x... --method getBalance"""
)
def contract():
    """Deploy smart contracts and call methods on deployed contract addresses."""
    pass


def _resolve_rpc_api_key(api_key: str | None) -> str:
    """Resolve the blockchain RPC API key for gated contract routes (#2350).

    Order: explicit ``--api-key`` → CLI config / ``BLOCKCHAIN_RPC_API_KEY``
    env. The fleet's ``verify_rpc_api_key`` dependency 403s POSTs without
    it; fail with a clear message rather than a bare 403. Mirrors
    ``trade._resolve_rpc_api_key``.
    """
    from ..config import get_config

    key = api_key or get_config().blockchain_rpc_api_key
    if not key:
        raise click.UsageError(
            "Blockchain RPC API key required: pass --api-key or set BLOCKCHAIN_RPC_API_KEY (or config blockchain_rpc_api_key)"
        )
    return key


def _rpc_client(rpc_url: str, api_key: str) -> AITBCHTTPClient:
    return AITBCHTTPClient(base_url=rpc_url, timeout=10, api_key=api_key)


_API_KEY_OPTION = click.option(
    "--api-key",
    "api_key",
    default=None,
    help="Blockchain RPC API key (default: BLOCKCHAIN_RPC_API_KEY env / config blockchain_rpc_api_key)",
)


@contract.command(
    epilog="""Examples:

  aitbc contract deploy --contract-name MyContract

  aitbc contract deploy --contract-name MyContract --rpc-url http://node2.example.net:8202"""
)
@click.option("--contract-name", required=True, help="Contract name")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@_API_KEY_OPTION
@click.pass_context
def deploy(ctx, contract_name, rpc_url, api_key):
    """Deploy a named smart contract to the blockchain."""
    try:
        key = _resolve_rpc_api_key(api_key)
        result = _rpc_client(rpc_url, key).post("/rpc/contracts/deploy", json={"name": contract_name})
        output(result, ctx.obj.get("output_format", "table"), title="Contract Deployed")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
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
@_API_KEY_OPTION
@click.pass_context
def call(ctx, contract_address, method, args, rpc_url, api_key):
    """Call a method on a deployed smart contract with optional arguments."""
    try:
        import json

        key = _resolve_rpc_api_key(api_key)
        http_client = _rpc_client(rpc_url, key)
        # The RPC handler reads ``address``/``method``/``params`` — sending
        # ``contract_address``/``args`` made every call fail "address is required".
        payload: dict = {"address": contract_address, "method": method}
        if args:
            payload["params"] = json.loads(args)
        result = http_client.post("/rpc/contracts/call", json=payload)
        output(result, ctx.obj.get("output_format", "table"), title="Contract Call")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
        abort(ctx, f"Error calling contract: {e}", from_exception=e)


def _get(ctx, path: str, rpc_url: str, title: str, params: dict | None = None):
    """GET ``path`` against the blockchain RPC and render the result."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.get(path, params={k: v for k, v in (params or {}).items() if v is not None})
        output(result, ctx.obj.get("output_format", "table"), title=title)
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
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
@_API_KEY_OPTION
@click.pass_context
def verify(ctx, contract_address, proof, chain_id, rpc_url, api_key):
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
        key = _resolve_rpc_api_key(api_key)
        result = _rpc_client(rpc_url, key).post("/rpc/contracts/verify", json=payload)
        output(result, ctx.obj.get("output_format", "table"), title="Contract Verify")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except _OPS_ERRORS as e:
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
