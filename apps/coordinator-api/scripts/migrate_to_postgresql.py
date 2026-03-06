#!/usr/bin/env python3
"""Migration script for Coordinator API from SQLite to PostgreSQL"""

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
import json

# Database configurations
SQLITE_DB = "coordinator.db"
PG_CONFIG = {
    "host": "localhost",
    "database": "aitbc_coordinator",
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
    cursor.execute("DROP TABLE IF EXISTS jobreceipt CASCADE")
    cursor.execute("DROP TABLE IF EXISTS marketplacebid CASCADE")
    cursor.execute("DROP TABLE IF EXISTS marketplaceoffer CASCADE")
    cursor.execute("DROP TABLE IF EXISTS job CASCADE")
    cursor.execute("DROP TABLE IF EXISTS usersession CASCADE")
    cursor.execute("DROP TABLE IF EXISTS wallet CASCADE")
    cursor.execute("DROP TABLE IF EXISTS miner CASCADE")
    cursor.execute("DROP TABLE IF EXISTS transaction CASCADE")
    cursor.execute("DROP TABLE IF EXISTS user CASCADE")
    
    # Create user table
    cursor.execute("""
        CREATE TABLE user (
            id VARCHAR(255) PRIMARY KEY,
            email VARCHAR(255),
            username VARCHAR(255),
            status VARCHAR(20) CHECK (status IN ('active', 'inactive', 'suspended')),
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE,
            last_login TIMESTAMP WITH TIME ZONE
        )
    """)
    
    # Create wallet table
    cursor.execute("""
        CREATE TABLE wallet (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) REFERENCES user(id),
            address VARCHAR(255) UNIQUE,
            balance NUMERIC(20, 8) DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create usersession table
    cursor.execute("""
        CREATE TABLE usersession (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) REFERENCES user(id),
            token VARCHAR(255) UNIQUE,
            expires_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            last_used TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create miner table
    cursor.execute("""
        CREATE TABLE miner (
            id VARCHAR(255) PRIMARY KEY,
            region VARCHAR(100),
            capabilities JSONB,
            concurrency INTEGER DEFAULT 1,
            status VARCHAR(20) DEFAULT 'active',
            inflight INTEGER DEFAULT 0,
            extra_metadata JSONB,
            last_heartbeat TIMESTAMP WITH TIME ZONE,
            session_token VARCHAR(255),
            last_job_at TIMESTAMP WITH TIME ZONE,
            jobs_completed INTEGER DEFAULT 0,
            jobs_failed INTEGER DEFAULT 0,
            total_job_duration_ms BIGINT DEFAULT 0,
            average_job_duration_ms NUMERIC(10, 2) DEFAULT 0,
            last_receipt_id VARCHAR(255)
        )
    """)
    
    # Create job table
    cursor.execute("""
        CREATE TABLE job (
            id VARCHAR(255) PRIMARY KEY,
            client_id VARCHAR(255),
            state VARCHAR(20) CHECK (state IN ('pending', 'assigned', 'running', 'completed', 'failed', 'expired')),
            payload JSONB,
            constraints JSONB,
            ttl_seconds INTEGER,
            requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            expires_at TIMESTAMP WITH TIME ZONE,
            assigned_miner_id VARCHAR(255) REFERENCES miner(id),
            result JSONB,
            receipt JSONB,
            receipt_id VARCHAR(255),
            error TEXT
        )
    """)
    
    # Create marketplaceoffer table
    cursor.execute("""
        CREATE TABLE marketplaceoffer (
            id VARCHAR(255) PRIMARY KEY,
            provider VARCHAR(255),
            capacity INTEGER,
            price NUMERIC(20, 8),
            sla JSONB,
            status VARCHAR(20) CHECK (status IN ('active', 'inactive', 'filled', 'expired')),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            attributes JSONB
        )
    """)
    
    # Create marketplacebid table
    cursor.execute("""
        CREATE TABLE marketplacebid (
            id VARCHAR(255) PRIMARY KEY,
            provider VARCHAR(255),
            capacity INTEGER,
            price NUMERIC(20, 8),
            notes TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create jobreceipt table
    cursor.execute("""
        CREATE TABLE jobreceipt (
            id VARCHAR(255) PRIMARY KEY,
            job_id VARCHAR(255) REFERENCES job(id),
            receipt_id VARCHAR(255),
            payload JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create transaction table
    cursor.execute("""
        CREATE TABLE transaction (
            id VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(255),
            type VARCHAR(50),
            amount NUMERIC(20, 8),
            status VARCHAR(20),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            metadata JSONB
        )
    """)
    
    # Create indexes for performance
    print("Creating indexes...")
    cursor.execute("CREATE INDEX idx_job_state ON job(state)")
    cursor.execute("CREATE INDEX idx_job_client ON job(client_id)")
    cursor.execute("CREATE INDEX idx_job_expires ON job(expires_at)")
    cursor.execute("CREATE INDEX idx_miner_status ON miner(status)")
    cursor.execute("CREATE INDEX idx_miner_heartbeat ON miner(last_heartbeat)")
    cursor.execute("CREATE INDEX idx_wallet_user ON wallet(user_id)")
    cursor.execute("CREATE INDEX idx_usersession_token ON usersession(token)")
    cursor.execute("CREATE INDEX idx_usersession_expires ON usersession(expires_at)")
    cursor.execute("CREATE INDEX idx_marketplaceoffer_status ON marketplaceoffer(status)")
    cursor.execute("CREATE INDEX idx_marketplaceoffer_provider ON marketplaceoffer(provider)")
    cursor.execute("CREATE INDEX idx_marketplacebid_provider ON marketplacebid(provider)")
    
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
    
    # Migration order respecting foreign keys
    migrations = [
        ('user', '''
            INSERT INTO "user" (id, email, username, status, created_at, updated_at, last_login)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''),
        ('wallet', '''
            INSERT INTO wallet (id, user_id, address, balance, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        '''),
        ('miner', '''
            INSERT INTO miner (id, region, capabilities, concurrency, status, inflight, 
                              extra_metadata, last_heartbeat, session_token, last_job_at,
                              jobs_completed, jobs_failed, total_job_duration_ms, 
                              average_job_duration_ms, last_receipt_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''),
        ('job', '''
            INSERT INTO job (id, client_id, state, payload, constraints, ttl_seconds,
                           requested_at, expires_at, assigned_miner_id, result, receipt,
                           receipt_id, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''),
        ('marketplaceoffer', '''
            INSERT INTO marketplaceoffer (id, provider, capacity, price, sla, status, 
                                        created_at, attributes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        '''),
        ('marketplacebid', '''
            INSERT INTO marketplacebid (id, provider, capacity, price, notes, status, 
                                       submitted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''),
        ('jobreceipt', '''
            INSERT INTO jobreceipt (id, job_id, receipt_id, payload, created_at)
            VALUES (%s, %s, %s, %s, %s)
        '''),
        ('usersession', '''
            INSERT INTO usersession (id, user_id, token, expires_at, created_at, last_used)
            VALUES (%s, %s, %s, %s, %s, %s)
        '''),
        ('transaction', '''
            INSERT INTO transaction (id, user_id, type, amount, status, created_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''')
    ]
    
    for table_name, insert_sql in migrations:
        print(f"Migrating {table_name}...")
        sqlite_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cursor.fetchall()
        
        count = 0
        for row in rows:
            # Convert row to dict and handle JSON fields
            values = []
            for key in row.keys():
                value = row[key]
                if key in ['payload', 'constraints', 'result', 'receipt', 'capabilities', 
                          'extra_metadata', 'sla', 'attributes', 'metadata']:
                    # Handle JSON fields
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except:
                            pass
                elif key in ['balance', 'price', 'average_job_duration_ms']:
                    # Handle numeric fields
                    if value is not None:
                        value = Decimal(str(value))
                values.append(value)
            
            pg_cursor.execute(insert_sql, values)
            count += 1
        
        print(f"  - Migrated {count} {table_name} records")
    
    pg_conn.commit()
    
    print(f"\n✅ Migration complete!")
    sqlite_conn.close()
    pg_conn.close()

def main():
    """Main migration process"""
    
    print("=" * 60)
    print("AITBC Coordinator API SQLite to PostgreSQL Migration")
    print("=" * 60)
    
    # Check if SQLite DB exists
    if not Path(SQLITE_DB).exists():
        print(f"❌ SQLite database '{SQLITE_DB}' not found!")
        return
    
    # Create PostgreSQL schema
    create_pg_schema()
    
    # Migrate data
    migrate_data()
    
    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Update coordinator-api configuration")
    print("2. Install PostgreSQL dependencies")
    print("3. Restart the coordinator service")
    print("4. Verify data integrity")

if __name__ == "__main__":
    main()
