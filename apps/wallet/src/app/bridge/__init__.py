"""
ETH-AIT Bridge Package
Bridge monitoring and exchange functionality for ETH-AIT swaps.
"""

from .bridge_db import get_pending_deposits, init_db, insert_deposit, update_deposit_status
from .bridge_monitor import start_monitoring
from .bridge_routes import router
from .price_api import calculate_ait_amount, get_eth_price_usd, get_exchange_rate

__all__ = [
    "init_db",
    "insert_deposit",
    "get_pending_deposits",
    "update_deposit_status",
    "get_eth_price_usd",
    "calculate_ait_amount",
    "get_exchange_rate",
    "start_monitoring",
    "router"
]
