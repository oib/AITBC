#!/usr/bin/env python3
"""Seed initial market price for the exchange"""

import sqlite3
from datetime import datetime
from aitbc.constants import DATA_DIR

def seed_initial_price():
    """Create initial trades to establish market price"""
    
    import os
    db_path = os.getenv("EXCHANGE_DATABASE_URL", f"sqlite:///{DATA_DIR}/data/exchange/exchange.db").replace("sqlite://///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create some initial trades at different price points
    initial_trades = [
        (1000, 0.00001),   # 1000 AITBC at 0.00001 BTC each
        (500, 0.0000105),  # 500 AITBC at slightly higher
        (750, 0.0000095),  # 750 AITBC at slightly lower
        (2000, 0.00001),   # 2000 AITBC at base price
        (1500, 0.000011),  # 1500 AITBC at higher price
    ]
    
    for amount, price in initial_trades:
        total = amount * price
        cursor.execute('''
            INSERT INTO trades (amount, price, total, created_at)
            VALUES (?, ?, ?, ?)
        ''', (amount, price, total, datetime.utcnow()))
    
    # Also create some initial orders for liquidity
    initial_orders = [
        ('BUY', 5000, 0.0000095),   # Buy order
        ('BUY', 3000, 0.00001),     # Buy order
        ('SELL', 2000, 0.0000105),  # Sell order
        ('SELL', 4000, 0.000011),   # Sell order
    ]
    
    for order_type, amount, price in initial_orders:
        total = amount * price
        cursor.execute('''
            INSERT INTO orders (order_type, amount, price, total, remaining, user_address)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (order_type, amount, price, total, amount, 'aitbcexchange00000000000000000000000000000000'))
    
    conn.commit()
    conn.close()
    
    print("✅ Seeded initial market data:")
    print(f"   - Created {len(initial_trades)} historical trades")
    print(f"   - Created {len(initial_orders)} liquidity orders")
    print(f"   - Initial price range: 0.0000095 - 0.000011 BTC")
    print("   The exchange should now show real prices!")

if __name__ == "__main__":
    seed_initial_price()
