"""
Blockchain service for AITBC token operations
"""

import re

from aitbc import get_logger, AITBCHTTPClient, NetworkError

logger = get_logger(__name__)

from ..config import settings

BLOCKCHAIN_RPC = "http://127.0.0.1:9080/rpc"

# Basic validation for blockchain addresses (alphanumeric, common prefixes)
ADDRESS_PATTERN = re.compile(r'^[a-zA-Z0-9]{20,50}$')


def validate_address(address: str) -> bool:
    """Validate that address is safe to use in URL construction"""
    if not address:
        return False
    # Check for path traversal or URL manipulation
    if any(char in address for char in ['/', '\\', '..', '\n', '\r', '\t']):
        return False
    # Check for URL-like patterns
    if address.startswith(('http://', 'https://', 'ftp://')):
        return False
    # Validate against address pattern
    return bool(ADDRESS_PATTERN.match(address))


async def mint_tokens(address: str, amount: float) -> dict:
    """Mint AITBC tokens to an address"""

    client = AITBCHTTPClient(timeout=10.0)
    try:
        response = client.post(
            f"{BLOCKCHAIN_RPC}/admin/mintFaucet",
            json={"address": address, "amount": amount},
            headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
        )
        return response
    except NetworkError as e:
        raise Exception(f"Failed to mint tokens: {e}")


def get_balance(address: str) -> float | None:
    """Get AITBC balance for an address"""

    if not validate_address(address):
        logger.error("Invalid address format")
        return None

    try:
        client = AITBCHTTPClient(timeout=10.0)
        try:
            response = client.get(
                f"{BLOCKCHAIN_RPC}/getBalance/{address}",
                headers={"X-Api-Key": settings.admin_api_keys[0] if settings.admin_api_keys else ""},
            )
            return float(response.get("balance", 0))
        except NetworkError as e:
            logger.error("Error getting balance: %s", e)
            return None
    except Exception as e:
        logger.error("Error getting balance: %s", e)
        return None
