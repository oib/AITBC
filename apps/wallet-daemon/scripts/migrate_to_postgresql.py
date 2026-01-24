#!/usr/bin/env python3
"""Migration script for Wallet Daemon from SQLite to PostgreSQL"""

import os
import sys
from pathlib import Path

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json

# Database configurations
SQLITE_DB = "data/wallet_ledger.db"
PG_CONFIG = {
    "host": "localhost",
    "database": "aitbc_wallet",
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
    cursor.execute("DROP TABLE IF EXISTS wallet_events CASCADE")
    cursor.execute("DROP TABLE IF EXISTS wallets CASCADE")
    
    # Create wallets table
    cursor.execute("""
        CREATE TABLE wallets (
            wallet_id VARCHAR(255) PRIMARY KEY,
            public_key TEXT,
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create wallet_events table
    cursor.execute("""
        CREATE TABLE wallet_events (
            id SERIAL PRIMARY KEY,
            wallet_id VARCHAR(255) REFERENCES wallets(wallet_id) ON DELETE CASCADE,
            event_type VARCHAR(100) NOT NULL,
            payload JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create indexes for performance
    print("Creating indexes...")
    cursor.execute("CREATE INDEX idx_wallet_events_wallet_id ON wallet_events(wallet_id)")
    cursor.execute("CREATE INDEX idx_wallet_events_type ON wallet_events(event_type)")
    cursor.execute("CREATE INDEX idx_wallet_events_created ON wallet_events(created_at DESC)")
    
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
    
    # Migrate wallets
    print("Migrating wallets...")
    sqlite_cursor.execute("SELECT * FROM wallets")
    wallets = sqlite_cursor.fetchall()
    
    wallets_count = 0
    for wallet in wallets:
        metadata = wallet['metadata']
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                metadata = {}
        
        pg_cursor.execute("""
            INSERT INTO wallets (wallet_id, public_key, metadata)
            VALUES (%s, %s, %s)
            ON CONFLICT (wallet_id) DO NOTHING
        """, (wallet['wallet_id'], wallet['public_key'], json.dumps(metadata)))
        wallets_count += 1
    
    # Migrate wallet events
    print("Migrating wallet events...")
    sqlite_cursor.execute("SELECT * FROM wallet_events")
    events = sqlite_cursor.fetchall()
    
    events_count = 0
    for event in events:
        payload = event['payload']
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except:
                payload = {}
        
        pg_cursor.execute("""
            INSERT INTO wallet_events (wallet_id, event_type, payload, created_at)
            VALUES (%s, %s, %s, %s)
        """, (event['wallet_id'], event['event_type'], json.dumps(payload), event['created_at']))
        events_count += 1
    
    pg_conn.commit()
    
    print(f"\n✅ Migration complete!")
    print(f"   - Migrated {wallets_count} wallets")
    print(f"   - Migrated {events_count} wallet events")
    
    sqlite_conn.close()
    pg_conn.close()

def main():
    """Main migration process"""
    
    print("=" * 60)
    print("AITBC Wallet Daemon SQLite to PostgreSQL Migration")
    print("=" * 60)
    
    # Check if SQLite DB exists
    if not Path(SQLITE_DB).exists():
        print(f"❌ SQLite database '{SQLITE_DB}' not found!")
        print("Looking for wallet databases...")
        # Find any wallet databases
        for db in Path(".").glob("**/*wallet*.db"):
            print(f"Found: {db}")
        return
    
    # Create PostgreSQL schema
    create_pg_schema()
    
    # Migrate data
    migrate_data()
    
    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Update wallet daemon configuration")
    print("2. Install PostgreSQL dependencies")
    print("3. Restart the wallet daemon service")
    print("4. Verify wallet operations")

if __name__ == "__main__":
    main()
