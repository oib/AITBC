"""``price_history`` rows for the shared bridge ledger.

Split out of ``bridge_db.py`` (pure code motion). Connection handling and
``DB_PATH`` live in ``bridge_db`` — helpers are imported back from that
module so a monkeypatched ``bridge_db.DB_PATH`` keeps applying here.
"""

from decimal import Decimal
from typing import Any

from .bridge_db import _connect_db


def insert_price_history(eth_usd: Decimal, eth_eur: Decimal, exchange_rate_usd: Decimal, exchange_rate_eur: Decimal) -> None:
    """Insert a new price history record."""
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO price_history (eth_usd_price, eth_eur_price, exchange_rate_usd, exchange_rate_eur)
        VALUES (?, ?, ?, ?)
        """,
        (eth_usd, eth_eur, exchange_rate_usd, exchange_rate_eur),
    )

    conn.commit()
    conn.close()


def get_all_time_average() -> dict[str, Any] | None:
    """Get all-time average prices from history."""
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            AVG(eth_usd_price) as avg_usd,
            AVG(eth_eur_price) as avg_eur,
            AVG(exchange_rate_usd) as avg_rate_usd,
            AVG(exchange_rate_eur) as avg_rate_eur,
            COUNT(*) as count
        FROM price_history
    """)

    result = cursor.fetchone()
    conn.close()

    if result and result[4] > 0:  # count > 0
        return {
            "eth_usd_avg": Decimal(str(result[0])) if result[0] is not None else None,
            "eth_eur_avg": Decimal(str(result[1])) if result[1] is not None else None,
            "exchange_rate_usd_avg": Decimal(str(result[2])) if result[2] is not None else None,
            "exchange_rate_eur_avg": Decimal(str(result[3])) if result[3] is not None else None,
            "count": result[4],
        }

    return None


def cleanup_old_prices(days: int = 30) -> int:
    """Clean up price history older than specified days."""
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM price_history
        WHERE timestamp < datetime('now', ?)
        """,
        (f"-{int(days)} days",),
    )

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count
