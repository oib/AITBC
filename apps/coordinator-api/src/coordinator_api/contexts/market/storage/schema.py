"""Market context database schema."""

from __future__ import annotations

# Table name prefixes for market context
MARKET_TABLE_PREFIX = "marketplace_"

# Market context table names
MARKET_OFFER_TABLE = f"{MARKET_TABLE_PREFIX}offer"
MARKET_BID_TABLE = f"{MARKET_TABLE_PREFIX}bid"
MARKET_STATS_TABLE = f"{MARKET_TABLE_PREFIX}stats"
GPU_REGISTRY_TABLE = f"{MARKET_TABLE_PREFIX}gpu_registry"
GPU_BOOKING_TABLE = f"{MARKET_TABLE_PREFIX}gpu_booking"
GPU_REVIEW_TABLE = f"{MARKET_TABLE_PREFIX}gpu_review"
GLOBAL_MARKET_OFFER_TABLE = f"{MARKET_TABLE_PREFIX}global_offer"
GLOBAL_MARKET_TRANSACTION_TABLE = f"{MARKET_TABLE_PREFIX}global_transaction"
