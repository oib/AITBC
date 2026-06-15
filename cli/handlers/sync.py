"""Handler for blockchain sync commands."""

import subprocess
from pathlib import Path


def handle_sync_bulk(args, ctx):
    """Handle bulk sync command."""
    # Resolve paths to the sync_cli.py script
    blockchain_dir = Path(__file__).resolve().parents[2] / "apps" / "blockchain-node"
    src_dir = blockchain_dir / "src"
    venv_python = blockchain_dir / ".venv" / "bin" / "python3"
    sync_cli = src_dir / "aitbc_chain" / "sync_cli.py"

    if not sync_cli.exists():
        print(f"Error: sync_cli.py not found at {sync_cli}")
        print("Ensure bulk sync feature is deployed.")
        return 1

    cmd = [
        str(venv_python),
        str(sync_cli),
        "--source",
        args.source,
        "--import-url",
        args.import_url,
        "--batch-size",
        str(args.batch_size),
        "--poll-interval",
        str(args.poll_interval),
    ]

    # Prepare environment
    env = {
        "PYTHONPATH": str(src_dir),
    }

    print(f"Running bulk sync from {args.source} to {args.import_url} (batch size: {args.batch_size})")

    try:
        result = subprocess.run(cmd, env=env, capture_output=False)
        if result.returncode != 0:
            print("Error: Bulk sync failed. Check logs for details.")
            return 1
        print("Bulk sync completed.")
        return 0
    except Exception as e:
        print(f"Error during bulk sync: {e}")
        return 1
