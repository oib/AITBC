"""Migration script from SQLite to PostgreSQL for AITBC Exchange"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))
import logging
import sqlite3
from decimal import Decimal
import psycopg2
logger = logging.getLogger(__name__)
SQLITE_DB = 'exchange.db'
PG_CONFIG = {'host': 'localhost', 'database': 'aitbc_exchange', 'user': 'aitbc_user', 'password': 'aitbc_password', 'port': 5432}

def create_pg_schema():
    """Create PostgreSQL schema with optimized types"""
    conn = psycopg2.connect(**PG_CONFIG)
    cursor = conn.cursor()
    logger.info('Creating PostgreSQL schema...')
    cursor.execute('DROP TABLE IF EXISTS trades CASCADE')
    cursor.execute('DROP TABLE IF EXISTS orders CASCADE')
    cursor.execute('\n        CREATE TABLE trades (\n            id SERIAL PRIMARY KEY,\n            amount NUMERIC(20, 8) NOT NULL,\n            price NUMERIC(20, 8) NOT NULL,\n            total NUMERIC(20, 8) NOT NULL,\n            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),\n            tx_hash VARCHAR(66),\n            maker_address VARCHAR(66),\n            taker_address VARCHAR(66)\n        )\n    ')
    cursor.execute("\n        CREATE TABLE orders (\n            id SERIAL PRIMARY KEY,\n            order_type VARCHAR(4) NOT NULL CHECK (order_type IN ('BUY', 'SELL')),\n            amount NUMERIC(20, 8) NOT NULL,\n            price NUMERIC(20, 8) NOT NULL,\n            total NUMERIC(20, 8) NOT NULL,\n            remaining NUMERIC(20, 8) NOT NULL,\n            filled NUMERIC(20, 8) DEFAULT 0,\n            status VARCHAR(20) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'FILLED', 'CANCELLED')),\n            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),\n            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),\n            user_address VARCHAR(66),\n            tx_hash VARCHAR(66)\n        )\n    ")
    logger.info('Creating indexes...')
    cursor.execute('CREATE INDEX idx_trades_created_at ON trades(created_at DESC)')
    cursor.execute('CREATE INDEX idx_trades_price ON trades(price)')
    cursor.execute('CREATE INDEX idx_orders_type ON orders(order_type)')
    cursor.execute('CREATE INDEX idx_orders_price ON orders(price)')
    cursor.execute('CREATE INDEX idx_orders_status ON orders(status)')
    cursor.execute('CREATE INDEX idx_orders_created_at ON orders(created_at DESC)')
    cursor.execute('CREATE INDEX idx_orders_user ON orders(user_address)')
    conn.commit()
    conn.close()
    logger.info('PostgreSQL schema created successfully')

def migrate_data():
    """Migrate data from SQLite to PostgreSQL"""
    logger.info('Starting data migration...')
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cursor = pg_conn.cursor()
    logger.info('Migrating trades...')
    sqlite_cursor.execute('SELECT * FROM trades')
    trades = sqlite_cursor.fetchall()
    trades_count = 0
    for trade in trades:
        pg_cursor.execute('\n            INSERT INTO trades (amount, price, total, created_at, tx_hash, maker_address, taker_address)\n            VALUES (%s, %s, %s, %s, %s, %s, %s)\n        ', (Decimal(str(trade['amount'])), Decimal(str(trade['price'])), Decimal(str(trade['total'])), trade['created_at'], trade.get('tx_hash'), trade.get('maker_address'), trade.get('taker_address')))
        trades_count += 1
    logger.info('Migrating orders...')
    sqlite_cursor.execute('SELECT * FROM orders')
    orders = sqlite_cursor.fetchall()
    orders_count = 0
    for order in orders:
        pg_cursor.execute('\n            INSERT INTO orders (order_type, amount, price, total, remaining, filled, status, \n                              created_at, updated_at, user_address, tx_hash)\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n        ', (order['order_type'], Decimal(str(order['amount'])), Decimal(str(order['price'])), Decimal(str(order['total'])), Decimal(str(order['remaining'])), Decimal(str(order['filled'])), order['status'], order['created_at'], order['updated_at'], order.get('user_address'), order.get('tx_hash')))
        orders_count += 1
    pg_conn.commit()
    logger.info('Migration complete')
    logger.info('Migrated %s trades', trades_count)
    logger.info('Migrated %s orders', orders_count)
    sqlite_conn.close()
    pg_conn.close()

def update_exchange_config():
    """Update exchange configuration to use PostgreSQL"""
    config_file = Path('simple_exchange_api.py')
    if not config_file.exists():
        logger.error('simple_exchange_api.py not found!')
        return
    logger.info('Updating exchange configuration...')
    content = config_file.read_text()
    pg_config = '\n# PostgreSQL Configuration\nPG_CONFIG = {\n    "host": "localhost",\n    "database": "aitbc_exchange",\n    "user": "aitbc_user",\n    "password": "aitbc_password",\n    "port": 5432\n}\n\ndef get_pg_connection():\n    """Get PostgreSQL connection"""\n    return psycopg2.connect(**PG_CONFIG)\n'
    new_init = '\ndef init_db():\n    """Initialize PostgreSQL database"""\n    try:\n        conn = get_pg_connection()\n        cursor = conn.cursor()\n        \n        # Check if tables exist\n        cursor.execute("""\n            SELECT EXISTS (\n                SELECT FROM information_schema.tables \n                WHERE table_name IN (\'trades\', \'orders\')\n            )\n        """)\n        \n        if not cursor.fetchone()[0]:\n            logger.info("Creating PostgreSQL tables...")\n            create_pg_schema()\n        \n        conn.close()\n    except Exception as e:\n        logger.error(f"Database initialization error: {e}")\n'
    content = content.replace('import sqlite3', 'import sqlite3\nimport psycopg2\nfrom psycopg2.extras import RealDictCursor')
    content = content.replace('def init_db():', new_init)
    content = content.replace("conn = sqlite3.connect('exchange.db')", 'conn = get_pg_connection()')
    content = content.replace('cursor = conn.cursor()', 'cursor = conn.cursor(cursor_factory=RealDictCursor)')
    config_file.write_text(content)
    logger.info('Configuration updated to use PostgreSQL')

def main():
    """Main migration process"""
    logger.info('=' * 60)
    logger.info('AITBC Exchange SQLite to PostgreSQL Migration')
    logger.info('=' * 60)
    if not Path(SQLITE_DB).exists():
        logger.error("SQLite database '%s' not found!", SQLITE_DB)
        return
    create_pg_schema()
    migrate_data()
    update_exchange_config()
    logger.info('\n' + '=' * 60)
    logger.info('Migration completed successfully!')
    logger.info('=' * 60)
    logger.info('Next steps:')
    logger.info('1. Install PostgreSQL dependencies: pip install psycopg2-binary')
    logger.info('2. Restart the exchange service')
    logger.info('3. Verify data integrity')
    logger.info('4. Backup and remove SQLite database')
if __name__ == '__main__':
    main()