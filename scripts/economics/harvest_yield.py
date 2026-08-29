#!/usr/bin/env python3
"""Harvest and compound yield across registered yield venues."""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal


def _import_yield_adapter():
    """Import the coordinator yield adapter module from the repo."""
    repo_root = os.getenv("AITBC_REPO_DIR", "/opt/aitbc")
    sys.path.insert(0, os.path.join(repo_root, "apps/coordinator-api/src"))
    from coordinator_api.contexts.agent_economics.yield_adapter import (  # noqa: PLC0415
        YieldPosition,
        YieldVenue,
        yield_registry,
    )

    return YieldPosition, YieldVenue, yield_registry


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Harvest yield across venues")
    parser.add_argument("--agent-id", default=os.getenv("AGENT_ID", "agent-1"))
    parser.add_argument("--venue", default="demo_staking")
    parser.add_argument("--principal", default="1000")
    parser.add_argument("--rewards", default="10")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", help="List registered yield venues")
    args = parser.parse_args(argv)

    YieldPosition, YieldVenue, yield_registry = _import_yield_adapter()

    if args.list:
        for name in yield_registry.list_adapters():
            print(name)
        return 0

    try:
        adapter_cls = yield_registry.get(args.venue)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    adapter = adapter_cls()
    position = YieldPosition(
        venue=YieldVenue.STAKING,
        agent_id=args.agent_id,
        principal=Decimal(args.principal),
        rewards=Decimal(args.rewards),
    )
    if args.dry_run:
        estimated = adapter.estimate_apy(position)
        print(f"dry-run: would harvest {position.rewards} AITBC at {estimated}% APY")
        return 0

    harvested = adapter.harvest(position)
    print(f"harvested {harvested} AITBC for {args.agent_id}; principal now {position.principal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
