"""Blockchain Explorer commands for AITBC CLI"""

import json

import click

from ..config import get_config
from ..utils import error, success
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


@click.group()
def explorer():
    """Blockchain Explorer commands - access blockchain data via Explorer API"""
    pass


def get_explorer_client() -> AITBCHTTPClient:
    """Get Explorer API client"""
    config = get_config()
    return AITBCHTTPClient(base_url=config.explorer_api_url, timeout=30)


@explorer.command()
@click.option("--chain-id", help="Chain ID to query")
def chain_head(chain_id: str | None):
    """Get current chain head (latest block)"""
    try:
        client = get_explorer_client()
        params = {"chain_id": chain_id} if chain_id else {}
        result = client.get("/api/chain/head", params=params)

        if result:
            success("Chain Head")
            click.echo(json.dumps(result, indent=2))
        else:
            error("No chain head data available")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting chain head: {e}")


@explorer.command()
@click.option("--limit", default=10, help="Number of blocks to return")
@click.option("--offset", default=0, help="Offset for pagination")
@click.option("--chain-id", help="Chain ID to query")
def latest_blocks(limit: int, offset: int, chain_id: str | None):
    """Get latest blocks"""
    try:
        client = get_explorer_client()
        params = {"limit": limit, "offset": offset}
        if chain_id:
            params["chain_id"] = chain_id

        result = client.get("/api/blocks/latest", params=params)
        blocks = result.get("blocks", [])

        success(f"Latest {len(blocks)} blocks")
        click.echo(json.dumps(blocks, indent=2))
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting latest blocks: {e}")


@explorer.command()
@click.option("--limit", default=10, help="Number of blocks to return")
@click.option("--offset", default=0, help="Offset for pagination")
@click.option("--chain-id", help="Chain ID to query")
def non_empty_blocks(limit: int, offset: int, chain_id: str | None):
    """Get non-empty blocks (blocks with transactions)"""
    try:
        client = get_explorer_client()
        params = {"limit": limit, "offset": offset}
        if chain_id:
            params["chain_id"] = chain_id

        result = client.get("/api/blocks/non-empty", params=params)
        blocks = result.get("blocks", [])

        success(f"Non-empty blocks: {len(blocks)}")
        click.echo(json.dumps(blocks, indent=2))
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting non-empty blocks: {e}")


@explorer.command()
@click.argument("height", type=int)
@click.option("--chain-id", help="Chain ID to query")
def block(height: int, chain_id: str | None):
    """Get block by height"""
    try:
        client = get_explorer_client()
        params = {"chain_id": chain_id} if chain_id else {}
        result = client.get(f"/api/blocks/{height}", params=params)

        if result:
            success(f"Block at height {height}")
            click.echo(json.dumps(result, indent=2))
        else:
            error(f"Block at height {height} not found")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting block: {e}")


@explorer.command()
@click.argument("block_hash")
@click.option("--chain-id", help="Chain ID to query")
def block_by_hash(block_hash: str, chain_id: str | None):
    """Get block by hash"""
    try:
        client = get_explorer_client()
        params = {"chain_id": chain_id} if chain_id else {}
        result = client.get(f"/api/blocks/by-hash/{block_hash}", params=params)

        if result:
            success(f"Block with hash {block_hash}")
            click.echo(json.dumps(result, indent=2))
        else:
            error(f"Block with hash {block_hash} not found")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting block by hash: {e}")


@explorer.command()
@click.argument("tx_hash")
@click.option("--chain-id", help="Chain ID to query")
def transaction(tx_hash: str, chain_id: str | None):
    """Get transaction by hash (alias for transaction-by-hash)"""
    try:
        client = get_explorer_client()
        params = {"chain_id": chain_id} if chain_id else {}
        result = client.get(f"/api/transactions/by-hash/{tx_hash}", params=params)

        if result:
            success(f"Transaction {tx_hash}")
            click.echo(json.dumps(result, indent=2))
        else:
            error(f"Transaction {tx_hash} not found")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting transaction: {e}")


@explorer.command()
@click.argument("tx_hash")
@click.option("--chain-id", help="Chain ID to query")
def transaction_by_hash(tx_hash: str, chain_id: str | None):
    """Get transaction by hash (full details)"""
    try:
        client = get_explorer_client()
        params = {"chain_id": chain_id} if chain_id else {}
        result = client.get(f"/api/transactions/by-hash/{tx_hash}", params=params)

        if result:
            success(f"Transaction details for {tx_hash}")
            click.echo(json.dumps(result, indent=2))
        else:
            error(f"Transaction {tx_hash} not found")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting transaction details: {e}")


@explorer.command()
@click.argument("address")
@click.option("--limit", default=100, help="Number of transactions to return")
@click.option("--chain-id", help="Chain ID to query")
def search_transactions(address: str, limit: int, chain_id: str | None):
    """Search transactions by address or node ID"""
    try:
        client = get_explorer_client()
        params = {"address": address, "limit": limit}
        if chain_id:
            params["chain_id"] = chain_id

        result = client.get("/api/transactions/search", params=params)
        transactions = result.get("transactions", [])

        success(f"Found {len(transactions)} transactions for {address}")
        click.echo(json.dumps(transactions, indent=2))
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error searching transactions: {e}")


@explorer.command()
@click.argument("address")
@click.option("--limit", default=50, help="Number of blocks to return")
@click.option("--chain-id", help="Chain ID to query")
def blocks_by_address(address: str, limit: int, chain_id: str | None):
    """Get blocks containing transactions for a given address"""
    try:
        client = get_explorer_client()
        params = {"address": address, "limit": limit}
        if chain_id:
            params["chain_id"] = chain_id

        result = client.get(f"/api/blocks/by-address/{address}", params=params)
        blocks = result.get("blocks", [])

        success(f"Found {len(blocks)} blocks for {address}")
        click.echo(json.dumps(blocks, indent=2))
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting blocks by address: {e}")


@explorer.command()
@click.option("--period", default="24h", help="Time period (1h, 24h, 7d, 30d)")
@click.option("--chain-id", help="Chain ID to query")
def activity_timeline(period: str, chain_id: str | None):
    """Get activity timeline (daily transaction counts)"""
    try:
        client = get_explorer_client()
        params = {"period": period}
        if chain_id:
            params["chain_id"] = chain_id

        result = client.get("/api/analytics/activity", params=params)

        if result:
            success(f"Activity timeline for {period}")
            click.echo(json.dumps(result, indent=2))
        else:
            error("No activity data available")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting activity timeline: {e}")


@explorer.command()
@click.option("--chain-id", help="Chain ID to query")
def network_stats(chain_id: str | None):
    """Get network statistics (total AIT, active offers, unique nodes)"""
    try:
        client = get_explorer_client()
        params = {"chain_id": chain_id} if chain_id else {}
        result = client.get("/api/analytics/network-stats", params=params)

        if result:
            success("Network Statistics")
            click.echo(json.dumps(result, indent=2))
        else:
            error("No network stats available")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting network stats: {e}")


@explorer.command()
@click.argument("provider_id")
@click.option("--chain-id", help="Chain ID to query")
def provider_reputation(provider_id: str, chain_id: str | None):
    """Get provider reputation score"""
    try:
        client = get_explorer_client()
        params = {"chain_id": chain_id} if chain_id else {}
        result = client.get(f"/api/analytics/provider-reputation/{provider_id}", params=params)

        if result:
            success(f"Reputation for provider {provider_id}")
            click.echo(json.dumps(result, indent=2))
        else:
            error(f"No reputation data for provider {provider_id}")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting provider reputation: {e}")


@explorer.command()
@click.option("--limit", default=20, help="Number of addresses to return")
@click.option("--chain-id", help="Chain ID to query")
def top_addresses(limit: int, chain_id: str | None):
    """Get top addresses by transaction count and volume"""
    try:
        client = get_explorer_client()
        params = {"limit": limit}
        if chain_id:
            params["chain_id"] = chain_id

        result = client.get("/api/analytics/top-addresses", params=params)
        addresses = result.get("addresses", [])

        success(f"Top {len(addresses)} addresses")
        click.echo(json.dumps(addresses, indent=2))
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting top addresses: {e}")


@explorer.command()
def chains():
    """List all supported chains"""
    try:
        client = get_explorer_client()
        result = client.get("/api/chains")

        if result:
            success("Supported Chains")
            click.echo(json.dumps(result, indent=2))
        else:
            error("No chains data available")
    except NetworkError as e:
        error(f"Explorer API unavailable: {e}")
    except Exception as e:
        error(f"Error getting chains: {e}")
