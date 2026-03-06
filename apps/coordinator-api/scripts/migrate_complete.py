#!/usr/bin/env python3
"""Complete migration script for Coordinator API"""

import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from decimal import Decimal

# Database configurations
SQLITE_DB = "coordinator.db"
PG_CONFIG = {
    "host": "localhost",
    "database": "aitbc_coordinator",
    "user": "aitbc_user",
    "password": "aitbc_password",
    "port": 5432
}

def migrate_all_data():
    """Migrate all data from SQLite to PostgreSQL"""
    
    print("\nStarting complete data migration...")
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_cursor = pg_conn.cursor()
    
    # Get all tables
    sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in sqlite_cursor.fetchall()]
    
    for table_name in tables:
        if table_name == 'sqlite_sequence':
            continue
            
        print(f"\nMigrating {table_name}...")
        
        # Get table schema
        sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
        columns = sqlite_cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # Get data
        sqlite_cursor.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            print(f"  No data in {table_name}")
            continue
        
        # Build insert query
        if table_name == 'user':
            insert_sql = f'''
                INSERT INTO "{table_name}" ({', '.join(column_names)})
                VALUES ({', '.join(['%s'] * len(column_names))})
            '''
        else:
            insert_sql = f'''
                INSERT INTO {table_name} ({', '.join(column_names)})
                VALUES ({', '.join(['%s'] * len(column_names))})
            '''
        
        # Insert data
        count = 0
        for row in rows:
            values = []
            for i, value in enumerate(row):
                col_name = column_names[i]
                # Handle special cases
                if col_name in ['payload', 'constraints', 'result', 'receipt', 'capabilities', 
                              'extra_metadata', 'sla', 'attributes', 'metadata'] and value:
                    if isinstance(value, str):
                        try:
                            value = json.loads(value)
                        except:
                            pass
                elif col_name in ['balance', 'price', 'average_job_duration_ms'] and value is not None:
                    value = Decimal(str(value))
                values.append(value)
            
            try:
                pg_cursor.execute(insert_sql, values)
                count += 1
            except Exception as e:
                print(f"  Error inserting row: {e}")
                print(f"  Values: {values}")
        
        print(f"  Migrated {count} rows from {table_name}")
    
    pg_conn.commit()
    sqlite_conn.close()
    pg_conn.close()
    
    print("\n✅ Complete migration finished!")

if __name__ == "__main__":
    migrate_all_data()
