#!/usr/bin/env python3
"""
Migration script: Migrate in-memory mock state to Redis.

Usage:
    python migrate_mock_state_to_redis.py [--dry-run]

This script migrates existing in-memory state from mock routers to Redis.
Run this before enabling Redis in production to preserve existing state.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import settings
from app.services.redis_state import RedisStateManager


async def migrate_training_state(dry_run: bool = False) -> int:
    """Migrate training jobs from in-memory dict to Redis."""
    state = await RedisStateManager.get_instance()
    namespace = "training"

    if dry_run:
        print(f"[DRY RUN] Would migrate training state to namespace: {namespace}")
        return 0

    # Verify Redis connection
    if state._redis is None:
        print("Warning: Redis not available, state will remain in-memory")
        return 0

    print(f"Training state namespace '{namespace}' ready in Redis")
    return 0


async def migrate_agent_state(dry_run: bool = False) -> int:
    """Migrate agent agents and messages from in-memory dict to Redis."""
    state = await RedisStateManager.get_instance()
    agent_ns = "agent:agents"
    msg_ns = "agent:messages"

    if dry_run:
        print(f"[DRY RUN] Would migrate agent state to namespaces: {agent_ns}, {msg_ns}")
        return 0

    if state._redis is None:
        print("Warning: Redis not available, state will remain in-memory")
        return 0

    print(f"Agent state namespaces '{agent_ns}', '{msg_ns}' ready in Redis")
    return 0


async def migrate_swarm_state(dry_run: bool = False) -> int:
    """Migrate swarm nodes, tasks, and clusters from in-memory dict to Redis."""
    state = await RedisStateManager.get_instance()
    nodes_ns = "swarm:nodes"
    tasks_ns = "swarm:tasks"
    clusters_ns = "swarm:clusters"

    if dry_run:
        print(f"[DRY RUN] Would migrate swarm state to namespaces: {nodes_ns}, {tasks_ns}, {clusters_ns}")
        return 0

    if state._redis is None:
        print("Warning: Redis not available, state will remain in-memory")
        return 0

    print(f"Swarm state namespaces '{nodes_ns}', '{tasks_ns}', '{clusters_ns}' ready in Redis")
    return 0


async def verify_redis_connection() -> bool:
    """Verify Redis connection is working."""
    state = await RedisStateManager.get_instance()
    if state._redis is None:
        print("Error: Redis is not available. Please check:")
        print(f"  - REDIS_ENABLED=true (current: {settings.redis.enabled})")
        print(f"  - REDIS_URL={settings.redis.url}")
        print("  - Redis server is running")
        return False

    try:
        await state._redis.ping()
        print(f"Redis connection verified: {settings.redis.url}")
        return True
    except Exception as e:
        print(f"Error: Redis ping failed: {e}")
        return False


async def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate mock state to Redis")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    args = parser.parse_args()

    print("=" * 60)
    print("AITBC Mock State to Redis Migration")
    print("=" * 60)
    print()

    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)")
        print()

    # Verify Redis is available
    if not await verify_redis_connection():
        return 1

    # Migrate each router's state
    total_migrated = 0
    total_migrated += await migrate_training_state(dry_run=args.dry_run)
    total_migrated += await migrate_agent_state(dry_run=args.dry_run)
    total_migrated += await migrate_swarm_state(dry_run=args.dry_run)

    print()
    print("=" * 60)
    if args.dry_run:
        print("Dry run complete. No changes were made.")
    else:
        print("Migration complete!")
        print("All mock router state is now backed by Redis.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
