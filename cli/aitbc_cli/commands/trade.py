"""Trade CLI commands (v0.8.0 §B7).

Provides commands for inter-chain trading operations:
- ``trade create`` — create an inter-chain trade
- ``trade list`` — list inter-chain trades
- ``trade chains`` — list registered chains
- ``trade get`` — get trade details
- ``trade status`` — get trade status
- ``trade register-chain`` — register a new chain
- ``trade health`` — check chain health
- ``trade history`` — view cross-chain trade history
- ``trade match`` — attempt to match a trade
- ``trade match-all`` — match all pending trades

These commands talk to the trading service REST API (port 8104).
"""

import click

from ..utils import error, output
from ..utils.http_client import AITBCHTTPClient, NetworkError

TRADING_SERVICE_URL = "http://localhost:8104"


def _get_client(url: str | None = None) -> AITBCHTTPClient:
    """Create an HTTP client for the trading service."""
    import os

    base_url = url or os.getenv("TRADING_SERVICE_URL", TRADING_SERVICE_URL)
    return AITBCHTTPClient(base_url=base_url, timeout=30)


@click.group()
def trade():
    """Inter-chain trading operations"""
    pass


@trade.command()
@click.option("--source-chain", required=True, help="Source chain ID")
@click.option("--dest-chain", required=True, help="Destination chain ID")
@click.option("--sender", required=True, help="Sender address (source chain)")
@click.option("--recipient", required=True, help="Recipient address (dest chain)")
@click.option("--amount", required=True, type=int, help="Amount to trade")
@click.option("--offer-id", default=None, help="Associated offer ID")
@click.option("--price", default=0.0, type=float, help="Trade price")
@click.option("--quantity", default=0, type=int, help="Trade quantity")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def create(ctx, source_chain, dest_chain, sender, recipient, amount, offer_id, price, quantity, format):
    """Create an inter-chain trade"""
    try:
        client = _get_client()
        params: dict[str, str | int | float | None] = {
            "source_chain": source_chain,
            "dest_chain": dest_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "price": price,
            "quantity": quantity,
        }
        if offer_id:
            params["offer_id"] = offer_id
        result = client.post("/v1/trading/inter-chain/create", json=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error creating trade: {e}")


@trade.command()
@click.option("--status", default=None, help="Filter by status (pending, matched, completed, etc.)")
@click.option("--source-chain", default=None, help="Filter by source chain")
@click.option("--dest-chain", default=None, help="Filter by destination chain")
@click.option("--limit", default=100, type=int, help="Max results")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list(ctx, status, source_chain, dest_chain, limit, format):
    """List inter-chain trades"""
    try:
        client = _get_client()
        params: dict[str, str | int] = {"limit": limit}
        if status:
            params["status"] = status
        if source_chain:
            params["source_chain"] = source_chain
        if dest_chain:
            params["dest_chain"] = dest_chain
        result = client.get("/v1/trading/inter-chain", params=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error listing trades: {e}")


@trade.command()
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def chains(ctx, format):
    """List registered chains for inter-chain trading"""
    try:
        client = _get_client()
        result = client.get("/v1/trading/chains")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error listing chains: {e}")


@trade.command()
@click.argument("trade_id")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get(ctx, trade_id, format):
    """Get inter-chain trade details"""
    try:
        client = _get_client()
        result = client.get(f"/v1/trading/inter-chain/{trade_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting trade: {e}")


@trade.command()
@click.option("--trade-id", required=True, help="Trade ID")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, trade_id, format):
    """Get inter-chain trade status"""
    try:
        client = _get_client()
        result = client.get(f"/v1/trading/inter-chain/{trade_id}/status")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting trade status: {e}")


@trade.command()
@click.option("--chain-id", required=True, help="Chain ID to register")
@click.option("--endpoint", required=True, help="Blockchain node RPC URL for the chain")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def register_chain(ctx, chain_id, endpoint, format):
    """Register a new chain in the island registry"""
    try:
        client = _get_client()
        params: dict[str, str] = {"chain_id": chain_id, "endpoint": endpoint}
        result = client.post("/v1/trading/chains/register", json=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error registering chain: {e}")


@trade.command()
@click.option("--chain-id", required=True, help="Chain ID to check")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def health(ctx, chain_id, format):
    """Check chain health"""
    try:
        client = _get_client()
        result = client.get(f"/v1/trading/chains/{chain_id}/health")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error checking chain health: {e}")


@trade.command()
@click.option("--source-chain", default=None, help="Filter by source chain")
@click.option("--dest-chain", default=None, help="Filter by destination chain")
@click.option("--limit", default=50, type=int, help="Max results")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def history(ctx, source_chain, dest_chain, limit, format):
    """View cross-chain trade history"""
    try:
        client = _get_client()
        params: dict[str, str | int] = {"limit": limit}
        if source_chain:
            params["source_chain"] = source_chain
        if dest_chain:
            params["dest_chain"] = dest_chain
        result = client.get("/v1/trading/inter-chain/history", params=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting trade history: {e}")


@trade.command()
@click.argument("trade_id")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def match(ctx, trade_id, format):
    """Attempt to match an inter-chain trade"""
    try:
        client = _get_client()
        result = client.post(f"/v1/trading/inter-chain/{trade_id}/match")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error matching trade: {e}")


@trade.command()
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def match_all(ctx, format):
    """Match all pending inter-chain trades"""
    try:
        client = _get_client()
        result = client.post("/v1/trading/inter-chain/match-all")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error matching trades: {e}")


# ============================================================================
# v0.8.1: Offer Sync Commands (B5)
# ============================================================================


@trade.command()
@click.option("--source-chain", default=None, help="Filter by source chain")
@click.option("--dest-chain", default=None, help="Filter by destination chain")
@click.option("--service-type", default=None, help="Filter by service type (e.g. gpu_marketplace)")
@click.option("--min-price", default=None, type=float, help="Minimum price filter")
@click.option("--max-price", default=None, type=float, help="Maximum price filter")
@click.option("--region", default=None, help="Filter by region")
@click.option("--gpu-model", default=None, help="Filter by GPU model")
@click.option("--limit", default=100, type=int, help="Max results")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def discover(ctx, source_chain, dest_chain, service_type, min_price, max_price, region, gpu_model, limit, format):
    """Discover offers across chains with filters"""
    try:
        client = _get_client()
        params: dict[str, str | int | float] = {"limit": limit}
        if source_chain:
            params["source_chain"] = source_chain
        if dest_chain:
            params["dest_chain"] = dest_chain
        if service_type:
            params["service_type"] = service_type
        if min_price is not None:
            params["min_price"] = min_price
        if max_price is not None:
            params["max_price"] = max_price
        if region:
            params["region"] = region
        if gpu_model:
            params["gpu_model"] = gpu_model
        result = client.post("/v1/trading/offers/discover", json=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error discovering offers: {e}")


@trade.command()
@click.option("--chain-id", default=None, help="Sync specific chain (default: all chains)")
@click.option("--service-type", default=None, help="Sync specific service type")
@click.option("--force", is_flag=True, default=False, help="Force sync even if offers are fresh")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def sync(ctx, chain_id, service_type, force, format):
    """Trigger offer sync for a specific chain or all chains"""
    try:
        client = _get_client()
        params: dict[str, str | bool] = {"force": force}
        if chain_id:
            params["chain_id"] = chain_id
        if service_type:
            params["service_type"] = service_type
        result = client.post("/v1/trading/offers/sync", json=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error syncing offers: {e}")


@trade.command(name="sync-status")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def sync_status(ctx, format):
    """Show offer sync status per chain"""
    try:
        client = _get_client()
        result = client.get("/v1/trading/offers/sync-status")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting sync status: {e}")


__all__ = ["trade"]
