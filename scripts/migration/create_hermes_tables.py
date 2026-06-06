#!/usr/bin/env python3
"""
Hermes Database Setup Script

Creates and verifies Hermes autonomy feature database tables.
Run this script to initialize the database for Hermes features.

Usage:
    python scripts/migration/create_hermes_tables.py              # Create tables (idempotent)
    python scripts/migration/create_hermes_tables.py --verify    # Verify tables exist
    python scripts/migration/create_hermes_tables.py --reset     # Drop and recreate (WARNING: data loss)
"""

import os
import sys
import sqlite3
import argparse
from pathlib import Path


def get_db_path():
    """Get SQLite database path from environment or use default."""
    # Default path consistent with blockchain-node pattern
    data_dir = Path("/var/lib/aitbc/data")
    if not data_dir.exists():
        data_dir = Path.home() / ".aitbc" / "data"
    
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "coordinator.db"


def verify_tables(db_path):
    """Verify all Hermes tables exist in the database."""
    expected_tables = [
        "hermes_decisions",
        "hermes_votes",
        "hermes_health_checks",
        "hermes_error_reports",
        "hermes_recovery_results",
        "hermes_resources",
        "hermes_resource_allocations",
        "hermes_pricing_adjustments",
    ]
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = {row[0] for row in cursor.fetchall()}
    
    missing_tables = set(expected_tables) - existing_tables
    conn.close()
    
    if missing_tables:
        print(f"✗ Missing tables: {', '.join(missing_tables)}")
        return False
    else:
        print("✓ All Hermes tables exist")
        return True


def create_tables(reset=False):
    """Create all Hermes database tables using SQLite."""
    print("Creating Hermes database tables...")
    
    db_path = get_db_path()
    print(f"Using SQLite database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        if reset:
            print("⚠️  WARNING: Dropping existing tables (data will be lost)")
            cursor.execute("DROP TABLE IF EXISTS hermes_pricing_adjustments;")
            cursor.execute("DROP TABLE IF EXISTS hermes_resource_allocations;")
            cursor.execute("DROP TABLE IF EXISTS hermes_resources;")
            cursor.execute("DROP TABLE IF EXISTS hermes_recovery_results;")
            cursor.execute("DROP TABLE IF EXISTS hermes_error_reports;")
            cursor.execute("DROP TABLE IF EXISTS hermes_health_checks;")
            cursor.execute("DROP TABLE IF EXISTS hermes_votes;")
            cursor.execute("DROP TABLE IF EXISTS hermes_decisions;")
            print("✓ Dropped existing tables")
        
        # Create decisions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hermes_decisions (
                id TEXT PRIMARY KEY,
                decision_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                proposed_by TEXT NOT NULL,
                voting_deadline TEXT NOT NULL,
                min_participation REAL DEFAULT 0.5,
                required_approval REAL DEFAULT 0.6,
                status TEXT DEFAULT 'pending',
                meta_data TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                concluded_at TEXT
            );
        """)
        
        # Create votes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hermes_votes (
                id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                vote TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create health checks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hermes_health_checks (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                service_name TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                response_time_ms REAL,
                error_message TEXT,
                meta_data TEXT DEFAULT '{}'
            );
        """)
        
        # Create error reports table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hermes_error_reports (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                service_name TEXT NOT NULL,
                error_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                error_message TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                context TEXT DEFAULT '{}'
            );
        """)
        
        # Create recovery results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hermes_recovery_results (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                success TEXT NOT NULL,
                message TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create resources table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hermes_resources (
                id TEXT PRIMARY KEY,
                resource_id TEXT UNIQUE NOT NULL,
                resource_type TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT DEFAULT 'available',
                capacity REAL NOT NULL,
                allocated REAL DEFAULT 0.0,
                utilization REAL DEFAULT 0.0,
                meta_data TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create resource allocations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hermes_resource_allocations (
                id TEXT PRIMARY KEY,
                allocation_id TEXT UNIQUE NOT NULL,
                resource_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                capacity REAL NOT NULL,
                strategy TEXT NOT NULL,
                priority INTEGER DEFAULT 5,
                allocated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT
            );
        """)
        
        # Create pricing adjustments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hermes_pricing_adjustments (
                id TEXT PRIMARY KEY,
                resource_id TEXT NOT NULL,
                current_price REAL NOT NULL,
                new_price REAL NOT NULL,
                adjustment_factor REAL NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_type ON hermes_decisions(decision_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_status ON hermes_decisions(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_decision ON hermes_votes(decision_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_agent ON hermes_votes(agent_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_agent ON hermes_health_checks(agent_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_service ON hermes_health_checks(service_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_errors_agent ON hermes_error_reports(agent_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_errors_severity ON hermes_error_reports(severity);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recovery_agent ON hermes_recovery_results(agent_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_resources_type ON hermes_resources(resource_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_resources_status ON hermes_resources(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_allocations_resource ON hermes_resource_allocations(resource_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_allocations_agent ON hermes_resource_allocations(agent_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pricing_resource ON hermes_pricing_adjustments(resource_id);")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("✓ All Hermes tables created successfully")
        print("\nCreated tables:")
        print("  - hermes_decisions")
        print("  - hermes_votes")
        print("  - hermes_health_checks")
        print("  - hermes_error_reports")
        print("  - hermes_recovery_results")
        print("  - hermes_resources")
        print("  - hermes_resource_allocations")
        print("  - hermes_pricing_adjustments")
        print("\nCreated indexes for performance optimization")
        
        return True
        
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Hermes Database Setup Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/migration/create_hermes_tables.py              # Create tables (idempotent)
  python scripts/migration/create_hermes_tables.py --verify    # Verify tables exist
  python scripts/migration/create_hermes_tables.py --reset     # Drop and recreate (WARNING: data loss)
        """
    )
    parser.add_argument("--verify", action="store_true", help="Verify tables exist without creating")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables (WARNING: data loss)")
    
    args = parser.parse_args()
    
    db_path = get_db_path()
    print(f"Database path: {db_path}\n")
    
    if args.verify:
        verify_tables(db_path)
    else:
        if not create_tables(reset=args.reset):
            sys.exit(1)
        print("\nVerifying tables...")
        verify_tables(db_path)


if __name__ == "__main__":
    main()
