"""
ETH-AIT Price API
Fetches ETH price from CoinGecko and calculates AIT exchange rate.
"""

import os
import requests
from typing import Optional


# Fixed AIT price in USD (for simplicity in MVP)
AIT_USD_PRICE = 1.0  # 1 AIT = $1 USD


def get_eth_price_usd() -> Optional[float]:
    """
    Fetch current ETH price in USD from CoinGecko API.
    Returns None if API call fails.
    """
    try:
        # CoinGecko public API (no API key required for basic usage)
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "ethereum",
            "vs_currencies": "usd"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        eth_price = data.get("ethereum", {}).get("usd")
        
        return float(eth_price) if eth_price else None
    except Exception as e:
        print(f"Error fetching ETH price: {e}")
        return None


def calculate_ait_amount(eth_amount: float, eth_price_usd: Optional[float] = None) -> Optional[float]:
    """
    Calculate AIT amount based on ETH deposited.
    
    Formula: AIT = (ETH * ETH_USD) / AIT_USD
    """
    if eth_price_usd is None:
        eth_price_usd = get_eth_price_usd()
    
    if eth_price_usd is None:
        return None
    
    return (eth_amount * eth_price_usd) / AIT_USD_PRICE


def get_exchange_rate() -> dict:
    """
    Get current ETH-AIT exchange rate information.
    """
    eth_price = get_eth_price_usd()
    
    if eth_price is None:
        return {
            "success": False,
            "error": "Failed to fetch ETH price"
        }
    
    return {
        "success": True,
        "eth_usd": eth_price,
        "ait_usd": AIT_USD_PRICE,
        "eth_ait_rate": eth_price / AIT_USD_PRICE,
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }
