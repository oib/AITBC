"""Parser for blockchain sync commands."""

def register(subparsers, ctx):
    """Register sync subcommands."""
    sync_parser = subparsers.add_parser(
        "sync",
        help="Blockchain synchronization utilities"
    )
    sync_subparsers = sync_parser.add_subparsers(dest="sync_action", help="Sync actions")

    # Bulk sync command
    bulk_parser = sync_subparsers.add_parser(
        "bulk",
        help="Bulk import blocks from a leader to catch up quickly"
    )
    bulk_parser.add_argument(
        "--source",
        default="http://127.0.0.1:8202",
        help="Source RPC URL (leader node)"
    )
    bulk_parser.add_argument(
        "--import-url",
        default="http://127.0.0.1:8202",
        help="Local RPC URL for import"
    )
    bulk_parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Blocks per batch (default: 100)"
    )
    bulk_parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.2,
        help="Seconds between batches (default: 0.2)"
    )
