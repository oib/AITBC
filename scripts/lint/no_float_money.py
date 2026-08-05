#!/usr/bin/env python3
"""Guard against float() conversions in money-sensitive source files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

MONEY_FILES = [
    "aitbc/ethereum_rpc.py",
    "aitbc/oracles/price_oracle.py",
    "aitbc/network/web3_utils.py",
    "aitbc/blockchain/rpc_client.py",
    "aitbc/security/validators.py",
    "aitbc/trading/offer_types.py",
    "apps/trading/src/trading_service/routers/exchange_compat.py",
    "apps/trading/src/trading_service/services/offer_sync_service.py",
    "apps/coordinator-api/src/coordinator_api/contexts/payments/services/payments.py",
    "apps/coordinator-api/src/coordinator_api/contexts/payments/routers/payments.py",
    "apps/coordinator-api/src/coordinator_api/schemas/__init__.py",
    "apps/coordinator-api/src/coordinator_api/contexts/blockchain/services/blockchain.py",
    "apps/coordinator-api/src/coordinator_api/contexts/developer_platform/services/developer_platform_service.py",
]

FLOAT_RE = re.compile(r"float\(")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    found = False

    for rel in MONEY_FILES:
        path = repo_root / rel
        if not path.exists():
            print(f"{path}: warning: file not found", file=sys.stderr)
            continue

        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in FLOAT_RE.finditer(line):
                col = match.start() + 1
                print(f"{path}:{lineno}:{col}: float() conversion is forbidden in money-sensitive code")
                found = True

    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
