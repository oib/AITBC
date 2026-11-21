"""#2423 pins: the shop role manifest must match deployed reality.

``health --role shop`` (and ``health_check.sh``'s ROLE_SERVICES) resolved
probes through a manifest listing coordinator-api, pool-hub and market —
units that are hub-side and ``not-found`` in systemd on the only shop node
(node2, verified 2026-11-21). The manifest now lists the units actually
deployed for the shop role.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_CHECK_SH = REPO_ROOT / "scripts" / "monitoring" / "health_check.sh"


def _shop_services() -> list[str]:
    text = HEALTH_CHECK_SH.read_text(encoding="utf-8")
    block = re.search(r"^_SHOP_SERVICES=\((.*?)\n\)", text, re.S | re.M)
    assert block, "_SHOP_SERVICES is no longer a bash array"
    return block.group(1).split()


def test_shop_manifest_drops_hub_side_units() -> None:
    shop = _shop_services()
    for retired in ("aitbc-coordinator-api", "aitbc-pool-hub", "aitbc-market"):
        assert retired not in shop, f"{retired} is not deployed on the shop node"


def test_shop_manifest_keeps_deployed_units() -> None:
    shop = _shop_services()
    for deployed in ("aitbc-gpu", "aitbc-miner", "aitbc-edge", "aitbc-api-gateway"):
        assert deployed in shop
