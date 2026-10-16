"""
ETH-AIT Price API
Fetches ETH price via the shared price oracle and calculates AIT exchange rate.
"""

import asyncio
import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.oracles.price_oracle import AIT_REFERENCE_PRICE_EUR

logger = get_logger(__name__)

# Last-resort flat USD value — only used when no ETH prices are available to
# convert the EUR-anchored compute reference and no env override is set.
_AIT_USD_FALLBACK = Decimal("0.25")


def _ait_usd_price(eth_usd: Decimal | None = None, eth_eur: Decimal | None = None) -> Decimal:
    """Resolve AIT/USD price.

    Priority:
      1. AIT_EUR_FIXED_PRICE env, derived via live ETH/USD and ETH/EUR.
      2. AIT_USD_FIXED_PRICE env (legacy flat USD override).
      3. AIT_USD_PRICE env (explicit USD override).
      4. Compute-backed reference — EUR 0.25 per compute-hour on the RTX 4060
         Ti 16GB reference rig, converted to USD via live ETH prices.
      5. Flat USD fallback when no ETH prices are available at all.
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
    usd_env = os.getenv("AIT_USD_PRICE")
    if usd_env:
        try:
            return Decimal(usd_env)
        except Exception:
            logger.warning("Invalid AIT_USD_PRICE: %s", usd_env)
    if eth_usd is not None and eth_eur is not None and eth_eur > 0:
        return AIT_REFERENCE_PRICE_EUR * eth_usd / eth_eur
    return _AIT_USD_FALLBACK


async def get_eth_prices() -> dict[str, Decimal] | None:
    """
    Fetch current ETH price in USD and EUR via the shared price oracle
    (Chainlink → CoinGecko, with in-memory and on-disk caching).
    Falls back to ETH_USD_FIXED_PRICE / ETH_EUR_FIXED_PRICE env vars.
    Returns None if no source yields both prices.
    """
    try:
        from aitbc.oracles.price_oracle import get_price_oracle

        oracle = get_price_oracle()
        eth_usd = await asyncio.to_thread(oracle.get_price, "ETH", "USD")
        eth_eur = await asyncio.to_thread(oracle.get_price, "ETH", "EUR")

        if eth_usd and eth_eur:
            return {"usd": eth_usd.price, "eur": eth_eur.price}
    except Exception as e:
        logger.error("Failed to fetch ETH prices: %s", e)

    fixed_usd = os.getenv("ETH_USD_FIXED_PRICE")
    fixed_eur = os.getenv("ETH_EUR_FIXED_PRICE")
    if fixed_usd:
        try:
            return {"usd": Decimal(str(fixed_usd)), "eur": Decimal(str(fixed_eur or fixed_usd))}
        except (ArithmeticError, TypeError, ValueError):
            logger.warning("Invalid fixed ETH price env: %s / %s", fixed_usd, fixed_eur)
    return None


def _bridge_price_max_age() -> float:
    """Max age in seconds a price feed may reach before it is stale."""
    try:
        return float(os.getenv("BRIDGE_PRICE_MAX_AGE", "7200"))
    except (TypeError, ValueError):
        return 7200.0


async def get_eth_prices_meta() -> dict[str, Any] | None:
    """ETH prices plus feed freshness.

    Returns {"usd", "eur", "feed_age_seconds", "feed_source"} or None when no
    source yields both prices. ``feed_age_seconds`` is the age of the oldest
    underlying price point (the Chainlink round's on-chain ``updatedAt`` when
    the oracle path is live); env-pinned prices are operator-set and report
    ``feed_source="env"`` with age 0 — an explicit pin is never "stale".
    """
    try:
        from aitbc.oracles.price_oracle import get_price_oracle

        oracle = get_price_oracle()
        usd_res = await asyncio.to_thread(oracle.get_price, "ETH", "USD")
        eur_res = await asyncio.to_thread(oracle.get_price, "ETH", "EUR")

        if usd_res and eur_res:
            oldest = min(usd_res.timestamp, eur_res.timestamp)
            return {
                "usd": usd_res.price,
                "eur": eur_res.price,
                "feed_age_seconds": max(0.0, time.time() - oldest),
                "feed_source": "oracle",
            }
    except Exception as e:  # noqa: BLE001 - feed failure falls back to the env override
        logger.error("Failed to fetch ETH prices: %s", e)

    fixed_usd = os.getenv("ETH_USD_FIXED_PRICE")
    fixed_eur = os.getenv("ETH_EUR_FIXED_PRICE")
    if fixed_usd:
        try:
            return {
                "usd": Decimal(str(fixed_usd)),
                "eur": Decimal(str(fixed_eur or fixed_usd)),
                "feed_age_seconds": 0.0,
                "feed_source": "env",
            }
        except (ArithmeticError, TypeError, ValueError):
            logger.warning("Invalid fixed ETH price env: %s / %s", fixed_usd, fixed_eur)
    return None


async def get_eth_prices_fresh() -> dict[str, Any] | None:
    """ETH prices only when the feed is younger than BRIDGE_PRICE_MAX_AGE.

    Returns None when prices are unavailable OR the feed is stale — callers
    that must not price off a dead feed (sell quotes, sell releases) use
    this; the returned dict still carries ``feed_age_seconds``.
    """
    meta = await get_eth_prices_meta()
    if meta is None:
        return None
    max_age = _bridge_price_max_age()
    if meta["feed_source"] != "env" and meta["feed_age_seconds"] > max_age:
        logger.warning(
            "ETH price feed stale: age %.0fs > BRIDGE_PRICE_MAX_AGE %.0fs",
            meta["feed_age_seconds"],
            max_age,
        )
        return None
    return meta


async def get_eth_price_usd() -> Decimal | None:
    """
    Fetch current ETH price in USD via the shared price oracle.
    Returns None if no price source is available.
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
    except (ArithmeticError, TypeError, ValueError):
        return Decimal("0.005")


def _min_withdraw_ait() -> Decimal:
    try:
        return Decimal(os.getenv("MIN_AIT_WITHDRAW", "0.01"))
    except (ArithmeticError, TypeError, ValueError):
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
