#!/usr/bin/env python3
"""Migration script from SQLite to PostgreSQL for AITBC Exchange"""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from decimal import Decimal

# Database configurations
SQLITE_DB = "exchange.db"
PG_CONFIG = {
    "host": "localhost",
    "database": "aitbc_exchange",
    "user": "aitbc_user",
    "password": "aitbc_password",
    "port": 5432
}

def create_pg_schema():
    """Create PostgreSQL schema with optimized types"""
    
    conn = psycopg2.connect(**PG_CONFIG)
    cursor = conn.cursor()
    
    print("Creating PostgreSQL schema...")
    
    # Drop existing tables
    cursor.execute("DROP TABLE IF EXISTS trades CASCADE")
    cursor.execute("DROP TABLE IF EXISTS orders CASCADE")
    
    # Create trades table with proper types
    cursor.execute("""
        CREATE TABLE trades (
            id SERIAL PRIMARY KEY,
            amount NUMERIC(20, 8) NOT NULL,
            price NUMERIC(20, 8) NOT NULL,
            total NUMERIC(20, 8) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            tx_hash VARCHAR(66),
            maker_address VARCHAR(66),
            taker_address VARCHAR(66)
        )
    """)
    
    # Create orders table with proper types
    cursor.execute("""
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            order_type VARCHAR(4) NOT NULL CHECK (order_type IN ('BUY', 'SELL')),
            amount NUMERIC(20, 8) NOT NULL,
            price NUMERIC(20, 8) NOT NULL,
            total NUMERIC(20, 8) NOT NULL,
            remaining NUMERIC(20, 8) NOT NULL,
            filled NUMERIC(20, 8) DEFAULT 0,
            status VARCHAR(20) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'FILLED', 'CANCELLED')),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            user_address VARCHAR(66),
            tx_hash VARCHAR(66)
        )
    """)
    
    # Create indexes for performance
    print("Creating indexes...")
    cursor.execute("CREATE INDEX idx_trades_created_at ON trades(created_at DESC)")
    cursor.execute("CREATE INDEX idx_trades_price ON trades(price)")
    cursor.execute("CREATE INDEX idx_orders_type ON orders(order_type)")
    cursor.execute("CREATE INDEX idx_orders_price ON orders(price)")
    cursor.execute("CREATE INDEX idx_orders_status ON orders(status)")
    cursor.execute("CREATE INDEX idx_orders_created_at ON orders(created_at DESC)")
    cursor.execute("CREATE INDEX idx_orders_user ON orders(user_address)")
    
    conn.commit()
    conn.close()
    print("✅ PostgreSQL schema created successfully!")

def migrate_data():
    """Migrate data from SQLite to PostgreSQL"""
    
    print("\nStarting data migration...")
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cursor = pg_conn.cursor()
    
    # Migrate trades
    print("Migrating trades...")
    sqlite_cursor.execute("SELECT * FROM trades")
    trades = sqlite_cursor.fetchall()
    
    trades_count = 0
    for trade in trades:
        pg_cursor.execute("""
            INSERT INTO trades (amount, price, total, created_at, tx_hash, maker_address, taker_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            Decimal(str(trade['amount'])),
            Decimal(str(trade['price'])),
            Decimal(str(trade['total'])),
            trade['created_at'],
            trade.get('tx_hash'),
            trade.get('maker_address'),
            trade.get('taker_address')
        ))
        trades_count += 1
    
    # Migrate orders
    print("Migrating orders...")
    sqlite_cursor.execute("SELECT * FROM orders")
    orders = sqlite_cursor.fetchall()
    
    orders_count = 0
    for order in orders:
        pg_cursor.execute("""
            INSERT INTO orders (order_type, amount, price, total, remaining, filled, status, 
                              created_at, updated_at, user_address, tx_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            order['order_type'],
            Decimal(str(order['amount'])),
            Decimal(str(order['price'])),
            Decimal(str(order['total'])),
            Decimal(str(order['remaining'])),
            Decimal(str(order['filled'])),
            order['status'],
            order['created_at'],
            order['updated_at'],
            order.get('user_address'),
            order.get('tx_hash')
        ))
        orders_count += 1
    
    pg_conn.commit()
    
    print(f"\n✅ Migration complete!")
    print(f"   - Migrated {trades_count} trades")
    print(f"   - Migrated {orders_count} orders")
    
    sqlite_conn.close()
    pg_conn.close()

def update_exchange_config():
    """Update exchange configuration to use PostgreSQL"""
    
    config_file = Path("simple_exchange_api.py")
    if not config_file.exists():
        print("❌ simple_exchange_api.py not found!")
        return
    
    print("\nUpdating exchange configuration...")
    
    # Read the current file
    content = config_file.read_text()
    
    # Add PostgreSQL configuration
    pg_config = """
# PostgreSQL Configuration
PG_CONFIG = {
    "host": "localhost",
    "database": "aitbc_exchange",
    "user": "aitbc_user",
    "password": "aitbc_password",
    "port": 5432
}

def get_pg_connection():
    \"\"\"Get PostgreSQL connection\"\"\"
    return psycopg2.connect(**PG_CONFIG)
"""
    
    # Replace SQLite init with PostgreSQL
    new_init = """
def init_db():
    \"\"\"Initialize PostgreSQL database\"\"\"
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute(\"\"\"
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name IN ('trades', 'orders')
            )
        \"\"\")
        
        if not cursor.fetchone()[0]:
            print("Creating PostgreSQL tables...")
            create_pg_schema()
        
        conn.close()
    except Exception as e:
        print(f"Database initialization error: {e}")
"""
    
    # Update the file
    content = content.replace("import sqlite3", "import sqlite3\nimport psycopg2\nfrom psycopg2.extras import RealDictCursor")
    content = content.replace("def init_db():", new_init)
    content = content.replace("conn = sqlite3.connect('exchange.db')", "conn = get_pg_connection()")
    content = content.replace("cursor = conn.cursor()", "cursor = conn.cursor(cursor_factory=RealDictCursor)")
    
    # Write back
    config_file.write_text(content)
    print("✅ Configuration updated to use PostgreSQL!")

def main():
    """Main migration process"""
    
    print("=" * 60)
    print("AITBC Exchange SQLite to PostgreSQL Migration")
    print("=" * 60)
    
    # Check if SQLite DB exists
    if not Path(SQLITE_DB).exists():
        print(f"❌ SQLite database '{SQLITE_DB}' not found!")
        return
    
    # Create PostgreSQL schema
    create_pg_schema()
    
    # Migrate data
    migrate_data()
    
    # Update configuration
    update_exchange_config()
    
    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Install PostgreSQL dependencies: pip install psycopg2-binary")
    print("2. Restart the exchange service")
    print("3. Verify data integrity")
    print("4. Backup and remove SQLite database")

if __name__ == "__main__":
    main()
