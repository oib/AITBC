"""
ETH-AIT Price API
Fetches ETH price from CoinGecko and calculates AIT exchange rate.
"""

from typing import Dict, Optional

import requests

# Fixed AIT price in USD (for simplicity in MVP)
AIT_USD_PRICE = 1.0  # 1 AIT = $1 USD


def get_eth_prices() -> Optional[Dict[str, float]]:
    """
    Fetch current ETH price in USD and EUR from CoinGecko API.
    Returns None if API call fails.
    """
    try:
        # CoinGecko public API (no API key required for basic usage)
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "ethereum",
            "vs_currencies": "usd,eur"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        eth_data = data.get("ethereum", {})
        eth_usd = eth_data.get("usd")
        eth_eur = eth_data.get("eur")
        
        if eth_usd and eth_eur:
            return {
                "usd": float(eth_usd),
                "eur": float(eth_eur)
            }
        
        return None
    except Exception as e:
        print(f"Error fetching ETH prices: {e}")
        return None


def get_eth_price_usd() -> Optional[float]:
    """
    Fetch current ETH price in USD from CoinGecko API.
    Returns None if API call fails.
    """
    prices = get_eth_prices()
    return prices["usd"] if prices else None


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
    Get current ETH-AIT exchange rate information for USD and EUR.
    """
    eth_prices = get_eth_prices()
    
    if eth_prices is None:
        return {
            "success": False,
            "error": "Failed to fetch ETH prices"
        }
    
    return {
        "success": True,
        "eth_usd": eth_prices["usd"],
        "eth_eur": eth_prices["eur"],
        "ait_usd": AIT_USD_PRICE,
        "ait_eur": AIT_USD_PRICE * (eth_prices["eur"] / eth_prices["usd"]),  # Approximate EUR price
        "eth_ait_rate_usd": eth_prices["usd"] / AIT_USD_PRICE,
        "eth_ait_rate_eur": eth_prices["eur"] / (AIT_USD_PRICE * (eth_prices["eur"] / eth_prices["usd"])),
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }
