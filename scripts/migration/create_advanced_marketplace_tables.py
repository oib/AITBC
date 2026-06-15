#!/usr/bin/env python3
"""
Advanced Marketplace Database Setup Script

Creates and verifies advanced marketplace feature database tables.
Run this script to initialize the database for advanced marketplace features.

Usage:
    python scripts/migration/create_advanced_marketplace_tables.py              # Create tables (idempotent)
    python scripts/migration/create_advanced_marketplace_tables.py --verify    # Verify tables exist
    python scripts/migration/create_advanced_marketplace_tables.py --reset     # Drop and recreate (WARNING: data loss)
"""

import argparse
import sqlite3
import sys
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
    """Verify all advanced marketplace tables exist in the database."""
    expected_tables = [
        "price_history",
        "price_forecast",
        "auction_config",
        "search_history",
        "resource_embeddings",
        "user_profiles",
        "market_metrics",
        "trend_data",
        "analytics_events",
        "external_providers",
        "provider_mappings",
        "sync_status",
        "plugins",
        "plugin_configs",
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
        print("✓ All advanced marketplace tables exist")
        return True


def create_tables(reset=False):
    """Create all advanced marketplace database tables using SQLite."""
    print("Creating advanced marketplace database tables...")

    db_path = get_db_path()
    print(f"Using SQLite database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if reset:
            print("⚠️  WARNING: Dropping existing tables (data will be lost)")
            cursor.execute("DROP TABLE IF EXISTS price_forecast;")
            cursor.execute("DROP TABLE IF EXISTS price_history;")
            cursor.execute("DROP TABLE IF EXISTS auction_config;")
            cursor.execute("DROP TABLE IF EXISTS user_profiles;")
            cursor.execute("DROP TABLE IF EXISTS resource_embeddings;")
            cursor.execute("DROP TABLE IF EXISTS search_history;")
            cursor.execute("DROP TABLE IF EXISTS analytics_events;")
            cursor.execute("DROP TABLE IF EXISTS trend_data;")
            cursor.execute("DROP TABLE IF EXISTS market_metrics;")
            cursor.execute("DROP TABLE IF EXISTS sync_status;")
            cursor.execute("DROP TABLE IF EXISTS provider_mappings;")
            cursor.execute("DROP TABLE IF EXISTS external_providers;")
            cursor.execute("DROP TABLE IF EXISTS plugin_configs;")
            cursor.execute("DROP TABLE IF EXISTS plugins;")
            print("✓ Dropped existing tables")

        # Create price history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id TEXT PRIMARY KEY,
                resource_id TEXT NOT NULL,
                resource_type TEXT DEFAULT 'gpu',
                price REAL DEFAULT 0.0,
                demand_level REAL DEFAULT 0.5,
                supply_level REAL DEFAULT 0.5,
                confidence REAL DEFAULT 0.8,
                strategy_used TEXT DEFAULT 'market_balance',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create price forecast table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_forecast (
                id TEXT PRIMARY KEY,
                resource_id TEXT NOT NULL,
                forecast_timestamp TEXT,
                predicted_price REAL DEFAULT 0.0,
                confidence_lower REAL DEFAULT 0.0,
                confidence_upper REAL DEFAULT 0.0,
                confidence_score REAL DEFAULT 0.8,
                model_version TEXT DEFAULT 'v1.0',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create auction config table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auction_config (
                id TEXT PRIMARY KEY,
                auction_id TEXT UNIQUE NOT NULL,
                auction_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                start_time TEXT DEFAULT CURRENT_TIMESTAMP,
                end_time TEXT,
                reserve_price REAL DEFAULT 0.0,
                start_price REAL,
                decrement_rate REAL,
                decrement_interval INTEGER,
                status TEXT DEFAULT 'active',
                winner_id TEXT,
                winning_price REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create search history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                search_query TEXT DEFAULT '',
                filters TEXT DEFAULT '{}',
                results_count INTEGER DEFAULT 0,
                clicked_resource_id TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create resource embeddings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resource_embeddings (
                id TEXT PRIMARY KEY,
                resource_id TEXT UNIQUE NOT NULL,
                embedding TEXT DEFAULT '[]',
                model_version TEXT DEFAULT 'v1.0',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create user profiles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id TEXT PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                preferred_gpu_models TEXT DEFAULT '[]',
                preferred_regions TEXT DEFAULT '[]',
                price_range_min REAL DEFAULT 0.0,
                price_range_max REAL DEFAULT 1000.0,
                min_memory_gb INTEGER DEFAULT 0,
                preferred_capabilities TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create market metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_metrics (
                id TEXT PRIMARY KEY,
                total_gpus INTEGER DEFAULT 0,
                available_gpus INTEGER DEFAULT 0,
                booked_gpus INTEGER DEFAULT 0,
                total_capacity REAL DEFAULT 0.0,
                available_capacity REAL DEFAULT 0.0,
                avg_price REAL DEFAULT 0.0,
                avg_utilization REAL DEFAULT 0.0,
                active_bookings INTEGER DEFAULT 0,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create trend data table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trend_data (
                id TEXT PRIMARY KEY,
                period_hours INTEGER DEFAULT 24,
                total_bookings INTEGER DEFAULT 0,
                bookings_per_hour REAL DEFAULT 0.0,
                avg_price REAL DEFAULT 0.0,
                avg_utilization REAL DEFAULT 0.0,
                trend_direction TEXT DEFAULT 'stable',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create analytics events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                user_id TEXT,
                event_metadata TEXT DEFAULT '{}',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create external providers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS external_providers (
                id TEXT PRIMARY KEY,
                provider_name TEXT UNIQUE NOT NULL,
                provider_type TEXT DEFAULT 'aws',
                api_key TEXT DEFAULT '',
                api_secret TEXT DEFAULT '',
                region TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                sync_interval_minutes INTEGER DEFAULT 60,
                last_sync TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create provider mappings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS provider_mappings (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                external_resource_id TEXT NOT NULL,
                internal_resource_id TEXT NOT NULL,
                mapping_type TEXT DEFAULT 'gpu',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create sync status table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_status (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                resources_synced INTEGER DEFAULT 0,
                resources_failed INTEGER DEFAULT 0,
                error_message TEXT,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            );
        """)

        # Create plugins table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plugins (
                id TEXT PRIMARY KEY,
                plugin_name TEXT UNIQUE NOT NULL,
                plugin_version TEXT DEFAULT '1.0.0',
                plugin_type TEXT DEFAULT 'extension',
                enabled INTEGER DEFAULT 1,
                config TEXT DEFAULT '{}',
                description TEXT DEFAULT '',
                author TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create plugin configs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plugin_configs (
                id TEXT PRIMARY KEY,
                plugin_id TEXT NOT NULL,
                config_key TEXT NOT NULL,
                config_value TEXT DEFAULT '',
                config_type TEXT DEFAULT 'string',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_resource ON price_history(resource_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_timestamp ON price_history(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_forecast_resource ON price_forecast(resource_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_forecast_timestamp ON price_forecast(forecast_timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auction_config_id ON auction_config(auction_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auction_config_resource ON auction_config(resource_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auction_config_type ON auction_config(auction_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auction_config_status ON auction_config(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_timestamp ON search_history(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_resource_embeddings_resource ON resource_embeddings(resource_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_profiles_user ON user_profiles(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_metrics_timestamp ON market_metrics(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trend_data_timestamp ON trend_data(timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_resource ON analytics_events(resource_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_user ON analytics_events(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_external_providers_name ON external_providers(provider_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_external_providers_type ON external_providers(provider_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_provider_mappings_provider ON provider_mappings(provider_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_provider_mappings_external ON provider_mappings(external_resource_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_provider_mappings_internal ON provider_mappings(internal_resource_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_status_provider ON sync_status(provider_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_status_status ON sync_status(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_plugins_name ON plugins(plugin_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_plugins_type ON plugins(plugin_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_plugin_configs_plugin ON plugin_configs(plugin_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_plugin_configs_key ON plugin_configs(config_key);")

        conn.commit()
        cursor.close()
        conn.close()

        print("✓ All advanced marketplace tables created successfully")
        print("\nCreated tables:")
        print("  - price_history")
        print("  - price_forecast")
        print("  - auction_config")
        print("  - search_history")
        print("  - resource_embeddings")
        print("  - user_profiles")
        print("  - market_metrics")
        print("  - trend_data")
        print("  - analytics_events")
        print("  - external_providers")
        print("  - provider_mappings")
        print("  - sync_status")
        print("  - plugins")
        print("  - plugin_configs")
        print("\nCreated indexes for performance optimization")

        return True

    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Advanced Marketplace Database Setup Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/migration/create_advanced_marketplace_tables.py              # Create tables (idempotent)
  python scripts/migration/create_advanced_marketplace_tables.py --verify    # Verify tables exist
  python scripts/migration/create_advanced_marketplace_tables.py --reset     # Drop and recreate (WARNING: data loss)
        """,
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
