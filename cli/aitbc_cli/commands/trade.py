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
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)

TRADING_SERVICE_URL = "http://localhost:8104"


def _get_client(url: str | None = None) -> AITBCHTTPClient:
    """Create an HTTP client for the trading service."""
    import os

    base_url = url or os.getenv("TRADING_SERVICE_URL") or TRADING_SERVICE_URL
    return AITBCHTTPClient(base_url=base_url, timeout=30)


@click.group(
    epilog="""Examples:

  aitbc trade list

  aitbc trade create --source-chain ait-mainnet --dest-chain ait-side --sender 0x... --recipient 0x... --amount 100"""
)
def trade():
    """Create, list, and settle inter-chain trading operations."""
    pass


@trade.command(
    epilog="""Examples:

  aitbc trade create --source-chain ait-mainnet --dest-chain ait-side --sender 0x... --recipient 0x... --amount 100"""
)
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
    """Create a new inter-chain trade between source and destination chains."""
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


@trade.command(
    epilog="""Examples:

  aitbc trade list

  aitbc trade list --status active --limit 50"""
)
@click.option("--status", default=None, help="Filter by status (pending, matched, completed, etc.)")
@click.option("--source-chain", default=None, help="Filter by source chain")
@click.option("--dest-chain", default=None, help="Filter by destination chain")
@click.option("--limit", default=100, type=int, help="Max results")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list(ctx, status, source_chain, dest_chain, limit, format):
    """List inter-chain trades with optional filters."""
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


@trade.command(
    epilog="""Examples:

  aitbc trade chains

  aitbc trade chains --output json"""
)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def chains(ctx, format):
    """List chains that participate in inter-chain trading."""
    try:
        client = _get_client()
        result = client.get("/v1/trading/chains")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error listing chains: {e}")


@trade.command(
    epilog="""Examples:

  aitbc trade get --trade-id trade-123

  aitbc trade get --trade-id trade-123 --output json"""
)
@click.argument("trade_id")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def get(ctx, trade_id, format):
    """Get details of a specific trade."""
    try:
        client = _get_client()
        result = client.get(f"/v1/trading/inter-chain/{trade_id}")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting trade: {e}")


@trade.command(
    epilog="""Examples:

  aitbc trade status --trade-id trade-123

  aitbc trade status --trade-id trade-123 --output json"""
)
@click.option("--trade-id", required=True, help="Trade ID")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def status(ctx, trade_id, format):
    """Get the status of a specific trade."""
    try:
        client = _get_client()
        result = client.get(f"/v1/trading/inter-chain/{trade_id}/status")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting trade status: {e}")


@trade.command(
    epilog="""Examples:

  aitbc trade register-chain --chain-id ait-side --endpoint http://localhost:8202

  aitbc trade register-chain --chain-id ait-side --endpoint http://localhost:8202 --output json"""
)
@click.option("--chain-id", required=True, help="Chain ID to register")
@click.option("--endpoint", required=True, help="Blockchain node RPC URL for the chain")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def register_chain(ctx, chain_id, endpoint, format):
    """Register a new chain for inter-chain trading."""
    try:
        client = _get_client()
        params: dict[str, str] = {"chain_id": chain_id, "endpoint": endpoint}
        result = client.post("/v1/trading/chains/register", json=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error registering chain: {e}")


@trade.command(
    epilog="""Examples:

  aitbc trade health

  aitbc trade health --chain-id ait-mainnet"""
)
@click.option("--chain-id", required=True, help="Chain ID to check")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def health(ctx, chain_id, format):
    """Check the health of inter-chain trading for a chain."""
    try:
        client = _get_client()
        result = client.get(f"/v1/trading/chains/{chain_id}/health")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error checking chain health: {e}")


@trade.command(
    epilog="""Examples:

  aitbc trade history

  aitbc trade history --source-chain ait-mainnet --dest-chain ait-side"""
)
@click.option("--source-chain", default=None, help="Filter by source chain")
@click.option("--dest-chain", default=None, help="Filter by destination chain")
@click.option("--limit", default=50, type=int, help="Max results")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def history(ctx, source_chain, dest_chain, limit, format):
    """Show the history of inter-chain trades between source and destination chains."""
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


@trade.command(
    epilog="""Examples:

  aitbc trade match --trade-id trade-123

  aitbc trade match --trade-id trade-123 --output json"""
)
@click.argument("trade_id")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def match(ctx, trade_id, format):
    """Match a trade with a counterparty or settlement path."""
    try:
        client = _get_client()
        result = client.post(f"/v1/trading/inter-chain/{trade_id}/match")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error matching trade: {e}")


@trade.command(
    epilog="""Examples:

  aitbc trade match-all

  aitbc trade match-all --output json"""
)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def match_all(ctx, format):
    """Match all open inter-chain trades automatically."""
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


@trade.command(
    epilog="""Examples:

  aitbc trade discover

  aitbc trade discover --source-chain ait-mainnet --dest-chain ait-side --service-type gpu"""
)
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
    """Discover trading offers across chains with optional filters."""
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


@trade.command(
    epilog="""Examples:

  aitbc trade sync

  aitbc trade sync --chain-id ait-mainnet --service-type gpu"""
)
@click.option("--chain-id", default=None, help="Sync specific chain (default: all chains)")
@click.option("--service-type", default=None, help="Sync specific service type")
@click.option("--force", is_flag=True, default=False, help="Force sync even if offers are fresh")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def sync(ctx, chain_id, service_type, force, format):
    """Sync trading data for a chain and service type."""
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


@trade.command(
    name="sync-status",
    epilog="""Examples:

  aitbc trade sync-status

  aitbc trade sync-status --output json""",
)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def sync_status(ctx, format):
    """Get the inter-chain trading sync status."""
    try:
        client = _get_client()
        result = client.get("/v1/trading/offers/sync-status")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting sync status: {e}")


# ============================================================================
# v0.8.2: Offer Subscription Commands (B6)
# ============================================================================


@trade.command(
    epilog="""Examples:

  aitbc trade watch

  aitbc trade watch --chain-id ait-mainnet --service-type gpu"""
)
@click.option("--chain-id", default=None, help="Filter by chain ID")
@click.option("--service-type", default=None, help="Filter by service type")
@click.option("--min-price", default=None, type=float, help="Minimum price filter")
@click.option("--max-price", default=None, type=float, help="Maximum price filter")
@click.option("--region", default=None, help="Filter by region")
@click.option("--gpu-model", default=None, help="Filter by GPU model")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def watch(ctx, chain_id, service_type, min_price, max_price, region, gpu_model, format):
    """Watch for new trading offers matching filters."""
    import asyncio
    import json as _json

    from aitbc.trading.subscription_client import OfferSubscriptionClient
    from aitbc.trading.subscription_types import OfferSubscription

    rpc_url = _get_client().base_url

    async def _watch() -> None:
        sub = OfferSubscription(
            chain_id=chain_id,
            service_type=service_type,
            min_price=min_price,
            max_price=max_price,
            region=region,
            gpu_model=gpu_model,
        )
        target_chain = chain_id or "ait-hub"
        client = OfferSubscriptionClient(rpc_url=rpc_url, node_id=f"cli-watch-{target_chain}")
        try:
            async for event in client.subscribe(target_chain, sub):
                click.echo(_json.dumps(event.to_dict(), indent=2))
        except KeyboardInterrupt:
            logger.debug("Offer watch interrupted by user", exc_info=True)
            pass
        finally:
            await client.close()

    try:
        asyncio.run(_watch())
    except KeyboardInterrupt:
        click.echo("Stopped watching")
    except Exception as e:
        error(f"Error watching offers: {e}")


@trade.command(
    name="subscription-status",
    epilog="""Examples:

  aitbc trade subscription-status

  aitbc trade subscription-status --output json""",
)
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def subscription_status(ctx, format):
    """Show the subscription status for trading updates."""
    try:
        client = _get_client()
        result = client.get("/v1/trading/offers/subscription-status")
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting subscription status: {e}")


@trade.command(
    epilog="""Examples:

  aitbc trade search --query gpu

  aitbc trade search --query gpu --chain-id ait-mainnet"""
)
@click.option("--query", default="", help="Search query text")
@click.option("--chain-id", default=None, help="Filter by chain ID")
@click.option("--service-type", default=None, help="Filter by service type")
@click.option("--min-price", default=None, type=float, help="Minimum price filter")
@click.option("--max-price", default=None, type=float, help="Maximum price filter")
@click.option("--limit", default=100, type=int, help="Max results")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def search(ctx, query, chain_id, service_type, min_price, max_price, limit, format):
    """Search trading offers with a query."""
    try:
        client = _get_client()
        params: dict[str, str | int | float] = {"q": query, "limit": limit}
        if chain_id:
            params["chain_id"] = chain_id
        if service_type:
            params["service_type"] = service_type
        if min_price is not None:
            params["min_price"] = min_price
        if max_price is not None:
            params["max_price"] = max_price
        result = client.get("/v1/trading/offers/search", params=params)
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error searching offers: {e}")


# ============================================================================
# v0.9.0 §B9: Settlement Commands
# ============================================================================


def _run_settlement_coro(coro):
    """Run an async settlement coroutine in a sync CLI context."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():  # pragma: no cover — nested loop (not expected in CLI)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(lambda: asyncio.run(coro)).result()
    except RuntimeError:
        logger.debug("No running event loop; falling through to asyncio.run", exc_info=True)
        pass  # no running loop — fall through to asyncio.run
    return asyncio.run(coro)


@trade.command(
    name="lock-escrow",
    epilog="""Examples:

  aitbc trade lock-escrow --trade-id trade-123""",
)
@click.option("--trade-id", required=True, help="Trade ID to lock escrow for")
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--timeout", type=int, default=None, help="Escrow timeout in seconds")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def lock_escrow_cmd(ctx, trade_id, node_url, timeout, format):
    """Lock escrow for a trade on the settlement node."""
    try:
        from aitbc.settlement.client import SettlementClient
        from aitbc.settlement.types import SettlementConfig

        config = SettlementConfig(settlement_rpc_url=node_url)

        async def _run():
            async with SettlementClient(config) as client:
                # Look up the trade via the trading service to get chain/sender/recipient/amount
                http_client = _get_client()
                trade = http_client.get(f"/v1/trading/inter-chain/{trade_id}")
                if not isinstance(trade, dict):
                    raise ValueError(f"Trade {trade_id} not found")
                return await client.create_escrow(
                    trade_id=trade_id,
                    source_chain=trade.get("source_chain", ""),
                    dest_chain=trade.get("dest_chain", ""),
                    sender=trade.get("sender", ""),
                    recipient=trade.get("recipient", ""),
                    amount=trade.get("amount", 0),
                    timeout_seconds=timeout,
                )

        result = _run_settlement_coro(_run())
        output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error locking escrow: {e}")


@trade.command(
    name="settle",
    epilog="""Examples:

  aitbc trade settle --trade-id trade-123 --secret '...'

  aitbc trade settle --trade-id trade-123 --secret '...' --node-url http://localhost:8202""",
)
@click.option("--trade-id", required=True, help="Trade ID to settle")
@click.option("--secret", required=True, help="HTLC secret to reveal")
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def settle_cmd(ctx, trade_id, secret, node_url, format):
    """Settle a trade with a secret."""
    try:
        from aitbc.settlement.client import SettlementClient
        from aitbc.settlement.types import SettlementConfig

        config = SettlementConfig(settlement_rpc_url=node_url)

        async def _run():
            # Look up the trade's escrow_id via the trading service
            http_client = _get_client()
            trade = http_client.get(f"/v1/trading/inter-chain/{trade_id}")
            if not isinstance(trade, dict):
                raise ValueError(f"Trade {trade_id} not found")
            escrow_id = trade.get("escrow_id")
            if not escrow_id:
                error(f"Trade {trade_id} has no escrow — lock escrow first")
                return None
            async with SettlementClient(config) as client:
                return await client.settle(escrow_id, secret)

        result = _run_settlement_coro(_run())
        if result is not None:
            output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error settling trade: {e}")


@trade.command(
    name="settlement-status",
    epilog="""Examples:

  aitbc trade settlement-status --trade-id trade-123

  aitbc trade settlement-status --trade-id trade-123 --node-url http://localhost:8202""",
)
@click.option("--trade-id", required=True, help="Trade ID to check")
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def settlement_status_cmd(ctx, trade_id, node_url, format):
    """Get the settlement status of a trade."""
    try:
        from aitbc.settlement.client import SettlementClient
        from aitbc.settlement.types import SettlementConfig

        config = SettlementConfig(settlement_rpc_url=node_url)

        async def _run():
            # Look up the trade's escrow_id via the trading service
            http_client = _get_client()
            trade = http_client.get(f"/v1/trading/inter-chain/{trade_id}")
            if not isinstance(trade, dict):
                raise ValueError(f"Trade {trade_id} not found")
            escrow_id = trade.get("escrow_id")
            if not escrow_id:
                return {
                    "trade_id": trade_id,
                    "settlement_phase": trade.get("settlement_phase", "none"),
                    "escrow_id": None,
                    "escrow_status": "none",
                }
            async with SettlementClient(config) as client:
                status = await client.get_escrow_status(escrow_id)
            return {
                "trade_id": trade_id,
                "settlement_phase": trade.get("settlement_phase", "none"),
                "escrow_id": escrow_id,
                "escrow_status": status,
            }

        result = _run_settlement_coro(_run())
        if result is not None:
            output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error getting settlement status: {e}")


@trade.command(
    name="refund",
    epilog="""Examples:

  aitbc trade refund --trade-id trade-123""",
)
@click.option("--trade-id", required=True, help="Trade ID to refund")
@click.option("--node-url", default="http://localhost:8202", help="Blockchain node RPC URL")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def refund_cmd(ctx, trade_id, node_url, format):
    """Refund a trade on the settlement node."""
    try:
        from aitbc.settlement.client import SettlementClient
        from aitbc.settlement.types import SettlementConfig

        config = SettlementConfig(settlement_rpc_url=node_url)

        async def _run():
            # Look up the trade's escrow_id via the trading service
            http_client = _get_client()
            trade = http_client.get(f"/v1/trading/inter-chain/{trade_id}")
            if not isinstance(trade, dict):
                raise ValueError(f"Trade {trade_id} not found")
            escrow_id = trade.get("escrow_id")
            if not escrow_id:
                raise ValueError(f"Trade {trade_id} has no escrow — lock escrow first")
            async with SettlementClient(config) as client:
                return await client.refund(escrow_id)

        result = _run_settlement_coro(_run())
        if result is not None:
            output(result, ctx.obj.get("output_format", format))
    except NetworkError as e:
        error(f"Network error: {e}")
    except Exception as e:
        error(f"Error refunding trade: {e}")


__all__ = ["trade"]
