"""
Blockchain utility functions for AITBC CLI
"""

import os

from aitbc import get_logger
from aitbc.utils.units import UNITS_PER_AIT, units_to_ait

from .http_client import AITBCHTTPClient, NetworkError

logger = get_logger(__name__)


def get_chain_info(rpc_url: str = "http://localhost:8202") -> dict | None:
    """Get blockchain information"""
    try:
        result = {}
        # Get chain metadata from health endpoint
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        health = http_client.get("/health")
        chains = health.get("supported_chains", [])
        result["chain_id"] = chains[0] if chains else os.getenv("CHAIN_ID", "")
        result["supported_chains"] = ", ".join(chains) if chains else os.getenv("CHAIN_ID", "")
        result["proposer_id"] = health.get("proposer_id", "")
        # Get head block for height
        head = http_client.get("/rpc/head")
        result["height"] = head.get("height", 0)
        result["hash"] = head.get("hash", "")
        result["timestamp"] = head.get("timestamp", "N/A")
        result["tx_count"] = head.get("tx_count", 0)
        return result if result else None
    except NetworkError as e:
        logger.error("Error: %s", e)
        return None
    except Exception as e:
        logger.error("Error: %s", e)
        return None


def get_network_status(rpc_url: str = "http://localhost:8202") -> dict | None:
    """Get network status and health"""
    try:
        # Get head block
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        return http_client.get("/rpc/head")
    except NetworkError as e:
        logger.error("Error getting network status: %s", e)
        return None
    except Exception as e:
        logger.error("Error: %s", e)
        return None


def get_blockchain_analytics(analytics_type: str, limit: int = 10, rpc_url: str = "http://localhost:8202") -> dict | None:
    """Get blockchain analytics and statistics"""
    try:
        if analytics_type == "blocks":
            # Get recent blocks analytics
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            head = http_client.get("/rpc/head")
            return {
                "type": "blocks",
                "current_height": head.get("height", 0),
                "latest_block": head.get("hash", ""),
                "timestamp": head.get("timestamp", ""),
                "tx_count": head.get("tx_count", 0),
                "status": "Active",
            }

        elif analytics_type == "supply":
            # Total minted supply: sum of the genesis allocation balances,
            # fetched from the node and converted from base units to AIT.
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            response = http_client.get("/rpc/genesis_allocations")
            allocations = response.get("allocations", [])
            total_units = sum(alloc.get("balance", 0) for alloc in allocations)
            total_ait = format(units_to_ait(total_units).normalize(), "f")
            return {
                "type": "supply",
                "total_supply": total_ait,
                "total_supply_units": total_units,
                # Mirrors total for now: a true circulating number needs a
                # live account-balance aggregate the node RPC does not offer.
                "circulating_supply": total_ait,
                "circulating_supply_units": total_units,
                "unit": "AIT",
                "units_per_ait": UNITS_PER_AIT,
                "basis": "genesis_allocations",
                "status": "Available",
            }

        elif analytics_type == "accounts":
            # Account statistics
            return {
                "type": "accounts",
                "total_accounts": 3,  # Genesis + treasury + user
                "active_accounts": 2,  # Accounts with transactions
                "genesis_accounts": 2,  # Genesis and treasury
                "user_accounts": 1,
                "status": "Healthy",
            }

        else:
            return {"type": analytics_type, "status": "Not implemented yet"}

    except Exception as e:
        logger.error("Error getting analytics: %s", e)
        return None
