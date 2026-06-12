#!/usr/bin/env python3
"""
Migration script: Convert plugin service JSON data to marketplace service database
Migrates /var/lib/aitbc/plugins.json to SoftwareService table in marketplace database
"""

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/apps/marketplace/src")))



# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////var/lib/aitbc/data/marketplace_service.db")

# Source JSON file
PLUGIN_JSON_PATH = "/var/lib/aitbc/plugins.json"
BACKUP_PATH = "/var/lib/aitbc/plugins.json.backup"


def backup_json_file():
    """Backup the original JSON file"""
    if os.path.exists(PLUGIN_JSON_PATH):
        shutil.copy2(PLUGIN_JSON_PATH, BACKUP_PATH)
        print(f"✓ Backed up {PLUGIN_JSON_PATH} to {BACKUP_PATH}")
        return True
    return False


def read_plugin_json():
    """Read the plugin JSON file"""
    if not os.path.exists(PLUGIN_JSON_PATH):
        print(f"✗ Plugin JSON file not found: {PLUGIN_JSON_PATH}")
        return None

    with open(PLUGIN_JSON_PATH) as f:
        return json.load(f)


async def migrate_to_database(plugin_data):
    """Migrate plugin data to marketplace database"""
    from marketplace_service.domain.marketplace import SoftwareService
    from marketplace_service.storage import get_session_context, init_db

    # Initialize database (creates tables if they don't exist)
    await init_db()

    migrated_count = 0
    errors = []

    async with get_session_context() as session:
        for plugin_id, data in plugin_data.items():
            try:
                # Check if already exists
                from sqlalchemy import select
                result = await session.execute(
                    select(SoftwareService).where(SoftwareService.plugin_id == plugin_id)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    print(f"  - Skipping {plugin_id} (already exists)")
                    continue

                # Convert JSON data to SoftwareService
                service = SoftwareService(
                    plugin_id=plugin_id,
                    service_type=data.get("service_type", ""),
                    model=data.get("model", ""),
                    price=data.get("price", 0.0),
                    price_unit=data.get("price_unit", "per_1k_tokens"),
                    offer_id=data.get("offer_id"),
                    endpoint=data.get("endpoint", ""),
                    public_endpoint=data.get("public_endpoint", ""),
                    health_url=data.get("health_url", ""),
                    provider_address=data.get("provider_address", ""),
                    node_id=data.get("node_id", ""),
                    gpu_name=data.get("gpu_name", ""),
                    gpu_device=data.get("gpu_device", "0"),
                    gpu_uuid=data.get("gpu_uuid"),
                    gpu_offer_id=data.get("gpu_offer_id"),
                    description=data.get("description", ""),
                    status=data.get("status", "active"),
                    registered_at=datetime.fromisoformat(data.get("registered_at", datetime.utcnow().isoformat())),
                    updated_at=datetime.fromisoformat(data.get("updated_at", datetime.utcnow().isoformat())),
                )

                session.add(service)
                await session.commit()
                print(f"  ✓ Migrated {plugin_id}")
                migrated_count += 1

            except Exception as e:
                errors.append((plugin_id, str(e)))
                print(f"  ✗ Error migrating {plugin_id}: {e}")
                await session.rollback()

    return migrated_count, errors


async def main():
    """Main migration function"""
    print("=" * 60)
    print("Plugin Service Migration")
    print("=" * 60)

    # Backup JSON file
    if not backup_json_file():
        print("✗ No JSON file to backup (may not exist yet)")
        return

    # Read plugin data
    plugin_data = read_plugin_json()
    if not plugin_data:
        print("✗ No plugin data to migrate")
        return

    print(f"\nFound {len(plugin_data)} plugin entries to migrate:")
    for plugin_id in plugin_data.keys():
        print(f"  - {plugin_id}")

    # Confirm migration
    print("\nProceeding with migration...")

    # Migrate to database
    migrated_count, errors = await migrate_to_database(plugin_data)

    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"✓ Migrated: {migrated_count} entries")
    print(f"✗ Errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for plugin_id, error in errors:
            print(f"  - {plugin_id}: {error}")

    print(f"\nBackup saved to: {BACKUP_PATH}")
    print("Original JSON file preserved at: " + PLUGIN_JSON_PATH)
    print("\nYou can now decommission aitbc-plugin.service")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
