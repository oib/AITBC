"""Sync management commands for AITBC."""

import asyncio
import os
import sys
from pathlib import Path

import click

from utils import success, error, run_subprocess


@click.group()
def sync():
    """Blockchain synchronization utilities."""
    pass


@sync.command()
@click.option('--source', default=lambda: os.getenv('AITBC_SYNC_SOURCE_URL', 'http://127.0.0.1:8005'), help='Source RPC URL (leader)')
@click.option('--import-url', default='http://127.0.0.1:8005', help='Local RPC URL for import')
@click.option('--batch-size', type=int, default=100, help='Blocks per batch')
@click.option('--poll-interval', type=float, default=0.2, help='Seconds between batches')
def bulk(source, import_url, batch_size, poll_interval):
    """Bulk import blocks from a leader to catch up quickly."""
    try:
        # Resolve paths
        blockchain_dir = Path(__file__).resolve().parents[3] / 'apps' / 'blockchain-node'
        src_dir = blockchain_dir / 'src'
        venv_python = blockchain_dir / '.venv' / 'bin' / 'python3'
        sync_cli = src_dir / 'aitbc_chain' / 'sync_cli.py'

        if not sync_cli.exists():
            error("sync_cli.py not found. Ensure bulk sync feature is deployed.")
            raise click.Abort()

        cmd = [
            str(venv_python),
            str(sync_cli),
            '--source', source,
            '--import-url', import_url,
            '--batch-size', str(batch_size),
            '--poll-interval', str(poll_interval),
        ]

        # Prepare environment
        env = {
            'PYTHONPATH': str(src_dir),
        }

        success(f"Running bulk sync from {source} to {import_url} (batch size: {batch_size})")
        result = run_subprocess(cmd, env=env, capture_output=False)
        if result.returncode != 0:
            error("Bulk sync failed. Check logs for details.")
            raise click.Abort()
        success("Bulk sync completed.")
    except Exception as e:
        error(f"Error during bulk sync: {e}")
        raise click.Abort()
