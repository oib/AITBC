"""
Blockchain service for AITBC token operations
"""

import logging

import httpx

logger = logging.getLogger(__name__)

from ..config import settings

BLOCKCHAIN_RPC = "http://127.0.0.1:9080/rpc"


async def mint_tokens(address: str, amount: float) -> dict:
    """Mint AITBC tokens to an address"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BLOCKCHAIN_RPC}/admin/mintFaucet",
            json={"address": address, "amount": amount},
            headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to mint tokens: {response.text}")


def get_balance(address: str) -> float | None:
    """Get AITBC balance for an address"""

    try:
        with httpx.Client() as client:
            response = client.get(
                f"{BLOCKCHAIN_RPC}/getBalance/{address}",
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )

            if response.status_code == 200:
                data = response.json()
                return float(data.get("balance", 0))

    except Exception as e:
        logger.error("Error getting balance: %s", e)

    return None
