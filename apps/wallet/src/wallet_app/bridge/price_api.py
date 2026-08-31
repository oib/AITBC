"""
ETH-AIT Price API
Fetches ETH price from CoinGecko and calculates AIT exchange rate.
"""

import os
from datetime import datetime
from decimal import Decimal
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.network import SharedHttpClient

logger = get_logger(__name__)

# Default AIT price in USD (fallback only; derived from oracle/fixed price when possible)
_AIT_USD_DEFAULT = Decimal(os.getenv("AIT_USD_PRICE", "0.25"))


def _ait_usd_price(eth_usd: Decimal | None = None, eth_eur: Decimal | None = None) -> Decimal:
    """Resolve AIT/USD price.

    Priority:
      1. AIT_EUR_FIXED_PRICE env, derived via live ETH/USD and ETH/EUR.
      2. AIT_USD_FIXED_PRICE env.
      3. AIT_USD_PRICE env.
    """
    eur_fixed = os.getenv("AIT_EUR_FIXED_PRICE")
    if eur_fixed and eth_usd is not None and eth_eur is not None and eth_eur > 0:
        try:
            ait_eur = Decimal(eur_fixed)
            return ait_eur * eth_usd / eth_eur
        except Exception:
            logger.warning("Invalid AIT_EUR_FIXED_PRICE: %s", eur_fixed)
    usd_fixed = os.getenv("AIT_USD_FIXED_PRICE")
    if usd_fixed:
        try:
            return Decimal(usd_fixed)
        except Exception:
            logger.warning("Invalid AIT_USD_FIXED_PRICE: %s", usd_fixed)
    return _AIT_USD_DEFAULT


async def get_eth_prices() -> dict[str, Decimal] | None:
    """
    Fetch current ETH price in USD and EUR from CoinGecko API.
    Returns None if API call fails.
    """
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": "ethereum", "vs_currencies": "usd,eur"}

        response = await SharedHttpClient.get(url, params=params, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        eth_data = data.get("ethereum", {})
        eth_usd = eth_data.get("usd")
        eth_eur = eth_data.get("eur")

        if eth_usd and eth_eur:
            return {"usd": Decimal(str(eth_usd)), "eur": Decimal(str(eth_eur))}

        return None
    except Exception as e:
        logger.error("Failed to fetch ETH prices: %s", e)
        return None


async def get_eth_price_usd() -> Decimal | None:
    """
    Fetch current ETH price in USD from CoinGecko API.
    Returns None if API call fails.
    """
    prices = await get_eth_prices()
    return prices["usd"] if prices else None


async def calculate_ait_amount(eth_amount: Decimal, eth_price_usd: Decimal | None = None) -> Decimal | None:
    """
    Calculate AIT amount based on ETH deposited.

    Formula: AIT = (ETH * ETH_USD) / AIT_USD
    """
    if eth_price_usd is None:
        eth_prices = await get_eth_prices()
        if not eth_prices:
            return None
        eth_price_usd = eth_prices["usd"]
        eth_price_eur = eth_prices["eur"]
    else:
        eth_price_eur = None

    ait_usd = _ait_usd_price(eth_price_usd, eth_price_eur)
    if ait_usd <= 0:
        return None

    return (eth_amount * eth_price_usd) / ait_usd


def _bridge_fee_rate() -> Decimal:
    try:
        return Decimal(os.getenv("BRIDGE_FEE_RATE", "0.005"))
    except Exception:
        return Decimal("0.005")


def _min_withdraw_ait() -> Decimal:
    try:
        return Decimal(os.getenv("MIN_AIT_WITHDRAW", "0.01"))
    except Exception:
        return Decimal("0.01")


def apply_bridge_fee(gross_ait: Decimal) -> tuple[Decimal, Decimal]:
    """Return (fee_ait, net_ait) after applying the configured bridge fee rate."""
    fee_rate = _bridge_fee_rate()
    fee_ait = (gross_ait * fee_rate).quantize(Decimal("0.000001"))
    net_ait = gross_ait - fee_ait
    return fee_ait, net_ait


async def calculate_eth_amount(gross_ait: Decimal, eth_price_usd: Decimal | None = None) -> dict[str, Any] | None:
    """
    Calculate the ETH amount for a given AIT withdrawal.

    Returns a dict with fee_ait, net_ait, amount_eth, eth_usd, ait_usd.
    """
    if eth_price_usd is None:
        eth_prices = await get_eth_prices()
        if not eth_prices:
            return None
        eth_price_usd = eth_prices["usd"]
        eth_price_eur = eth_prices["eur"]
    else:
        eth_price_eur = None

    ait_usd = _ait_usd_price(eth_price_usd, eth_price_eur)
    if ait_usd <= 0 or eth_price_usd <= 0:
        return None

    fee_ait, net_ait = apply_bridge_fee(gross_ait)
    if net_ait <= 0:
        return None

    amount_eth = (net_ait * ait_usd) / eth_price_usd
    return {
        "gross_ait": gross_ait,
        "fee_ait": fee_ait,
        "net_ait": net_ait,
        "amount_eth": amount_eth,
        "eth_usd": eth_price_usd,
        "ait_usd": ait_usd,
    }


async def get_exchange_rate() -> dict[str, Any]:
    """
    Get current ETH-AIT exchange rate information for USD and EUR.
    """
    eth_prices = await get_eth_prices()

    if eth_prices is None:
        return {"success": False, "error": "Failed to fetch ETH prices"}

    eth_usd = eth_prices["usd"]
    eth_eur = eth_prices["eur"]
    ait_usd = _ait_usd_price(eth_usd, eth_eur)
    ait_eur = ait_usd * eth_eur / eth_usd if eth_usd > 0 else Decimal("0")

    return {
        "success": True,
        "eth_usd": eth_usd,
        "eth_eur": eth_eur,
        "ait_usd": ait_usd,
        "ait_eur": ait_eur,
        "eth_ait_rate_usd": eth_usd / ait_usd,
        "eth_ait_rate_eur": eth_eur / ait_eur if ait_eur > 0 else Decimal("0"),
        "timestamp": datetime.now().isoformat(),
    }
