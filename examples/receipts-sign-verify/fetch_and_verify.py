"""Example script that fetches a job receipt from the coordinator API and verifies signatures.

Usage::

    export PYTHONPATH=packages/py/aitbc-sdk/src:packages/py/aitbc-crypto/src
    python examples/receipts-sign-verify/fetch_and_verify.py --job-id <job_id> \
        --coordinator http://localhost:8011 --api-key REDACTED_CLIENT_KEY

The script prints the verification results for the miner signature and any
coordinator attestations present on the receipt payload.
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterable

from aitbc_sdk import CoordinatorReceiptClient, verify_receipt


def _print_attestations(attestations: Iterable[bool]) -> None:
    statuses = ["✔" if valid else "✖" for valid in attestations]
    if statuses:
        print("Coordinator attestations:", " ".join(statuses))
    else:
        print("Coordinator attestations: none")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify receipts")
    parser.add_argument("--job-id", required=True, help="Job ID to fetch receipts for")
    parser.add_argument(
        "--coordinator",
        default="http://localhost:8011",
        help="Coordinator base URL (default: http://localhost:8011)",
    )
    parser.add_argument(
        "--api-key",
        default="REDACTED_CLIENT_KEY",
        help="Client API key to authenticate against the coordinator",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Fetch full receipt history instead of only the latest receipt",
    )

    args = parser.parse_args(argv)

    client = CoordinatorReceiptClient(args.coordinator, args.api_key)

    if args.history:
        receipts = client.fetch_history(args.job_id)
        if not receipts:
            print("No receipts found for job", args.job_id)
            return 0
        for idx, receipt in enumerate(receipts, start=1):
            verification = verify_receipt(receipt)
            print(f"Receipt #{idx} ({verification.receipt['receipt_id']}):")
            print("  Miner signature valid:", verification.miner_signature.valid)
            _print_attestations(att.valid for att in verification.coordinator_attestations)
        return 0

    receipt = client.fetch_latest(args.job_id)
    if receipt is None:
        print("Latest receipt not available for job", args.job_id)
        return 1

    verification = verify_receipt(receipt)
    print("Latest receipt ID:", verification.receipt["receipt_id"])
    print("Miner signature valid:", verification.miner_signature.valid)
    _print_attestations(att.valid for att in verification.coordinator_attestations)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual invocation
    sys.exit(main())
