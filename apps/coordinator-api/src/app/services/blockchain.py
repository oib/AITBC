"""
Blockchain service for AITBC token operations
"""

import httpx
import asyncio
from typing import Optional

from ..config import settings

BLOCKCHAIN_RPC = f"http://127.0.0.1:9080/rpc"

async def mint_tokens(address: str, amount: float) -> dict:
    """Mint AITBC tokens to an address"""
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BLOCKCHAIN_RPC}/admin/mintFaucet",
            json={
                "address": address,
                "amount": amount
            },
            headers={"X-Api-Key": "REDACTED_ADMIN_KEY"}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to mint tokens: {response.text}")

def get_balance(address: str) -> Optional[float]:
    """Get AITBC balance for an address"""
    
    try:
        import requests
        
        response = requests.get(
            f"{BLOCKCHAIN_RPC}/getBalance/{address}",
            headers={"X-Api-Key": "REDACTED_ADMIN_KEY"}
        )
        
        if response.status_code == 200:
            data = response.json()
            return float(data.get("balance", 0))
        
    except Exception as e:
        print(f"Error getting balance: {e}")
    
    return None
