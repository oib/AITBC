#!/usr/bin/env python3
"""
Migration: 003_data_migration
Description: Data migration scripts for Coordinator API
Created: 2026-01-24

Usage:
    python 003_data_migration.py --action=migrate_receipts
    python 003_data_migration.py --action=migrate_jobs
    python 003_data_migration.py --action=all
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import asyncpg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataMigration:
    """Data migration utilities for Coordinator API"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None
    
    async def connect(self):
        """Connect to database."""
        self.pool = await asyncpg.create_pool(self.database_url)
        logger.info("Connected to database")
    
    async def close(self):
        """Close database connection."""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from database")
    
    async def migrate_receipts_from_json(self, json_path: str):
        """Migrate receipts from JSON file to database."""
        logger.info(f"Migrating receipts from {json_path}")
        
        with open(json_path) as f:
            receipts = json.load(f)
        
        async with self.pool.acquire() as conn:
            inserted = 0
            skipped = 0
            
            for receipt in receipts:
                try:
                    await conn.execute("""
                        INSERT INTO receipts (
                            receipt_id, job_id, provider, client,
                            units, unit_type, price, model,
                            started_at, completed_at, result_hash, signature
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (receipt_id) DO NOTHING
                    """,
                        receipt.get("receipt_id"),
                        receipt.get("job_id"),
                        receipt.get("provider"),
                        receipt.get("client"),
                        receipt.get("units", 0),
                        receipt.get("unit_type", "gpu_seconds"),
                        receipt.get("price"),
                        receipt.get("model"),
                        receipt.get("started_at"),
                        receipt.get("completed_at"),
                        receipt.get("result_hash"),
                        json.dumps(receipt.get("signature")) if receipt.get("signature") else None
                    )
                    inserted += 1
                except Exception as e:
                    logger.warning(f"Skipped receipt {receipt.get('receipt_id')}: {e}")
                    skipped += 1
            
            logger.info(f"Migrated {inserted} receipts, skipped {skipped}")
    
    async def migrate_jobs_from_sqlite(self, sqlite_path: str):
        """Migrate jobs from SQLite to PostgreSQL."""
        logger.info(f"Migrating jobs from {sqlite_path}")
        
        import sqlite3
        
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        cursor = sqlite_conn.cursor()
        
        cursor.execute("SELECT * FROM jobs")
        jobs = cursor.fetchall()
        
        async with self.pool.acquire() as conn:
            inserted = 0
            
            for job in jobs:
                try:
                    await conn.execute("""
                        INSERT INTO jobs (
                            job_id, status, prompt, model, params,
                            result, client_id, miner_id,
                            created_at, started_at, completed_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        ON CONFLICT (job_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            result = EXCLUDED.result,
                            completed_at = EXCLUDED.completed_at
                    """,
                        job["job_id"],
                        job["status"],
                        job["prompt"],
                        job.get("model", "llama3.2"),
                        json.dumps(job.get("params", {})),
                        job.get("result"),
                        job.get("client_id"),
                        job.get("miner_id"),
                        self._parse_datetime(job.get("created_at")),
                        self._parse_datetime(job.get("started_at")),
                        self._parse_datetime(job.get("completed_at"))
                    )
                    inserted += 1
                except Exception as e:
                    logger.warning(f"Skipped job {job.get('job_id')}: {e}")
            
            logger.info(f"Migrated {inserted} jobs")
        
        sqlite_conn.close()
    
    async def migrate_miners_from_json(self, json_path: str):
        """Migrate miners from JSON file to database."""
        logger.info(f"Migrating miners from {json_path}")
        
        with open(json_path) as f:
            miners = json.load(f)
        
        async with self.pool.acquire() as conn:
            inserted = 0
            
            for miner in miners:
                try:
                    await conn.execute("""
                        INSERT INTO miners (
                            miner_id, status, capabilities, gpu_info,
                            endpoint, max_concurrent_jobs, score
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (miner_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            capabilities = EXCLUDED.capabilities,
                            gpu_info = EXCLUDED.gpu_info
                    """,
                        miner.get("miner_id"),
                        miner.get("status", "offline"),
                        miner.get("capabilities", []),
                        json.dumps(miner.get("gpu_info", {})),
                        miner.get("endpoint"),
                        miner.get("max_concurrent_jobs", 1),
                        miner.get("score", 100.0)
                    )
                    inserted += 1
                except Exception as e:
                    logger.warning(f"Skipped miner {miner.get('miner_id')}: {e}")
            
            logger.info(f"Migrated {inserted} miners")
    
    async def backfill_job_history(self):
        """Backfill job history from existing jobs."""
        logger.info("Backfilling job history")
        
        async with self.pool.acquire() as conn:
            # Get all completed jobs without history
            jobs = await conn.fetch("""
                SELECT j.job_id, j.status, j.created_at, j.started_at, j.completed_at
                FROM jobs j
                LEFT JOIN job_history h ON j.job_id = h.job_id
                WHERE h.id IS NULL AND j.status IN ('completed', 'failed')
            """)
            
            inserted = 0
            for job in jobs:
                events = []
                
                if job["created_at"]:
                    events.append(("created", job["created_at"], {}))
                if job["started_at"]:
                    events.append(("started", job["started_at"], {}))
                if job["completed_at"]:
                    events.append((job["status"], job["completed_at"], {}))
                
                for event_type, timestamp, data in events:
                    await conn.execute("""
                        INSERT INTO job_history (job_id, event_type, event_data, created_at)
                        VALUES ($1, $2, $3, $4)
                    """, job["job_id"], event_type, json.dumps(data), timestamp)
                    inserted += 1
            
            logger.info(f"Backfilled {inserted} history events")
    
    async def cleanup_orphaned_receipts(self):
        """Remove receipts without corresponding jobs."""
        logger.info("Cleaning up orphaned receipts")
        
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM receipts r
                WHERE NOT EXISTS (
                    SELECT 1 FROM jobs j WHERE j.job_id = r.job_id
                )
            """)
            logger.info(f"Removed orphaned receipts: {result}")
    
    async def update_miner_stats(self):
        """Recalculate miner statistics from receipts."""
        logger.info("Updating miner statistics")
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE miners m SET
                    jobs_completed = (
                        SELECT COUNT(*) FROM receipts r WHERE r.provider = m.miner_id
                    ),
                    score = LEAST(100, 70 + (
                        SELECT COUNT(*) FROM receipts r WHERE r.provider = m.miner_id
                    ) * 0.1)
            """)
            logger.info("Miner statistics updated")
    
    def _parse_datetime(self, value) -> datetime:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None


async def main():
    parser = argparse.ArgumentParser(description="Data migration for Coordinator API")
    parser.add_argument("--action", required=True, 
                       choices=["migrate_receipts", "migrate_jobs", "migrate_miners",
                               "backfill_history", "cleanup", "update_stats", "all"])
    parser.add_argument("--database-url", default="postgresql://aitbc:aitbc@localhost:5432/coordinator")
    parser.add_argument("--input-file", help="Input file for migration")
    
    args = parser.parse_args()
    
    migration = DataMigration(args.database_url)
    await migration.connect()
    
    try:
        if args.action == "migrate_receipts":
            await migration.migrate_receipts_from_json(args.input_file)
        elif args.action == "migrate_jobs":
            await migration.migrate_jobs_from_sqlite(args.input_file)
        elif args.action == "migrate_miners":
            await migration.migrate_miners_from_json(args.input_file)
        elif args.action == "backfill_history":
            await migration.backfill_job_history()
        elif args.action == "cleanup":
            await migration.cleanup_orphaned_receipts()
        elif args.action == "update_stats":
            await migration.update_miner_stats()
        elif args.action == "all":
            await migration.backfill_job_history()
            await migration.cleanup_orphaned_receipts()
            await migration.update_miner_stats()
    finally:
        await migration.close()


if __name__ == "__main__":
    asyncio.run(main())
