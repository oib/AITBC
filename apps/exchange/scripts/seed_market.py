"""Seed initial market price for the exchange"""

import sqlite3
from datetime import UTC, datetime

from aitbc.aitbc_logging import get_logger
from aitbc.constants import DATA_DIR

logger = get_logger(__name__)


def seed_initial_price():
    """Create initial trades to establish market price"""
    import os

    db_path = os.getenv("EXCHANGE_DATABASE_URL", f"sqlite:///{DATA_DIR}/data/exchange/exchange.db").replace("sqlite://///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    initial_trades = [(1000, 1e-05), (500, 1.05e-05), (750, 9.5e-06), (2000, 1e-05), (1500, 1.1e-05)]
    for amount, price in initial_trades:
        total = amount * price
        cursor.execute(
            "\n            INSERT INTO trades (amount, price, total, created_at)\n            VALUES (?, ?, ?, ?)\n        ",
            (amount, price, total, datetime.now(UTC)),
        )
    initial_orders = [("BUY", 5000, 9.5e-06), ("BUY", 3000, 1e-05), ("SELL", 2000, 1.05e-05), ("SELL", 4000, 1.1e-05)]
    for order_type, amount, price in initial_orders:
        total = amount * price
        cursor.execute(
            "\n            INSERT INTO orders (order_type, amount, price, total, remaining, user_address)\n            VALUES (?, ?, ?, ?, ?, ?)\n        ",
            (order_type, amount, price, total, amount, "aitbcexchange00000000000000000000000000000000"),
        )
    conn.commit()
    conn.close()
    logger.info("Seeded initial market data")
    logger.info("Created %s historical trades", len(initial_trades))
    logger.info("Created %s liquidity orders", len(initial_orders))
    logger.info("Initial price range: 0.0000095 - 0.000011 BTC")
    logger.info("The exchange should now show real prices")


if __name__ == "__main__":
    seed_initial_price()
